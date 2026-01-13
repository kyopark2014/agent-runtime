# 구현 내용

## Server

LangGraph Workflow를 아래와 같이 구현합니다. 아래는 기본적인 ReAct를 구현한 LangGraph workflow 입니다.

```python
from langgraph.prebuilt import ToolNode
from langgraph.graph import START, END, StateGraph

def buildChatAgent(tools):
    tool_node = ToolNode(tools)

    workflow = StateGraph(State)

    workflow.add_node("agent", call_model)
    workflow.add_node("action", tool_node)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "continue": "action",
            "end": END,
        },
    )
    workflow.add_edge("action", "agent")

    return workflow.compile() 

    return workflow.compile() 
```

Dockerfile을 아래와 같이 생성합니다.

```text
FROM --platform=linux/arm64 python:3.13-slim

WORKDIR /app

RUN pip install boto3 botocore --upgrade
RUN pip install langchain_aws langchain langchain_community langchain_experimental langgraph
RUN pip install mcp langchain-mcp-adapters
RUN pip install bedrock-agentcore bedrock-agentcore-starter-toolkit uv

# OpenTelemetry
RUN pip install aws-opentelemetry-distro>=0.10.0

COPY . .

# Add the current directory to Python path
ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["uv", "run", "opentelemetry-instrument", "uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]
```


AgentCore에서 사용할 Agent를 agent.py로 구현합니다.

```python
from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

@app.entrypoint
async def agent_langgraph(payload):
    query = payload.get("prompt")
    mcp_servers = payload.get("mcp_servers", [])
    user_id = payload.get("user_id")

    mcp_json = mcp_config.load_selected_config(mcp_servers)
    server_params = langgraph_agent.load_multiple_mcp_server_parameters(mcp_json)

    client = MultiServerMCPClient(server_params)
    tools = await client.get_tools()
    
    tool_list = [tool.name for tool in tools]
    
    app = langgraph_agent.buildChatAgent(tools)
    config = {
        "recursion_limit": 50,
        "configurable": {"thread_id": user_id},
        "tools": tools,
        "system_prompt": None
    }
    
    inputs = {
        "messages": [HumanMessage(content=query)]
    }
            
    value = final_output = None
    async for output in app.astream(inputs, config):
        for key, value in output.items():
            if key == "messages" or key == "agent":
                if isinstance(value, dict) and "messages" in value:
                    final_output = value
                elif isinstance(value, list):
                    final_output = {"messages": value, "image_url": []}
                else:
                    final_output = {"messages": [value], "image_url": []}

            if "messages" in value:
                for message in value["messages"]:
                    if isinstance(message, AIMessage):
                        yield({'data': message.content})

                        tool_calls = message.tool_calls
                        if tool_calls:
                            for tool_call in tool_calls:
                                tool_name = tool_call["name"]
                                tool_content = tool_call["args"]
                                toolUseId = tool_call["id"]
                                yield({'tool': tool_name, 'input': tool_content, 'toolUseId': toolUseId})

                    elif isinstance(message, ToolMessage):
                        toolResult = message.content
                        toolUseId = message.tool_call_id

                        yield({'toolResult': toolResult, 'toolUseId': toolUseId})
    
    yield({'result': final_output})

if __name__ == "__main__":
    app.run()
```

Agent를 배포합니다.

```python
client = boto3.client('bedrock-agentcore-control', region_name=aws_region)
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
print(f"response of create agent runtime: {response}")

agentRuntimeArn = response['agentRuntimeArn']
```


## Client

아래와 같이 runtime id와 session_id를 이용해 client에서 서버로 요청을 보내고 결과를 stream으로 수신합니다.

```python
prompt = "보일러 에러 코드?"
mcp_servers = ["kb-retriever"]
user_id = "user01"
runtime_session_id = str(uuid.uuid4())

payload = json.dumps({
    "prompt": prompt,
    "mcp_servers": mcp_servers,
    "user_id": user_id
})

agent_core_client = boto3.client('bedrock-agentcore', region_name=bedrock_region)
response = agent_core_client.invoke_agent_runtime(
    agentRuntimeArn=agent_runtime_arn,
    runtimeSessionId=runtime_session_id,
    payload=payload,
    qualifier="DEFAULT" # DEFAULT or LATEST
)

print(f"\n=== show stream response ===")
if "text/event-stream" in response.get("contentType", ""):
    for line in response["response"].iter_lines(chunk_size=10):
        line = line.decode("utf-8")
        if line:
            print(f"-> {line}")
```
