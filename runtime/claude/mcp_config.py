import logging
import sys
import json
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

bearer_token = None

def get_cognito_config(cognito_config):    
    user_pool_name = cognito_config.get('user_pool_name')
    user_pool_id = cognito_config.get('user_pool_id')
    if not user_pool_name:        
        user_pool_name = 'mcp-agentcore-user-pool'
        print(f"No user pool name found in config, using default user pool name: {user_pool_name}")
        cognito_config.setdefault('user_pool_name', user_pool_name)

        cognito_client = boto3.client('cognito-idp', region_name=region)
        response = cognito_client.list_user_pools(MaxResults=60)
        for pool in response['UserPools']:
            if pool['Name'] == user_pool_name:
                user_pool_id = pool['Id']
                print(f"Found cognito user pool: {user_pool_id}")
                cognito_config['user_pool_id'] = user_pool_id
                break

    client_name = cognito_config.get('client_name')
    if not client_name:        
        client_name = f"mcp-agentcore-client"
        print(f"No client name found in config, using default client name: {client_name}")
        cognito_config['client_name'] = client_name

    client_id = cognito_config.get('client_id')
    if not client_id:
        response = cognito_client.list_user_pool_clients(UserPoolId=user_pool_id)
        for client in response['UserPoolClients']:
            if client['ClientName'] == client_name:
                client_id = client['ClientId']
                print(f"Found cognito client: {client_id}")
                cognito_config['client_id'] = client_id     
                break

    username = cognito_config.get('test_username')
    password = cognito_config.get('test_password')
    if not username or not password:
        print("No test username found in config, using default username and password. Please check config.json and update the test username and password.")
        username = f"mcp-test-user@example.com"
        password = "TestPassword123!"        
        cognito_config['test_username'] = username
        cognito_config['test_password'] = password
    
    return cognito_config

def get_agent_runtime_arn(mcp_type: str):
    #logger.info(f"mcp_type: {mcp_type}")
    agent_runtime_name = f"mcp_{mcp_type.replace('-', '_')}"
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

def get_bearer_token_from_secret_manager(secret_name):
    try:
        session = boto3.Session()
        client = session.client('secretsmanager', region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        bearer_token_raw = response['SecretString']
        
        token_data = json.loads(bearer_token_raw)        
        if 'bearer_token' in token_data:
            bearer_token = token_data['bearer_token']
            return bearer_token
        else:
            logger.info("No bearer token found in secret manager")
            return None
    
    except Exception as e:
        logger.info(f"Error getting stored token: {e}")
        return None

def create_cognito_bearer_token(config):
    """Get a fresh bearer token from Cognito"""
    try:
        region = config['region']

        cognito_config = config.get('cognito', {})
        if not cognito_config:
            cognito_config = get_cognito_config(cognito_config)
            if 'cognito' not in config:
                config['cognito'] = {}
            config['cognito'].update(cognito_config)

            # save config            
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            logger.info(f"Cognito config updated in config.json: {cognito_config}")

        client_name = cognito_config['client_name']
        username = cognito_config['test_username']
        password = cognito_config['test_password']

        cognito_client = boto3.client('cognito-idp', region_name=region)
        try:
            response = cognito_client.list_user_pools(MaxResults=10)
            for pool in response['UserPools']:
                logger.info(f"Existing User Pool found: {pool['Id']}")
                user_pool_id = pool['Id']

                client_response = cognito_client.list_user_pool_clients(UserPoolId=user_pool_id)
                for client in client_response['UserPoolClients']:
                    if client['ClientName'] == client_name:
                        client_id = client['ClientId']
                        logger.info(f"Existing App client found: {client_id}")

                        # Update config.json with client_id
                        try:
                            config['cognito']['client_id'] = client_id
                            config_file = "config.json"
                            with open(config_file, "w") as f:
                                json.dump(config, f, indent=2)
                            logger.info(f"Client ID updated in config.json: {client_id}")
                        except Exception as e:
                            logger.info(f"Warning: Failed to update config.json with client_id: {e}")
        except Exception as e:
            logger.error(f"Failed to check User Pool list: {e}")
    
        # Create Cognito client
        client = boto3.client('cognito-idp', region_name=region)
        
        # Authenticate and get tokens
        response = client.initiate_auth(
            ClientId=client_id,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': username,
                'PASSWORD': password
            }
        )
        
        auth_result = response['AuthenticationResult']
        access_token = auth_result['AccessToken']
        # id_token = auth_result['IdToken']
        
        logger.info("Successfully obtained fresh Cognito tokens")
        return access_token
        
    except Exception as e:
        logger.info(f"Error getting Cognito token: {e}")
        return None

def save_bearer_token(secret_name, bearer_token):
    try:        
        session = boto3.Session()
        client = session.client('secretsmanager', region_name=region)
        
        # Create secret value with bearer_key 
        secret_value = {
            "bearer_key": "mcp_server_bearer_token",
            "bearer_token": bearer_token
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
            logger.info(f"Bearer token updated in secret manager with key: {secret_value['bearer_key']}")
        except client.exceptions.ResourceNotFoundException:
            # Secret doesn't exist, create it
            client.create_secret(
                Name=secret_name,
                SecretString=secret_string,
                Description="MCP Server Cognito credentials with bearer key and token"
            )
            logger.info(f"Bearer token created in secret manager with key: {secret_value['bearer_key']}")
            
    except Exception as e:
        logger.info(f"Error saving bearer token: {e}")
        # Continue execution even if saving fails

def retrieve_bearer_token(secret_name):
    bearer_token = get_bearer_token_from_secret_manager(secret_name)
    logger.info(f"Bearer token from secret manager: {bearer_token[:100] if bearer_token else 'None'}...")

    # verify bearer token
    try:
        client = boto3.client('cognito-idp', region_name=region)
        response = client.get_user(
            AccessToken=bearer_token
        )
        logger.info(f"response: {response}")

        username = response['Username']
        logger.info(f"Username: {username}")

    except Exception as e:
        logger.info(f"Error verifying bearer token: {e}")

        # Try to get fresh bearer token from Cognito
        logger.info("Error verifying bearer token, getting fresh bearer token from Cognito...")
        bearer_token = create_cognito_bearer_token(config)
        logger.info(f"Bearer token from cognito: {bearer_token[:100] if bearer_token else 'None'}...")
        
        if bearer_token:
            save_bearer_token(secret_name, bearer_token)
        else:
            logger.info("Failed to get bearer token from Cognito. Exiting.")
            return {}
        
    return bearer_token

def load_config(mcp_type):
    global bearer_token, gateway_url

    if mcp_type == "aws document":
        mcp_type = 'aws_documentation'

    if mcp_type == "kb-retriever":   # use agentcore runtime mcp
        agent_arn = get_agent_runtime_arn(mcp_type)
        logger.info(f"mcp_type: {mcp_type}, agent_arn: {agent_arn}")
        encoded_arn = agent_arn.replace(':', '%3A').replace('/', '%2F')

        secret_name = 'agentcore/credentials' # use prebuilt secret

        if not bearer_token:
            bearer_token = retrieve_bearer_token(secret_name)
            logger.info(f"Bearer token from secret manager: {bearer_token[:100] if bearer_token else 'None'}...")

        return {
            "mcpServers": {
                "kb-retriever": {
                    "type": "streamable_http",
                    "url": f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT",
                    "headers": {
                        "Authorization": f"Bearer {bearer_token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"
                    }
                }
            }
        }
    
    elif mcp_type == "use-aws":
        agent_arn = get_agent_runtime_arn(mcp_type)
        logger.info(f"mcp_type: {mcp_type}, agent_arn: {agent_arn}")
        encoded_arn = agent_arn.replace(':', '%3A').replace('/', '%2F')

        if not bearer_token:
            bearer_token = retrieve_bearer_token(config['secret_name'])
            logger.info(f"Bearer token from secret manager: {bearer_token[:100] if bearer_token else 'None'}...")

        return {
            "mcpServers": {
                "use_aws": {
                    "type": "streamable_http",
                    "url": f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT",
                    "headers": {
                        "Authorization": f"Bearer {bearer_token}",
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
