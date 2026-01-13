import asyncio
import os
import json
import boto3
import uuid

def load_config():
    config = None
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)    
    return config

config = load_config()

projectName = config['projectName']
bedrock_region = config['region']

def load_agentcore_config(agent_name):
    client = boto3.client('bedrock-agentcore-control', region_name=bedrock_region)
    response = client.list_agent_runtimes(
        maxResults=100
    )
    print(f"response: {response}")

    agentRuntimes = response['agentRuntimes']
    for agentRuntime in agentRuntimes:
        if agentRuntime['agentRuntimeName'] == agent_name:
            return agentRuntime['agentRuntimeArn']
    return None

async def main():
    print(f"\n=== get agentcore runtime arn ===")

    current_folder_name = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
    target = current_folder_name.split('/')[-1]
    print(f"target: {target}")

    runtime_name = projectName.replace('-', '_')+'_'+target
    agent_runtime_arn = load_agentcore_config(runtime_name)
    print(f"agent_runtime_arn: {agent_runtime_arn}")

    print(f"\n=== invoke agentcore runtime ===")
    
    runtime_session_id = str(uuid.uuid4())
    print(f"runtime_session_id: {runtime_session_id}")

    prompt = "보일러 에러 코드?"
    mcp_servers = ["kb-retriever"]
    model_name = "Claude 3.7 Sonnet"
    user_id = target
    history_mode = "Disable"

    payload = json.dumps({
        "prompt": prompt,
        "mcp_servers": mcp_servers,
        "model_name": model_name,
        "user_id": user_id,
        "history_mode": history_mode
    })

    agent_core_client = boto3.client('bedrock-agentcore', region_name=bedrock_region)
    response = agent_core_client.invoke_agent_runtime(
        agentRuntimeArn=agent_runtime_arn,
        runtimeSessionId=runtime_session_id,
        payload=payload,
        qualifier="DEFAULT" # DEFAULT or LATEST
    )

    print(f"response: {response}")  

    print(f"\n=== show stream response ===")
    
    if "text/event-stream" in response.get("contentType", ""):
        for line in response["response"].iter_lines(chunk_size=10):
            line = line.decode("utf-8")
            if line:
                print(f"-> {line}")
                
if __name__ == "__main__":
    asyncio.run(main())
