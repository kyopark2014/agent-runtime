#!/bin/bash

# Agent Docker Build Script (with ARG credentials)
echo "🚀 Agent Docker Build Script (with ARG credentials)"
echo "=========================================================="

# Get AWS credentials from local AWS CLI configuration
AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id)
AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key)
AWS_DEFAULT_REGION=$(aws configure get region)
AWS_SESSION_TOKEN=$(aws configure get aws_session_token)

echo "   Region: ${AWS_DEFAULT_REGION:-us-west-2}"

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

# Build Docker image with build arguments
echo ""
echo "🔨 Building Docker image with ARG credentials..."
sudo docker build \
    --platform linux/arm64 \
    --build-arg AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
    --build-arg AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
    --build-arg AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" \
    --build-arg AWS_SESSION_TOKEN="$AWS_SESSION_TOKEN" \
    -t ${DOCKER_NAME}:latest .

if [ $? -eq 0 ]; then
    echo "✅ Docker image built successfully"
    echo ""
    echo "🚀 로컬 실행: ./run-docker.sh (호스트 ~/.aws 마운트 + AWS 환경 변수)"
    echo "   기본 Dockerfile에는 자격 증명이 포함되지 않습니다."
    echo "   이미지 안에 넣으려면 Dockerfile.local 및 해당 빌드 스크립트를 사용하세요."
else
    echo "❌ Docker build failed"
    exit 1
fi 