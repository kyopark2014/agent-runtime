import boto3 
import logging
import sys
import os
import json
from urllib.parse import quote

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("retrieve")

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")
    
def load_config():
    config = None
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)    
    return config

config = load_config()

bedrock_region = config.get('region', 'us-west-2')
projectName = config.get('projectName')

def get_cloudfront_url():
    cloudfront_url = None
    cloudfront_client = boto3.client('cloudfront', region_name=bedrock_region)
    response = cloudfront_client.list_distributions(MaxItems='10')
    distributions = response.get('DistributionList', {}).get('Items', [])
    for distribution in distributions:
        comment = distribution.get('Comment', '')
        
        if f"CloudFront-for-{projectName}" in comment:
            DomainName = distribution.get('DomainName', '')
            print(f"DomainName: {DomainName}")

            cloudfront_url = f"https://{DomainName}"
            print(f"cloudfront_url: {cloudfront_url}")
            break

    return cloudfront_url

path = get_cloudfront_url()
doc_prefix = "docs/"

def update_knowledge_base_id():
    knowledge_base_id = None
    
    bedrock_agent = boto3.client('bedrock-agent', region_name=bedrock_region)
    response = bedrock_agent.list_knowledge_bases(maxResults=50)
    knowledge_bases = response.get('knowledgeBaseSummaries', [])
    for knowledge_base in knowledge_bases:
        if knowledge_base['name'] == projectName:
            knowledge_base_id = knowledge_base['knowledgeBaseId']

            config['knowledge_base_id'] = knowledge_base_id
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            break
    return knowledge_base_id

knowledge_base_id = update_knowledge_base_id()

number_of_results = 5

bedrock_agent_runtime_client = boto3.client("bedrock-agent-runtime", region_name=bedrock_region)

def retrieve(query: str) -> str:
    response = bedrock_agent_runtime_client.retrieve(
        retrievalQuery={"text": query},
        knowledgeBaseId=knowledge_base_id,
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": number_of_results},
            },
        )
    
    # logger.info(f"response: {response}")
    retrieval_results = response.get("retrievalResults", [])
    # logger.info(f"retrieval_results: {retrieval_results}")

    json_docs = []
    for result in retrieval_results:
        text = url = name = None
        if "content" in result:
            content = result["content"]
            if "text" in content:
                text = content["text"]

        if "location" in result:
            location = result["location"]
            if "s3Location" in location:
                uri = location["s3Location"]["uri"] if location["s3Location"]["uri"] is not None else ""
                
                if path:
                    name = uri.split("/")[-1]
                    encoded_name = quote(name)          
                    url = f"{path}/{doc_prefix}{encoded_name}"
                else:
                    url = uri
                
            elif "webLocation" in location:
                url = location["webLocation"]["url"] if location["webLocation"]["url"] is not None else ""
                name = "WEB"

        json_docs.append({
            "contents": text,              
            "reference": {
                "url": url,                   
                "title": name,
                "from": "RAG"
            }
        })
    logger.info(f"json_docs: {json_docs}")

    return json.dumps(json_docs, ensure_ascii=False)