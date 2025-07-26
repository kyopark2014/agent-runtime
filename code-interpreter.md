# Code Interpreter

AgentCore의 Code Interpreter는 서버리스 환경에서 안전하게 코드를 실행할 수 있도록 도와줍니다. 여기에서는 AgentCore SDK 또는 boto3를 이용하는 방법에 대해 설명합니다. 

## Coder Interpreter 구현 (AgentCore SDK)

AgentCore의 code interpreter를 이용한 Code 실행에 대해 설명합니다. 상세한 코드는 [code_interpreter.py](./code_interpreter.py)을 참조합니다.

여기에서는 [data.csv](./contents/data.csv)에 대해 분석을 수행합니다.

<img width="470" height="618" alt="image" src="https://github.com/user-attachments/assets/a75d0a19-16df-4854-9445-82e00bbd9e35" />


아래와 같이 code를 실행하는 execute_python을 tool로 생성합니다.

```python
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter

code_client = CodeInterpreter('us-west-2')
code_client.start(session_timeout_seconds=1200)

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
from strands_tools import file_read

model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0"
model= BedrockModel(model_id=model_id)

agent=Agent(
    model=model,
        tools=[execute_python, file_read],
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
python code_interpreter.py
```

이때의 결과는 아래와 같습니다.

```python
'contents/data.csv' 파일의 탐색적 데이터 분석을 수행한 결과를 다음과 같이 정리했습니다. 파일에 접근 제한이 있어 파일 미리보기에서 추출한 데이터 샘플(30개 행)을 기반으로 분석했습니다.

## 1. 데이터셋 개요
- **규모**: 30개 행, 4개 컬럼
- **컬럼**: Name, Preferred_City, Preferred_Animal, Preferred_Thing
- **데이터 타입**: 모든 컬럼은 문자열(object) 타입
- **결측치**: 없음 (모든 필드가 채워짐)

## 2. 데이터 분포 분석

### 선호 도시 분포
- **가장 빈번한 도시**: London (3회, 10%)
- **중간 빈도 도시**: Buenos Aires, Paris, Zurich, Naples (각 2회, 6.7%)
- **희소 도시**: 19개 도시가 각각 1회만 등장 (전체의 63.3%)

### 선호 동물 분포
- **동일 빈도 동물**: Elephant, Zebra, Chicken, Goat, Shark, Panda, Duck (각 2회, 6.7%)
- **희소 동물**: 16개 동물이 각각 1회만 등장 (전체의 53.3%)
- **이 결과는 동물 선호도가 매우 고르게 분산되어 있음을 보여줌**

### 선호 물건 분포
- **동일 빈도 물건**: Sofa, Ball, Hat, Picture, Dress, Bracelet, Wallet (각 2회, 6.7%)
- **희소 물건**: 16개 물건이 각각 1회만 등장 (전체의 53.3%)
- **물건 선호도 역시 매우 고르게 분산됨**

## 3. 이상치 및 특이점 분석

### 강한 상관관계를 보이는 조합
- **도시-동물 조합**: Amsterdam-Cat, Cape Town-Turkey, Copenhagen-Snake 등은 1:1 매핑 관계를 보임
- **도시-물건 조합**: Atlanta-Chair, Beijing-Phone, Berlin-Pillow 등도 완벽한 상관관계를 보임
- **이는 각 도시마다 고유한 동물과 물건 선호도가 존재함을 의미**

### 독특한 선호 조합 식별
- 전체 데이터의 20%가 독특한 선호 조합을 보임:
  * Michael Clark (Naples, Shark, Coat)
  * Joshua Martin (London, Hawk, Earrings)
  * Donald Taylor (Paris, Guinea Pig, Computer)
  * Patricia Sanchez (Buenos Aires, Frog, Painting)
  * Lisa Rodriguez (London, Deer, Picture)
  * Richard Scott (Zurich, Panda, Ball)

## 4. 성씨별 선호도 패턴 분석

- **Wright 가족**: 3명 모두 다른 도시(Buenos Aires, Los Angeles, Berlin), 동물(Goat, Chicken, Shark), 물건(Wallet, Dress, Pillow) 선호
- **Green 가족**: 3명 모두 다른 도시(Naples, Geneva, Phoenix), 동물(Bee, Panda, Lion), 물건(Shirt, Ball, Bag) 선호
- **Allen 가족**: 2명 모두 다른 도시(Atlanta, Zurich)와 다른 선호도 패턴 보임
- **가족 내에서도 선호도 패턴이 매우 다양하여 유전적/환경적 요인에 의한 가족 유사성이 낮음을 시사**

## 5. 전반적인 데이터 특성

1. **희소성(Sparsity)**: 대부분의 범주가 1-2회만 출현하는 희소 데이터 특성을 보임
2. **고른 분포**: 선호도가 매우 고르게 분산되어 있어 뚜렷한 추세나 집중 현상이 적음
3. **높은 다양성**: 30명의 데이터에서 24개 도시, 23개 동물, 23개 물건이 등장하여 선호도의 다양성이 매우 높음
4. **낮은 패턴성**: 성씨나 이름 간의 뚜렷한 선호도 패턴이 관찰되지 않음

## 6. 결론

분석 결과, 이 데이터셋은 매우 다양하고 고르게 분산된 선호도를 보이며, 특별한 패턴이나 집중 현상은 관찰되지 않았습니다. 각 개인은 매우 고유한 선호도 조합을 가지고 있으며, 같은 성씨를 가진 사람들 사이에서도 선호도의 유사성은 낮았습니다. 전체 데이터의 20%가 독특한 선호 조합을 보였으며, 이는 데이터의 다양성과 개인 선호의 고유성을 강조합니다.%
```

## MCP로 활용하기 (Boto3)

### Built-in and Custom Code Interpreter

AgentCore에서는 ID가 "aws.codeinterpreter.v1"인 built-in code interpreter를 제공하고 있습니다. 이 code interpreter는 AgentCore가 설치된 리전에 기본 설치가 되어 있어서 쉽게 사용할 수 있으며, 제한된 option으로 설정되어 있습니다. 

Custom code interpreter를 생성하면, network setting으로 sandbox와 public을 설정할 수 있으며, execution role을 정의하여 사용하는 목적에 맞게 권한을 설정할 수 있습니다. 아래는 boto3로 code interpreter를 생성하는 예제입니다. executionRoleArn을 통해 사용하는 목적에 맞게 권한을 설정할 수 있습니다.

```python
import boto3
# Initialize the boto3 client
client = boto3.client(
    'bedrock-agentcore-control',
    region_name="us-west-2",
    endpoint_url="https://bedrock-agentcore-control.us-west-2.amazonaws.com"
)
# Create a Code Interpreter
response = client.create_code_interpreter(
    name="myTestSandbox1",
    description="Test code sandbox for development",
    executionRoleArn="arn:aws:iam::123456789012:role/my-execution-role",
    networkConfiguration={
        "networkMode": "PUBLIC"
    }
)
# Print the Code Interpreter ID
code_interpreter_id = response["codeInterpreterId"]
print(f"Code Interpreter ID: {code_interpreter_id}")
```

아래는 code interpreter의 execution role에 대한 trust policy 입니다.

```java
 {
   "Version":"2012-10-17",
   "Statement":[
      {
         "Effect":"Allow",
         "Principal":{
            "Service":"bedrock-agentcore.amazonaws.com"
         },
         "Action":"sts:AssumeRole"
      }
   ]
}
```

아래는 code interpreter동작에 필요한 기본 권한입니다.

```java
{
   "Version":"2012-10-17",
   "Statement":[
      {
         "Effect":"Allow",
         "Action":[
            "bedrock-agentcore:CreateCodeInterpreter",
            "bedrock-agentcore:StartCodeInterpreterSession",
            "bedrock-agentcore:InvokeCodeInterpreter",
            "bedrock-agentcore:StopCodeInterpreterSession",
            "bedrock-agentcore:DeleteCodeInterpreter",
            "bedrock-agentcore:ListCodeInterpreters",
            "bedrock-agentcore:GetCodeInterpreter",
            "bedrock-agentcore:GetCodeInterpreterSession",
            "bedrock-agentcore:ListCodeInterpreterSessions"
         ],
         "Resource":"arn:aws:bedrock-agentcore:*"
      }
   ]
}
```

### Boto3 APIs

[start_code_interpreter_session](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore/client/start_code_interpreter_session.html)의 결과는 아래와 같습니다. 

```java
{
   "codeInterpreterIdentifier":"aws.codeinterpreter.v1",
   "sessionId":"01K12NP7J6E90BXX19AGA4S017",
   "createdAt":datetime.datetime(2025,7,26,6,10,56,149252,"tzinfo=tzutc())"
}
```

[list_code_interpreter_sessions](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore/client/list_code_interpreter_sessions.html)을 이용하여 현재 READY인 세션을 확인합니다.

```python
response = client.list_code_interpreter_sessions(
    codeInterpreterIdentifier='aws.codeinterpreter.v1',
    maxResults=5,
    status='READY'
)
items = response['items']
```

이에 대한 결과는 아래와 같습니다.

```java
{
   "items":[
      {
         "codeInterpreterIdentifier":"aws.codeinterpreter.v1",
         "sessionId":"01K12NP7J6E90BXX19AGA4S017",
         "name":"my-code-session",
         "status":"READY",
         "createdAt":datetime.datetime(2025,7,26,6,10,56,149252,"tzinfo=tzutc())",
         "lastUpdatedAt":datetime.datetime(2025,7,26,6,10,56,149252,"tzinfo=tzutc())"
      }
   ]
}
```

[get_code_interpreter_session](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore/client/get_code_interpreter_session.html)은 세션의 상태를 확인합니다.

```java
{
   "codeInterpreterIdentifier":"aws.codeinterpreter.v1",
   "sessionId":"01K12Q3BYGCVWZBHMWAQNRR893",
   "name":"my-code-session",
   "createdAt":datetime.datetime(2025,7,26,6,35,35,220159,"tzinfo=tzutc())",
   "sessionTimeoutSeconds":900,
   "status":"READY"
}
```

### Code Interpreter의 결과를 전달하기 

[Amazon Bedrock AgentCore - Developer Guide](https://docs.aws.amazon.com/pdfs/bedrock-agentcore/latest/devguide/bedrock-agentcore-dg.pdf)와 같이 code interpreter가 생성한 결과를 S3로 옮길 수 있습니다. 이때 execution role은 S3에 대한 권한을 가지고 있어야 합니다.

```python
print(f"Uploading generated artifact to S3")
command_to_execute = f"aws s3 cp generated_data.csv s3://{S3_BUCKET_NAME}/output_artifacts/"
response = bedrock_agentcore_client.invoke_code_interpreter(
    codeInterpreterIdentifier=code_interpreter_id,
    sessionId=session_id,
    name="executeCommand",
    arguments={
        "command": command_to_execute
    }
)
for event in response["stream"]:
    print(json.dumps(event["result"], default=str, indent=2))
```

### 상세 구현

[mcp_server_agentcore_coder.py](./langgraph/mcp_server_agentcore_coder.py)와 같이 MCP 서버를 설정하고, [mcp_agentcore_coder.py](./langgraph/mcp_agentcore_coder.py)와 같이 구현합니다. 

아래와 같이 bedrock-agentcore를 이용해 AgentCore의 code interpreter를 생성할 수 있습니다.

```python
client = boto3.client(
    "bedrock-agentcore", 
    region_name=aws_region,
    endpoint_url=f"https://bedrock-agentcore.{aws_region}.amazonaws.com"
)

def get_code_interpreter_sessionId():
    session_id = None
    response = client.list_code_interpreter_sessions(
        codeInterpreterIdentifier='aws.codeinterpreter.v1',
        maxResults=5,
        status='READY'
    )
    items = response['items']

    if items is not None:
        for item in items:
            session_id = item['sessionId']
            break
    
    if session_id is None:  # still no sessionId
        logger.info("No ready sessions found")
        response = client.start_code_interpreter_session(
            codeInterpreterIdentifier='aws.codeinterpreter.v1',
            name="agentcore-code-session",
            sessionTimeoutSeconds=900
        )
        logger.info(f"response of start_code_interpreter_session: {response}")
        session_id = response['sessionId']

    return session_id
```

Code interpreter의 session 정보를 가지고 아래와 같이 LLM이 생성한 code를 실행할 수 있습니다.

```java
execute_response = client.invoke_code_interpreter(
  codeInterpreterIdentifier="aws.codeinterpreter.v1",
  sessionId=sessionId,
  name="executeCode",
  arguments={
      "language": "python",
      "code": code
  }
)
logger.info(f"execute_response: {execute_response}")

result_text = ""
for event in execute_response['stream']:
  if 'result' in event:
      result = event['result']
      if 'content' in result:
          for content_item in result['content']:
              if content_item['type'] == 'text':
                  result_text = content_item['text']
                  logger.info(f"result: {result_text}")
```

"'contents/stock_prices.csv'의 내용을 분석해서 insight를 열거해보세요."와 같이 질문하면 아래와 같은 분석 결과를 얻을 수 있습니다.

<img width="724" height="782" alt="image" src="https://github.com/user-attachments/assets/cd0a210c-97c9-4439-8168-7a2ca62bcce7" />



## Reference

[Advanced Data Analysis using Amazon AgentCore Bedrock Code Interpreter- Tutorial(Strands)](https://github.com/awslabs/amazon-bedrock-agentcore-samples/blob/main/01-tutorials/05-AgentCore-tools/01-Agent-Core-code-interpreter/03-advanced-data-analysis-with-agent-using-code-interpreter/strands-agent-advanced-data-analysis-code-interpreter.ipynb)

[Amazon AgentCore Bedrock Code Interpreter - Getting Started Tutorial](https://github.com/awslabs/amazon-bedrock-agentcore-samples/tree/main/01-tutorials/05-AgentCore-tools/01-Agent-Core-code-interpreter/01-file-operations-using-code-interpreter)

[Agent-Based Code Execution using Amazon AgentCore Bedrock Code Interpreter- Tutorial(Strands)](https://github.com/awslabs/amazon-bedrock-agentcore-samples/blob/main/01-tutorials/05-AgentCore-tools/01-Agent-Core-code-interpreter/02-code-execution-with-agent-using-code-interpreter/strands-agent-code-execution-code-interpreter.ipynb)

