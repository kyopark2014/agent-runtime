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

    agent = strands_agent.create_agent()

    agent_stream = agent.stream_async(query)

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
        else:
            logger.info(f"event: {event}")

        yield (stream)

if __name__ == "__main__":
    app.run()

