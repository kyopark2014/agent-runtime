import logging
import sys
import json
import boto3
import os
import s3vector

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("utils")

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")
    
def load_config():
    config = None
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        config = {}
        config['projectName'] = "claude-agent"
        session = boto3.Session()
        bedrock_region = session.region_name

        sts = boto3.client("sts")
        response = sts.get_caller_identity()        
        config['region'] = bedrock_region
        accountId = response["Account"]
        config['accountId'] = accountId
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    
    return config

config = load_config()

bedrock_region = config['region']
projectName = config['projectName']
bedrock_region = config['region']
accountId = config.get('accountId')

# Bucket for Knowledge Base
bucket_name = config.get("bucket_name", "")
logger.info(f"bucket_name: {bucket_name}")

if not bucket_name:
    bucket_name = f"storage-for-{projectName}-{accountId}-{bedrock_region}"
    config['bucket_name'] = bucket_name
    logger.info(f"bucket_name: {bucket_name}")
    
    s3vector.create_bucket(bucket_name, bedrock_region)
    
    # write bucket name
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

# Knowledge Base
knowledge_base_id = config.get('knowledge_base_id', "")
logger.info(f"knowledge_base_id: {knowledge_base_id}")    
if not knowledge_base_id:
    logger.info(f"knowledge_base_id is required.")    
    knowledge_base_name = projectName
    logger.info(f"knowledge_base_name: {knowledge_base_name}")
    s3vector.create_knowledge_base(knowledge_base_name, bedrock_region)

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

def load_mcp_env():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mcp_env_path = os.path.join(script_dir, "mcp.env")
    
    try:
        with open(mcp_env_path, "r", encoding="utf-8") as f:
            mcp_env = json.load(f)
        return mcp_env
    except FileNotFoundError:
        # 파일이 없으면 빈 딕셔너리를 반환
        return {}

def save_mcp_env(mcp_env):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mcp_env_path = os.path.join(script_dir, "mcp.env")
    
    with open(mcp_env_path, "w", encoding="utf-8") as f:
        json.dump(mcp_env, f)

# api key to get weather information in agent
secretsmanager = boto3.client(
    service_name='secretsmanager',
    region_name=bedrock_region
)

def save_secret(secret_name, api_key_name, secret_value):
    try:        
        session = boto3.Session()
        client = session.client('secretsmanager', region_name=bedrock_region)
        
        # Create secret value with bearer_key 
        secret_value = {
            "project_name": projectName,
            api_key_name: secret_value
        }
        
        # Convert to JSON string
        secret_string = json.dumps(secret_value)
        
        # Check if secret already exists
        try:
            client.describe_secret(SecretId=secret_name)
            # Secret exists, update it
            client.put_secret_value(
                SecretId=secret_name,
                SecretString=secret_string
            )
            print(f"update api key for {api_key_name}")
        except client.exceptions.ResourceNotFoundException:
            # Secret doesn't exist, create it
            client.create_secret(
                Name=secret_name,
                SecretString=secret_string,
                Description=f"{api_key_name} of {projectName}"
            )
            print(f"create api key for {api_key_name}")
            
    except Exception as e:
        print(f"Error saving api key: {e}")
        pass

# api key for weather
def get_weather_api_key():
    weather_api_key = ""
    try:
        get_weather_api_secret = secretsmanager.get_secret_value(
            SecretId=f"openweathermap-{projectName}"
        )
        #logger.info('get_weather_api_secret: ', get_weather_api_secret)
        secret = json.loads(get_weather_api_secret['SecretString'])
        #logger.info('secret: ', secret)
        weather_api_key = secret['weather_api_key']

    except Exception as e:
        logger.info(f"Weather API key is required: {e}")
        save_secret(f"openweathermap-{projectName}", "weather_api_key", weather_api_key)
        pass
    
    return weather_api_key

weather_api_key = get_weather_api_key()
logger.info(f"weather_api_key: {weather_api_key}")

def get_tavily_api_key():
    # api key to use Tavily Search
    tavily_key = tavily_api_wrapper = ""
    try:
        get_tavily_api_secret = secretsmanager.get_secret_value(
            SecretId=f"tavilyapikey-{projectName}"
        )
        #logger.info('get_tavily_api_secret: ', get_tavily_api_secret)
        secret = json.loads(get_tavily_api_secret['SecretString'])
        #logger.info('secret: ', secret)
        
        if "tavily_api_key" in secret:
            tavily_key = secret['tavily_api_key']

    except Exception as e: 
        logger.info(f"Tavily credential is required: {e}")
        save_secret(f"tavilyapikey-{projectName}", "tavily_api_key", tavily_key)
        pass

    return tavily_key

tavily_key = get_tavily_api_key()
logger.info(f"tavily_key: {tavily_key}")