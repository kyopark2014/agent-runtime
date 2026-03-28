# Runtime MCP

### Dockerfile

[Dockerfile](./iam_auth/kb-retriever/Dockerfile)와 같이 필요한 패키지를 지정하고 8000 포트를 expose 합니다. 여기에서는 [mcp_server_retrieve.py](./iam_auth/kb-retriever/mcp_server_retrieve.py)를 entrypoint로 활용합니다.

```bash
FROM --platform=linux/arm64 python:3.13-slim
        
WORKDIR /app

RUN pip install --upgrade boto3 botocore \
    && pip install mcp \
    && pip install aws-opentelemetry-distro>=0.10.0

# Add the current directory to Python path
ENV PYTHONPATH=/app

EXPOSE 8080
EXPOSE 8000

COPY . .

CMD ["opentelemetry-instrument", "python", "-m", "mcp_server_retrieve"]
```

### MCP 파일

아래와 fast api를 이용해 MCP runtime을 구성합니다.

```python
import mcp_retrieve
from mcp.server.fastmcp import FastMCP 

mcp = FastMCP(
    name = "mcp-retrieve",
    host="0.0.0.0",
    stateless_http=True
)
    
@mcp.tool()
def retrieve(keyword: str) -> str:
    """
    Query the keyword using RAG based on the knowledge base.
    keyword: the keyword to query
    return: the result of query
    """
    return mcp_retrieve.retrieve(keyword)

if __name__ =="__main__":
    mcp.run(transport="streamable-http")
```

## MCP Runtime 생성

### IAM

```python
client = boto3.client('bedrock-agentcore-control', region_name=aws_region)
        
response = client.create_agent_runtime(
    agentRuntimeName=runtime_name,
    agentRuntimeArtifact={
        'containerConfiguration': {
            'containerUri': f"{account_id}.dkr.ecr.{aws_region}.amazonaws.com/{repository_name}:{image_tag}"
        }
    },
    networkConfiguration={"networkMode": "PUBLIC"}, 
    roleArn=agent_runtime_role,
    protocolConfiguration={"serverProtocol": "MCP"}
)
```

### JWT token

아래에서는 Cognito를 이용한 JWT Token 인증으로 MCP Runtime을 생성하는 것을 설명합니다.


```python
client = boto3.client('bedrock-agentcore-control', region_name=aws_region)

response = client.create_agent_runtime(
    agentRuntimeName=runtime_name,
    agentRuntimeArtifact={
        'containerConfiguration': {
            'containerUri': f"{account_id}.dkr.ecr.{aws_region}.amazonaws.com/{repository_name}:{image_tag}"
        }
    },
    networkConfiguration={"networkMode": "PUBLIC"}, 
    roleArn=agent_runtime_role,
    protocolConfiguration={"serverProtocol": "MCP"},
    authorizerConfiguration={
        "customJWTAuthorizer": {
            "allowedClients": [
                cognito_config['client_id']
            ],
            "discoveryUrl": cognito_config['discovery_url']
        }
    }
)
```



## Client에서 MCP Runtime 호출

### IAM

[test_mcp_remote.py](./iam_auth/kb-retriever/test_mcp_remote.py)를 참조합니다.

```python
agent_arn = config['agent_runtime_arn']                
encoded_arn = agent_arn.replace(':', '%3A').replace('/', '%2F')

mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

request_body = json.dumps({
    "jsonrpc": "2.0",
    "id": "1",
    "method": "initialize", 
    "params": {
        "protocolVersion": "2024-11-05", 
        "capabilities": {}, 
        "clientInfo": {
            "name": "test-client", 
            "version": "1.0.0"
        }
    }
})

# Generate SigV4 headers for the request
headers = get_sigv4_headers("POST", mcp_url, request_body.encode('utf-8'), region)

response = requests.post(
    mcp_url,
    headers=headers,
    data=request_body,
    timeout=30
)
```
