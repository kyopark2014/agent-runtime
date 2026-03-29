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

### IAM (Request)

[test_mcp_remote.py](./iam_auth/kb-retriever/test_mcp_remote.py)와 같이 MCP URL을 직접 요청하는 방법으로도 MCP 를 호출할 수 있습니다.

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

### IAM (MCP)

IAM으로 된 MCP 서버의 mcp.json 포맷은 아래와 같습니다.

```java
{
    "mcpServers": {
        "kb-retriever": {
            "type": "streamable_http",
            "url": f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT",
            "headers": {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        }
    }
}
```

[agent.py in strands](https://github.com/kyopark2014/agent-runtime/blob/main/runtime_agent/strands/agent.py)와 같이 http에 인증을 하는 event_hook을 설정합니다. 이것은 일반 HTTP 클라이언트(httpx)로 보내는 요청에 AWS 서명(SigV4)을 붙입니다.

```python
import httpx

_original_httpx_async_init = httpx.AsyncClient.__init__

def _patched_httpx_async_init(self, *args, **kwargs):
    if "event_hooks" not in kwargs:
        kwargs["event_hooks"] = {"request": [], "response": []}
    elif not isinstance(kwargs["event_hooks"], dict):
        kwargs["event_hooks"] = {"request": [], "response": []}
    if "request" not in kwargs["event_hooks"]:
        kwargs["event_hooks"]["request"] = []
    kwargs["event_hooks"]["request"].append(sign_request)

    _original_httpx_async_init(self, *args, **kwargs)

if auth_type == "iam":
    httpx.AsyncClient.__init__ = _patched_httpx_async_init
```

여기서 sign_request는 아래와 같이 구현할 수 있습니다. URL에 bedrock-agentcore가 있으면 AgentCore의 endpoint의 요청에 AWS 서명을 붙입니다. 


```python
async def sign_request(request: httpx.Request) -> None:
    if "bedrock-agentcore" not in str(request.url):
        return
    boto_session = boto3.Session()
    credentials = boto_session.get_credentials().get_frozen_credentials()

    parsed_url = urlparse(str(request.url))
    host = parsed_url.netloc
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    body = None
    if request.content:
        if isinstance(request.content, bytes):
            body = request.content
        else:
            try:
                body = await request.aread()
                if hasattr(request, "_content"):
                    request._content = body
            except Exception:
                pass

    aws_headers = {
        "host": host,
        "x-amz-date": timestamp,
        "Content-Type": request.headers.get("Content-Type", "application/json"),
        "Accept": request.headers.get("Accept", "application/json, text/event-stream"),
    }
    if body:
        aws_headers["Content-Length"] = str(len(body))

    aws_request = AWSRequest(
        method=request.method,
        url=str(request.url),
        headers=aws_headers,
        data=body,
    )

    region = utils.load_config().get("region", "us-west-2")
    auth = BotocoreSigV4Auth(credentials, "bedrock-agentcore", region)
    auth.add_auth(aws_request)

    request.headers["X-Amz-Date"] = timestamp
    request.headers["Authorization"] = aws_request.headers["Authorization"]
    if credentials.token:
        request.headers["X-Amz-Security-Token"] = credentials.token
```        

### JWT token 

mcp.json은 아래와 같습니다.

```java
{
    "mcpServers": {
        "kb-retriever": {
            "type": "streamable_http",
            "url": f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT",
            "headers": {
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        }
    }
}
```

여기서 Cognito를 이용한다면 아래와 같이 jwt token을 얻을 수 있습니다.

```python
client = boto3.client('cognito-idp', region_name=region)
response = client.initiate_auth(
    ClientId=client_id,
    AuthFlow='USER_PASSWORD_AUTH',
    AuthParameters={
        'USERNAME': username,
        'PASSWORD': password
    }
)

auth_result = response['AuthenticationResult']
access_token = auth_result['AccessToken']
```

