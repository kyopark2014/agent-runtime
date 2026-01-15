import asyncio
import os
import json
import boto3
import requests
import httpx
import logging
import sys

from datetime import datetime, timezone
from botocore.auth import SigV4Auth as BotocoreSigV4Auth
from botocore.awsrequest import AWSRequest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from urllib.parse import urlparse
            
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

def get_sigv4_headers(method: str, url: str, body: bytes = None, region: str = None) -> dict:
    """Generate SigV4 authentication headers for HTTP request"""
    if region is None:
        region = config['region']
    
    # Get AWS credentials for SigV4 signing
    boto_session = boto3.Session()
    credentials = boto_session.get_credentials().get_frozen_credentials()
    
    # Parse URL
    from urllib.parse import urlparse
    parsed_url = urlparse(url)
    host = parsed_url.netloc
    path = parsed_url.path + ('?' + parsed_url.query if parsed_url.query else '')
    
    # Generate timestamp for request
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    
    # Create AWS request for signing
    headers = {
        'host': host,
        'x-amz-date': timestamp,
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream'
    }
    
    if body:
        headers['Content-Length'] = str(len(body))
    
    request = AWSRequest(
        method=method,
        url=url,
        headers=headers,
        data=body
    )
    
    # Sign the request with SigV4
    auth = BotocoreSigV4Auth(credentials, "bedrock-agentcore", region)
    auth.add_auth(request)
    
    # Build headers dict
    signed_headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/event-stream',
        'X-Amz-Date': timestamp,
        'Authorization': request.headers['Authorization']
    }
    
    # Add security token if present
    if credentials.token:
        signed_headers['X-Amz-Security-Token'] = credentials.token
    
    return signed_headers

# Create a custom httpx event hook that signs requests with SigV4
async def sign_request(request: httpx.Request) -> None:
    """Sign the request with AWS SigV4 including the body"""
    # Get credentials
    boto_session = boto3.Session()
    credentials = boto_session.get_credentials().get_frozen_credentials()
    
    # Parse URL
    parsed_url = urlparse(str(request.url))
    host = parsed_url.netloc
    
    # Generate timestamp
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    
    # Read request body if available
    body = None
    if request.content:
        if isinstance(request.content, bytes):
            body = request.content
        else:
            # Try to read the body asynchronously
            try:
                body = await request.aread()
                # Reset the stream so it can be read again
                if hasattr(request, '_content'):
                    request._content = body
            except Exception:
                # If we can't read the body, sign without it
                pass
    
    # Create AWS request headers
    aws_headers = {
        'host': host,
        'x-amz-date': timestamp,
        'Content-Type': request.headers.get('Content-Type', 'application/json'),
        'Accept': request.headers.get('Accept', 'application/json, text/event-stream')
    }
    
    if body:
        aws_headers['Content-Length'] = str(len(body))
    
    # Create AWS request for signing
    aws_request = AWSRequest(
        method=request.method,
        url=str(request.url),
        headers=aws_headers,
        data=body
    )
    
    # Sign the request
    auth = BotocoreSigV4Auth(credentials, "bedrock-agentcore", region)
    auth.add_auth(aws_request)
    
    # Update request headers
    request.headers['X-Amz-Date'] = timestamp
    request.headers['Authorization'] = aws_request.headers['Authorization']
    
    if credentials.token:
        request.headers['X-Amz-Security-Token'] = credentials.token

async def main():
    agent_arn = config['agent_runtime_arn']
    region = config['region']
                    
    encoded_arn = agent_arn.replace(':', '%3A').replace('/', '%2F')
    
    # Try different endpoint URLs based on common patterns
    mcp_url = f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    logging.info(f"MCP URL: {mcp_url}")

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
    
    # Generate SigV4 headers for the request
    headers = get_sigv4_headers("POST", mcp_url, request_body.encode('utf-8'), region)
    logging.info(f"Headers: {headers}")
    
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
        logging.info("1. Attempting streamable_http_client connection...")
                
        # Use event hooks for signing
        http_client = httpx.AsyncClient(
            timeout=120.0,
            event_hooks={'request': [sign_request]}
        )
        
        async with streamable_http_client(mcp_url, http_client=http_client, terminate_on_close=False) as (
            read_stream, write_stream, _):
            
            logging.info("2. streamable_http_client connection successful!")
            logging.info("3. Creating ClientSession...")
            
            async with ClientSession(read_stream, write_stream) as session:
                logging.info("4. ClientSession created successfully!")
                logging.info("5. Calling session.initialize()...")
                
                # Add timeout for initialize
                try:
                    await asyncio.wait_for(session.initialize(), timeout=60)
                    logging.info("6. session.initialize() successful!")
                except asyncio.TimeoutError:
                    logging.info("session.initialize() timeout (60s)")
                    return
                except Exception as init_error:
                    logging.info(f"session.initialize() failed: {init_error}")
                    logging.info(f"Error type: {type(init_error)}")
                    return
                
                logging.info("7. Calling session.list_tools()...")
                
                # Add timeout for list_tools
                try:
                    tool_result = await asyncio.wait_for(session.list_tools(), timeout=60)
                    logging.info(f"8. session.list_tools() successful!")
                    logging.info(f"\nAvailable tools: {len(tool_result.tools)}")
                    for tool in tool_result.tools:
                        logging.info(f"  - {tool.name}: {tool.description[:100]}...")
                except asyncio.TimeoutError:
                    logging.info("session.list_tools() timeout (60s)")
                    return
                except Exception as tools_error:
                    logging.info(f"session.list_tools() failed: {tools_error}")
                    logging.info(f"Error type: {type(tools_error)}")
                    return
                                
                # Test retrieve function
                logging.info("\n=== Testing retrieve function ===")
                params = {
                    "keyword": "보일러 에러 코드"
                }
                
                try:
                    result = await asyncio.wait_for(session.call_tool("retrieve", params), timeout=30)
                    logging.info(f"retrieve result: {result}")
                    
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
