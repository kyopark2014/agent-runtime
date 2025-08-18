import logging
import sys
import chat
import mcp_config
import langgraph_agent
import agentcore_memory

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

    # initate memory variables    
    memory_id, actor_id, session_id, namespace = agentcore_memory.load_memory_variables(user_id)
    logger.info(f"memory_id: {memory_id}, actor_id: {actor_id}, session_id: {session_id}, namespace: {namespace}")

    if memory_id is None:
        # retrieve memory id
        memory_id = agentcore_memory.retrieve_memory_id()
        logger.info(f"memory_id: {memory_id}")        
        
        # create memory if not exists
        if memory_id is None:
            logger.info(f"Memory will be created...")
            memory_id = agentcore_memory.create_memory(namespace)
            logger.info(f"Memory was created... {memory_id}")
        
        # create strategy if not exists
        agentcore_memory.create_strategy_if_not_exists(memory_id=memory_id, namespace=namespace, strategy_name=user_id)

        # save memory variables
        agentcore_memory.update_memory_variables(
            user_id=user_id, 
            memory_id=memory_id, 
            actor_id=actor_id, 
            session_id=session_id, 
            namespace=namespace)

    mcp_json = mcp_config.load_selected_config(mcp_servers)
    logger.info(f"mcp_json: {mcp_json}")        

    server_params = langgraph_agent.load_multiple_mcp_server_parameters(mcp_json)
    logger.info(f"server_params: {server_params}")    

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
            
    value = result = None
    final_output = None
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
                    # if isinstance(message, HumanMessage):
                    #     logger.info(f"HumanMessage: {message.content}")
                    if isinstance(message, AIMessage):
                        logger.info(f"AIMessage: {message.content}")

                        yield({'data': message.content})

                        tool_calls = message.tool_calls
                        logger.info(f"tool_calls: {tool_calls}")

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
    
    if final_output and "messages" in final_output and len(final_output["messages"]) > 0:
        result = final_output["messages"][-1].content
        # save event to memory
        if memory_id is not None:
            agentcore_memory.save_conversation_to_memory(memory_id, actor_id, session_id, query, result) 
    else:
        result = "답변을 찾지 못하였습니다."        
    logger.info(f"result: {result}")

    yield({'result': result})

if __name__ == "__main__":
    app.run()

