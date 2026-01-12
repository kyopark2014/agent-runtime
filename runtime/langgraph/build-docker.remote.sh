#!/bin/bash

# Agent Docker Build Script (with ARG credentials)
echo "🚀 Agent Docker Build Script"
echo "=========================================================="

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
    -t ${DOCKER_NAME}:latest .

if [ $? -eq 0 ]; then
    echo "✅ Docker image built successfully with embedded credentials"
    echo ""
    echo "🚀 To run the container:"
    echo "   sudo docker run -d --name ${DOCKER_NAME} -p 8080:8080 ${DOCKER_NAME}:latest"
    echo ""
    echo "⚠️  Note: AWS credentials are embedded in the Docker image"
    echo "   - Do not share this image publicly"
    echo "   - For production, use environment variables or IAM roles"
else
    echo "❌ Docker build failed"
    exit 1
fi 