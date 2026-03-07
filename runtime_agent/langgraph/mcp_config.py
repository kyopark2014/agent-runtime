import logging
import sys
import os
import boto3
import utils

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("mcp-config")

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")

config = utils.load_config()
logger.info(f"config: {config}")
region = config["region"] if "region" in config else "us-west-2"
projectName = config["projectName"] if "projectName" in config else "mcp"

workingDir = os.path.dirname(os.path.abspath(__file__))
logger.info(f"workingDir: {workingDir}")

mcp_user_config = {}    

def get_agent_runtime_arn(mcp_type: str):
    #logger.info(f"mcp_type: {mcp_type}")
    agent_runtime_name = f"{projectName.lower().replace('-', '_')}_{mcp_type.replace('-', '_')}"
    logger.info(f"agent_runtime_name: {agent_runtime_name}")
    client = boto3.client('bedrock-agentcore-control', region_name=region)
    response = client.list_agent_runtimes(
        maxResults=100
    )
    logger.info(f"response: {response}")
    
    agentRuntimes = response['agentRuntimes']
    for agentRuntime in agentRuntimes:
        if agentRuntime["agentRuntimeName"] == agent_runtime_name:
            logger.info(f"agent_runtime_name: {agent_runtime_name}, agentRuntimeArn: {agentRuntime["agentRuntimeArn"]}")
            return agentRuntime["agentRuntimeArn"]
    return None

def load_config(mcp_type):
    global bearer_token, gateway_url

    if mcp_type == "aws document":
        mcp_type = 'aws_documentation'

    if mcp_type == "kb-retriever":   # use agentcore runtime mcp
        agent_arn = get_agent_runtime_arn(mcp_type)
        logger.info(f"mcp_type: {mcp_type}, agent_arn: {agent_arn}")
        if agent_arn is None:
            logger.warning(f"Agent runtime for '{mcp_type}' not found. Skipping MCP server. Ensure agent_runtime_{mcp_type.replace('-', '_')} is deployed.")
            return None
        encoded_arn = agent_arn.replace(':', '%3A').replace('/', '%2F')
        
        mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
        
        return {
            "mcpServers": {
                "kb-retriever": {
                    "type": "streamable_http",
                    "url": mcp_url,
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"
                    }
                }
            }
        }

    elif mcp_type == "use-aws":
        agent_arn = get_agent_runtime_arn(mcp_type)
        logger.info(f"mcp_type: {mcp_type}, agent_arn: {agent_arn}")
        if agent_arn is None:
            logger.warning(f"Agent runtime for '{mcp_type}' not found. Skipping MCP server. Ensure agent_runtime_{mcp_type.replace('-', '_')} is deployed.")
            return None
        encoded_arn = agent_arn.replace(':', '%3A').replace('/', '%2F')
        
        mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
        
        return {
            "mcpServers": {
                "use_aws": {
                    "type": "streamable_http",
                    "url": mcp_url,
                    "headers": {
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"
                    }
                }
            }
        }    
    
    elif mcp_type == "aws_documentation":
        return {
            "mcpServers": {
                "awslabs.aws-documentation-mcp-server": {
                    "command": "uvx",
                    "args": ["awslabs.aws-documentation-mcp-server@latest"],
                    "env": {
                        "FASTMCP_LOG_LEVEL": "ERROR"
                    }
                }
            }
        }
        
    elif mcp_type == "사용자 설정":
        return mcp_user_config
    
    else:
        return {"mcpServers": {}}

def load_selected_config(mcp_servers: dict):
    logger.info(f"mcp_servers: {mcp_servers}")
    
    loaded_config = {}
    for server in mcp_servers:
        config = load_config(server)        
        if config:
            loaded_config.update(config["mcpServers"])
    return {
        "mcpServers": loaded_config
    }
