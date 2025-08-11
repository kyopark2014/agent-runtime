# Simple Tester

가벼운 AgentCore 테스트를 위해서 strands SDK를 활용합니다.

## 배포 및 실행하기

### Local에서 동작 확인

[build-docker.sh](./build-docker.sh)와 [run-docker.sh](./run-docker.sh)을 이용해 local 환경에서 docker 동작을 확인할 수 있습니다.

```text
./build-docker.sh
./run-docker.sh
```

이후 [curl.sh](./curl.sh)과 같이 동작을 테스트 할 수 있습니다. 

```text
./curl.sh
```

[curl.sh](./curl.sh)을 이용하면 아래와 같이 local에서 테스트 할 수 있습니다. MCP server와 model 정보를 질문과 함께 제공합니다.

```text
curl -X POST http://localhost:8080/invocations \
-H "Content-Type: application/json" \
-d '{"prompt": "내 s3 bucket 리스트는?", "mcp_servers": ["basic", "use_aws", "tavily-search", "filesystem", "terminal"], "model_name": "Claude 3.7 Sonnet"}'
```

[invoke_agent.py](./invoke_agent.py)와 같이 코드로도 동작으로 확인할 수 있습니다.

```text
python invoke_agent.py
```

[invoke_agent.py](./invoke_agent.py)에서는 아래와 같이 [invoke_agent_runtime](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore/client/invoke_agent_runtime.html)을 이용하여 실행합니다.

```python
payload = json.dumps({
    "prompt": "서울 날씨는?",
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
response_data = json.loads(response_body)
```

문제 발생시 Docker 로그를 아래와 같이 확인합니다.

```text
sudo docker logs coreagent-langgraph-container
```


## Docker 


## AgentCore


