import boto3
import json
import uuid
import os
import logging
import sys
import requests

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

    langgraph_arn_path = os.path.join(script_dir, "..", 'langgraph', "agent_runtime_arn.json")
    with open(langgraph_arn_path, "r", encoding="utf-8") as f:
        langgraph_agent_runtime_arn = json.load(f)['agent_runtime_arn']
        logger.info(f"langgraph_agent_runtime_arn: {langgraph_agent_runtime_arn}")
    
    strands_arn_path = os.path.join(script_dir, "..", 'strands', "agent_runtime_arn.json")
    with open(strands_arn_path, "r", encoding="utf-8") as f:
        strands_agent_runtime_arn = json.load(f)['agent_runtime_arn']
        logger.info(f"strands_agent_runtime_arn: {strands_agent_runtime_arn}")
    
    return config, langgraph_agent_runtime_arn, strands_agent_runtime_arn

config, langgraph_agent_runtime_arn, strands_agent_runtime_arn = load_config()

bedrock_region = config['region']
accountId = config['accountId']
projectName = config['projectName']

def run_agent(prompt, agent_type, mcp_servers, model_name):
    payload = json.dumps({
        "prompt": prompt,
        "mcp_servers": mcp_servers,
        "model_name": model_name
    })

    if agent_type == 'LangGraph':
        agent_runtime_arn = langgraph_agent_runtime_arn
    else: 
        agent_runtime_arn = strands_agent_runtime_arn

    logger.info(f"agent_runtime_arn: {agent_runtime_arn}")

    agent_core_client = boto3.client('bedrock-agentcore', region_name=bedrock_region)
    response = agent_core_client.invoke_agent_runtime(
        agentRuntimeArn=agent_runtime_arn,
        runtimeSessionId=str(uuid.uuid4()),
        payload=payload,
        qualifier="DEFAULT"
    )

    response_body = response['response'].read()
    response_data = json.loads(response_body)
    logger.info(f"Agent Response: {response_data}")

    return response_data.get("result", "")

def run_agent_in_docker(prompt, mcp_servers, model_name):
    payload = json.dumps({
        "prompt": prompt,
        "mcp_servers": mcp_servers,
        "model_name": model_name,
    })

    headers = {
        "Content-Type": "application/json"
    }   
    destination = f"http://localhost:8080/invocations"

    try:
        logger.info(f"Sending request to Docker container at {destination}")
        logger.info(f"Payload: {payload}")
        
        response = requests.post(destination, headers=headers, data=payload, timeout=30)
        
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response headers: {response.headers}")
        logger.info(f"Response text: {response.text}")
        
        if response.status_code != 200:
            error_msg = f"Docker container returned status code {response.status_code}: {response.text}"
            logger.error(error_msg)
            return f"Error: {error_msg}"
        
        if not response.text.strip():
            error_msg = "Docker container returned empty response"
            logger.error(error_msg)
            return f"Error: {error_msg}"
        
        response_data = response.json()
        logger.info(f"Agent Response: {response_data}")

        return response_data.get("result", "")
        
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
