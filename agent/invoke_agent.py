import boto3
import json
import utils
import uuid

region_name = utils.bedrock_region
accountId = utils.accountId
projectName = utils.projectName
agent_runtime_role = utils.agent_runtime_role
agentRuntimeArn = utils.agent_runtime_arn
print(f"agentRuntimeArn: {agentRuntimeArn}")

payload = json.dumps({
    "prompt": "서울 날씨는?",
    "mcp_servers": ["basic", "use_aws", "tavily-search", "filesystem", "terminal"]
})

agent_core_client = boto3.client('bedrock-agentcore', region_name=region_name)

response = agent_core_client.invoke_agent_runtime(
    agentRuntimeArn=agentRuntimeArn,
    runtimeSessionId=str(uuid.uuid4()),
    payload=payload,
    qualifier="DEFAULT"
)

response_body = response['response'].read()
response_data = json.loads(response_body)
print("Agent Response:", response_data)