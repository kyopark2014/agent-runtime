import boto3
import json
import utils
import uuid
import os

region_name = utils.bedrock_region
accountId = utils.accountId
projectName = utils.projectName
agent_runtime_role = utils.agent_runtime_role

def load_agent_config():
    config = None
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)    
    return config

agent_config = load_agent_config()
agentRuntimeArn = agent_config['agent_runtime_arn']
print(f"agentRuntimeArn: {agentRuntimeArn}")

payload = json.dumps({
    "prompt": "안녕",
    "mcp_servers": ["basic", "use_aws", "tavily-search", "filesystem", "terminal"],
    "model_name": "Claude 3.7 Sonnet",
})

agent_core_client = boto3.client('bedrock-agentcore', region_name=region_name)

response = agent_core_client.invoke_agent_runtime(
    agentRuntimeArn=agentRuntimeArn,
    runtimeSessionId=str(uuid.uuid4()),
    payload=payload,
    qualifier="DEFAULT"
)

response_body = response['response'].read()
print(f"response_body: {response_body}")

try:
    response_data = json.loads(response_body)
    print("Agent Response:", response_data)
except json.JSONDecodeError:
    print("Invalid JSON response")
    print(response_body)

# Process and print the response
# if "text/event-stream" in response.get("contentType", ""):
#     # Handle streaming response
#     content = []
#     for line in response["response"].iter_lines(chunk_size=10):
#         if line: 
#             line = line.decode("utf-8")
#         if line.startswith("data: "):
#             line = line[6:]
#             print(line)
#             content.append(line)
#     print("\nComplete response:", "\n".join(content))

# elif response.get("contentType") == "application/json":
#     # Handle standard JSON response
#     content = []
#     for chunk in response.get("response", []):
#         content.append(chunk.decode('utf-8'))
#         print(json.loads(''.join(content)))

# else:
#     # Print raw response
#     print(response)