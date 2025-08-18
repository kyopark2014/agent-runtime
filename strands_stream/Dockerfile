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

# Install AWS CLI for ARM64
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && rm -rf aws awscliv2.zip

# AWS credentials will be passed at build time via ARG
ARG AWS_ACCESS_KEY_ID
ARG AWS_SECRET_ACCESS_KEY
ARG AWS_DEFAULT_REGION
ARG AWS_SESSION_TOKEN

# Create AWS credentials directory and files
RUN mkdir -p /root/.aws

# Create credentials file from build args
RUN if [ ! -z "$AWS_ACCESS_KEY_ID" ] && [ ! -z "$AWS_SECRET_ACCESS_KEY" ]; then \
        echo "[default]" > /root/.aws/credentials && \
        echo "aws_access_key_id = $AWS_ACCESS_KEY_ID" >> /root/.aws/credentials && \
        echo "aws_secret_access_key = $AWS_SECRET_ACCESS_KEY" >> /root/.aws/credentials && \
        if [ ! -z "$AWS_SESSION_TOKEN" ]; then \
            echo "aws_session_token = $AWS_SESSION_TOKEN" >> /root/.aws/credentials; \
        fi && \
        chmod 600 /root/.aws/credentials; \
    fi

# Create config file
RUN echo "[default]" > /root/.aws/config && \
    echo "region = ${AWS_DEFAULT_REGION:-us-west-2}" >> /root/.aws/config && \
    echo "output = json" >> /root/.aws/config && \
    chmod 600 /root/.aws/config
 
WORKDIR /app

# Core dependencies
RUN pip install --upgrade "boto3==1.39.12" "botocore==1.39.12"
RUN pip install langchain_aws langchain langchain_community langchain_experimental
RUN pip install bedrock-agentcore
RUN pip install mcp==1.12.1 langchain-mcp-adapters==0.1.9
RUN pip install strands-agents==1.0.1 strands-agents-tools
RUN pip install bedrock-agentcore bedrock-agentcore-starter-toolkit uv

# AWS and search dependencies
RUN pip install opensearch-py
RUN pip install tavily-python==0.5.0

# Data processing and analysis
RUN pip install yfinance==0.2.52 pytz==2024.2 beautifulsoup4==4.12.3

# PDF and document processing
RUN pip install PyPDF2 reportlab

# Image processing
RUN pip install Pillow colorama

# Additional utilities
RUN pip install requests uuid playwright nova-act

# OpenTelemetry
RUN pip install aws-opentelemetry-distro>=0.10.0

COPY . .

# Add the current directory to Python path
ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["uv", "run", "opentelemetry-instrument", "uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]