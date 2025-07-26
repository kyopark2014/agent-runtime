import logging
import sys
import mcp_agentcore_coder as coder

from typing import Dict, Optional, Any
from mcp.server.fastmcp import FastMCP 

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("coder")

try:
    mcp = FastMCP(
        name = "coder",
        instructions=(
            "You are a helpful assistant. "
            "You can generate a code or draw a graph using python code"
        )
    )
    logger.info("MCP server initialized successfully")
except Exception as e:
        err_msg = f"Error: {str(e)}"
        logger.info(f"{err_msg}")

######################################
# Code Interpreter
######################################

@mcp.tool()
def agentcore_coder(code):
    """
    Use this to execute python code and do math. 
    If you want to see the output of a value, you should print it out with `print(...)`. This is visible to the user.
    code: the Python code was written in English
    """
    logger.info(f"agentcore_coder --> code:\n {code}")

    return coder.agentcore_coder(code)

if __name__ =="__main__":
    print(f"###### main ######")
    mcp.run(transport="stdio")


