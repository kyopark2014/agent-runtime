import logging
import sys
import chat
import mcp_config
import langgraph_agent
import utils
import httpx
import boto3
from datetime import datetime, timezone
from urllib.parse import urlparse
from botocore.auth import SigV4Auth as BotocoreSigV4Auth
from botocore.awsrequest import AWSRequest

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(
    level=logging.INFO,  
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("agent")

# Monkey patch httpx.AsyncClient for SigV4 authentication
original_init = httpx.AsyncClient.__init__
def patched_init(self, *args, **kwargs):
    # Add SigV4 signing event hook if needed
    async def sign_request(request: httpx.Request) -> None:
        """Sign the request with AWS SigV4 including the body"""
        # Only sign requests to bedrock-agentcore
        if "bedrock-agentcore" not in str(request.url):
            return
        
        # Get credentials
        boto_session = boto3.Session()
        credentials = boto_session.get_credentials().get_frozen_credentials()
        
        # Parse URL
        parsed_url = urlparse(str(request.url))
        host = parsed_url.netloc
        
        # Generate timestamp
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        
        # Read request body if available
        body = None
        if request.content:
            if isinstance(request.content, bytes):
                body = request.content
            else:
                try:
                    body = await request.aread()
                    if hasattr(request, '_content'):
                        request._content = body
                except Exception:
                    pass
        
        # Create AWS request headers
        aws_headers = {
            'host': host,
            'x-amz-date': timestamp,
            'Content-Type': request.headers.get('Content-Type', 'application/json'),
            'Accept': request.headers.get('Accept', 'application/json, text/event-stream')
        }
        
        if body:
            aws_headers['Content-Length'] = str(len(body))
        
        # Create AWS request for signing
        aws_request = AWSRequest(
            method=request.method,
            url=str(request.url),
            headers=aws_headers,
            data=body
        )
        
        # Sign the request
        region = utils.load_config().get("region", "us-west-2")
        auth = BotocoreSigV4Auth(credentials, "bedrock-agentcore", region)
        auth.add_auth(aws_request)
        
        # Update request headers
        request.headers['X-Amz-Date'] = timestamp
        request.headers['Authorization'] = aws_request.headers['Authorization']
        
        if credentials.token:
            request.headers['X-Amz-Security-Token'] = credentials.token
    
    # Add event_hooks to kwargs if not already present
    if 'event_hooks' not in kwargs:
        kwargs['event_hooks'] = {'request': [], 'response': []}
    elif not isinstance(kwargs['event_hooks'], dict):
        kwargs['event_hooks'] = {'request': [], 'response': []}
    
    if 'request' not in kwargs['event_hooks']:
        kwargs['event_hooks']['request'] = []
    
    # Add the sign_request hook
    kwargs['event_hooks']['request'].append(sign_request)

    # Call original init with modified kwargs
    original_init(self, *args, **kwargs)

auth_type = "iam"
        
app = BedrockAgentCoreApp()

@app.entrypoint
async def agent_langgraph(payload):
    """
    Invoke the agent with a payload
    """
    logger.info(f"payload: {payload}")
    query = payload.get("prompt")
    logger.info(f"query: {query}")

    mcp_servers = payload.get("mcp_servers", [])
    logger.info(f"mcp_servers: {mcp_servers}")

    model_name = payload.get("model_name")
    logger.info(f"model_name: {model_name}")

    user_id = payload.get("user_id")
    logger.info(f"user_id: {user_id}")

    chat.update(modelName=model_name, userId=user_id)

    history_mode = payload.get("history_mode")
    logger.info(f"history_mode: {history_mode}")

    mcp_json = mcp_config.load_selected_config(mcp_servers)
    # logger.info(f"mcp_json: {mcp_json}")        
    
    server_params = langgraph_agent.load_multiple_mcp_server_parameters(mcp_json)
    # logger.info(f"server_params: {server_params}")    
    
    # Handle case when no MCP servers are available with empty tools list
    if not server_params:
        logger.info("No valid MCP servers configured, using empty tools list")
        tools = []
    else:        
        logger.info(f"auth_type: {auth_type}")
        if auth_type == "iam":
            # Apply monkey patch only if SigV4 is needed
            # Keep it global so it applies to all httpx.AsyncClient instances created during tool execution        
            httpx.AsyncClient.__init__ = patched_init
            logger.info(f"Applied SigV4 monkey patch")
        
        client = MultiServerMCPClient(server_params)
        tools = await client.get_tools()
        
    tool_list = [tool.name for tool in tools]
    logger.info(f"tool_list: {tool_list}")

    app = langgraph_agent.buildChatAgentWithHistory(tools)
    config = {
        "recursion_limit": 50,
        "configurable": {"thread_id": user_id},
        "tools": tools,
        "system_prompt": None
    }
    
    inputs = {
        "messages": [HumanMessage(content=query)]
    }
            
    value = final_output = None
    async for output in app.astream(inputs, config):
        for key, value in output.items():
            logger.info(f"--> key: {key}, value: {value}")

            if key == "messages" or key == "agent":
                if isinstance(value, dict) and "messages" in value:
                    final_output = value
                elif isinstance(value, list):
                    final_output = {"messages": value, "image_url": []}
                else:
                    final_output = {"messages": [value], "image_url": []}

            if "messages" in value:
                for message in value["messages"]:
                    if isinstance(message, AIMessage):
                        logger.info(f"AIMessage: {message.content}")

                        yield({'data': message.content})

                        tool_calls = message.tool_calls
                        # logger.info(f"tool_calls: {tool_calls}")

                        if tool_calls:
                            for tool_call in tool_calls:
                                tool_name = tool_call["name"]
                                tool_content = tool_call["args"]
                                toolUseId = tool_call["id"]
                                logger.info(f"tool_name: {tool_name}, content: {tool_content}, toolUseId: {toolUseId}")
                                yield({'tool': tool_name, 'input': tool_content, 'toolUseId': toolUseId})

                    elif isinstance(message, ToolMessage):
                        logger.info(f"ToolMessage: {message.name}, {message.content}")

                        toolResult = message.content
                        toolUseId = message.tool_call_id

                        yield({'toolResult': toolResult, 'toolUseId': toolUseId})
    
    yield({'result': final_output})

if __name__ == "__main__":
    app.run()

