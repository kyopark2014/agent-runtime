import boto3
import json
import utils
import uuid

aws_region = utils.bedrock_region
accountId = utils.accountId
projectName = utils.projectName
agent_runtime_role = utils.agent_runtime_role

agent_core_client = boto3.client('bedrock-agentcore', region_name='us-west-2')

payload = json.dumps({
    "prompt": "서울 날씨는?"
})
response = agent_core_client.invoke_agent_runtime(
    agentRuntimeArn=f'arn:aws:bedrock-agentcore:us-west-2:262976740991:runtime/agentcore_langgraph-OvvIK7DIFD',
    runtimeSessionId=str(uuid.uuid4()),
    payload=payload,
    qualifier="DEFAULT"
)

response_body = response['response'].read()
response_data = json.loads(response_body)
print("Agent Response:", response_data)