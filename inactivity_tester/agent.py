import chat
import os
import contextlib
import logging
import sys
import utils
import boto3
import time

from strands.models import BedrockModel
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands import Agent
from botocore.config import Config
from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("tester")

initiated = False

history_mode = "Disable"
aws_region = utils.bedrock_region

#########################################################
# Strands Agent 
#########################################################
def get_model():
    if chat.model_type == 'nova':
        STOP_SEQUENCE = '"\n\n<thinking>", "\n<thinking>", " <thinking>"'
    elif chat.model_type == 'claude':
        STOP_SEQUENCE = "\n\nHuman:" 

    if chat.model_type == 'claude':
        maxOutputTokens = 4096 # 4k
    else:
        maxOutputTokens = 5120 # 5k

    maxReasoningOutputTokens=64000
    thinking_budget = min(maxOutputTokens, maxReasoningOutputTokens-1000)

    # AWS 자격 증명 설정
    aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_session_token = os.environ.get('AWS_SESSION_TOKEN')

    # Bedrock 클라이언트 설정
    bedrock_config = Config(
        read_timeout=900,
        connect_timeout=900,
        retries=dict(max_attempts=3, mode="adaptive"),
    )

    if aws_access_key and aws_secret_key:
        bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=aws_region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            aws_session_token=aws_session_token,
            config=bedrock_config
        )
    else:
        bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=aws_region,
            config=bedrock_config
        )

    if chat.reasoning_mode=='Enable':
        model = BedrockModel(
            client=bedrock_client,
            model_id=chat.model_id,
            max_tokens=64000,
            stop_sequences = [STOP_SEQUENCE],
            temperature = 1,
            additional_request_fields={
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": thinking_budget,
                }
            },
        )
    else:
        model = BedrockModel(
            client=bedrock_client,
            model_id=chat.model_id,
            max_tokens=maxOutputTokens,
            stop_sequences = [STOP_SEQUENCE],
            temperature = 0.1,
            top_p = 0.9,
            additional_request_fields={
                "thinking": {
                    "type": "disabled"
                }
            }
        )
    return model

conversation_manager = SlidingWindowConversationManager(
    window_size=10,  
)

def create_agent(system_prompt, tools, history_mode):
    if system_prompt==None:
        system_prompt = (
            "당신의 이름은 서연이고, 질문에 대해 친절하게 답변하는 사려깊은 인공지능 도우미입니다."
            "상황에 맞는 구체적인 세부 정보를 충분히 제공합니다." 
            "모르는 질문을 받으면 솔직히 모른다고 말합니다."
        )

    if not system_prompt or not system_prompt.strip():
        system_prompt = "You are a helpful AI assistant."

    model = get_model()
    if history_mode == "Enable":
        logger.info("history_mode: Enable")
        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=tools,
            conversation_manager=conversation_manager
        )
    else:
        logger.info("history_mode: Disable")
        agent = Agent(
            model=model,
            system_prompt=system_prompt,
            tools=tools
            #max_parallel_tools=2
        )
    return agent

app = BedrockAgentCoreApp()

@app.entrypoint
async def agentcore_strands(payload):
    """
    Invoke the agent with a payload
    """
    logger.info(f"payload: {payload}")
    query = payload.get("prompt")
    logger.info(f"query: {query}")

    model_name = payload.get("model_name")
    logger.info(f"model_name: {model_name}")
    
    # initiate agent
    agent = create_agent(
        system_prompt=None, 
        tools=[], 
        history_mode='Disable')

    while True:
        agent_stream = agent.stream_async(query)

        async for event in agent_stream:
            if "result" in event:
                logger.info(f"event: {event}")
                final = event["result"]                
                message = final.message
                if message:
                    content = message.get("content", [])
                    result = content[0].get("text", "")
                    logger.info(f"result: {result}")
            yield (event)

        time.sleep(10)

if __name__ == "__main__":
    app.run()

