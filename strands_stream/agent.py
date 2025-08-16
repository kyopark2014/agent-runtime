import logging
import sys
import strands_agent

from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("agent")
# Agentcore Endpoints
app = BedrockAgentCoreApp()

@app.entrypoint
async def agentcore_strands(payload):
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

    history_mode = payload.get("history_mode")
    logger.info(f"history_mode: {history_mode}")

    global tool_list
    tool_list = []

    # # initate memory variables
    # memory_id, actor_id, session_id, namespace = agentcore_memory.load_memory_variables(chat.user_id)
    # logger.info(f"memory_id: {memory_id}, actor_id: {actor_id}, session_id: {session_id}, namespace: {namespace}")

    # if memory_id is None:
    #     # retrieve memory id
    #     memory_id = agentcore_memory.retrieve_memory_id()
    #     logger.info(f"memory_id: {memory_id}")        
        
    #     # create memory if not exists
    #     if memory_id is None:
    #         logger.info(f"Memory will be created...")
    #         memory_id = agentcore_memory.create_memory(namespace)
    #         logger.info(f"Memory was created... {memory_id}")
        
    #     # create strategy if not exists
    #     agentcore_memory.create_strategy_if_not_exists(
    #         memory_id=memory_id, namespace=namespace, strategy_name=chat.user_id)

    #     # save memory variables
    #     agentcore_memory.update_memory_variables(
    #         user_id=chat.user_id, 
    #         memory_id=memory_id, 
    #         actor_id=actor_id, 
    #         session_id=session_id, 
    #         namespace=namespace)
    
    # initiate agent
    await strands_agent.initiate_agent(
        system_prompt=None, 
        strands_tools=strands_agent.strands_tools, 
        mcp_servers=mcp_servers, 
        historyMode='Disable'
    )
    logger.info(f"tool_list: {tool_list}")    

    # run agent    
    with strands_agent.mcp_manager.get_active_clients(mcp_servers) as _:
        agent_stream = strands_agent.agent.stream_async(query)

        stream = ""
        async for event in agent_stream:
            text = ""            
            if "data" in event:
                text = event["data"]
                logger.info(f"[data] {text}")
                stream = {'data': text}

            elif "result" in event:
                final = event["result"]                
                message = final.message
                if message:
                    content = message.get("content", [])
                    result = content[0].get("text", "")
                    logger.info(f"[result] {result}")
                    stream = {'result': result}

            elif "current_tool_use" in event:
                current_tool_use = event["current_tool_use"]
                #logger.info(f"current_tool_use: {current_tool_use}")
                name = current_tool_use.get("name", "")
                input = current_tool_use.get("input", "")
                toolUseId = current_tool_use.get("toolUseId", "")

                text = f"name: {name}, input: {input}"
                #logger.info(f"[current_tool_use] {text}")
                stream = {'tool': name, 'input': input, 'toolUseId': toolUseId}
            
            elif "message" in event:
                message = event["message"]
                logger.info(f"[message] {message}")

                if "content" in message:
                    content = message["content"]
                    logger.info(f"tool content: {content}")
                    if "toolResult" in content[0]:
                        toolResult = content[0]["toolResult"]
                        toolUseId = toolResult["toolUseId"]
                        toolContent = toolResult["content"]
                        toolResult = toolContent[0].get("text", "")
                        logger.info(f"[toolResult] {toolResult}, [toolUseId] {toolUseId}")
                        stream = {'toolResult': toolResult, 'toolUseId': toolUseId}
            
            elif "contentBlockDelta" or "contentBlockStop" or "messageStop" or "metadata" in event:
                pass

            else:
                logger.info(f"event: {event}")

            yield (stream)
    
    # save event to memory
    # if memory_id is not None and result:
    #     agentcore_memory.save_conversation_to_memory(memory_id, actor_id, session_id, query, result) 

if __name__ == "__main__":
    app.run()

