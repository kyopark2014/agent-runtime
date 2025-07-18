# agentcore-langgraph
It is a langgraph agent based on AgentCore.


### Local Test

아래와 같이 app.py를 실행합니다.

```text
python application/app.py
```

이후 아래와 같이 local에서 테스트 할 수 있습니다. "Hello world!"라고 입력시 현재 시간 확인후 아래와 같이 답변하고 있습니다.

```text
curl -X POST http://localhost:8080/invocations \
-H "Content-Type: application/json" \
-d '{"prompt": "Hello world!"}'
"안녕하세요! 저는 서연이에요. 현재 시각은 2025년 7월 18일 12시 37분이네요. 오늘 하루도 좋은 하루 보내고 계신가요? 궁금하신 점이나 도움이 필요한 부분이 있다면 언제든 말씀해주세요. 날씨, 주식 정보, 도서 검색 등 다양한 정보를 알려드릴 수 있어!"%
```



## Reference 

[Invoke streaming agents](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html)

[Get started with the Amazon Bedrock AgentCore Runtime starter toolkit](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-getting-started-toolkit.html)

[Amazon Bedrock AgentCore - Developer Guide](https://docs.aws.amazon.com/pdfs/bedrock-agentcore/latest/devguide/bedrock-agentcore-dg.pdf)
