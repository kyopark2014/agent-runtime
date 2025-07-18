# agentcore-langgraph
It is a langgraph agent based on AgentCore.


bedrock-agentcore:GetAgentRuntime 퍼미션이 필요합니다.



### Local Test

#### 동작 테스트

아래와 같이 app.py를 실행합니다.

```text
python application/app.py
```

이후 아래와 같이 local에서 테스트 할 수 있습니다. "Hello world!"라고 입력시 현재 시간 확인후 아래와 같이 답변하고 있습니다.

```text
curl -X POST http://localhost:8080/invocations \
-H "Content-Type: application/json" \
-d '{"prompt": "Hello world!"}'
{"result":"안녕하세요! 저는 서연이에요 😊 \n오늘도 즐거운 하루 보내고 계신가요? 제가 도움이 필요하신 일이 있다면 말씀해주세요. \n\n날씨 정보, 주식 정보, 책 검색 등 다양한 정보를 알려드릴 수 있어요. 어떤 것이 궁금하신가요?"}
```

#### 빌드 테스트

아래와 같이 빌드를 수행합니다.

```text
cd agent && ./build-docker.sh
```

아래와 같이 Docker를 실행합니다.

```text
./run-docker.sh
```

이후 아래와 같이 실행합니다.

```text
./curl.sh
```

이때, curl.sh에는 아래와 같은 값으로 채워져 있습니다.

```text
curl -X POST http://localhost:8080/invocations \
-H "Content-Type: application/json" \
-d '{"prompt": "서울 날씨는?", "mcp_servers": ["basic", "use_aws", "tavily-search", "filesystem", "terminal"]}'
```

문제 발생시 Docker 로그를 아래와 같이 확인합니다.

```text
sudo docker logs langgraph-agent-container
```


## 실행하기

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

