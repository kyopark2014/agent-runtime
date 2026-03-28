# Strands Agent Runtime 

## 배포를 위한 Agent.py의 준비

Bedrock AgentCore를 설치하고 아래와 같이 BedrockAgentCoreApp를 app으로 설정합니다. 이때 entrypoint에는 agent 실행에 필요한 함수를 아래와 같이 정의할 수 있습니다.

```python
import strands_agent
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

@app.entrypoint
async def agentcore_strands(payload):
    query = payload.get("prompt")
    mcp_servers = payload.get("mcp_servers", [])
    model_name = payload.get("model_name")
    user_id = payload.get("user_id")

    global tool_list
    tool_list = []
    
    # initiate agent
    await strands_agent.initiate_agent(
        system_prompt=None, 
        strands_tools=strands_agent.strands_tools, 
        mcp_servers=mcp_servers
    )

    with strands_agent.mcp_manager.get_active_clients(mcp_servers) as _:
        agent_stream = strands_agent.agent.stream_async(query)

        final_output = ""
        async for event in agent_stream:
            text = ""            
            if "data" in event:
                text = event["data"]
                logger.info(f"[data] {text}")
                yield({'data': text})

            elif "result" in event:
                final = event["result"]                
                message = final.message
                if message:
                    content = message.get("content", [])
                    text = content[0].get("text", "")
                    logger.info(f"[result] {text}")
                
                    final_output = {"messages": text, "image_url": []}

    yield({'result': final_output})

if __name__ == "__main__":
    app.run()
```



## Dockerfile

[Dockerfile](./Dockerfile)와 같이 필요한 패키지를 설치하고 Runtime을 동작시킵니다.

```dockerfile
FROM --platform=linux/arm64 python:3.13-slim

WORKDIR /app

# Core dependencies
RUN pip install boto3 --upgrade
RUN pip install mcp
RUN pip install strands-agents strands-agents-tools
RUN pip install bedrock-agentcore uv

# OpenTelemetry
RUN pip install aws-opentelemetry-distro>=0.10.0

COPY . .

# Add the current directory to Python path
ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["uv", "run", "opentelemetry-instrument", "uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]
```

## Installer

`installer.py`는 Strands 에이전트를 **AWS Bedrock AgentCore**에 올리기 위한 통합 설치 스크립트입니다. `config.json`을 읽고, 아래 순서로 **IAM 준비 → Docker 이미지 빌드·ECR 푸시 → Agent Runtime 생성/갱신**을 한 번에 수행합니다.

### 배포(실행) 순서

`main()`에서 다음 3단계가 **순차 실행**되며, 한 단계라도 실패하면 이후 단계는 실행되지 않고 종료(`sys.exit(1)`)합니다.

| 순서 | 단계 이름 | 진입 함수 | 설명 |
|------|-----------|-----------|------|
| 1 | IAM 정책·역할 생성 | `create_iam_policies()` | Bedrock AgentCore용 IAM 정책·역할을 만들고 `agent_runtime_role`을 `config.json`에 저장 |
| 2 | Docker 빌드 및 ECR 푸시 | `push_to_ecr()` | 현재 디렉터리 기준으로 이미지를 빌드해 ECR에 푸시하고, 태그·저장소명을 `config.json`에 반영 |
| 3 | Agent Runtime 생성/업데이트 | `create_agent_runtime()` | ECR의 최신 이미지로 AgentCore Runtime을 **신규 생성**하거나 **기존 런타임 갱신**하고 `agent_runtime_arn` 저장 |

### 설정 로드·저장

| 함수 | 역할 |
|------|------|
| `load_config()` | `config.json` 로드. 파일이 없거나 파싱 실패 시 리전·계정 ID 등을 채워 새로 생성할 수 있음 |
| `update_config(key, value)` | `config.json`에 키-값 갱신 (예: `agent_runtime_role`, `latest_image_tag`, `ecr_repository`, `agent_runtime_arn`) |

### 1단계: IAM (`create_iam_policies`)

| 함수 | 역할 |
|------|------|
| `create_bedrock_agentcore_policy(config)` | `AmazonBedrockAgentCoreRuntimePolicyFor{projectName}` 정책 생성 또는 버전 갱신(Bedrock AgentCore, Secrets Manager, Cognito, ECR, Logs, CloudWatch/X-Ray, S3/Bedrock, EC2 등 권한) |
| `create_trust_policy_for_bedrock(config)` | `bedrock-agentcore.amazonaws.com` 및 계정 root가 역할을 맡을 수 있는 trust policy JSON 생성 |
| `attach_policy_to_role(role_name, policy_arn)` | 생성한 정책을 역할에 연결 |
| `create_bedrock_agentcore_role(config)` | `AmazonBedrockAgentCoreRuntimeRoleFor{projectName}` 역할 생성 또는 기존 역할의 trust policy 갱신 후 정책 연결 |
| `create_iam_policies()` | 위 순서로 정책 → 역할 → `update_config('agent_runtime_role', role_arn)` 실행 |

### 2단계: Docker·ECR (`push_to_ecr`)

| 함수 | 역할 |
|------|------|
| `check_aws_cli()` | `aws` CLI 설치 여부 확인 |
| `check_aws_credentials()` | `sts.get_caller_identity()`로 자격 증명 확인 |
| `ensure_ecr_repository(ecr_client, repository_name, region)` | ECR 저장소 없으면 생성 (`{projectName}_{현재폴더명}`) |
| `docker_login(account_id, region)` | ECR 토큰으로 `docker login` |
| `run_docker_command(command, description)` | `subprocess`로 docker 명령 실행 및 실패 처리 |
| `push_to_ecr()` | 타임스탬프 태그로 `docker build` → `docker tag` → `docker push` 후 `latest_image_tag`, `ecr_repository` 저장 |

**참고:** ECR 저장소 이름은 `{projectName}_{현재 작업 디렉터리 폴더명}`이며, 스크립트는 **실행 시 `cwd`가 `strands` 등 해당 런타임 디렉터리**라고 가정합니다.

### 3단계: Agent Runtime (`create_agent_runtime`)

| 함수 | 역할 |
|------|------|
| `get_latest_image_tag(config)` | ECR에서 해당 저장소의 **가장 최근 푸시된** 이미지 태그 조회 |
| `create_agent_runtime_func(config, repository_name, image_tag)` | `bedrock-agentcore-control` 클라이언트로 `create_agent_runtime` 호출. 런타임 이름은 `repository_name`의 `-`를 `_`로 바꾼 값 |
| `update_agent_runtime_func(config, repository_name, agent_runtime_id, image_tag)` | 기존 런타임에 새 컨테이너 URI·역할·네트워크( PUBLIC )·HTTP 프로토콜로 갱신 |
| `update_agentcore_json(agent_runtime_arn)` | `agent_runtime_arn`을 `config.json`에 기록 |
| `create_agent_runtime()` | `list_agent_runtimes`로 동일 이름 런타임 존재 여부 확인 후 **없으면 생성**, **있으면 업데이트** |

### 실행 방법

```bash
python installer.py
```

사전에 AWS 자격 증명이 설정되어 있고, Docker가 동작하며, IAM·ECR·Bedrock AgentCore API에 필요한 권한이 있어야 합니다.

### 인프라의 삭제

더이상 설치한 인프라가 불필요한 경우에 아래와 같이 삭제합니다.

```bash
python uninstaller.py
```
