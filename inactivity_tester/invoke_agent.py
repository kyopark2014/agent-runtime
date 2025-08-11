import boto3
import json
import utils
import uuid

region_name = utils.bedrock_region
accountId = utils.accountId
projectName = utils.projectName
agentRuntimeArn = utils.agent_runtime_arn
print(f"agentRuntimeArn: {agentRuntimeArn}")

payload = json.dumps({
    "prompt": "안녕",
    "model_name": "Claude 3.7 Sonnet",
})

runtime_session_id = str(uuid.uuid4())
print(f"runtime_session_id: {runtime_session_id}")

agent_core_client = boto3.client('bedrock-agentcore', region_name=region_name)
try:
    response = agent_core_client.invoke_agent_runtime(
        agentRuntimeArn=agentRuntimeArn,
        runtimeSessionId=runtime_session_id,
        payload=payload,
        qualifier="DEFAULT"
    )

    # response_body = response['response'].read()
    # response_data = json.loads(response_body)
    # print("Agent Response:", response_data)

    # stream response
    if "text/event-stream" in response.get("contentType", ""):
        content = []
        for line in response["response"].iter_lines(chunk_size=10):
            if line: 
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]

                    try:
                        stream = json.loads(line)

                        if 'data' in stream:
                            text = stream['data']
                            print(f"[data] {text}")
                        elif 'result' in stream:
                            result = stream['result']
                            print(f"[result] {result}")
                        else:
                            print(f"[other] {stream}")
                    except json.JSONDecodeError:
                        pass

        print("\nComplete response:", "\n".join(content))

    elif response.get("contentType") == "application/json":
        content = []
        for chunk in response.get("response", []):
            content.append(chunk.decode('utf-8'))
            print(json.loads(''.join(content)))
    else:
        # Print raw response
        print(response)

except Exception as e:
    print(f"Error: {e}")

