import asyncio
import os
import json
import boto3
import requests
import sys
import logging

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

# Setup logging for Knowledge Base functions
logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("installer")

def load_config():
    config = None
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)    
    return config

config = load_config()

projectName = config['projectName']
region = config['region']

def create_cognito_bearer_token(config):
    """Get a fresh bearer token from Cognito"""
    try:
        cognito_config = config['cognito']
        region = config['region']
        client_id = cognito_config['client_id']
        username = cognito_config['test_username']
        password = cognito_config['test_password']
        
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
        
        logging.info("Successfully obtained fresh Cognito tokens")
        return access_token
        
    except Exception as e:
        logging.info(f"Error getting Cognito token: {e}")
        return None

def get_bearer_token():
    try:
        secret_name = config['secret_name']
        session = boto3.Session()
        client = session.client('secretsmanager', region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        bearer_token_raw = response['SecretString']
        
        token_data = json.loads(bearer_token_raw)        
        if 'bearer_token' in token_data:
            bearer_token = token_data['bearer_token']
            return bearer_token
        else:
            logging.info("No bearer token found in secret manager")
            return None
    
    except Exception as e:
        logging.info(f"Error getting stored token: {e}")
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
            logging.info(f"Bearer token updated in secret manager with key: {secret_value['bearer_key']}")
        except client.exceptions.ResourceNotFoundException:
            # Secret doesn't exist, create it
            client.create_secret(
                Name=secret_name,
                SecretString=secret_string,
                Description="MCP Server Cognito credentials with bearer key and token"
            )
            logging.info(f"Bearer token created in secret manager with key: {secret_value['bearer_key']}")
            
    except Exception as e:
        logging.info(f"Error saving bearer token: {e}")
        # Continue execution even if saving fails

async def main():
    agent_arn = config['agent_runtime_arn']
    region = config['region']
    
    # Check if agent_arn is properly configured
    if not agent_arn:
        logging.info("Error: agent_runtime_arn is not configured in config.json")
        logging.info("Please set the agent_runtime_arn value in config.json to your AWS Bedrock Agent Runtime ARN")
        return
    
    # Check basic AWS connectivity
    bearer_token = get_bearer_token()
    logging.info(f"Bearer token from secret manager: {bearer_token[:100] if bearer_token else 'None'}...")
    #logging.info(f"Bearer token from secret manager: {bearer_token}")

    if not bearer_token:    
        # Try to get fresh bearer token from Cognito
        logging.info("No bearer token found in secret manager, getting fresh bearer token from Cognito...")
        bearer_token = create_cognito_bearer_token(config)
        logging.info(f"Bearer token from cognito: {bearer_token[:100] if bearer_token else 'None'}...")
        
        if bearer_token:
            secret_name = config['secret_name']
            save_bearer_token(secret_name, bearer_token)
        else:
            logging.info("Failed to get bearer token from Cognito. Exiting.")
            return
                
    encoded_arn = agent_arn.replace(':', '%3A').replace('/', '%2F')
    
    # Try different endpoint URLs based on common patterns
    mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }

    # Prepare the request body for MCP initialization
    request_body = json.dumps({
        "jsonrpc": "2.0",
        "id": "1",
        "method": "initialize", 
        "params": {
            "protocolVersion": "2024-11-05", 
            "capabilities": {}, 
            "clientInfo": {
                "name": "test-client", 
                "version": "1.0.0"
            }
        }
    })
    
    successful_url = None
    successful_headers = None
    
    # url test
    try:
        response = requests.post(
            mcp_url,
            headers=headers,
            data=request_body,
            timeout=30
        )
        
        if response.status_code == 200:
            logging.info("Success!")
            successful_url = mcp_url
            successful_headers = headers            
        else:
            logging.info(f"Error: {response.status_code}")
            logging.info(f"Response body: {response.text}")
            if response.status_code == 401 or response.status_code == 403:
                error_msg = "401 Unauthorized" if response.status_code == 401 else "403 Forbidden"
                logging.info(f"{error_msg} - Token may be expired, trying to get fresh token from Cognito...")
                # Try to get fresh bearer token from Cognito
                fresh_bearer_token = create_cognito_bearer_token(config)
                if fresh_bearer_token:
                    logging.info("Successfully obtained fresh token, updating headers and retrying...")
                    # Update headers with fresh token
                    headers["Authorization"] = f"Bearer {fresh_bearer_token}"
                    # Save the fresh token
                    secret_name = config['secret_name']
                    save_bearer_token(secret_name, fresh_bearer_token)
                    
                    # Retry the request with fresh token
                    response = requests.post(
                        mcp_url,
                        headers=headers,
                        data=request_body,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        logging.info("Success with fresh token!")
                        successful_url = mcp_url
                        successful_headers = headers
                    else:
                        logging.info(f"Still getting error with fresh token: {response.status_code}")
                        logging.info(f"Response body: {response.text}")
                        return
                else:
                    logging.info("Failed to get fresh token from Cognito")
                    return
            else:
                return
    except Exception as e:
        logging.info(f"Connection failed: {e}")
        return

    if not successful_url or not successful_headers:
        logging.info("Failed to establish successful connection. Exiting.")
        return

    mcp_url = successful_url
    headers = successful_headers

    try:
        logging.info(f"\n=== Attempting MCP Connection ===")
        logging.info(f"URL: {mcp_url}")
        logging.info(f"Timeout: 120 seconds")
        
        # Now try the MCP connection with better error handling
        logging.info("1. Attempting streamablehttp_client connection...")
        async with streamablehttp_client(mcp_url, headers, timeout=120, terminate_on_close=False) as (
            read_stream, write_stream, _):
            
            logging.info("2. streamablehttp_client connection successful!")
            logging.info("3. Creating ClientSession...")
            
            async with ClientSession(read_stream, write_stream) as session:
                logging.info("4. ClientSession created successfully!")
                logging.info("5. Calling session.initialize()...")
                
                # Add timeout for initialize
                try:
                    await asyncio.wait_for(session.initialize(), timeout=30)
                    logging.info("6. session.initialize() successful!")
                except asyncio.TimeoutError:
                    logging.info("session.initialize() timeout (30s)")
                    return
                except Exception as init_error:
                    logging.info(f"session.initialize() failed: {init_error}")
                    return
                
                logging.info("7. Calling session.list_tools()...")
                
                # Add timeout for list_tools
                try:
                    tool_result = await asyncio.wait_for(session.list_tools(), timeout=30)
                    logging.info(f"8. session.list_tools() successful!")
                    logging.info(f"\nAvailable tools: {len(tool_result.tools)}")
                    for tool in tool_result.tools:
                        logging.info(f"  - {tool.name}: {tool.description[:100]}...")
                except asyncio.TimeoutError:
                    logging.info("session.list_tools() timeout (30s)")
                    return
                except Exception as tools_error:
                    logging.info(f"session.list_tools() failed: {tools_error}")
                    return
                                
                # Test retrieve function
                logging.info("\n=== Testing retrieve function ===")
                params = {
                    "keyword": "보일러 에러 코드"
                }
                
                logging.info("8. retrieve 호출 중...")
                try:
                    result = await asyncio.wait_for(session.call_tool("retrieve", params), timeout=30)
                    logging.info(f"9. retrieve 성공!")
                    logging.info(f"Result: {result}")
                    
                    if hasattr(result, 'content') and result.content:
                        for content in result.content:
                            if hasattr(content, 'text'):
                                logging.info(f"Content: {content.text}")
                    else:
                        logging.info("No content in result")
                except asyncio.TimeoutError:
                    logging.info("retrieve function timeout (30s)")
                except Exception as retrieve_error:
                    logging.info(f"retrieve function failed: {retrieve_error}")
                
                logging.info("\n=== MCP Connection Test Complete ===")
                                
    except Exception as e:
        logging.info(f"MCP connection failed: {e}")
        logging.info(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        
if __name__ == "__main__":
    asyncio.run(main())
