import traceback
import boto3
import os
import re
import uuid
import info 
import utils
from urllib import parse

from langchain_aws import ChatBedrock
from botocore.config import Config
from langchain_core.prompts import ChatPromptTemplate
from langchain.docstore.document import Document
from tavily import TavilyClient  

import logging
import sys

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("chat")

userId = uuid.uuid4().hex
map_chain = dict() 

config = utils.load_config()
print(f"config: {config}")

bedrock_region = config["region"] if "region" in config else "us-west-2"
projectName = config["projectName"] if "projectName" in config else "mcp-rag"
accountId = config["accountId"] if "accountId" in config else None

if accountId is None:
    raise Exception ("No accountId")
region = config["region"] if "region" in config else "us-west-2"
logger.info(f"region: {region}")

numberOfDocs = 4

MSG_LENGTH = 100    

# Default model
model_name = "Claude 3.5 Sonnet"
model_type = "claude"
models = info.get_model_info(model_name)
model_id = models[0]["model_id"]

aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
aws_session_token = os.environ.get('AWS_SESSION_TOKEN')
aws_region = os.environ.get('AWS_DEFAULT_REGION', 'us-west-2')

# Default reasoning mode
reasoning_mode = 'Disable'
debug_mode = 'Disable'
user_id = None

def update(modelName, debugMode, userId):
    global model_name, models, model_type, model_id, debug_mode, user_id

    if modelName is not model_name:
        model_name = modelName
        logger.info(f"modelName: {modelName}")

        models = info.get_model_info(model_name)
        model_type = models[0]["model_type"]
        model_id = models[0]["model_id"]
        logger.info(f"model_id: {model_id}")
        logger.info(f"model_type: {model_type}")
    
    if debugMode is not debug_mode:
        debug_mode = debugMode
        logger.info(f"debugMode: {debugMode}")

    if userId is not user_id:
        user_id = userId
        logger.info(f"user_id: {user_id}")

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
    if aws_access_key and aws_secret_key:
        boto3_bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=bedrock_region,
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            aws_session_token=aws_session_token,
            config=Config(
                retries = {
                    'max_attempts': 30
                }
            )
        )
    else:
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

def print_doc(i, doc):
    if len(doc.page_content)>=100:
        text = doc.page_content[:100]
    else:
        text = doc.page_content
            
    logger.info(f"{i}: {text}, metadata:{doc.metadata}")

def tavily_search(query, k):
    docs = []    
    try:
        tavily_client = TavilyClient(api_key=utils.tavily_key)
        response = tavily_client.search(query, max_results=k)
        # print('tavily response: ', response)
            
        for r in response["results"]:
            name = r.get("title")
            if name is None:
                name = 'WWW'
            
            docs.append(
                Document(
                    page_content=r.get("content"),
                    metadata={
                        'name': name,
                        'url': r.get("url"),
                        'from': 'tavily'
                    },
                )
            )                   
    except Exception as e:
        logger.info(f"Exception: {e}")

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
    
def traslation(chat, text, input_language, output_language):
    system = (
        "You are a helpful assistant that translates {input_language} to {output_language} in <article> tags." 
        "Put it in <result> tags."
    )
    human = "<article>{text}</article>"
    
    prompt = ChatPromptTemplate.from_messages([("system", system), ("human", human)])
    # print('prompt: ', prompt)
    
    chain = prompt | chat    
    try: 
        result = chain.invoke(
            {
                "input_language": input_language,
                "output_language": output_language,
                "text": text,
            }
        )
        
        msg = result.content
        # print('translated text: ', msg)
    except Exception:
        err_msg = traceback.format_exc()
        logger.info(f"error message: {err_msg}")     
        raise Exception ("Not able to request to LLM")

    return msg[msg.find('<result>')+8:len(msg)-9] # remove <result> tag

s3_prefix = 'docs'
s3_image_prefix = 'images'

s3_bucket = config["s3_bucket"] if "s3_bucket" in config else None
if s3_bucket is None:
    raise Exception ("No storage!")

path = config["sharing_url"] if "sharing_url" in config else None
if path is None:
    raise Exception ("No Sharing URL")

def upload_to_s3(file_bytes, file_name):
    """
    Upload a file to S3 and return the URL
    """
    try:
        if aws_access_key and aws_secret_key:
            s3_client = boto3.client(
                service_name='s3',
                region_name=bedrock_region,
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                aws_session_token=aws_session_token,
            )
        else:
            s3_client = boto3.client(
                service_name='s3',
                region_name=bedrock_region,
            )

        # Generate a unique file name to avoid collisions
        #timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        #unique_id = str(uuid.uuid4())[:8]
        #s3_key = f"uploaded_images/{timestamp}_{unique_id}_{file_name}"

        content_type = utils.get_contents_type(file_name)       
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

