"""Browser automation script using Amazon Bedrock AgentCore and Nova Act.

This script demonstrates AI-powered web automation by:
- Initializing a browser session through Amazon Bedrock AgentCore
- Connecting to Nova Act for natural language web interactions
- Performing automated searches and data extraction using browser

Source: https://github.com/awslabs/amazon-bedrock-agentcore-samples/blob/main/01-tutorials/05-AgentCore-tools/02-Agent-Core-browser-tool/01-browser-with-NovaAct/02_agentcore-browser-tool-live-view-with-nova-act.ipynb
"""

from bedrock_agentcore.tools.browser_client import browser_session
from nova_act import NovaAct
from rich.console import Console
import logging
import sys
import json
import boto3
import os

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("rag")

def load_config():
    config = None
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    return config

config = load_config()

bedrock_region = config['region']
projectName = config['projectName']

console = Console()

starting_page = "https://www.amazon.com"

# api key to get weather information in agent
secretsmanager = boto3.client(
    service_name='secretsmanager',
    region_name=bedrock_region
)

# api key to use nova act
nova_act_key = ""
try:
    get_nova_act_api_secret = secretsmanager.get_secret_value(
        SecretId=f"nova-act-{projectName}"
    )
    #print('get_nova_act_api_secret: ', get_nova_act_api_secret)
    secret_string = get_nova_act_api_secret['SecretString']
    
    # Try to parse as JSON first
    try:
        secret = json.loads(secret_string)
        if "nova_act_api_key" in secret:
            nova_act_key = secret['nova_act_api_key']
        else:
            # If no JSON structure, use the string directly
            nova_act_key = secret_string
    except json.JSONDecodeError:
        # If not JSON, use the string directly
        nova_act_key = secret_string
    
    print('nova_act_api_key loaded successfully')
    print(f'Secret string length: {len(secret_string)}')
    print(f'First 10 chars: {secret_string[:10]}...')

except Exception as e: 
    logger.info(f"nova act credential is required: {e}")
    # raise e
    pass

def browser_with_nova_act(prompt):
    """Run browser automation with Nova Act without viewer."""
    result = None  # Initialize result variable
    
    try:
        # Step 1: Create browser session
        with browser_session(bedrock_region) as client:
            ws_url, headers = client.generate_ws_headers()

            # Step 2: Use Nova Act
            console.print(f"\n[cyan]Executing NovaAct with prompt: {prompt}[/cyan]")
            
            print(f"NovaAct API key length: {len(nova_act_key) if nova_act_key else 0}")
            print(f"NovaAct API key set: {bool(nova_act_key)}")
            
            with NovaAct(
                cdp_endpoint_url=ws_url,
                cdp_headers=headers,
                preview={"playwright_actuation": True},
                nova_act_api_key=nova_act_key,
                starting_page=starting_page,
            ) as nova_act:
                print(f"Executing NovaAct with prompt: {prompt}")
                
                # Perform the search action
                search_result = nova_act.act(prompt)
                print(f"Search result type: {type(search_result)}")
                print(f"Search result: {search_result}")
                
                # Create a simple result message
                final_result = f"Successfully searched for '{prompt}' on Amazon. The search results are now visible in the browser. You can view the products, prices, and descriptions in the browser window."
                
                result = final_result
                
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        result = f"Browser search failed: {str(e)}"
    
    # Ensure we always return a string
    if result is None:
        result = "Browser search completed without result"
    elif not isinstance(result, str):
        result = str(result)
    
    return result


if __name__ == "__main__":
    result = browser_with_nova_act(
        prompt="Go to Amazon.com and search for coffee maker"
    )
    
    console.print(f"\n[bold green]Nova Act Result:[/bold green] {result}")