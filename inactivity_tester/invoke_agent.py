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
                    # print(f"line: {line}")
                    if isinstance(line, str):
                        try:
                            # Try JSON parsing first
                            json_line = json.loads(line)
                            print(f"JSON parsed: {type(json_line)}")
                            # Check if the result is actually a dictionary
                            if isinstance(json_line, dict) and "message" in json_line:
                                message = json_line["message"]
                                print(f"Message: {type(message)}")
                                if "content" in message:
                                    content_list = message["content"]
                                    print(f"Content list: {type(content_list)}, value: {content_list}")
                                    if isinstance(content_list, list) and len(content_list) > 0:
                                        print(f"text: {content_list[0]['text']}")
                                        content.append(content_list[0]['text'])
                            else:
                                # If JSON parsing returned a string, it's likely a Python object string
                                raise json.JSONDecodeError("Not a valid JSON object", line, 0)
                        except json.JSONDecodeError:
                            # If JSON parsing fails, try ast.literal_eval for Python object strings
                            try:
                                import ast
                                parsed_line = ast.literal_eval(line)
                                print(f"AST parsed: {type(parsed_line)}")
                                if isinstance(parsed_line, dict) and "result" in parsed_line:
                                    result = parsed_line["result"]
                                    print(f"Result: {type(result)}")
                                    if hasattr(result, 'message') and result.message:
                                        message = result.message
                                        print(f"Result message: {type(message)}")
                                        if "content" in message:
                                            content_list = message["content"]
                                            print(f"Result content: {type(content_list)}, value: {content_list}")
                                            if isinstance(content_list, list) and len(content_list) > 0:
                                                print(f"text: {content_list[0]['text']}")
                                                content.append(content_list[0]['text'])
                            except (ValueError, SyntaxError, AttributeError) as e:
                                print(f"AST parsing error: {e}")
                                # Try to extract text using string manipulation for complex objects
                                try:
                                    if "'text': '" in line:
                                        start_idx = line.find("'text': '") + 9
                                        end_idx = line.find("'", start_idx)
                                        if start_idx > 8 and end_idx > start_idx:
                                            extracted_text = line[start_idx:end_idx]
                                            print(f"Extracted text: {extracted_text}")
                                            content.append(extracted_text)
                                except Exception as extract_error:
                                    print(f"Text extraction error: {extract_error}")
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

