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

console = Console()

starting_page = "https://www.amazon.com"
region="us-west-2"

def browser_with_nova_act(prompt):
    result = None  # Initialize result variable
    with browser_session(region) as client:
        ws_url, headers = client.generate_ws_headers()
        try:
            with NovaAct(
                cdp_endpoint_url=ws_url,
                cdp_headers=headers,
                preview={"playwright_actuation": True},
                # nova_act_api_key=NOVA_ACT_API_KEY,
                starting_page=starting_page,
            ) as nova_act:
                result = nova_act.act(prompt)
        except Exception as e:
            console.print(f"NovaAct error: {e}")
        return result


if __name__ == "__main__":
    
    result = browser_with_nova_act(
        prompt="Search for coffee maker and get the details of the lowest priced one on the first page"
    )
    
    if result is not None:
        try:
            console.print(f"\n[cyan]Response:[/cyan] {result.response}")
        except AttributeError:
            console.print(f"\n[cyan]Response:[/cyan] {result}")
        console.print(f"\n[bold green]Nova Act Result:[/bold green] {result}")
    else:
        console.print(f"\n[red]No result returned from Nova Act[/red]")