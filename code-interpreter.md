# Code Interpreter

AgentCore의 Code Interpreter는 서버리스 환경에서 안전하게 코드를 실행할 수 있도록 도와줍니다. AgentCore의 Code Executor를 이용한 Code 실행에 대해 설명합니다. 상세한 코드는 [code_executor.py](./code_executor.py)을 참조합니다.

## Code Executor

여기에서는 [data.csv](./contents/data.csv)에 대해 분석을 수행합니다.

<img width="470" height="618" alt="image" src="https://github.com/user-attachments/assets/a75d0a19-16df-4854-9445-82e00bbd9e35" />


아래와 같이 code를 실행하는 execute_python을 tool로 생성합니다.

```python
from bedrock_agentcore.tools.code_interpreter_client import code_session

@tool
def execute_python(code: str, description: str = "") -> str:
    """Execute Python code in the sandbox."""

    if description:
        code = f"# {description}\n{code}"

    #Print generated Code to be executed
    print(f"\n Generated Code: {code}")

    # Call the Invoke method and execute the generated code, within the initialized code interpreter session
    response = code_client.invoke("executeCode", {
        "code": code,
        "language": "python",
        "clearContext": False
    })
    for event in response["stream"]:
        return json.dumps(event["result"])
```

이때 agent는 아래와 같이 정의합니다.

```python
import asyncio

model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0"
model= BedrockModel(model_id=model_id)

agent=Agent(
    model=model,
        tools=[execute_python],
        system_prompt=SYSTEM_PROMPT,
        callback_handler=None)

query = "파일 'contents/data.csv'를 로드하고 탐색적 데이터 분석(EDA)을 수행하세요. 분포와 이상치 값에 대해 알려주세요."

async def main():
    response_text = ""
    async for event in agent.stream_async(query):
        if "data" in event:
            # Stream text response
            chunk = event["data"]
            response_text += chunk
            print(chunk, end="")

asyncio.run(main())
```

이후 아래와 같이 실행합니다.

```text
python code_executor.py
```


## Reference

[Advanced Data Analysis using Amazon AgentCore Bedrock Code Interpreter- Tutorial(Strands)](https://github.com/awslabs/amazon-bedrock-agentcore-samples/blob/main/01-tutorials/05-AgentCore-tools/01-Agent-Core-code-interpreter/03-advanced-data-analysis-with-agent-using-code-interpreter/strands-agent-advanced-data-analysis-code-interpreter.ipynb)

[Amazon AgentCore Bedrock Code Interpreter - Getting Started Tutorial](https://github.com/awslabs/amazon-bedrock-agentcore-samples/tree/main/01-tutorials/05-AgentCore-tools/01-Agent-Core-code-interpreter/01-file-operations-using-code-interpreter)

[Agent-Based Code Execution using Amazon AgentCore Bedrock Code Interpreter- Tutorial(Strands)](https://github.com/awslabs/amazon-bedrock-agentcore-samples/blob/main/01-tutorials/05-AgentCore-tools/01-Agent-Core-code-interpreter/02-code-execution-with-agent-using-code-interpreter/strands-agent-code-execution-code-interpreter.ipynb)

