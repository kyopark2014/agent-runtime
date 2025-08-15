import boto3
import json
import os
import logging
import sys
import requests
import uuid

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("agentcore_client")

def load_config():
    config = None
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "..", 'langgraph', "config.json")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    return config

config = load_config()

bedrock_region = config['region']
accountId = config['accountId']
projectName = config['projectName']

streaming_index = None
index = 0
def add_notification(containers, message):
    global index

    if index == streaming_index:
        index += 1

    if containers is not None:
        containers['notification'][index].info(message)
    index += 1

def update_streaming_result(containers, message):
    global streaming_index
    streaming_index = index 

    if containers is not None:
        containers['notification'][streaming_index].markdown(message)

def update_tool_notification(containers, tool_index, message):
    if containers is not None:
        containers['notification'][tool_index].info(message)

def load_agentcore_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    langgraph_arn_path = os.path.join(script_dir, "..", 'langgraph_stream', "agentcore.json")
    with open(langgraph_arn_path, "r", encoding="utf-8") as f:
        langgraph_data = json.load(f)
        langgraph_agent_runtime_arn = langgraph_data['agent_runtime_arn']
        logger.info(f"langgraph_agent_runtime_arn: {langgraph_agent_runtime_arn}")
    
    strands_arn_path = os.path.join(script_dir, "..", 'strands_stream', "agentcore.json")
    with open(strands_arn_path, "r", encoding="utf-8") as f:
        strands_data = json.load(f)
        strands_agent_runtime_arn = strands_data['agent_runtime_arn']
        logger.info(f"strands_agent_runtime_arn: {strands_agent_runtime_arn}")
    
    return langgraph_agent_runtime_arn, strands_agent_runtime_arn, 

langgraph_agent_runtime_arn, strands_agent_runtime_arn = load_agentcore_config()

runtime_session_id = str(uuid.uuid4())
logger.info(f"runtime_session_id: {runtime_session_id}")

tool_info_list = dict()
tool_result_list = dict()

def run_agent_in_docker(prompt, agent_type, history_mode, mcp_servers, model_name, containers):
    global index
    index = 0

    user_id = agent_type
    logger.info(f"user_id: {user_id}")

    payload = json.dumps({
        "prompt": prompt,
        "mcp_servers": mcp_servers,
        "model_name": model_name,
        "user_id": user_id,
        "history_mode": history_mode
    })

    destination = f"http://localhost:8080/invocations"

    try:
        logger.info(f"Sending request to Docker container at {destination}")
        logger.info(f"Payload: {payload}")
        
        # Set headers for SSE connection
        sse_headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
        
        # Connect using SSE client
        response = requests.post(destination, headers=sse_headers, data=payload, timeout=300, stream=True)
        
        logger.info(f"response: {response}")
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response headers: {response.headers}")

        result = current = ""
        
        # Direct stream processing (instead of SSE client library)
        buffer = ""
        processed_data = set()  # Prevent duplicate data
        
        for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
            if chunk:
                buffer += chunk
                
                # Find SSE event boundaries
                while '\n\n' in buffer:
                    event_data, buffer = buffer.split('\n\n', 1)
                
                 # Find data: lines                
                for line in event_data.split('\n'):
                    if line.startswith('data: '):
                        data = line[6:].strip()  # Remove "data: " prefix
                        if data:  # Only process non-empty data
                            # Check for duplicate data
                            if data in processed_data:
                                # logger.info(f"Skipping duplicate data: {data[:50]}...")
                                continue
                            processed_data.add(data)
                            
                            try:                                
                                data_json = json.loads(data)
                                logger.info(f"index: {index}")
                                
                                if agent_type == 'strands':
                                    if 'data' in data_json:
                                        text = data_json['data']
                                        logger.info(f"[data] {text}")
                                        current += text
                                        # containers['result'].markdown(result)
                                        update_streaming_result(containers, current)
                                    elif 'result' in data_json:
                                        result = data_json['result']
                                        logger.info(f"[result] {result}")
                                        # containers['result'].markdown(result)
                                        # update_streaming_result(containers, result)
                                    elif 'tool' in data_json:
                                        tool = data_json['tool']
                                        input = data_json['input']
                                        toolUseId = data_json['toolUseId']
                                        logger.info(f"[tool] {tool}, [input] {input}, [toolUseId] {toolUseId}")

                                        if toolUseId not in tool_info_list: # new tool info
                                            index += 1
                                            current = ""
                                            logger.info(f"new tool info: {toolUseId} -> {index}")
                                            tool_info_list[toolUseId] = index
                                            add_notification(containers, f"Tool: {tool}, Input: {input}")
                                            # containers['notification'][tool_info_list[toolUseId]].info(f"Tool: {tool}, Input: {input}")

                                        else: # overwrite tool info if already exists
                                            logger.info(f"overwrite tool info: {toolUseId} -> {tool_info_list[toolUseId]}")
                                            # update_tool_notification(containers, tool_info_list[toolUseId], f"Tool: {tool}, Input: {input}")
                                            containers['notification'][tool_info_list[toolUseId]].info(f"Tool: {tool}, Input: {input}")
                                        
                                    elif 'toolResult' in data_json:                                    
                                        toolResult = data_json['toolResult']
                                        toolUseId = data_json['toolUseId']
                                        logger.info(f"[tool_result] {toolResult}")

                                        if toolUseId not in tool_result_list:  # new tool result
                                            index += 1
                                            logger.info(f"new tool result: {toolUseId} -> {index}")
                                            tool_result_list[toolUseId] = index
                                            add_notification(containers, f"Tool Result: {str(toolResult)}")
                                        else: # overwrite tool result
                                            logger.info(f"overwrite tool result: {toolUseId} -> {tool_result_list[toolUseId]}")
                                            containers['notification'][tool_result_list[toolUseId]].info(f"Tool Result: {str(toolResult)}")
                                else: # langgraph
                                    if 'data' in data_json:
                                        text = data_json['data']
                                        logger.info(f"[data] {text}")
                                        update_streaming_result(containers, text)
                                    elif 'result' in data_json:
                                        result = data_json['result']
                                        logger.info(f"[result] {result}")
                                    elif 'tool' in data_json:
                                        tool = data_json['tool']
                                        input = data_json['input']
                                        toolUseId = data_json['toolUseId']
                                        logger.info(f"[tool] {tool}, [input] {input}, [toolUseId] {toolUseId}")

                                        logger.info(f"tool info: {toolUseId} -> {index}")
                                        add_notification(containers, f"Tool: {tool}, Input: {input}")
                                        
                                    elif 'toolResult' in data_json:
                                        toolResult = data_json['toolResult']
                                        toolUseId = data_json['toolUseId']
                                        logger.info(f"[tool_result] {toolResult}")

                                        tool_result_list[toolUseId] = index
                                        logger.info(f"tool result: {toolUseId} -> {index}")                                    
                                        add_notification(containers, f"Tool Result: {str(toolResult)}")

                            except json.JSONDecodeError:
                                logger.info(f"Not JSON: {data}")
                            except Exception as e:
                                logger.error(f"Error processing data: {e}")
                                break
    
        return result
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"

def run_agent(prompt, agent_type, history_mode, mcp_servers, model_name, containers):
    global index
    index = 0
    
    user_id = agent_type # for testing
    logger.info(f"user_id: {user_id}")

    payload = json.dumps({
        "prompt": prompt,
        "mcp_servers": mcp_servers,
        "model_name": model_name,
        "user_id": user_id,
        "history_mode": history_mode
    })

    if agent_type == 'langgraph':
        agent_runtime_arn = langgraph_agent_runtime_arn
    else: 
        agent_runtime_arn = strands_agent_runtime_arn

    logger.info(f"agent_runtime_arn: {agent_runtime_arn}")
    logger.info(f"Payload: {payload}")
    
    try:
        agent_core_client = boto3.client('bedrock-agentcore', region_name=bedrock_region)
        response = agent_core_client.invoke_agent_runtime(
            agentRuntimeArn=agent_runtime_arn,
            runtimeSessionId=runtime_session_id,
            payload=payload,
            qualifier="DEFAULT" # DEFAULT or LATEST
        )
        
        result = current = ""
        processed_data = set()  # Prevent duplicate data
        
        # stream response
        if "text/event-stream" in response.get("contentType", ""):
            for line in response["response"].iter_lines(chunk_size=10):
                line = line.decode("utf-8")
                
                if line.startswith('data: '):
                    data = line[6:].strip()  # Remove "data:" prefix and whitespace
                    if data:  # Only process non-empty data
                        # Check for duplicate data
                        if data in processed_data:
                            # logger.info(f"Skipping duplicate data: {data[:50]}...")
                            continue
                        processed_data.add(data)
                        
                        try:
                            data_json = json.loads(data)

                            if agent_type == 'strands':
                                if 'data' in data_json:
                                    text = data_json['data']
                                    logger.info(f"[data] {text}")
                                    current += text
                                    # containers['result'].markdown(current)
                                    update_streaming_result(containers, current)
                                elif 'result' in data_json:
                                    result = data_json['result']
                                    logger.info(f"[result] {result}")
                                    # containers['result'].markdown(result)
                                elif 'tool' in data_json:
                                    tool = data_json['tool']
                                    input = data_json['input']
                                    toolUseId = data_json['toolUseId']
                                    logger.info(f"[tool] {tool}, [input] {input}, [toolUseId] {toolUseId}")

                                    if toolUseId not in tool_info_list: # new tool info
                                        index += 1
                                        current = ""
                                        logger.info(f"new tool info: {toolUseId} -> {index}")
                                        tool_info_list[toolUseId] = index                                        
                                        add_notification(containers, f"Tool: {tool}, Input: {input}")
                                        # containers['notification'][tool_info_list[toolUseId]].info(f"Tool: {tool}, Input: {input}")
                                    else: # overwrite tool info
                                        logger.info(f"overwrite tool info: {toolUseId} -> {tool_info_list[toolUseId]}")
                                        # update_tool_notification(containers, f"Tool: {tool}, Input: {input}")
                                        containers['notification'][tool_info_list[toolUseId]].info(f"Tool: {tool}, Input: {input}")
                                    
                                elif 'toolResult' in data_json:
                                    toolResult = data_json['toolResult']
                                    toolUseId = data_json['toolUseId']
                                    logger.info(f"[tool_result] {toolResult}")

                                    if toolUseId not in tool_result_list:  # new tool result    
                                        index += 1
                                        tool_result_list[toolUseId] = index
                                        # add_notification(containers, f"Tool Result: {toolResult}")
                                        logger.info(f"new tool result: {toolUseId} -> {index}")                                    
                                        add_notification(containers, f"Tool Result: {str(toolResult)}")
                                    else: # overwrite tool result
                                        logger.info(f"overwrite tool result: {toolUseId} -> {tool_result_list[toolUseId]}")
                                        containers['notification'][tool_result_list[toolUseId]].info(f"Tool Result: {str(toolResult)}")
                            else: # langgraph
                                if 'data' in data_json:
                                    text = data_json['data']
                                    logger.info(f"[data] {text}")
                                    update_streaming_result(containers, text)
                                elif 'result' in data_json:
                                    result = data_json['result']
                                    logger.info(f"[result] {result}")
                                elif 'tool' in data_json:
                                    tool = data_json['tool']
                                    input = data_json['input']
                                    toolUseId = data_json['toolUseId']
                                    logger.info(f"[tool] {tool}, [input] {input}, [toolUseId] {toolUseId}")

                                    logger.info(f"tool info: {toolUseId} -> {index}")
                                    add_notification(containers, f"Tool: {tool}, Input: {input}")
                                    
                                elif 'toolResult' in data_json:
                                    toolResult = data_json['toolResult']
                                    toolUseId = data_json['toolUseId']
                                    logger.info(f"[tool_result] {toolResult}")

                                    tool_result_list[toolUseId] = index
                                    logger.info(f"tool result: {toolUseId} -> {index}")                                    
                                    add_notification(containers, f"Tool Result: {str(toolResult)}")

                        except json.JSONDecodeError:
                            logger.info(f"Not JSON: {data}")
                        except Exception as e:
                            logger.error(f"Error processing data: {e}")
                            break
    
        logger.info(f"result: {result}")
        return result
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"
