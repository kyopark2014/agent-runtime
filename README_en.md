# AgentCore for Agent Production

This document explains how to deploy and safely use Agents created with LangGraph and Strands using AgentCore.

## Key Implementations

### Overall Architecture

The overall architecture is as follows. Here, we deploy Strands and LangGraph agents that support MCP using [AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html) and use them through a streamlit application. Developers create docker images using the appropriate [Dockerfile](./langgraph/Dockerfile) for each agent and upload them to ECR. Then, they deploy them as AgentCore runtimes using [create_agent_runtime.py](./langgraph/create_agent_runtime.py) from [bedrock-agentcore-control](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/Welcome.html). Once this process is complete, LangGraph and Strands agents can be utilized in streamlit on compute resources like EC2. When calling the AgentCore runtime from the application, [invoke_agent_runtime](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore/client/invoke_agent_runtime.html) from [bedrock-agentcore](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore.html) is used. At this time, the [agentRuntimeArn](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/API_Agent.html) that can be verified when creating each agent is used. Agents can utilize services such as RAG, AWS Document, and Tavily search using [MCP](https://modelcontextprotocol.io/introduction). Here, Lambda is used for RAG. Knowledge Base is used for data store management, and OpenSearch is used as the vector store. AWS CDK is used to deploy resources needed by the agent such as S3, CloudFront, OpenSearch, and Lambda.

<img width="862" height="428" alt="image" src="https://github.com/user-attachments/assets/e01e4c99-869d-435c-a573-9468311ada73" />

AgentCore's runtime uses Docker for deployment. As of July 2025, it supports arm64 and docker images less than 1GB.

### Introduction to AgentCore

- AgentCore Runtime: A serverless runtime that can deploy AI agents and tools and automatically scale according to traffic. It supports various open-source frameworks including LangGraph, CrewAI, and Strands Agents. It supports fast cold start, session isolation, built-in identity verification, and multimodal payload. This enables safe and rapid deployment.
- AgentCore Memory: Allows agents to conveniently manage short-term and long-term memory.
- AgentCore Code Interpreter: Enables safe code execution in a separate sandbox environment.
- AgentCore Browser: Allows fast and safe execution of tasks such as web crawling using a browser.
- AgentCore Gateway: Makes it easy to use services such as APIs and Lambda as Tools.
- AgentCore Observability: Allows developers to trace, debug, and monitor agent behavior in production environments.

### Deploying to AgentCore

Build images for LangGraph and strands agents using [Dockerfile](./langgraph/Dockerfile) and deploy them to ECR. You can easily deploy using [push-to-ecr.sh](./langgraph/push-to-ecr.sh).

```text
./push-to-ecr.sh
```

Then, deploy to AgentCore as a runtime using [create_agent_runtime.py](./langgraph/create_agent_runtime.py) as follows:

```text
python create_agent_runtime.py
```

In [create_agent_runtime.py](./langgraph/create_agent_runtime.py), it checks if this is the first deployment to AgentCore and creates a runtime as follows:

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

To check if a runtime already exists, use [list_agent_runtimes](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore-control/client/list_agent_runtimes.html) as follows:

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

If a runtime already exists, update it using [update_agent_runtime](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore-control/client/update_agent_runtime.html) as follows:

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

## Deployment and Execution

### Verifying Operation Locally

You can verify docker operation in a local environment using [build-docker.sh](./langgraph/build-docker.sh) and [run-docker.sh](./langgraph/run-docker.sh).

```text
./build-docker.sh
./run-docker.sh
```

Then you can test the operation with [curl.sh](./curl.sh).

```text
./curl.sh
```

Using [curl.sh](./curl.sh), you can test locally as follows. MCP server and model information are provided along with the question.

```text
curl -X POST http://localhost:8080/invocations \
-H "Content-Type: application/json" \
-d '{"prompt": "내 s3 bucket 리스트는?", "mcp_servers": ["basic", "use_aws", "tavily-search", "filesystem", "terminal"], "model_name": "Claude 3.7 Sonnet"}'
```

You can also verify operation with code using [invoke_agent.py](./langgraph/invoke_agent.py).

```text
python invoke_agent.py
```

In [invoke_agent.py](./langgraph/invoke_agent.py), it executes using [invoke_agent_runtime](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore/client/invoke_agent_runtime.html) as follows:

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

In Streamlit, you can test the local docker by selecting "Docker" as shown below.

<img width="195" height="95" alt="image" src="https://github.com/user-attachments/assets/f0bc2385-30d4-4486-b002-a3ff25928802" />

When "Docker" is selected, it sends a request to http://localhost:8080/invocations and checks the response as in [chat.py](./application/chat.py).

```python
import requests
payload = json.dumps({
    "prompt": prompt, "mcp_servers": mcp_servers, "model_name": model_name,
})
headers = {"Content-Type": "application/json"}   
destination = f"http://localhost:8080/invocations"
response = requests.post(destination, headers=headers, data=payload, timeout=300)
```

If problems occur, check the Docker logs as follows:

```text
sudo docker logs coreagent-langgraph-container
```

### Installing Agent Support Services

S3, CloudFront, OpenSearch (Serverless), and Bedrock Knowledge Base are required for testing agent operation. For detailed information, refer to [cdk-agentcore](./cdk-agentcore/lib/cdk-agentcore-stack.ts). To deploy this as infrastructure, proceed as follows:

First, navigate to cdk-agentcore and prepare the CDK environment settings. If you have never performed bootstrapping, refer to [AWS CDK Bootstrapping](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html).

- Bootstrapping

Check your account-id and replace "123456789012" below before executing:

```text
cdk bootstrap aws://123456789012/us-west-2
```

- CDK Deployment

```text
cd cdk-agentcore && npm install
cdk deploy --require-approval never --all
```

Once deployment is complete, copy CdkAgentcoreStack.environmentforagentcore from the Output file as shown below and update [config.json](./langgraph/config.json) in the langgraph and strands folders.

<img width="945" height="132" alt="image" src="https://github.com/user-attachments/assets/ce2a5a90-2306-4048-927e-5bf698691dec" />

### Synchronizing Documents

To utilize documents in Knowledge Base, document registration and synchronization in S3 are required. When files are input in Streamlit, synchronization starts automatically, but when uploading files directly to S3, proceed as follows. Access the [S3 Console](https://us-west-2.console.aws.amazon.com/s3/home?region=us-west-2), select "storage-for-agentcore-xxxxxxxxxxxx-us-west-2", create a docs folder as shown below, and upload files.

<img width="400" alt="image" src="https://github.com/user-attachments/assets/482f635e-a38d-4525-b9a3-fb1c2a9089c8" />

Then access the [Knowledge Bases Console](https://us-west-2.console.aws.amazon.com/bedrock/home?region=us-west-2#/knowledge-bases), select the Knowledge Base named "agentcore", and select [Sync] as shown below.

<img width="1533" height="287" alt="noname" src="https://github.com/user-attachments/assets/2edd3b6b-dbce-4784-b640-139fa84cc223" />

### Running in Streamlit

Here, you can test the operation of AgentCore using Streamlit. You can run streamlit as follows:

```text
streamlit run application/app.py
```

After execution, select the MCP server to use from the left menu and enter your question as shown below.

<img width="1330" height="847" alt="image" src="https://github.com/user-attachments/assets/50cda7f5-3cd2-4a21-8c36-c0d8272fad2a" />

## Execution Results

If you select "use_aws" from the MCP server and enter "내 cloudwatch 로그 리스트는?" (What are my cloudwatch log lists?), it will check the AWS cloudwatch log list using AWS CLI and show it as follows:

<img width="724" height="732" alt="image" src="https://github.com/user-attachments/assets/58191496-eee0-4dbb-ab9a-7ddb71340e69" />

If you select "tavily search" and search for "강남역 맛집은?" (What are good restaurants near Gangnam Station?), it will search for information about Gangnam Station and show the results as follows:

<img width="723" height="662" alt="image" src="https://github.com/user-attachments/assets/cbb1241d-8f17-4894-a43c-2d578e2987e2" />

## Reference 

[Invoke streaming agents](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html)

[Get started with the Amazon Bedrock AgentCore Runtime starter toolkit](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-getting-started-toolkit.html)

[Amazon Bedrock AgentCore - Developer Guide](https://docs.aws.amazon.com/pdfs/bedrock-agentcore/latest/devguide/bedrock-agentcore-dg.pdf)

[BedrockAgentCoreControlPlaneFrontingLayer](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore-control.html)

[get_agent_runtime](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agentcore-control/client/get_agent_runtime.html)

[Amazon Bedrock AgentCore Samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)
