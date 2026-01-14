FROM --platform=linux/amd64 python:3.13-slim

WORKDIR /app

# Install Python packages
RUN pip install streamlit streamlit-chat
RUN pip install boto3 langchain_aws langchain langchain_community langgraph langchain_experimental langgraph-supervisor langgraph-swarm langchain-text-splitters
RUN pip install mcp langchain-mcp-adapters
RUN pip install pandas numpy
RUN pip install tavily-python==0.5.0 pytz>=2025.2
RUN pip install beautifulsoup4==4.12.3 plotly_express==0.4.1 matplotlib==3.10.0 PyPDF2==3.0.1
RUN pip install opensearch-py wikipedia aioboto3 requests
RUN pip install uv kaleido diagrams graphviz rich colorama

RUN mkdir -p /root/.streamlit
COPY config.toml /root/.streamlit/

COPY . .

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

ENTRYPOINT ["python", "-m", "streamlit", "run", "application/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
