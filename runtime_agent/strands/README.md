# Strands Agent Runtime 

## Dockerfile

```python
FROM --platform=linux/arm64 python:3.13-slim

RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    unzip \
    build-essential \
    gcc \
    python3-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*
 
WORKDIR /app

# Core dependencies
RUN pip install boto3 botocore --upgrade
RUN pip install mcp
RUN pip install strands-agents strands-agents-tools
RUN pip install bedrock-agentcore bedrock-agentcore-starter-toolkit uv

# OpenTelemetry
RUN pip install aws-opentelemetry-distro>=0.10.0

COPY . .

# Add the current directory to Python path
ENV PYTHONPATH=/app

EXPOSE 8080
```
CMD ["uv", "run", "opentelemetry-instrument", "uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]
`
