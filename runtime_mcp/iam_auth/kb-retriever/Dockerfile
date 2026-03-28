FROM --platform=linux/arm64 python:3.13-slim
        
WORKDIR /app

RUN pip install --upgrade boto3 botocore \
    && pip install mcp \
    && pip install aws-opentelemetry-distro>=0.10.0

# Add the current directory to Python path
ENV PYTHONPATH=/app

EXPOSE 8000

COPY . .

CMD ["opentelemetry-instrument", "python", "-m", "mcp_server_retrieve"]

