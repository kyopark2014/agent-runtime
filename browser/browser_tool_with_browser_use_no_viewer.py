"""
Basic Browser tool usage with Browser-Use SDK
Source: https://github.com/awslabs/amazon-bedrock-agentcore-samples/blob/main/01-tutorials/05-AgentCore-tools/02-Agent-Core-browser-tool/02-browser-with-browserUse/getting_started-agentcore-browser-tool-with-browser-use.ipynb
"""

from bedrock_agentcore.tools.browser_client import BrowserClient
from browser_use import Agent
from browser_use.browser.session import BrowserSession
from browser_use.browser import BrowserProfile
from browser_use.llm import ChatAWSBedrock
from rich.console import Console
from contextlib import suppress
import asyncio
import os

from boto3.session import Session
boto_session = Session()
region = boto_session.region_name

client = BrowserClient(region)
client.start()

console = Console()

# Extract ws_url and headers
ws_url, headers = client.generate_ws_headers()

async def run_browser_task(browser_session: BrowserSession, bedrock_chat: ChatAWSBedrock, task: str) -> None:
    """
    Run a browser automation task using browser_use
    
    Args:
        browser_session: Existing browser session to reuse
        bedrock_chat: Bedrock chat model instance
        task: Natural language task for the agent
    """
    try:
        # Show task execution
        console.print(f"\n[bold blue]🤖 Executing task:[/bold blue] {task}")
        
        # Create and run the agent
        agent = Agent(
            task=task,
            llm=bedrock_chat,
            browser_session=browser_session
        )
        
        # Run with progress indicator
        with console.status("[bold green]Running browser automation...[/bold green]", spinner="dots"):
            await agent.run()
        
        console.print("[bold green]✅ Task completed successfully![/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]❌ Error during task execution:[/bold red] {str(e)}")
        import traceback
        if console.is_terminal:
            traceback.print_exc()

async def main():
    # Create persistent browser session and model
    browser_session = None
    bedrock_chat = None

    try:
        # Create browser profile with headers
        browser_profile = BrowserProfile(
            headers=headers,
            timeout=1500000,  # 150 seconds timeout
        )
        
        # Create a browser session with CDP URL and keep_alive=True for persistence
        browser_session = BrowserSession(
            cdp_url=ws_url,
            browser_profile=browser_profile,
            keep_alive=True,  # Keep browser alive between tasks
            starting_page="https://www.amazon.com"  # Set starting page
        )
        
        # Initialize the browser session
        console.print("[cyan]🔄 Initializing browser session...[/cyan]")
        await browser_session.start()
        
        # Create ChatAWSBedrock with AWS credentials
        bedrock_chat = ChatAWSBedrock(
            model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            aws_region=region,
            aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
            session=boto_session,
            max_tokens=4096,
            temperature=0.1
        )
        
        console.print("[green]✅ Browser session initialized and ready for tasks[/green]\n")

        task = "Go to Amazon.com and search for coffee maker" 

        await run_browser_task(browser_session, bedrock_chat, task)

    finally:
        # Close the browser session
        if browser_session:
            console.print("\n[yellow]🔌 Closing browser session...[/yellow]")
            with suppress(Exception):
                await browser_session.close()
            console.print("[green]✅ Browser session closed[/green]")

if __name__ == "__main__":
    asyncio.run(main())            