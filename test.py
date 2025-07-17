import boto3
import json

input_text = "Hello, how can you assist me today?"

client = boto3.client(
    service_name='bedrock-agentcore', 
    region_name='us-west-2'
)

agent_core_client = boto3.client('bedrock-agentcore')
  
payload = json.dumps({"prompt": input_text}).encode()

agent_arn="arn:aws:bedrock-agentcore:us-west-2:262976740991:runtime/langgraph_agent-oGYQf1DKTm"
  
# Invoke the agent
response = agent_core_client.invoke_agent_runtime(
    agentRuntimeArn=agent_arn,
    payload=payload
)
print(f"response: {response}")  

# Process and print the response
if "text/event-stream" in response.get("contentType", ""):
  
    # Handle streaming response
    content = []
    for line in response["response"].iter_lines(chunk_size=10):
        if line:
            line = line.decode("utf-8")
            if line.startswith("data: "):
                line = line[6:]
                print(line)
                content.append(line)
    print("\nComplete response:", "\n".join(content))

elif response.get("contentType") == "application/json":
    # Handle standard JSON response
    content = []
    for chunk in response.get("response", []):
        content.append(chunk.decode('utf-8'))
    print(json.loads(''.join(content)))
  
else:
    # Print raw response for other content types
    print(response)


