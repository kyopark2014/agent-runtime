import logging
import sys
import chat
import mcp_config
import claude_agent
import json
import uuid

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from claude_agent_sdk import (
    query,
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,    
    SystemMessage,
    UserMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock
)

logging.basicConfig(
    level=logging.INFO,  
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("agent")

app = BedrockAgentCoreApp()

session_id = uuid.uuid4().hex
tool_name = dict()

@app.entrypoint
async def agent_claude(payload):    
    """
    Invoke the agent with a payload
    """
    global session_id

    logger.info(f"payload: {payload}")
    prompt = payload.get("prompt")
    logger.info(f"prompt: {prompt}")

    mcp_servers = payload.get("mcp_servers", [])
    logger.info(f"mcp_servers: {mcp_servers}")

    model_name = payload.get("model_name")
    logger.info(f"model_name: {model_name}")

    user_id = payload.get("user_id")
    logger.info(f"user_id: {user_id}")

    chat.update(modelName=model_name, userId=user_id)

    history_mode = payload.get("history_mode")
    logger.info(f"history_mode: {history_mode}")

    mcp_config.bearer_token = None
    mcp_json = mcp_config.load_selected_config(mcp_servers)
    logger.info(f"mcp_json: {mcp_json}")

    server_params = claude_agent.load_multiple_mcp_server_parameters(mcp_json)
    logger.info(f"server_params: {server_params}")

    system = (
        "당신의 이름은 서연이고, 질문에 친근한 방식으로 대답하도록 설계된 대화형 AI입니다."
        "상황에 맞는 구체적인 세부 정보를 충분히 제공합니다."
        "모르는 질문을 받으면 솔직히 모른다고 말합니다."
        "한국어로 답변하세요."
    )

    logger.info(f"session_id: {session_id}")
    if session_id is not None and history_mode == "Enable":
        options = ClaudeAgentOptions(
            system_prompt=system,
            max_turns=100,
            permission_mode="default", # "default", "acceptEdits", "plan", "bypassPermissions"
            model=claude_agent.get_model_id(),
            mcp_servers=server_params,
            resume=session_id,
            can_use_tool=claude_agent.prompt_for_tool_approval
        )
    else:
       options = ClaudeAgentOptions(
            system_prompt=system,
            max_turns=100,
            permission_mode="default", 
            mcp_servers=server_params,
            model=claude_agent.get_model_id(),
            can_use_tool=claude_agent.prompt_for_tool_approval
        ) 
    
    final_result = ""    
    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)

        async for message in client.receive_response():
            # logger.info(message)
            if isinstance(message, SystemMessage):
                logger.info(f"SystemMessage: {message}")
                subtype = message.subtype
                data = message.data
                logger.info(f"SystemMessage: type={subtype}")

                if subtype == "init":
                    session_id = message.data.get('session_id')
                    logger.info(f"Session started with ID: {session_id}")
                    
                if "tools" in data:
                    tools = data["tools"]
                    logger.info(f"--> tools: {tools}")

                    yield({'Tools': tools})

            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        logger.info(f"--> TextBlock: {block.text}")
                        final_result = block.text
                        yield({'TextBlock': block.text})
                        
                    elif isinstance(block, ToolUseBlock):
                        logger.info(f"--> tool_use_id: {block.id}, name: {block.name}, input: {block.input}")
                        yield({'ToolUseBlock': block.name, 'input': block.input})
                        tool_name[block.id] = block.name

                    elif isinstance(block, ToolResultBlock):
                        logger.info(f"--> tool_use_id: {block.tool_use_id}, content: {block.content}")
                        logger.info(f"--> tool_name: {tool_name[block.tool_use_id]}")

                        yield({'ToolName': tool_name[block.tool_use_id], 'ToolResultBlock': block.content})
                    else:
                        logger.info(f"AssistantMessage: {block}")
                    
            elif isinstance(message, UserMessage):
                for block in message.content:
                    if isinstance(block, ToolResultBlock):
                        logger.info(f"--> tool_use_id: {block.tool_use_id}, content: {block.content}")
                        logger.info(f"--> tool_name: {tool_name[block.tool_use_id]}")

                        yield({'ToolName': tool_name[block.tool_use_id], 'ToolResultBlock': block.content})
                        
                        if isinstance(block.content, list):
                            for item in block.content:
                                if isinstance(item, dict) and "text" in item:
                                    logger.info(f"--> ToolResult: {item['text']}")
                                    if "path" in item['text']:
                                        json_path = json.loads(item['text'])
                                        path = json_path.get('path', "")
                                        logger.info(f"path: {path}")
                    else:
                        logger.info(f"UserMessage: {block}")
            else:
                logger.info(f"Message: {message}")

    yield({'result': final_result})

if __name__ == "__main__":
    app.run()

