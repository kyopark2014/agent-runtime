from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter
from strands import Agent, tool
from strands.models import BedrockModel
import json
import pandas as pd
from typing import Dict, Any, List
from strands_tools import file_read

SYSTEM_PROMPT = """You are a helpful AI assistant that validates all answers through code execution using the tools provided. DO NOT Answer questions without using the tools

VALIDATION PRINCIPLES:
1. When making claims about code, algorithms, or calculations - write code to verify them
2. Use execute_python to test mathematical calculations, algorithms, and logic
3. Create test scripts to validate your understanding before giving answers
4. Always show your work with actual code execution
5. If uncertain, explicitly state limitations and validate what you can

APPROACH:
- If asked about a programming concept, implement it in code to demonstrate
- If asked for calculations, compute them programmatically AND show the code
- If implementing algorithms, include test cases to prove correctness
- Document your validation process for transparency
- The sandbox maintains state between executions, so you can refer to previous results

TOOL AVAILABLE:
- execute_python: Run Python code and see output

RESPONSE FORMAT: The execute_python tool returns a JSON response with:
- sessionId: The sandbox session ID
- id: Request ID
- isError: Boolean indicating if there was an error
- content: Array of content objects with type and text/data
- structuredContent: For code execution, includes stdout, stderr, exitCode, executionTime

For successful code execution, the output will be in content[0].text and also in structuredContent.stdout.
Check isError field to see if there was an error.

Be thorough, accurate, and always validate your answers when possible."""

# Initialize the Code Interpreter within a supported AWS region.
code_client = CodeInterpreter('us-west-2')
code_client.start(session_timeout_seconds=1200)

#Define and configure the code interpreter tool
@tool
def execute_python(code: str, description: str = "") -> str:
    """Execute Python code in the sandbox."""

    if description:
        code = f"# {description}\n{code}"

    #Print generated Code to be executed
    print(f"\n Generated Code: {code}")

    # Call the Invoke method and execute the generated code, within the initialized code interpreter session
    response = code_client.invoke("executeCode", {
        "code": code,
        "language": "python",
        "clearContext": False
    })
    for event in response["stream"]:
        return json.dumps(event["result"])
    
model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0"
model= BedrockModel(model_id=model_id)

#configure the strands agent including the model and tool(s)
agent=Agent(
    model=model,
        tools=[execute_python, file_read],
        system_prompt=SYSTEM_PROMPT,
        callback_handler=None)

#query = "Load the file 'contents/data.csv' and perform exploratory data analysis(EDA) on it. Tell me about distributions and outlier values."
query = "파일 'contents/data.csv'를 로드하고 탐색적 데이터 분석(EDA)을 수행하세요. 분포와 이상치 값에 대해 알려주세요."

# Invoke the agent asynchcronously and stream the response
async def main():
    response_text = ""
    async for event in agent.stream_async(query):
        if "data" in event:
            # Stream text response
            chunk = event["data"]
            response_text += chunk
            print(chunk, end="")

# Run the async function
import asyncio
asyncio.run(main())