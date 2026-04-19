FROM --platform=linux/arm64 python:3.13-slim

WORKDIR /app

RUN pip install boto3 botocore --upgrade
RUN pip install langchain_aws langchain langchain_community langchain_experimental langgraph 
RUN pip install mcp langchain-mcp-adapters
RUN pip install bedrock-agentcore uv
RUN pip install PyPDF2 Pillow pytz tavily-python langchain-text-splitters

# OpenTelemetry
RUN pip install aws-opentelemetry-distro>=0.10.0

COPY . .

# Add the current directory to Python path
ENV PYTHONPATH=/app
# Minimal config (MCP/LangGraph agent without full RAG keys in config.json)
ENV ALLOW_MISSING_RAG_CONFIG=1

EXPOSE 8080

CMD ["uv", "run", "opentelemetry-instrument", "uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]