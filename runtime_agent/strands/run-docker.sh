#!/bin/bash

# Agent Docker Run Script — ~/.aws 마운트 및 AWS 환경 변수 전달
echo "🚀 Agent Docker Run Script"
echo "=================================="

if [ -f "config.json" ]; then
    PROJECT_NAME=$(python3 -c "import json; print(json.load(open('config.json'))['projectName'])")

    CURRENT_FOLDER_NAME=$(basename $(pwd))
    echo "CURRENT_FOLDER_NAME: ${CURRENT_FOLDER_NAME}"

    DOCKER_NAME="${PROJECT_NAME}_${CURRENT_FOLDER_NAME}"
    echo "DOCKER_NAME: ${DOCKER_NAME}"
else
    echo "Error: config.json file not found"
    exit 1
fi

# Check if image exists
if ! docker images | grep -q "${DOCKER_NAME}.*latest"; then
    echo "❌ Docker image '${DOCKER_NAME}:latest' not found."
    echo "   Please build the image first using:"
    echo "   ./build-docker.sh"
    exit 1
fi

# Stop and remove existing container if it exists
echo "🧹 Cleaning up existing container..."
docker stop ${DOCKER_NAME}-container 2>/dev/null || true
docker rm ${DOCKER_NAME}-container 2>/dev/null || true

# Disable OpenTelemetry for local development
echo "🔍 OpenTelemetry disabled for local development"

# AWS credentials (로컬 aws CLI / SSO 이후 configure와 동일한 소스)
echo ""
echo "Checking AWS credentials..."
AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id 2>/dev/null || echo "")
AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key 2>/dev/null || echo "")
AWS_DEFAULT_REGION=$(aws configure get region 2>/dev/null || echo "us-west-2")
AWS_SESSION_TOKEN=$(aws configure get aws_session_token 2>/dev/null || echo "")

if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "Warning: AWS credentials not found in AWS CLI configuration"
    echo "   Attempting to use ~/.aws directory..."
else
    echo "AWS credentials found in AWS CLI configuration"
fi

AWS_CREDENTIALS_DIR="$HOME/.aws"
if [ -d "$AWS_CREDENTIALS_DIR" ]; then
    echo "Found AWS credentials directory: ${AWS_CREDENTIALS_DIR}"
    echo "   Mounting to container: /root/.aws"
    AWS_VOLUME_MOUNT="-v ${AWS_CREDENTIALS_DIR}:/root/.aws:ro"
else
    echo "Warning: AWS credentials directory not found: ${AWS_CREDENTIALS_DIR}"
    if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
        echo "Error: No AWS credentials available!"
        echo "   Please configure AWS credentials using one of the following methods:"
        echo "   1. Run: aws configure"
        echo "   2. Set environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY"
        echo "   3. Create ~/.aws/credentials file"
        exit 1
    fi
    AWS_VOLUME_MOUNT=""
fi

echo ""
echo "🚀 Starting Docker container..."
echo "OpenTelemetry disabled - running uvicorn directly"

DOCKER_CMD=(
    docker run -d
    --name "${DOCKER_NAME}-container"
    -p 8080:8080
    -e "ALLOW_MISSING_RAG_CONFIG=1"
)

if [ ! -z "$AWS_VOLUME_MOUNT" ]; then
    DOCKER_CMD+=($AWS_VOLUME_MOUNT)
fi

if [ ! -z "$AWS_ACCESS_KEY_ID" ] && [ ! -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "   Setting AWS credentials as environment variables"
    DOCKER_CMD+=(
        -e "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
        -e "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}"
        -e "AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}"
    )
    if [ ! -z "$AWS_SESSION_TOKEN" ]; then
        DOCKER_CMD+=(-e "AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}")
        echo "   Including AWS_SESSION_TOKEN"
    fi
else
    echo "   Using AWS credentials from mounted volume only"
fi

DOCKER_CMD+=(
    --entrypoint=""
    "${DOCKER_NAME}:latest"
    uv run uvicorn agent:app --host 0.0.0.0 --port 8080
)

"${DOCKER_CMD[@]}"

if [ $? -eq 0 ]; then
    echo "✅ Container started successfully!"
    echo ""
    echo "🌐 Access your application at: http://localhost:8080"
    echo ""
    echo "📊 Container status:"
    docker ps | grep ${DOCKER_NAME}-container
    echo ""
    echo "📝 To view logs: docker logs ${DOCKER_NAME}-container"
    echo "🛑 To stop: docker stop ${DOCKER_NAME}-container"
    echo "🗑️  To remove: docker rm ${DOCKER_NAME}-container"
    echo ""
    echo "🔍 To test AWS credentials in container:"
    echo "   docker exec -it ${DOCKER_NAME}-container python -c \"import boto3; print(boto3.client('sts').get_caller_identity())\""
else
    echo "❌ Failed to start container"
    exit 1
fi
