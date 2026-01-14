FROM --platform=linux/arm64 python:3.13-slim

WORKDIR /app

RUN pip install --upgrade boto3 botocore
RUN pip install mcp==1.12.1 langchain-mcp-adapters==0.1.9
RUN pip install uv
RUN pip install aws-opentelemetry-distro>=0.10.0

# install package for use_aws
RUN pip install rich colorama

# Add the current directory to Python path
ENV PYTHONPATH=/app

EXPOSE 8080
EXPOSE 8000

COPY . .

CMD ["opentelemetry-instrument", "python", "-m", "mcp_server_use_aws"]