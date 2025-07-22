# AgentCore Gateway

## 정의 

AgentCore에서 Gateway란 AI agent가 도구(tools)들을 발견하고 상호작용할 수 있도록 제공하는 표준화된 방식입니다.  Gateway는 AI 에이전트가 다양한 도구들과 효율적으로 상호작용할 수 있도록 돕는 중요한 인프라 구성요소라고 할 수 있습니다.

- Gateway는 MCP(Master Control Program) 서버처럼 작동하여 에이전트가 도구들과 상호작용할 수 있는 단일 접근점을 제공합니다
- 하나의 Gateway는 여러 개의 target을 가질 수 있으며, 각 target은 서로 다른 도구나 도구 세트를 나타냅니다

### Gateway Target

Target 은 Gateway가 에이전트에게 도구로 제공할 API나 Lambda 함수를 정의합니다. 다음과 같은 형태로 정의될 수 있습니다:
- Lambda 함수
- OpenAPI 명세
- Smithy 모델
- 기타 도구 정의

  
### 서비스 할당량
- 계정당 최대 100개의 gateway 생성 가능 (조정 가능)
- Gateway당 최대 10개의 target 설정 가능 (조정 가능)
- Target당 최대 200개의 도구 설정 가능 (조정 가능)

### 관리 기능: Gateway는 다음과 같은 주요 관리 작업을 지원합니다:

- CreateGateway: 새로운 gateway 생성
- UpdateGateway: 기존 gateway 업데이트
- DeleteGateway: gateway 삭제
- GetGateway: gateway 정보 조회
- ListGateways: 모든 gateway 목록 조회
- Gateway 타겟 관련 작업(생성, 업데이트, 삭제, 조회, 목록 확인)

## 구현하기

아래와 같이 [bedrock-agentcore-control](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore-control.html) 서비스에 대한 client를 준비합니다.

```python
cp_client = boto3.client(
 'bedrock-agentcore-control',
 region_name="us-west-2",
 endpoint_url="https://bedrock-agentcore-control.us-west-2.amazonaws.com"
)
```

아래와 같이 credential을 생성할 수 있습니다.

```python
response = cp_client.create_api_key_credential_provider(
    name='tavilyapikey-agentcore',
    apiKey='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'
)
print(response)
```

생성된 credential은 아래와 같이 확인할 수 있습니다.

```python
response = cp_client.list_api_key_credential_providers()
print(response)
```

이때의 응답은 아래와 같습니다.

```python
{
   "credentialProviders":[
      {
         "name":"tavilyapikey-agentcore",
         "credentialProviderArn":"arn:aws:bedrock-agentcore:us-west-2:262976740991:token-vault/default/apikeycredentialprovider/tavilyapikey-agentcore",
         "createdTime":datetime.datetime(2025,7,22,16,28,49,295000,"tzinfo=tzlocal())",
         "lastUpdatedTime":datetime.datetime(2025,7,22,16,28,49,295000,"tzinfo=tzlocal())"
      }
   ]
}
```

## Reference

[boto3 - create_gateway_target](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore-control/client/create_gateway_target.html)

[boto3 - list_api_key_credential_providers](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore-control/client/list_api_key_credential_providers.html)


