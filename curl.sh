curl -X POST http://localhost:8080/invocations \
-H "Content-Type: application/json" \
-d '{"prompt": "내 s3 bucket 리스트는?", "mcp_servers": ["basic", "use_aws", "tavily-search", "filesystem", "terminal"]}'