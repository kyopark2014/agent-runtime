curl -X POST http://localhost:8080/invocations \
-H "Content-Type: application/json" \
-d '{"prompt": "안녕하세요?", "model_name": "Claude 3.7 Sonnet"}'