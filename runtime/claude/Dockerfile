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

# Create non-root user for running the application
RUN groupadd -r appuser && useradd -r -g appuser -m appuser

# Create app directory and set ownership
WORKDIR /app
RUN chown -R appuser:appuser /app

# Create necessary directories for appuser and set permissions
RUN mkdir -p /home/appuser/.cache/uv && \
    mkdir -p /home/appuser/.local && \
    chown -R appuser:appuser /home/appuser

# Core dependencies - Install boto3/botocore first with exact versions
RUN pip install boto3 botocore --upgrade 
RUN pip install claude-agent-sdk anyio
RUN pip install bedrock-agentcore bedrock-agentcore-starter-toolkit uv

RUN pip install requests uuid

# OpenTelemetry
RUN pip install aws-opentelemetry-distro>=0.10.0

COPY . .

# Set ownership of copied files to appuser
RUN chown -R appuser:appuser /app

# Create AWS credentials directory for appuser
RUN mkdir -p /home/appuser/.aws && \
    cp /root/.aws/credentials /home/appuser/.aws/ 2>/dev/null || true && \
    cp /root/.aws/config /home/appuser/.aws/ 2>/dev/null || true && \
    chown -R appuser:appuser /home/appuser/.aws && \
    chmod 600 /home/appuser/.aws/credentials 2>/dev/null || true && \
    chmod 600 /home/appuser/.aws/config 2>/dev/null || true

# Add the current directory to Python path
ENV PYTHONPATH=/app

# Switch to non-root user
USER appuser

# Install Claude Code as appuser
RUN npm install -g @anthropic-ai/claude-code --unsafe-perm=true --allow-root

EXPOSE 8080

CMD ["uv", "run", "opentelemetry-instrument", "uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]