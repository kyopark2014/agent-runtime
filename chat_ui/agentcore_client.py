import boto3
from botocore.config import Config
import json
import os
import logging
import sys
import requests
import uuid

# Import utils from application package
try:
    from application import utils
except ImportError:
    import utils

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("agentcore_client")

config = utils.load_config()

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

def load_agentcore_config(agent_name):
    client = boto3.client('bedrock-agentcore-control', region_name=bedrock_region)
    response = client.list_agent_runtimes()
    logger.info(f"response: {response}")

    agentRuntimes = response['agentRuntimes']
    for agentRuntime in agentRuntimes:
        if agentRuntime['agentRuntimeName'] == agent_name:
            return agentRuntime['agentRuntimeArn']
    return None

runtime_session_id = str(uuid.uuid4())
logger.info(f"runtime_session_id: {runtime_session_id}")

tool_info_list = dict()
tool_result_list = dict()
tool_name_list = dict()

def get_tool_info(tool_name, tool_content):
    tool_references = []    
    urls = []
    content = ""

    # tavily
    if isinstance(tool_content, str) and "Title:" in tool_content and "URL:" in tool_content and "Content:" in tool_content:
        logger.info("Tavily parsing...")
        items = tool_content.split("\n\n")
        for i, item in enumerate(items):
            # logger.info(f"item[{i}]: {item}")
            if "Title:" in item and "URL:" in item and "Content:" in item:
                try:
                    title_part = item.split("Title:")[1].split("URL:")[0].strip()
                    url_part = item.split("URL:")[1].split("Content:")[0].strip()
                    content_part = item.split("Content:")[1].strip().replace("\n", "")
                    
                    logger.info(f"title_part: {title_part}")
                    logger.info(f"url_part: {url_part}")
                    logger.info(f"content_part: {content_part}")

                    content += f"{content_part}\n\n"
                    
                    tool_references.append({
                        "url": url_part,
                        "title": title_part,
                        "content": content_part[:100] + "..." if len(content_part) > 100 else content_part
                    })
                except Exception as e:
                    logger.info(f"Parsing error: {str(e)}")
                    continue                

    # OpenSearch
    elif tool_name == "SearchIndexTool": 
        if ":" in tool_content:
            extracted_json_data = tool_content.split(":", 1)[1].strip()
            try:
                json_data = json.loads(extracted_json_data)
                # logger.info(f"extracted_json_data: {extracted_json_data[:200]}")
            except json.JSONDecodeError:
                logger.info("JSON parsing error")
                json_data = {}
        else:
            json_data = {}
        
        if "hits" in json_data:
            hits = json_data["hits"]["hits"]
            if hits:
                logger.info(f"hits[0]: {hits[0]}")

            for hit in hits:
                text = hit["_source"]["text"]
                metadata = hit["_source"]["metadata"]
                
                content += f"{text}\n\n"

                filename = metadata["name"].split("/")[-1]
                # logger.info(f"filename: {filename}")
                
                content_part = text.replace("\n", "")
                tool_references.append({
                    "url": metadata["url"], 
                    "title": filename,
                    "content": content_part[:100] + "..." if len(content_part) > 100 else content_part
                })
                
        logger.info(f"content: {content}")
        
    # Knowledge Base
    elif tool_name == "QueryKnowledgeBases": 
        try:
            # Handle case where tool_content contains multiple JSON objects
            if tool_content.strip().startswith('{'):
                # Parse each JSON object individually
                json_objects = []
                current_pos = 0
                brace_count = 0
                start_pos = -1
                
                for i, char in enumerate(tool_content):
                    if char == '{':
                        if brace_count == 0:
                            start_pos = i
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0 and start_pos != -1:
                            try:
                                json_obj = json.loads(tool_content[start_pos:i+1])
                                # logger.info(f"json_obj: {json_obj}")
                                json_objects.append(json_obj)
                            except json.JSONDecodeError:
                                logger.info(f"JSON parsing error: {tool_content[start_pos:i+1][:100]}")
                            start_pos = -1
                
                json_data = json_objects
            else:
                # Try original method
                json_data = json.loads(tool_content)                
            # logger.info(f"json_data: {json_data}")

            # Build content
            if isinstance(json_data, list):
                for item in json_data:
                    if isinstance(item, dict) and "content" in item:
                        content_text = item["content"].get("text", "")
                        content += content_text + "\n\n"

                        uri = "" 
                        if "location" in item:
                            if "s3Location" in item["location"]:
                                uri = item["location"]["s3Location"]["uri"]
                                # logger.info(f"uri (list): {uri}")
                                ext = uri.split(".")[-1]

                                # # if ext is an image 
                                # url = sharing_url + "/" + s3_prefix + "/" + uri.split("/")[-1]
                                # if ext in ["jpg", "jpeg", "png", "gif", "bmp", "tiff", "ico", "webp"]:
                                #     url = sharing_url + "/" + capture_prefix + "/" + uri.split("/")[-1]
                                # logger.info(f"url: {url}")
                                
                                tool_references.append({
                                    "url": url, 
                                    "title": uri.split("/")[-1],
                                    "content": content_text[:100] + "..." if len(content_text) > 100 else content_text
                                })          
                
        except json.JSONDecodeError as e:
            logger.info(f"JSON parsing error: {e}")
            json_data = {}
            content = tool_content  # Use original content if parsing fails

        logger.info(f"content: {content}")
        logger.info(f"tool_references: {tool_references}")

    # aws document
    elif tool_name == "search_documentation":
        try:
            # Handle case where tool_content is already a list (e.g., from toolResult)
            if isinstance(tool_content, list):
                # Extract text from list items if they have 'text' key
                json_data = []
                for item in tool_content:
                    if isinstance(item, dict) and 'text' in item:
                        try:
                            parsed_text = json.loads(item['text'])
                            if isinstance(parsed_text, dict) and 'search_results' in parsed_text:
                                json_data = parsed_text['search_results']
                            elif isinstance(parsed_text, list):
                                json_data = parsed_text
                            else:
                                json_data.append(parsed_text)
                        except (json.JSONDecodeError, TypeError):
                            logger.info(f"Failed to parse text from list item: {item}")
                    elif isinstance(item, dict):
                        json_data.append(item)
                    else:
                        json_data.append(item)
            elif isinstance(tool_content, str):
                json_data = json.loads(tool_content)
            else:
                json_data = tool_content
            
            # Ensure json_data is iterable
            if not isinstance(json_data, list):
                json_data = [json_data]
            
            for item in json_data:
                logger.info(f"item: {item}")
                
                if isinstance(item, str):
                    try:
                        item = json.loads(item)
                    except json.JSONDecodeError:
                        logger.info(f"Failed to parse item as JSON: {item}")
                        continue
                
                if isinstance(item, dict) and 'url' in item and 'title' in item:
                    url = item['url']
                    title = item['title']
                    context_text = item.get('context', '')
                    content_text = context_text[:100] + "..." if len(context_text) > 100 else context_text
                    content += context_text + "\n\n"
                    tool_references.append({
                        "url": url,
                        "title": title,
                        "content": content_text
                    })
                else:
                    logger.info(f"Invalid item format: {item}")
                    
        except json.JSONDecodeError as e:
            logger.info(f"JSON parsing error: {e}, tool_content type: {type(tool_content)}")
            pass
        except Exception as e:
            logger.error(f"Error processing search_documentation: {e}")
            pass

        logger.info(f"content: {content}")
        logger.info(f"tool_references: {tool_references}")
            
    # ArXiv
    elif tool_name == "search_papers" and "papers" in tool_content:
        try:
            json_data = json.loads(tool_content)

            papers = json_data['papers']
            for paper in papers:
                url = paper['url']
                title = paper['title']
                abstract = paper['abstract'].replace("\n", "")
                content_text = abstract[:100] + "..." if len(abstract) > 100 else abstract
                content += f"{content_text}\n\n"
                logger.info(f"url: {url}, title: {title}, content: {content_text}")

                tool_references.append({
                    "url": url,
                    "title": title,
                    "content": content_text
                })
        except json.JSONDecodeError:
            logger.info(f"JSON parsing error: {tool_content}")
            pass

        logger.info(f"content: {content}")
        logger.info(f"tool_references: {tool_references}")

    # aws-knowledge
    elif tool_name == "aws___read_documentation":
        logger.info(f"#### {tool_name} ####")
        if isinstance(tool_content, dict):
            json_data = tool_content
        elif isinstance(tool_content, list):
            json_data = tool_content
        else:
            json_data = json.loads(tool_content)
        
        logger.info(f"json_data: {json_data}")
        payload = json_data["response"]["payload"]
        if "content" in payload:
            payload_content = payload["content"]
            if "result" in payload_content:
                result = payload_content["result"]
                logger.info(f"result: {result}")
                if isinstance(result, str) and "AWS Documentation from" in result:
                    logger.info(f"Processing AWS Documentation format: {result}")
                    try:
                        # Extract URL from "AWS Documentation from https://..."
                        url_start = result.find("https://")
                        if url_start != -1:
                            # Find the colon after the URL (not inside the URL)
                            url_end = result.find(":", url_start)
                            if url_end != -1:
                                # Check if the colon is part of the URL or the separator
                                url_part = result[url_start:url_end]
                                # If the colon is immediately after the URL, use it as separator
                                if result[url_end:url_end+2] == ":\n":
                                    url = url_part
                                    content_start = url_end + 2  # Skip the colon and newline
                                else:
                                    # Try to find the actual URL end by looking for space or newline
                                    space_pos = result.find(" ", url_start)
                                    newline_pos = result.find("\n", url_start)
                                    if space_pos != -1 and newline_pos != -1:
                                        url_end = min(space_pos, newline_pos)
                                    elif space_pos != -1:
                                        url_end = space_pos
                                    elif newline_pos != -1:
                                        url_end = newline_pos
                                    else:
                                        url_end = len(result)
                                    
                                    url = result[url_start:url_end]
                                    content_start = url_end + 1
                                
                                # Remove trailing colon from URL if present
                                if url.endswith(":"):
                                    url = url[:-1]
                                
                                # Extract content after the URL
                                if content_start < len(result):
                                    content_text = result[content_start:].strip()
                                    # Truncate content for display
                                    display_content = content_text[:100] + "..." if len(content_text) > 100 else content_text
                                    display_content = display_content.replace("\n", "")
                                    
                                    tool_references.append({
                                        "url": url,
                                        "title": "AWS Documentation",
                                        "content": display_content
                                    })
                                    content += content_text + "\n\n"
                                    logger.info(f"Extracted URL: {url}")
                                    logger.info(f"Extracted content length: {len(content_text)}")
                    except Exception as e:
                        logger.error(f"Error parsing AWS Documentation format: {e}")
        logger.info(f"content: {content}")
        logger.info(f"tool_references: {tool_references}")

    else:        
        try:
            if isinstance(tool_content, dict):
                json_data = tool_content
            elif isinstance(tool_content, list):
                json_data = tool_content
            else:
                json_data = json.loads(tool_content)
            
            logger.info(f"json_data: {json_data}")
            if isinstance(json_data, dict) and "path" in json_data:  # path
                path = json_data["path"]
                if isinstance(path, list):
                    for url in path:
                        urls.append(url)
                else:
                    urls.append(path)            

            if isinstance(json_data, dict):
                for item in json_data:
                    logger.info(f"item: {item}")
                    if "reference" in item and "contents" in item:
                        url = item["reference"]["url"]
                        title = item["reference"]["title"]
                        content_text = item["contents"][:100] + "..." if len(item["contents"]) > 100 else item["contents"]
                        tool_references.append({
                            "url": url,
                            "title": title,
                            "content": content_text
                        })
            else:
                logger.info(f"json_data is not a dict: {json_data}")

                for item in json_data:
                    if "reference" in item and "contents" in item:
                        url = item["reference"]["url"]
                        title = item["reference"]["title"]
                        content_text = item["contents"][:100] + "..." if len(item["contents"]) > 100 else item["contents"]
                        tool_references.append({
                            "url": url,
                            "title": title,
                            "content": content_text
                        })
                
            logger.info(f"tool_references: {tool_references}")

        except json.JSONDecodeError:
            pass

    return content, urls, tool_references

def run_agent_in_docker(prompt, agent_type, history_mode, mcp_servers, model_name, containers):
    global index
    index = 0

    references = []
    image_url = []

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
                                # logger.info(f"index: {index}")
                                
                                if agent_type == 'strands':
                                    if 'data' in data_json:
                                        text = data_json['data']
                                        logger.info(f"[data] {text}")
                                        current += text
                                        update_streaming_result(containers, current)
                                    elif 'result' in data_json:
                                        final_output = data_json['result']
                                        logger.info(f"[result] {final_output}")

                                        result = final_output.get('messages', [])
                                        logger.info(f"result: {result}")

                                        if "image_url" in final_output:
                                            image_url = final_output.get('image_url', [])
                                            logger.info(f"image_url: {image_url}")                                        
                                        
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
                                            tool_name_list[toolUseId] = tool
                                            add_notification(containers, f"Tool: {tool}, Input: {input}")

                                        else: # overwrite tool info if already exists
                                            logger.info(f"overwrite tool info: {toolUseId} -> {tool_info_list[toolUseId]}")
                                            containers['notification'][tool_info_list[toolUseId]].info(f"Tool: {tool}, Input: {input}")
                                        
                                    elif 'toolResult' in data_json:                                    
                                        toolResult = data_json['toolResult']
                                        toolUseId = data_json['toolUseId']
                                        tool_name = tool_name_list[toolUseId]
                                        logger.info(f"[tool_result] {toolResult}")

                                        if toolUseId not in tool_result_list:  # new tool result
                                            index += 1
                                            logger.info(f"new tool result: {toolUseId} -> {index}")
                                            tool_result_list[toolUseId] = index
                                            add_notification(containers, f"Tool Result: {str(toolResult)}")
                                        else: # overwrite tool result
                                            logger.info(f"overwrite tool result: {toolUseId} -> {tool_result_list[toolUseId]}")
                                            containers['notification'][tool_result_list[toolUseId]].info(f"Tool Result: {str(toolResult)}")
                                        
                                        content, urls, refs = get_tool_info(tool_name, toolResult)
                                        if refs:
                                            for r in refs:
                                                references.append(r)
                                            logger.info(f"refs: {refs}")
                                        if urls:
                                            for url in urls:
                                                image_url.append(url)
                                            logger.info(f"urls: {urls}")

                                        if content:
                                            logger.info(f"content: {content}")    

                                elif(agent_type == 'langgraph'): # langgraph
                                    if 'data' in data_json:
                                        text = data_json['data']
                                        logger.info(f"[data] {text}")
                                        update_streaming_result(containers, text)
                                    elif 'result' in data_json:
                                        final_output = data_json['result']
                                        logger.info(f"[result] {final_output}")

                                        messages = final_output.get('messages', [])
                                        result = messages[-1].get('content')
                                        logger.info(f"result: {result}")
                                        
                                        if "image_url" in final_output:
                                            image_url = final_output.get('image_url', [])
                                            logger.info(f"image_url: {image_url}")                

                                    elif 'tool' in data_json:
                                        tool = data_json['tool']
                                        input = data_json['input']
                                        toolUseId = data_json['toolUseId']
                                        tool_name_list[toolUseId] = tool
                                        logger.info(f"[tool] {tool}, [input] {input}, [toolUseId] {toolUseId}")

                                        logger.info(f"tool info: {toolUseId} -> {index}")
                                        add_notification(containers, f"Tool: {tool}, Input: {input}")
                                        
                                    elif 'toolResult' in data_json:
                                        toolResult = data_json['toolResult']
                                        toolUseId = data_json['toolUseId']
                                        tool_name = tool_name_list[toolUseId]
                                        logger.info(f"[tool_result] {toolResult}")

                                        tool_result_list[toolUseId] = index
                                        logger.info(f"tool result: {toolUseId} -> {index}")                                    
                                        add_notification(containers, f"Tool Result: {str(toolResult)}")

                                        content, urls, refs = get_tool_info(tool_name, toolResult)
                                        if refs:
                                            for r in refs:
                                                references.append(r)
                                            logger.info(f"refs: {refs}")
                                        if urls:
                                            for url in urls:
                                                image_url.append(url)
                                            logger.info(f"urls: {urls}")

                                        if content:
                                            logger.info(f"content: {content}")     

                                else: # claude
                                    if 'TextBlock' in data_json:
                                        TextBlock = data_json['TextBlock']
                                        logger.info(f"TextBlock: {TextBlock}")
                                        update_streaming_result(containers, TextBlock)

                                        result = TextBlock

                                    elif 'tools' in data_json:
                                        tools = data_json['tools']
                                        logger.info(f"[tools] {tools}")
                                        add_notification(containers, f"Tools: {tools}")

                                    elif 'ToolUseBlock' in data_json:
                                        ToolUseBlock = data_json['ToolUseBlock']
                                        input = data_json['input']
                                        logger.info(f"tool: {ToolUseBlock}, input: {input}")
                                        add_notification(containers, f"Tool: {ToolUseBlock}, Input: {input}")
                                        
                                    elif 'ToolResultBlock' in data_json:
                                        ToolResultBlock = data_json['ToolResultBlock']
                                        logger.info(f"ToolResult: {ToolResultBlock}")

                                        logger.info(f"tool result: {ToolResultBlock}")                                    
                                        add_notification(containers, f"Tool Result: {str(ToolResultBlock)}")

                                        content, urls, refs = get_tool_info(tool_name, ToolResultBlock)
                                        if refs:
                                            for r in refs:
                                                references.append(r)
                                            logger.info(f"refs: {refs}")
                                        if urls:
                                            for url in urls:
                                                image_url.append(url)
                                            logger.info(f"urls: {urls}")

                                        if content:
                                            logger.info(f"content: {content}")    

                            except json.JSONDecodeError:
                                logger.info(f"Not JSON: {data}")
                            except Exception as e:
                                logger.error(f"Error processing data: {e}")
                                break

        if references:
            ref = "\n\n### Reference\n"
            for i, reference in enumerate(references):
                ref += f"{i+1}. [{reference['title']}]({reference['url']}), {reference['content']}...\n"    
            result += ref

        if containers is not None:
            containers['notification'][index].markdown(result)
    
        return result, image_url
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}", []

def run_agent(prompt, agent_type, history_mode, mcp_servers, model_name, containers):
    global index
    index = 0

    references = []
    image_url = []
    
    user_id = agent_type # for testing
    logger.info(f"user_id: {user_id}")

    payload = json.dumps({
        "prompt": prompt,
        "mcp_servers": mcp_servers,
        "model_name": model_name,
        "user_id": user_id,
        "history_mode": history_mode
    })

    runtime_name = projectName.replace('-', '_')+'_'+agent_type
    agent_runtime_arn = load_agentcore_config(runtime_name)
    print(f"agent_runtime_arn: {agent_runtime_arn}")

    logger.info(f"agent_runtime_arn: {agent_runtime_arn}")
    logger.info(f"Payload: {payload}")
    
    if agent_runtime_arn is None:
        logger.error(f"agent_runtime_arn is not found")
        return f"Error: agent_runtime_arn is not found", []

    try:
        # Configure boto3 client with longer timeout for streaming responses
        boto_config = Config(
            read_timeout=300,  # 5 minutes
            connect_timeout=60,
            retries={'max_attempts': 0}
        )
        agent_core_client = boto3.client(
            'bedrock-agentcore', 
            region_name=bedrock_region,
            config=boto_config
        )
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
                if line:
                    print(f"-> {line}")
                
                tool_name = ""
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
                                    update_streaming_result(containers, current)

                                elif 'result' in data_json:
                                    final_output = data_json['result']
                                    logger.info(f"[result] {final_output}")

                                    result = final_output.get('messages', [])
                                    logger.info(f"result: {result}")

                                    if "image_url" in final_output:
                                        image_url = final_output.get('image_url', [])
                                        logger.info(f"image_url: {image_url}")                

                                elif 'tool' in data_json:
                                    tool = data_json['tool']
                                    input = data_json['input']
                                    toolUseId = data_json['toolUseId']
                                    # logger.info(f"[tool] {tool}, [input] {input}, [toolUseId] {toolUseId}")

                                    if toolUseId not in tool_info_list: # new tool info
                                        index += 1
                                        current = ""
                                        # logger.info(f"new tool info: {toolUseId} -> {index}")
                                        tool_info_list[toolUseId] = index      
                                        tool_name_list[toolUseId] = tool                                  
                                        add_notification(containers, f"Tool: {tool}, Input: {input}")
                                    else: # overwrite tool info
                                        # logger.info(f"overwrite tool info: {toolUseId} -> {tool_info_list[toolUseId]}")
                                        containers['notification'][tool_info_list[toolUseId]].info(f"Tool: {tool}, Input: {input}")
                                    
                                elif 'toolResult' in data_json:
                                    toolResult = data_json['toolResult']
                                    toolUseId = data_json['toolUseId']
                                    tool_name = tool_name_list[toolUseId]
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

                                    content, urls, refs = get_tool_info(tool_name, toolResult)
                                    if refs:
                                        for r in refs:
                                            references.append(r)
                                        logger.info(f"refs: {refs}")
                                    if urls:
                                        for url in urls:
                                            image_url.append(url)
                                        logger.info(f"urls: {urls}")

                                    if content:
                                        logger.info(f"content: {content}")    

                            elif agent_type == 'langgraph': # langgraph
                                if 'data' in data_json:
                                    text = data_json['data']
                                    logger.info(f"[data] {text}")
                                    update_streaming_result(containers, text)
                                elif 'result' in data_json:
                                    final_output = data_json['result']
                                    logger.info(f"[result] {final_output}")

                                    messages = final_output.get('messages', [])
                                    result = messages[-1].get('content')
                                    logger.info(f"result: {result}")

                                    if "image_url" in final_output:
                                        image_url = final_output.get('image_url', [])
                                        logger.info(f"image_url: {image_url}")                                        

                                elif 'tool' in data_json:
                                    tool = data_json['tool']
                                    input = data_json['input']
                                    toolUseId = data_json['toolUseId']
                                    tool_name_list[toolUseId] = tool
                                    logger.info(f"[tool] {tool}, [input] {input}, [toolUseId] {toolUseId}")

                                    logger.info(f"tool info: {toolUseId} -> {index}")
                                    add_notification(containers, f"Tool: {tool}, Input: {input}")
                                    
                                elif 'toolResult' in data_json:
                                    toolResult = data_json['toolResult']
                                    toolUseId = data_json['toolUseId']
                                    tool_name = tool_name_list[toolUseId]
                                    logger.info(f"[tool_result] {toolResult}")

                                    tool_result_list[toolUseId] = index
                                    logger.info(f"tool result: {toolUseId} -> {index}")                                    
                                    add_notification(containers, f"Tool Result: {str(toolResult)}")

                                    content, urls, refs = get_tool_info(tool_name, toolResult)
                                    if refs:
                                        for r in refs:
                                            references.append(r)
                                        logger.info(f"refs: {refs}")
                                    if urls:
                                        for url in urls:
                                            image_url.append(url)
                                        logger.info(f"urls: {urls}")

                                    if content:
                                        logger.info(f"content: {content}")      

                            else: # claude
                                if 'TextBlock' in data_json:
                                    TextBlock = data_json['TextBlock']
                                    logger.info(f"TextBlock: {TextBlock}")
                                    update_streaming_result(containers, TextBlock)

                                    result = TextBlock

                                elif 'tools' in data_json:
                                    tools = data_json['tools']
                                    logger.info(f"[tools] {tools}")
                                    add_notification(containers, f"Tools: {tools}")

                                elif 'ToolUseBlock' in data_json:
                                    ToolUseBlock = data_json['ToolUseBlock']
                                    input = data_json['input']
                                    logger.info(f"tool: {ToolUseBlock}, input: {input}")
                                    add_notification(containers, f"Tool: {ToolUseBlock}, Input: {input}")
                                    
                                elif 'ToolResultBlock' in data_json:
                                    ToolResultBlock = data_json['ToolResultBlock']
                                    logger.info(f"ToolResult: {ToolResultBlock}")

                                    logger.info(f"tool result: {ToolResultBlock}")                                    
                                    add_notification(containers, f"Tool Result: {str(ToolResultBlock)}")

                                    content, urls, refs = get_tool_info(tool_name, ToolResultBlock)
                                    if refs:
                                        for r in refs:
                                            references.append(r)
                                        logger.info(f"refs: {refs}")
                                    if urls:
                                        for url in urls:
                                            image_url.append(url)
                                        logger.info(f"urls: {urls}")

                                    if content:
                                        logger.info(f"content: {content}")              
                        
                        except json.JSONDecodeError:
                            logger.info(f"Not JSON: {data}")
                        except Exception as e:
                            logger.error(f"Error processing data: {e}")
                            break
        
        if references:
            ref = "\n\n### Reference\n"
            for i, reference in enumerate(references):
                ref += f"{i+1}. [{reference['title']}]({reference['url']}), {reference['content']}...\n"    
            result += ref

        if containers is not None:
            containers['notification'][index].markdown(result)
    
        logger.info(f"result: {result}")
        return result, image_url
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}", []
