import asyncio
import httpx

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    mcp_url = "http://127.0.0.1:8000/mcp"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }

    http_client = httpx.AsyncClient(headers=headers, timeout=120.0)
    async with streamable_http_client(mcp_url, http_client=http_client, terminate_on_close=False) as (
        read_stream, write_stream, _,):
        
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tool_result = await session.list_tools()
            print("Available tools:")
            for tool in tool_result.tools:
                print(f"  - {tool.name}: {tool.description}")
            
            # Test use_aws function
            print("\n=== Testing use_aws function ===")
            params = {
                "service_name": "s3",
                "operation_name": "list_buckets",
                "parameters": {},
                "region": "us-west-2",
                "label": "List S3 buckets"
            }
            
            try:
                result = await asyncio.wait_for(session.call_tool("use_aws", params), timeout=60)
                print(f"use_aws result: {result}")
                
                if hasattr(result, 'content') and result.content:
                    for content in result.content:
                        if hasattr(content, 'text'):
                            print(f"Content: {content.text}")
                else:
                    print("No content in result")
            except asyncio.TimeoutError:
                print("use_aws function timeout (60s)")
            except Exception as aws_error:
                print(f"use_aws function failed: {aws_error}")
            
            print("\n=== MCP Connection Test Complete ===")

if __name__ == "__main__":
    asyncio.run(main())