import os
import json
import boto3
import logging
import sys

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("utils")

def load_config():
    config = None
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    return config

config = load_config()

bedrock_region = config['region']
accountId = config['accountId']
projectName = config['projectName']
agent_runtime_role = config['agent_runtime_role']
agent_runtime_arn = None

def get_agent_runtime_arn():    
    client = boto3.client('bedrock-agentcore-control', region_name=bedrock_region)
    response = client.list_agent_runtimes()
    logger.info(f"response: {response}")

    current_folder_name = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
    target = current_folder_name.split('/')[-1]
    print(f"target: {target}")

    isExist = False
    agentRuntimeId = None
    targetAgentRuntime = projectName.replace('-', '_')+'_'+target
    print(f"targetAgentRuntime: {targetAgentRuntime}")

    agentRuntimes = response['agentRuntimes']
    for agentRuntime in agentRuntimes:
        agentRuntimeName = agentRuntime['agentRuntimeName']
        print(f"agentRuntimeName: {agentRuntimeName}")
        if agentRuntimeName == targetAgentRuntime:
            print(f"agentRuntimeName: {agentRuntimeName} is already exists")
            agentRuntimeId = agentRuntime['agentRuntimeId']
            print(f"agentRuntimeId: {agentRuntimeId}")
            agentRuntimeArn = agentRuntime['agentRuntimeArn']
            print(f"agentRuntimeArn: {agentRuntimeArn}")
            isExist = True        
            break
    
    if isExist:
        return agentRuntimeArn
    else:
        return None

get_agent_runtime_arn()