import logging
import sys
import os
import pwd 
import asyncio
import langgraph_agent

from bedrock_agentcore.runtime import BedrockAgentCoreApp

logging.basicConfig(
    level=logging.INFO,  
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("streamlit")

try:
    user_info = pwd.getpwuid(os.getuid())
    username = user_info.pw_name
    home_dir = user_info.pw_dir
    logger.info(f"Username: {username}")
    logger.info(f"Home directory: {home_dir}")
except (ImportError, KeyError):
    username = "root"
    logger.info(f"Username: {username}")
    pass  

mcp_options = [
    "basic", "tavily-search", "aws-api", "aws-knowledge", "aws document", 
    "use_aws", "code interpreter", "knowledge base",     
    "perplexity", "wikipedia",  
    "filesystem", "terminal", "text editor", "context7", "puppeteer", 
    "playwright", "airbnb",  
    "pubmed", "chembl", "clinicaltrial", "arxiv"  # "ArXiv" "firecrawl" "obsidian"
]
        
app = BedrockAgentCoreApp()

@app.entrypoint
def langgraph_bedrock(payload):
    """
    Invoke the agent with a payload
    """
    user_message = payload.get("prompt")
    logger.info(f"user_message: {user_message}")

    mcp_servers = payload.get("mcp_servers", [])
    logger.info(f"mcp_servers: {mcp_servers}")

    response, image_url = asyncio.run(langgraph_agent.run_agent(user_message, mcp_servers))    
    logger.info(f"response: {response}")

    return {
        "result": response
    }

if __name__ == "__main__":
    app.run()

