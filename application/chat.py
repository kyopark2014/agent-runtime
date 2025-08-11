import boto3
import json
import uuid
import os
import logging
import sys
import requests
import knowledge_base
import traceback
import base64
import info
import re
import csv
import PyPDF2
import ast

from io import BytesIO
from PIL import Image
from langchain_core.messages import HumanMessage
from urllib import parse
from langchain_aws import ChatBedrock
from botocore.config import Config
from langchain.docstore.document import Document
from langchain_core.prompts import MessagesPlaceholder, ChatPromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from bedrock_agentcore.memory import MemoryClient
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("chat")

def load_config():
    config = None
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "..", 'langgraph', "config.json")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    return config

config = load_config()

index = 0
def add_notification(containers, message):
    global index
    if containers is not None:
        containers['notification'][index].info(message)
    index += 1

bedrock_region = config['region']
accountId = config['accountId']
projectName = config['projectName']

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

model_name = "Claude 3.5 Sonnet"
model_type = "claude"
models = info.get_model_info(model_name)
model_id = models[0]["model_id"]

s3_prefix = 'docs'
s3_image_prefix = 'images'
doc_prefix = s3_prefix+'/'

s3_bucket = config["s3_bucket"] if "s3_bucket" in config else None
if s3_bucket is None:
    raise Exception ("No storage!")

path = config["sharing_url"] if "sharing_url" in config else None
if path is None:
    raise Exception ("No Sharing URL")

runtime_session_id = str(uuid.uuid4())
logger.info(f"runtime_session_id: {runtime_session_id}")
user_id = None 

def initiate():
    global runtime_session_id
    runtime_session_id=str(uuid.uuid4())
    logger.info(f"runtime_session_id: {runtime_session_id}")

debug_mode = 'Disable'

def update(modelName):
    global model_name, models, model_type, model_id

    if modelName is not model_name:
        model_name = modelName
        logger.info(f"modelName: {modelName}")

        models = info.get_model_info(model_name)
        model_type = models[0]["model_type"]
        model_id = models[0]["model_id"]
        logger.info(f"model_id: {model_id}")
        logger.info(f"model_type: {model_type}")

def get_contents_type(file_name):
    if file_name.lower().endswith((".jpg", ".jpeg")):
        content_type = "image/jpeg"
    elif file_name.lower().endswith((".pdf")):
        content_type = "application/pdf"
    elif file_name.lower().endswith((".txt")):
        content_type = "text/plain"
    elif file_name.lower().endswith((".csv")):
        content_type = "text/csv"
    elif file_name.lower().endswith((".ppt", ".pptx")):
        content_type = "application/vnd.ms-powerpoint"
    elif file_name.lower().endswith((".doc", ".docx")):
        content_type = "application/msword"
    elif file_name.lower().endswith((".xls")):
        content_type = "application/vnd.ms-excel"
    elif file_name.lower().endswith((".py")):
        content_type = "text/x-python"
    elif file_name.lower().endswith((".js")):
        content_type = "application/javascript"
    elif file_name.lower().endswith((".md")):
        content_type = "text/markdown"
    elif file_name.lower().endswith((".png")):
        content_type = "image/png"
    else:
        content_type = "no info"    
    return content_type

def upload_to_s3(file_bytes, file_name):
    """
    Upload a file to S3 and return the URL
    """
    try:
        s3_client = boto3.client(
            service_name='s3',
            region_name=bedrock_region,
        )

        content_type = get_contents_type(file_name)       
        logger.info(f"content_type: {content_type}") 

        if content_type == "image/jpeg" or content_type == "image/png":
            s3_key = f"{s3_image_prefix}/{file_name}"
        else:
            s3_key = f"{s3_prefix}/{file_name}"
        
        user_meta = {  # user-defined metadata
            "content_type": content_type,
            "model_name": model_name
        }
        
        response = s3_client.put_object(
            Bucket=s3_bucket, 
            Key=s3_key, 
            ContentType=content_type,
            Metadata = user_meta,
            Body=file_bytes            
        )
        logger.info(f"upload response: {response}")

        #url = f"https://{s3_bucket}.s3.amazonaws.com/{s3_key}"
        url = path+'/'+s3_image_prefix+'/'+parse.quote(file_name)
        return url
    
    except Exception as e:
        err_msg = f"Error uploading to S3: {str(e)}"
        logger.info(f"{err_msg}")
        return None

def get_chat(extended_thinking=None):
    # Set default value if not provided or invalid
    if extended_thinking is None or extended_thinking not in ['Enable', 'Disable']:
        extended_thinking = 'Disable'

    logger.info(f"model_name: {model_name}")
    profile = models[0]
    bedrock_region =  profile['bedrock_region']
    modelId = profile['model_id']
    model_type = profile['model_type']
    maxOutputTokens = 4096 # 4k
    logger.info(f"LLM: bedrock_region: {bedrock_region}, modelId: {modelId}, model_type: {model_type}")

    STOP_SEQUENCE = "\n\nHuman:" 
                          
    # bedrock   
    boto3_bedrock = boto3.client(
        service_name='bedrock-runtime',
        region_name=bedrock_region,
        config=Config(
            retries = {
                'max_attempts': 30
            }
        )
    )
    
    if extended_thinking=='Enable':
        maxReasoningOutputTokens=64000
        logger.info(f"extended_thinking: {extended_thinking}")
        thinking_budget = min(maxOutputTokens, maxReasoningOutputTokens-1000)

        parameters = {
            "max_tokens":maxReasoningOutputTokens,
            "temperature":1,            
            "thinking": {
                "type": "enabled",
                "budget_tokens": thinking_budget
            },
            "stop_sequences": [STOP_SEQUENCE]
        }
    else:
        parameters = {
            "max_tokens":maxOutputTokens,     
            "temperature":0.1,
            "top_k":250,
            "top_p":0.9,
            "stop_sequences": [STOP_SEQUENCE]
        }

    chat = ChatBedrock(   # new chat model
        model_id=modelId,
        client=boto3_bedrock, 
        model_kwargs=parameters,
        region_name=bedrock_region
    )    
    return chat

def summary_of_code(code, mode):
    if mode == 'py':
        system = (
            "다음의 <article> tag에는 python code가 있습니다."
            "code의 전반적인 목적에 대해 설명하고, 각 함수의 기능과 역할을 자세하게 한국어 500자 이내로 설명하세요."
        )
    elif mode == 'js':
        system = (
            "다음의 <article> tag에는 node.js code가 있습니다." 
            "code의 전반적인 목적에 대해 설명하고, 각 함수의 기능과 역할을 자세하게 한국어 500자 이내로 설명하세요."
        )
    else:
        system = (
            "다음의 <article> tag에는 code가 있습니다."
            "code의 전반적인 목적에 대해 설명하고, 각 함수의 기능과 역할을 자세하게 한국어 500자 이내로 설명하세요."
        )
    
    human = "<article>{code}</article>"
    
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", human)])
    # print('prompt: ', prompt)
    
    llm = get_chat(extended_thinking="Disable")

    chain = prompt | llm    
    try: 
        result = chain.invoke(
            {
                "code": code
            }
        )
        
        summary = result.content
        logger.info(f"result of code summarization: {summary}")
    except Exception:
        err_msg = traceback.format_exc()
        logger.info(f"error message: {err_msg}")        
        raise Exception ("Not able to request to LLM")
    
    return summary

def summary_image(img_base64, instruction):      
    llm = get_chat(extended_thinking="Disable")

    if instruction:
        logger.info(f"instruction: {instruction}")
        query = f"{instruction}. <result> tag를 붙여주세요."
        
    else:
        query = "이미지가 의미하는 내용을 풀어서 자세히 알려주세요. markdown 포맷으로 답변을 작성합니다."
    
    messages = [
        HumanMessage(
            content=[
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_base64}", 
                    },
                },
                {
                    "type": "text", "text": query
                },
            ]
        )
    ]
    
    for attempt in range(5):
        logger.info(f"attempt: {attempt}")
        try: 
            result = llm.invoke(messages)
            
            extracted_text = result.content
            # print('summary from an image: ', extracted_text)
            break
        except Exception:
            err_msg = traceback.format_exc()
            logger.info(f"error message: {err_msg}")                    
            raise Exception ("Not able to request to LLM")
        
    return extracted_text

# load csv documents from s3
def load_csv_document(s3_file_name):
    s3r = boto3.resource("s3")
    doc = s3r.Object(s3_bucket, s3_prefix+'/'+s3_file_name)

    lines = doc.get()['Body'].read().decode('utf-8').split('\n')   # read csv per line
    logger.info(f"prelinspare: {len(lines)}")
        
    columns = lines[0].split(',')  # get columns
    #columns = ["Category", "Information"]  
    #columns_to_metadata = ["type","Source"]
    logger.info(f"columns: {columns}")
    
    docs = []
    n = 0
    for row in csv.DictReader(lines, delimiter=',',quotechar='"'):
        # print('row: ', row)
        #to_metadata = {col: row[col] for col in columns_to_metadata if col in row}
        values = {k: row[k] for k in columns if k in row}
        content = "\n".join(f"{k.strip()}: {v.strip()}" for k, v in values.items())
        doc = Document(
            page_content=content,
            metadata={
                'name': s3_file_name,
                'row': n+1,
            }
            #metadata=to_metadata
        )
        docs.append(doc)
        n = n+1
    logger.info(f"docs[0]: {docs[0]}")

    return docs

def isKorean(text):
    # check korean
    pattern_hangul = re.compile('[\u3131-\u3163\uac00-\ud7a3]+')
    word_kor = pattern_hangul.search(str(text))
    # print('word_kor: ', word_kor)

    if word_kor and word_kor != 'None':
        # logger.info(f"Korean: {word_kor}")
        return True
    else:
        # logger.info(f"Not Korean:: {word_kor}")
        return False
    
def get_summary(docs):    
    llm = get_chat(extended_thinking="Disable")

    text = ""
    for doc in docs:
        text = text + doc
    
    if isKorean(text)==True:
        system = (
            "다음의 <article> tag안의 문장을 요약해서 500자 이내로 설명하세오."
        )
    else: 
        system = (
            "Here is pieces of article, contained in <article> tags. Write a concise summary within 500 characters."
        )
    
    human = "<article>{text}</article>"
    
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", human)])
    # print('prompt: ', prompt)
    
    chain = prompt | llm    
    try: 
        result = chain.invoke(
            {
                "text": text
            }
        )
        
        summary = result.content
        logger.info(f"esult of summarization: {summary}")
    except Exception:
        err_msg = traceback.format_exc()
        logger.info(f"error message: {err_msg}") 
        raise Exception ("Not able to request to LLM")
    
    return summary

# load documents from s3 for pdf and txt
def load_document(file_type, s3_file_name):
    s3r = boto3.resource("s3")
    doc = s3r.Object(s3_bucket, s3_prefix+'/'+s3_file_name)
    logger.info(f"s3_bucket: {s3_bucket}, s3_prefix: {s3_prefix}, s3_file_name: {s3_file_name}")
    
    contents = ""
    if file_type == 'pdf':
        contents = doc.get()['Body'].read()
        reader = PyPDF2.PdfReader(BytesIO(contents))
        
        raw_text = []
        for page in reader.pages:
            raw_text.append(page.extract_text())
        contents = '\n'.join(raw_text)    
        
    elif file_type == 'txt' or file_type == 'md':        
        contents = doc.get()['Body'].read().decode('utf-8')
        
    logger.info(f"contents: {contents}")
    new_contents = str(contents).replace("\n"," ") 
    logger.info(f"length: {len(new_contents)}")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        separators=["\n\n", "\n", ".", " ", ""],
        length_function = len,
    ) 
    texts = text_splitter.split_text(new_contents) 
    if texts:
        logger.info(f"exts[0]: {texts[0]}")
    
    return texts

def summary_image(img_base64, instruction):      
    llm = get_chat(extended_thinking="Disable")

    if instruction:
        logger.info(f"instruction: {instruction}")
        query = f"{instruction}. <result> tag를 붙여주세요."
        
    else:
        query = "이미지가 의미하는 내용을 풀어서 자세히 알려주세요. markdown 포맷으로 답변을 작성합니다."
    
    messages = [
        HumanMessage(
            content=[
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_base64}", 
                    },
                },
                {
                    "type": "text", "text": query
                },
            ]
        )
    ]
    
    for attempt in range(5):
        logger.info(f"attempt: {attempt}")
        try: 
            result = llm.invoke(messages)
            
            extracted_text = result.content
            # print('summary from an image: ', extracted_text)
            break
        except Exception:
            err_msg = traceback.format_exc()
            logger.info(f"error message: {err_msg}")                    
            raise Exception ("Not able to request to LLM")
        
    return extracted_text

def extract_text(img_base64):    
    multimodal = get_chat(extended_thinking="Disable")
    query = "텍스트를 추출해서 markdown 포맷으로 변환하세요. <result> tag를 붙여주세요."
    
    extracted_text = ""
    messages = [
        HumanMessage(
            content=[
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_base64}", 
                    },
                },
                {
                    "type": "text", "text": query
                },
            ]
        )
    ]
    
    for attempt in range(5):
        logger.info(f"attempt: {attempt}")
        try: 
            result = multimodal.invoke(messages)
            
            extracted_text = result.content
            # print('result of text extraction from an image: ', extracted_text)
            break
        except Exception:
            err_msg = traceback.format_exc()
            logger.info(f"error message: {err_msg}")                    
            # raise Exception ("Not able to request to LLM")
    
    logger.info(f"Extracted_text: {extracted_text}")
    if len(extracted_text)<10:
        extracted_text = "텍스트를 추출하지 못하였습니다."    

    return extracted_text

fileId = uuid.uuid4().hex
# print('fileId: ', fileId)
def get_summary_of_uploaded_file(file_name, st):
    file_type = file_name[file_name.rfind('.')+1:len(file_name)]            
    logger.info(f"file_type: {file_type}")
    
    if file_type == 'csv':
        docs = load_csv_document(file_name)
        contexts = []
        for doc in docs:
            contexts.append(doc.page_content)
        logger.info(f"contexts: {contexts}")
    
        msg = get_summary(contexts)

    elif file_type == 'pdf' or file_type == 'txt' or file_type == 'md' or file_type == 'pptx' or file_type == 'docx':
        texts = load_document(file_type, file_name)

        if len(texts):
            docs = []
            for i in range(len(texts)):
                docs.append(
                    Document(
                        page_content=texts[i],
                        metadata={
                            'name': file_name,
                            # 'page':i+1,
                            'url': path+'/'+doc_prefix+parse.quote(file_name)
                        }
                    )
                )
            logger.info(f"docs[0]: {docs[0]}") 
            logger.info(f"docs size: {len(docs)}")

            contexts = []
            for doc in docs:
                contexts.append(doc.page_content)
            logger.info(f"contexts: {contexts}")

            msg = get_summary(contexts)
        else:
            msg = "문서 로딩에 실패하였습니다."
        
    elif file_type == 'py' or file_type == 'js':
        s3r = boto3.resource("s3")
        doc = s3r.Object(s3_bucket, s3_prefix+'/'+file_name)
        
        contents = doc.get()['Body'].read().decode('utf-8')
        
        #contents = load_code(file_type, object)                
                        
        msg = summary_of_code(contents, file_type)                  
        
    elif file_type == 'png' or file_type == 'jpeg' or file_type == 'jpg':
        logger.info(f"multimodal: {file_name}")
        
        s3_client = boto3.client(
            service_name='s3',
            region_name=bedrock_region,
        )

        if debug_mode=="Enable":
            status = "이미지를 가져옵니다."
            logger.info(f"status: {status}")
            st.info(status)
            
        image_obj = s3_client.get_object(Bucket=s3_bucket, Key=s3_prefix+'/'+file_name)
        # print('image_obj: ', image_obj)
        
        image_content = image_obj['Body'].read()
        img = Image.open(BytesIO(image_content))
        
        width, height = img.size 
        logger.info(f"width: {width}, height: {height}, size: {width*height}")
        
        # Image resizing and size verification
        isResized = False
        max_size = 5 * 1024 * 1024  # 5MB in bytes
        
        # Initial resizing (based on pixel count)
        while(width*height > 2000000):  # Limit to approximately 2M pixels
            width = int(width/2)
            height = int(height/2)
            isResized = True
            logger.info(f"width: {width}, height: {height}, size: {width*height}")
        
        if isResized:
            img = img.resize((width, height))
        
        # Base64 크기 확인 및 추가 리사이징
        max_attempts = 5
        for attempt in range(max_attempts):
            buffer = BytesIO()
            img.save(buffer, format="PNG", optimize=True)
            img_bytes = buffer.getvalue()
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")
            
            # Base64 크기 확인 (실제 전송될 크기)
            base64_size = len(img_base64.encode('utf-8'))
            logger.info(f"attempt {attempt + 1}: base64_size = {base64_size} bytes")
            
            if base64_size <= max_size:
                break
            else:
                # If size is still large, resize further
                width = int(width * 0.8)
                height = int(height * 0.8)
                img = img.resize((width, height))
                logger.info(f"resizing to {width}x{height} due to size limit")
        
        if base64_size > max_size:
            logger.warning(f"Image still too large after {max_attempts} attempts: {base64_size} bytes")
            raise Exception(f"이미지 크기가 너무 큽니다. 5MB 이하의 이미지를 사용해주세요.")
               
        # extract text from the image
        if debug_mode=="Enable":
            status = "이미지에서 텍스트를 추출합니다."
            logger.info(f"status: {status}")
            st.info(status)
        
        text = extract_text(img_base64)
        # print('extracted text: ', text)

        if text.find('<result>') != -1:
            extracted_text = text[text.find('<result>')+8:text.find('</result>')] # remove <result> tag
            # print('extracted_text: ', extracted_text)
        else:
            extracted_text = text

        if debug_mode=="Enable":
            logger.info(f"### Extracted Text\n\n{extracted_text}")
            print('status: ', status)
            st.info(status)
    
        if debug_mode=="Enable":
            status = "이미지의 내용을 분석합니다."
            logger.info(f"status: {status}")
            st.info(status)

        image_summary = summary_image(img_base64, "")
        logger.info(f"image summary: {image_summary}")
            
        if len(extracted_text) > 10:
            contents = f"## 이미지 분석\n\n{image_summary}\n\n## 추출된 텍스트\n\n{extracted_text}"
        else:
            contents = f"## 이미지 분석\n\n{image_summary}"
        logger.info(f"image content: {contents}")

        msg = contents

    global fileId
    fileId = uuid.uuid4().hex
    # print('fileId: ', fileId)

    return msg

def run_agent(prompt, agent_type, history_mode, mcp_servers, model_name, containers):
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

        logger.info(f"Response received from agent runtime")
        
        response_body = response['response'].read()
        
        if not response_body:
            error_msg = "Agent runtime returned empty response"
            logger.error(error_msg)
            return f"Error: {error_msg}"
        
        # decode if response_body is bytes
        if isinstance(response_body, bytes):
            response_body = response_body.decode('utf-8')
            
        logger.info(f"Response body length: {len(response_body)}")
        logger.info(f"Response body type: {type(response_body)}")
        
        # Check if response is streaming format (contains 'data:' lines)
        content_type = "text/event-stream" if response_body.startswith('data:') else "application/json"
        logger.info(f"Detected Content-Type: {content_type}")
        
        result = current_response = ""
        if content_type.startswith('text/event-stream'):
            # Split stream data line by line
            lines = response_body.split('\n')
            for line in lines:
                if line.startswith('data:'):
                    data = line[5:].strip()  # Remove "data:" prefix and whitespace
                    if data:
                        try:
                            data_json = json.loads(data)

                            if agent_type == 'strands':     
                                if isinstance(data_json, dict) and 'event' in data_json and 'contentBlockDelta' in data_json['event']:
                                    delta = data_json['event']['contentBlockDelta'].get('delta', {})
                                    if 'text' in delta:
                                        current_response += delta['text']
                                        containers['result'].markdown(current_response)
                                        logger.info(f"{delta['text']}")
                                elif isinstance(data_json, dict) and 'delta' in data_json and 'toolUse' in data_json:
                                    logger.info(f"DEBUG: data_json type: {type(data_json)}, keys: {data_json.keys()}")
                                    logger.info(f"{data_json}")
                                    tool_name = data_json['toolUse']['toolName']
                                    input = data_json['toolUse']['input']
                                    logger.info(f"Tool: {tool_name}\nInput: {input}")
                                    add_notification(containers, f"Tool: {tool_name}\nInput: {input}")
                                
                                # for tool info
                                elif isinstance(data_json, dict) and 'current_tool_use' in data_json:
                                    tool_info = data_json['current_tool_use']
                                    tool_name = tool_info.get('name', '')
                                    input_data = tool_info.get('input', '')
                                    logger.info(f"Tool: {tool_name}\nInput: {input_data}")
                                    add_notification(containers, f"Tool: {tool_name}\nInput: {input_data}")
                                elif isinstance(data_json, str) and 'delta' in data_json:
                                    try:
                                        parsed_data = json.loads(data_json)
                                        if isinstance(parsed_data, dict) and 'current_tool_use' in parsed_data:
                                            tool_info = parsed_data['current_tool_use']
                                            tool_name = tool_info.get('name', '')
                                            input_data = tool_info.get('input', '')
                                            logger.info(f"Tool (from string): {tool_name}\nInput: {input_data}")
                                            add_notification(containers, f"Tool: {tool_name}\nInput: {input_data}")
                                    except json.JSONDecodeError:
                                        logger.debug(f"Skipping non-JSON string: {data_json[:50]}...")
                                    except Exception as e:
                                        logger.warning(f"Failed to parse data_json string: {e}")
                                
                                elif 'data' in data_json:
                                    if isinstance(data_json, dict):
                                        continue
                                    elif isinstance(data_json, str) and data_json.startswith("{'data':"):
                                        continue
                                    else:
                                        logger.info(f"DEBUG: data_json type: {type(data_json)}, keys: {data_json.keys() if isinstance(data_json, dict) else 'Not a dict'}")
                                        logger.info(f"{data_json}")
                                elif isinstance(data_json, dict) and 'message' in data_json:
                                    try:
                                        message = data_json['message']
                                        content = message.get('content', [])
                                        
                                        if content and isinstance(content, list):
                                            content_item = content[0]                                            
                                            # toolUse
                                            if 'toolUse' in content_item:
                                                tool_use = content_item['toolUse']
                                                tool_name = tool_use.get('name', '')
                                                input_data = tool_use.get('input', {})
                                                logger.info(f"Tool Use: {tool_name}, Input: {input_data}")
                                                add_notification(containers, f"Tool Use: {tool_name}\nInput: {input_data}")
                                            
                                            # toolResult 
                                            elif 'toolResult' in content_item:
                                                tool_result = content_item['toolResult']
                                                status = tool_result.get('status', '')
                                                result_content = tool_result.get('content', [])
                                                
                                                if result_content and isinstance(result_content, list):
                                                    result_text = result_content[0].get('text', '')
                                                    logger.info(f"Tool Result: {result_text}")
                                                    add_notification(containers, f"Tool Result: {result_text}")
                                                else:
                                                    logger.info(f"Tool Result: {status}")
                                                    add_notification(containers, f"Tool Result: {status}")                                                    
                                            
                                            # text 
                                            elif 'text' in content_item:
                                                if result == "":
                                                    result = content_item['text']
                                                else:
                                                    result += '\n' + content_item['text']
                                                logger.info(f"Message text: {result}")
                                                
                                    except (KeyError, IndexError, TypeError) as e:
                                        logger.warning(f"Error processing message content: {e}, data_json: {data_json}")
                                        continue
                            else: # langgraph   
                                logger.info(f"DEBUG: data_json type: {type(data_json)}")
                                logger.info(f"DEBUG: data_json content: {str(data_json)[:200]}...")
                                
                                parsed_data_json = data_json
                                
                                if isinstance(data_json, str):
                                    logger.info(f"data_json is string, attempting to parse...")
                                    try:
                                        parsed_data_json = json.loads(data_json)
                                        logger.info(f"Successfully parsed string data_json to dict using json.loads")
                                    except json.JSONDecodeError:
                                        try:
                                            parsed_data_json = ast.literal_eval(data_json)
                                            logger.info(f"Successfully parsed string data_json to dict using ast.literal_eval")
                                        except (ValueError, SyntaxError) as e:
                                            logger.info(f"ast.literal_eval failed: {e}")
                                            try:
                                                parsed_data_json = eval(data_json)
                                                logger.info(f"Successfully parsed string data_json to dict using eval")
                                            except Exception as eval_error:
                                                logger.info(f"All parsing methods failed: {eval_error}")
                                                logger.info(f"data_json content: {data_json[:500]}...")
                                                continue
                                elif isinstance(data_json, dict):
                                    logger.info(f"data_json is already a dict")
                                    parsed_data_json = data_json
                                else:
                                    logger.info(f"data_json is neither string nor dict: {type(data_json)}")
                                    continue
                                
                                if isinstance(parsed_data_json, dict) and 'messages' in parsed_data_json:
                                    messages = parsed_data_json['messages']
                                    logger.info(f"messages: {messages}")

                                    for message in messages:
                                        if isinstance(message, AIMessage):
                                            result += message.content
                                            logger.info(f"AI Message: {message.content}")
                                            containers['result'].markdown(message.content)
                                        elif isinstance(message, HumanMessage):
                                            result += message.content
                                            logger.info(f"Human Message: {message.content}")
                                            containers['result'].markdown(message.content)
                                        elif isinstance(message, ToolMessage):
                                            result += message.content
                                            logger.info(f"Tool Message: {message.content}")
                                            add_notification(containers, f"Tool Message: {message.content}")
                                        else:
                                            logger.info(f"Unknown message type: {type(message)}")
                                else:
                                    logger.info(f"No messages found in the response: {parsed_data_json}")
                                                                    
                        except json.JSONDecodeError:
                            logger.info(f"Not JSON: {data}")
        
        return result
        
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Docker container connection failed: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"
        
    except requests.exceptions.Timeout as e:
        error_msg = f"Request timeout: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"
        
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON response from Docker container: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Raw response: {response_body}")
        return f"Error: {error_msg}"
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"

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

    headers = {
        "Content-Type": "application/json"
    }   
    destination = f"http://localhost:8080/invocations"

    try:
        logger.info(f"Sending request to Docker container at {destination}")
        logger.info(f"Payload: {payload}")
        
        response = requests.post(destination, headers=headers, data=payload, timeout=300)
        
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response headers: {response.headers}")

        if response.status_code != 200:
            error_msg = f"Docker container returned status code {response.status_code}: {response.text}"
            logger.error(error_msg)
            return f"Error: {error_msg}"
        
        if not response.text.strip():
            error_msg = "Docker container returned empty response"
            logger.error(error_msg)
            return f"Error: {error_msg}"

        result = current_response = ""
        if 'content-type' in response.headers:
            content_type = response.headers['content-type']
            logger.info(f"Content-Type: {content_type}")

            if content_type.startswith('text/event-stream'):
                # Split stream data line by line
                lines = response.text.split('\n')
                for line in lines:
                    if line.startswith('data:'):
                        data = line[5:].strip()  # Remove "data:" prefix and whitespace
                        if data:
                            try:
                                data_json = json.loads(data)
                                logger.info(f"data_json: {data_json}")

                                logger.info(f"agent_type: {agent_type}")

                                if agent_type == 'strands':                                    
                                    if isinstance(data_json, dict) and 'event' in data_json and 'contentBlockDelta' in data_json['event']:
                                        delta = data_json['event']['contentBlockDelta'].get('delta', {})
                                        if 'text' in delta:
                                            current_response += delta['text']
                                            containers['result'].markdown(current_response)
                                            logger.info(f"{delta['text']}")
                                    elif isinstance(data_json, dict) and 'delta' in data_json and 'toolUse' in data_json:
                                        logger.info(f"DEBUG: data_json type: {type(data_json)}, keys: {data_json.keys()}")
                                        logger.info(f"{data_json}")
                                        tool_name = data_json['toolUse']['toolName']
                                        input = data_json['toolUse']['input']
                                        logger.info(f"Tool: {tool_name}\nInput: {input}")
                                        add_notification(containers, f"Tool: {tool_name}\nInput: {input}")
                                    
                                    # for tool info
                                    elif isinstance(data_json, dict) and 'current_tool_use' in data_json:
                                        tool_info = data_json['current_tool_use']
                                        tool_name = tool_info.get('name', '')
                                        input_data = tool_info.get('input', '')
                                        logger.info(f"Tool: {tool_name}\nInput: {input_data}")
                                        add_notification(containers, f"Tool: {tool_name}\nInput: {input_data}")
                                    elif isinstance(data_json, str) and 'delta' in data_json:
                                        try:
                                            parsed_data = json.loads(data_json)
                                            if isinstance(parsed_data, dict) and 'current_tool_use' in parsed_data:
                                                tool_info = parsed_data['current_tool_use']
                                                tool_name = tool_info.get('name', '')
                                                input_data = tool_info.get('input', '')
                                                logger.info(f"Tool (from string): {tool_name}\nInput: {input_data}")
                                                add_notification(containers, f"Tool: {tool_name}\nInput: {input_data}")
                                        except json.JSONDecodeError:
                                            logger.debug(f"Skipping non-JSON string: {data_json[:50]}...")
                                        except Exception as e:
                                            logger.warning(f"Failed to parse data_json string: {e}")
                                    
                                    elif 'data' in data_json:
                                        if isinstance(data_json, dict):
                                            continue
                                        elif isinstance(data_json, str) and data_json.startswith("{'data':"):
                                            continue
                                        else:
                                            logger.info(f"DEBUG: data_json type: {type(data_json)}, keys: {data_json.keys() if isinstance(data_json, dict) else 'Not a dict'}")
                                            logger.info(f"{data_json}")
                                    elif isinstance(data_json, dict) and 'message' in data_json:
                                        try:
                                            message = data_json['message']
                                            content = message.get('content', [])
                                            
                                            if content and isinstance(content, list):
                                                content_item = content[0]                                            
                                                # toolUse
                                                if 'toolUse' in content_item:
                                                    tool_use = content_item['toolUse']
                                                    tool_name = tool_use.get('name', '')
                                                    input_data = tool_use.get('input', {})
                                                    logger.info(f"Tool Use: {tool_name}, Input: {input_data}")
                                                    add_notification(containers, f"Tool Use: {tool_name}\nInput: {input_data}")
                                                
                                                # toolResult 
                                                elif 'toolResult' in content_item:
                                                    tool_result = content_item['toolResult']
                                                    status = tool_result.get('status', '')
                                                    result_content = tool_result.get('content', [])
                                                    
                                                    if result_content and isinstance(result_content, list):
                                                        result_text = result_content[0].get('text', '')
                                                        logger.info(f"Tool Result: {result_text}")
                                                        add_notification(containers, f"Tool Result: {result_text}")
                                                    else:
                                                        logger.info(f"Tool Result: {status}")
                                                        add_notification(containers, f"Tool Result: {status}")                                                    
                                                
                                                # text 
                                                elif 'text' in content_item:
                                                    result = content_item['text']
                                                    logger.info(f"Message text: {result}")
                                                    
                                        except (KeyError, IndexError, TypeError) as e:
                                            logger.warning(f"Error processing message content: {e}, data_json: {data_json}")
                                            continue
                                    else:
                                        logger.info(f"DEBUG: data_json type: {type(data_json)}, keys: {data_json.keys() if isinstance(data_json, dict) else 'Not a dict'}")
                                        logger.info(f"{data_json}")
                                else: # langgraph   
                                    logger.info(f"DEBUG: data_json type: {type(data_json)}")
                                    logger.info(f"DEBUG: data_json content: {str(data_json)}...")
                                    
                                    # if 'result' in data_json:
                                    #     agent_result = data_json['result']
                                    #     logger.info(f"agent_result: {agent_result}")
                                    #     message = agent_result.message
                                    #     content = message.get('content', [])
                                    #     result = content[0].get('text', '')
                                    #     logger.info(f"result: {result}")
                                        
                                    parsed_data_json = data_json
                                    
                                    if isinstance(data_json, str):
                                        logger.info(f"data_json is string, attempting to parse...")
                                        try:
                                            parsed_data_json = json.loads(data_json)
                                            logger.info(f"Successfully parsed string data_json to dict using json.loads")
                                        except json.JSONDecodeError:
                                            try:
                                                parsed_data_json = ast.literal_eval(data_json)
                                                logger.info(f"Successfully parsed string data_json to dict using ast.literal_eval")
                                            except (ValueError, SyntaxError) as e:
                                                logger.info(f"ast.literal_eval failed: {e}")
                                                try:
                                                    parsed_data_json = eval(data_json)
                                                    logger.info(f"Successfully parsed string data_json to dict using eval")
                                                except Exception as eval_error:
                                                    logger.info(f"All parsing methods failed: {eval_error}")
                                                    logger.info(f"data_json content: {data_json[:500]}...")
                                                    continue
                                    elif isinstance(data_json, dict):
                                        logger.info(f"data_json is already a dict")
                                        parsed_data_json = data_json
                                    else:
                                        logger.info(f"data_json is neither string nor dict: {type(data_json)}")
                                        continue
                                    
                                    if isinstance(parsed_data_json, dict) and 'messages' in parsed_data_json:
                                        messages = parsed_data_json['messages']
                                        logger.info(f"messages: {messages}")

                                        for message in messages:
                                            if isinstance(message, AIMessage):
                                                result += message.content
                                                logger.info(f"AI Message: {message.content}")
                                                containers['result'].markdown(message.content)
                                            elif isinstance(message, HumanMessage):
                                                result += message.content
                                                logger.info(f"Human Message: {message.content}")
                                                containers['result'].markdown(message.content)
                                            elif isinstance(message, ToolMessage):
                                                result += message.content
                                                logger.info(f"Tool Message: {message.content}")
                                                add_notification(containers, f"Tool Message: {message.content}")
                                            else:
                                                logger.info(f"Unknown message type: {type(message)}")
                                    else:
                                        logger.info(f"No messages found in the response: {parsed_data_json}")
                                        
                            except json.JSONDecodeError:
                                logger.info(f"Not JSON: {data}")
        
        return result
        
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Docker container connection failed: {str(e)}"
        logger.error(error_msg)
        return f"Error: Docker container is not running or not accessible at {destination}. Please start the Docker container first."
        
    except requests.exceptions.Timeout as e:
        error_msg = f"Request timeout: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"
        
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON response from Docker container: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Raw response: {response.text}")
        return f"Error: {error_msg}"
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg)
        return f"Error: {error_msg}"