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

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser

# Create AWS credentials directory and files for appuser
RUN mkdir -p /home/appuser/.aws

# Create credentials file from build args
RUN if [ ! -z "$AWS_ACCESS_KEY_ID" ] && [ ! -z "$AWS_SECRET_ACCESS_KEY" ]; then \
        echo "[default]" > /home/appuser/.aws/credentials && \
        echo "aws_access_key_id = $AWS_ACCESS_KEY_ID" >> /home/appuser/.aws/credentials && \
        echo "aws_secret_access_key = $AWS_SECRET_ACCESS_KEY" >> /home/appuser/.aws/credentials && \
        if [ ! -z "$AWS_SESSION_TOKEN" ]; then \
            echo "aws_session_token = $AWS_SESSION_TOKEN" >> /home/appuser/.aws/credentials; \
        fi && \
        chmod 600 /home/appuser/.aws/credentials; \
    fi

# Create config file
RUN echo "[default]" > /home/appuser/.aws/config && \
    echo "region = ${AWS_DEFAULT_REGION:-us-west-2}" >> /home/appuser/.aws/config && \
    echo "output = json" >> /home/appuser/.aws/config && \
    chmod 600 /home/appuser/.aws/config

# Set ownership of AWS directory
RUN chown -R appuser:appuser /home/appuser/.aws

# Create app directory and set ownership
WORKDIR /app

RUN npm install -g @anthropic-ai/claude-code

RUN pip install boto3 botocore --upgrade 
RUN pip install claude-agent-sdk anyio
RUN pip install bedrock-agentcore bedrock-agentcore-starter-toolkit uv

RUN pip install requests uuid

RUN pip install aws-opentelemetry-distro>=0.10.0

COPY . .

# Set ownership of app directory to appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

EXPOSE 8080

CMD ["uv", "run", "opentelemetry-instrument", "uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]