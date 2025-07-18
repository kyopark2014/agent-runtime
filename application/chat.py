import boto3
import json
import uuid
import os
import logging
import sys

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("chat")

def load_config():
    config = None
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "..", "agent", "config.json")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    return config

config = load_config()

bedrock_region = config['region']
accountId = config['accountId']
projectName = config['projectName']
agent_runtime_arn = config['agent_runtime_arn']

def run_agent(prompt, mcp_servers):
    payload = json.dumps({
        "prompt": prompt,
        "mcp_servers": mcp_servers
    })

    agent_core_client = boto3.client('bedrock-agentcore', region_name=bedrock_region)
    response = agent_core_client.invoke_agent_runtime(
        agentRuntimeArn=agent_runtime_arn,
        runtimeSessionId=str(uuid.uuid4()),
        payload=payload,
        qualifier="DEFAULT"
    )

    response_body = response['response'].read()
    response_data = json.loads(response_body)
    logger.info(f"Agent Response: {response_data}")

    return response_data.get("result", "")
