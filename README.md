# AgentCore를 이용해 Agent 배포하기

여기에서는 AgentCore를 이용해 LangGraph로 만든 Agent를 사용하는 방법에 대해 설명합니다.

bedrock-agentcore:GetAgentRuntime 퍼미션이 필요합니다.

## 주요 구현

### 전체 Architecture

전체적인 Architecture는 아래와 같습니다. 여기서는 MCP를 지원하는 Strands와 LangGraph agent를 [AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)를 이용해 배포하고 streamlit 애플리케이션을 이용해 사용합니다. 개발자는 각 agent에 맞는 [Dockerfile](./langgraph/Dockerfile)을 이용하여, docker image를 생성하고 ECR에 업로드 합니다. 이후 [bedrock-agentcore-control](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/Welcome.html)의 [create_agent_runtime.py](./langgraph/create_agent_runtime.py)을 이용해서 [AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)의 runtime으로 배포합니다. 이 작업이 끝나면 EC2와 같은 compute에 있는 streamlit에서 LangGraph와 Strands agent를 활용할 수 있습니다. 애플리케이션에서 AgentCore의 runtime을 호출할 때에는 [bedrock-agentcore](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore.html)의 [invoke_agent_runtime](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore/client/invoke_agent_runtime.html)을 이용합니다. 이때에 각 agent를 생성할 때에 확인할 수 있는 [agentRuntimeArn](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_Agent.html)을 이용합니다. Agent는 [MCP](https://modelcontextprotocol.io/introduction)을 이용해 RAG, AWS Document, Tavily와 같은 검색 서비스를 활용할 수 있습니다. 여기에서는 RAG를 위하여 Lambda를 이용합니다. 데이터 저장소의 관리는 Knowledge base를 사용하고, 벡터 스토어로는 OpenSearch를 이용합니다. Agent에 필요한 S3, CloudFront, OpenSearch, Lambda등의 배포를 위해서는 AWS CDK를 이용합니다.

<img width="862" height="428" alt="image" src="https://github.com/user-attachments/assets/e01e4c99-869d-435c-a573-9468311ada73" />


AgentCore의 runtime은 배포를 위해 Docker를 이용합니다. 현재(2025.7) 기준으로 arm64와 1GB 이하의 docker image를 지원합니다.

### AgentCore 소개

- AgentCore Runtime: AI agent와 tool을 배포하고 트래픽에 따라 자동으로 확장(Scaling)이 가능한 serverless runtime입니다. LangGraph, CrewAI, Strands Agents를 포함한 다양한 오픈소스 프레임워크을 지원합니다. 빠른 cold start, 세션 격리, 내장된 신원 확인(built-in identity), multimodal payload를 지원합니다. 이를 통해 안전하고 빠른 출시가 가능합니다.
- AgentCore Memory: Agent가 편리하게 short term, long term 메모리를 관리할 수 있습니다.
- AgentCore Code Interpreter: 분리된 sandbox 환경에서 안전하게 코드를 실행할 수 있습니다.
- AgentCore Broswer: 브라우저를 이용해 빠르고 안전하게 웹크롤링과 같은 작업을 수행할 수 있습니다.
- AgentCore Gateway: API, Lambda를 비롯한 서비스들을 쉽게 Tool로 활용할 수 있습니다.
- AgentCore Observability: 상용 환경에서 개발자가 agent의 동작을 trace, debug, monitor 할 수 있습니다.

### AgentCore에 배포하기

LangGraph와 strands agent에 대한 이미지를 [Dockerfile](./langgraph/Dockerfile)을 이용해 빌드후 ECR에 배포합니다. [push-to-ecr.sh](./langgraph/push-to-ecr.sh)를 이용하면 손쉽게 배포할 수 있습니다.

```text
./push-to-ecr.sh
```

이후, 아래와 같이 [create_agent_runtime.py](./langgraph/create_agent_runtime.py)를 이용해 AgentCore에 runtime으로 배포합니다.

```text
python create_agent_runtime.py
```

[create_agent_runtime.py](./langgraph/create_agent_runtime.py)에서는 AgentCore에 처음으로 배포하는지 확인하여 아래와 같이 runtime을 생성합니다.

```python
response = client.create_agent_runtime(
    agentRuntimeName=runtime_name,
    agentRuntimeArtifact={
        'containerConfiguration': {
            'containerUri': f"{accountId}.dkr.ecr.{aws_region}.amazonaws.com/{repositoryName}:{imageTags}"
        }
    },
    networkConfiguration={"networkMode":"PUBLIC"}, 
    roleArn=agent_runtime_role
)
agentRuntimeArn = response['agentRuntimeArn']
```

기존에 runtime이 있는지는 아래와 같이 [list_agent_runtimes](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore-control/client/list_agent_runtimes.html)을 이용해 확인합니다. 

```python
client = boto3.client('bedrock-agentcore-control', region_name=aws_region)
response = client.list_agent_runtimes()

isExist = False
agentRuntimeId = None
agentRuntimes = response['agentRuntimes']
targetAgentRuntime = repositoryName
if len(agentRuntimes) > 0:
    for agentRuntime in agentRuntimes:
        agentRuntimeName = agentRuntime['agentRuntimeName']
        if agentRuntimeName == targetAgentRuntime:
            agentRuntimeId = agentRuntime['agentRuntimeId']
            isExist = True        
            break
```

이미 runtime이 있다면 아래와 같이 [update_agent_runtime](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore-control/client/update_agent_runtime.html)을 이용해 업데이트 합니다.

```python
response = client.update_agent_runtime(
    agentRuntimeId=agentRuntimeId,
    description="Update agent runtime",
    agentRuntimeArtifact={
        'containerConfiguration': {
            'containerUri': f"{accountId}.dkr.ecr.{aws_region}.amazonaws.com/{targetAgentRuntime}:{imageTags}"
        }
    },
    roleArn=agent_runtime_role,
    networkConfiguration={"networkMode":"PUBLIC"},
    protocolConfiguration={"serverProtocol":"HTTP"}
)
```

## 실행하기

### Local에서 동작 확인

[build-docker.sh](./langgraph/build-docker.sh)와 [run-docker.sh](./langgraph/run-docker.sh)을 이용해 local 환경에서 docker 동작을 확인할 수 있습니다.

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

[invoke_agent.py](./langgraph/invoke_agent.py)와 같이 코드로도 동작으로 확인할 수 있습니다.

```text
python invoke_agent.py
```

[invoke_agent.py](./langgraph/invoke_agent.py)에서는 아래와 같이 [invoke_agent_runtime](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore/client/invoke_agent_runtime.html)을 이용하여 실행합니다.

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

Streamlit에서 아래와 같이 "Docker"를 선택하면, local의 docker를 테스트 할 수 있습니다.

<img width="195" height="95" alt="image" src="https://github.com/user-attachments/assets/f0bc2385-30d4-4486-b002-a3ff25928802" />

"Docker"를 선택하면, [chat.py](./application/chat.py)와 같이 http://localhost:8080/invocations 로 요청을 보내서 응답을 확인합니다.

```python
import requests
payload = json.dumps({
    "prompt": prompt, "mcp_servers": mcp_servers, "model_name": model_name,
})
headers = {"Content-Type": "application/json"}   
destination = f"http://localhost:8080/invocations"
response = requests.post(destination, headers=headers, data=payload, timeout=300)
```

문제 발생시 Docker 로그를 아래와 같이 확인합니다.

```text
sudo docker logs coreagent-langgraph-container
```

### Agent 지원 서비스 설치

Agent의 동작 테스트를 위해 S3, CloudFront, OpenSearch (Serverless), Bedrock Knowledge Base이 필요합니다. 이를 위한 상세 내용은 [cdk-agentcore](./cdk-agentcore/lib/cdk-agentcore-stack.ts)을 참조합니다. 이를 인프라로 배포할 때에는 아래와 같이 수행합니다.

먼저, cdk-agentcore로 이동하여 CDK 환경설정을 준비합니다. 만약 한번도 bootstrapping을 하지 않았다면, [AWS CDK 부트스트래핑](https://docs.aws.amazon.com/ko_kr/cdk/v2/guide/bootstrapping.html)을 참조하여 수행합니다.

- Bootstrapping

여기서 account-id를 확인하여 아래의 "123456789012"을 바꾼후 실행합니다.

```text
cdk bootstrap aws://123456789012/us-west-2
```

- CDK 배포

```text
cd cdk-agentcore && npm install
cdk deploy --require-approval never --all
```

배포가 완료되면 아래와 같은 Output 파일에서 CdkAgentcoreStack.environmentforagentcore 을 복사하여 langgraph와 strands 폴더에 [config.json](./langgraph/config.json)로 업데이트 합니다.

<img width="945" height="132" alt="image" src="https://github.com/user-attachments/assets/ce2a5a90-2306-4048-927e-5bf698691dec" />


### 문서 동기화 하기 

Knowledge Base에서 문서를 활용하기 위해서는 S3에 문서 등록 및 동기화기 필요합니다. Streamlit에서 파일을 입력하면 자동으로 동기화가 시작되지만 S3로 파일을 직접 올리는 경우에는 아래와 같이 수행합니다. [S3 Console](https://us-west-2.console.aws.amazon.com/s3/home?region=us-west-2)에 접속하여 "storage-for-agentcore-xxxxxxxxxxxx-us-west-2"를 선택하고, 아래와 같이 docs폴더를 생성한 후에 파일을 업로드 합니다. 

<img width="400" alt="image" src="https://github.com/user-attachments/assets/482f635e-a38d-4525-b9a3-fb1c2a9089c8" />

이후 [Knowledge Bases Console](https://us-west-2.console.aws.amazon.com/bedrock/home?region=us-west-2#/knowledge-bases)에 접속하여, "agentcore"라는 Knowledge Base를 선택합니다. 이후 아래와 같이 [Sync]를 선택합니다.

<img width="1533" height="287" alt="noname" src="https://github.com/user-attachments/assets/2edd3b6b-dbce-4784-b640-139fa84cc223" />


### Streamlit에서 실행하기

여기서는 Streamlit을 이용하여 AgentCore의 동작을 테스트 할 수 있습니다. 아래와 streamlit을 실행할 수 있습니다.

```text
streamlit run application/app.py
```

실행 후에 아래와 같이 왼쪽 메뉴에서 사용할 MCP 서버를 선택하고 질문을 입력합니다.

<img width="1330" height="847" alt="image" src="https://github.com/user-attachments/assets/50cda7f5-3cd2-4a21-8c36-c0d8272fad2a" />



## Reference 

[Invoke streaming agents](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html)

[Get started with the Amazon Bedrock AgentCore Runtime starter toolkit](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-getting-started-toolkit.html)

[Amazon Bedrock AgentCore - Developer Guide](https://docs.aws.amazon.com/pdfs/bedrock-agentcore/latest/devguide/bedrock-agentcore-dg.pdf)

[BedrockAgentCoreControlPlaneFrontingLayer](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore-control.html)

[get_agent_runtime](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore-control/client/get_agent_runtime.html)

