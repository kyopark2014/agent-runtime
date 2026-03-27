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

    global tool_list
    tool_list = []

    # initiate agent
    await strands_agent.initiate_agent(
        system_prompt=None, 
        strands_tools=strands_agent.strands_tools, 
        mcp_servers=mcp_servers
    )

    # run agent    
    with strands_agent.mcp_manager.get_active_clients(mcp_servers) as _:
        agent_stream = strands_agent.agent.stream_async(query)

        final_output = ""
        async for event in agent_stream:
            text = ""            
            if "data" in event:
                text = event["data"]
                logger.info(f"[data] {text}")
                yield({'data': text})

            elif "result" in event:
                final = event["result"]                
                message = final.message
                if message:
                    content = message.get("content", [])
                    text = content[0].get("text", "")
                    logger.info(f"[result] {text}")
                
                    final_output = {"messages": text, "image_url": []}

            elif "current_tool_use" in event:
                current_tool_use = event["current_tool_use"]
                name = current_tool_use.get("name", "")
                input = current_tool_use.get("input", "")
                toolUseId = current_tool_use.get("toolUseId", "")

                text = f"name: {name}, input: {input}"
                logger.info(f"[current_tool_use] {text}")

                yield({'tool': name, 'input': input, 'toolUseId': toolUseId})
            
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
                        
                        yield({'toolResult': toolResult, 'toolUseId': toolUseId})
            
            elif "contentBlockDelta" or "contentBlockStop" or "messageStop" or "metadata" in event:
                pass

            else:
                logger.info(f"event: {event}")

    yield({'result': final_output})

if __name__ == "__main__":
    app.run()

