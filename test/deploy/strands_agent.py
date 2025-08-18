import chat
import os
import logging
import sys
import boto3

from strands.models import BedrockModel
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands import Agent
from botocore.config import Config

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("strands-agent")

aws_region = "us-west-2"

#########################################################
# Strands Agent 
#########################################################
def get_model():
    STOP_SEQUENCE = "\n\nHuman:" 

    maxOutputTokens = 4096 
    
    aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_session_token = os.environ.get('AWS_SESSION_TOKEN')

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

def create_agent():
    system_prompt = (
        "당신의 이름은 서연이고, 질문에 대해 친절하게 답변하는 사려깊은 인공지능 도우미입니다."
        "상황에 맞는 구체적인 세부 정보를 충분히 제공합니다." 
        "모르는 질문을 받으면 솔직히 모른다고 말합니다."
    )
    
    model = get_model()

    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=[],
        conversation_manager=conversation_manager
    )

    return agent

