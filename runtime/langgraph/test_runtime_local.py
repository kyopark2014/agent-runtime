import asyncio
import uuid
import requests
import os

async def main():
    print(f"\n=== invoke agentcore runtime ===")
        
    runtime_session_id = str(uuid.uuid4())
    print(f"runtime_session_id: {runtime_session_id}")

    prompt = "보일러 에러 코드?"
    mcp_servers = ["kb-retriever"]
    model_name = "Claude 4.5 Haiku"
    user_id = uuid.uuid4().hex
    history_mode = "Disable"

    payload = {
        "prompt": prompt,
        "mcp_servers": mcp_servers,
        "model_name": model_name,
        "user_id": user_id,
        "history_mode": history_mode
    }

    runtime_url = "http://127.0.0.1:8080/invocations"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }

    response = requests.post(runtime_url, headers=headers, json=payload, stream=True)
    
    print(f"response status: {response.status_code}")
    print(f"response headers: {response.headers}")

    print(f"\n=== show stream response ===")
    
    if "text/event-stream" in response.headers.get("content-type", ""):
        for line in response.iter_lines(chunk_size=10):
            if line:
                line = line.decode("utf-8")
                print(f"-> {line}")
    else:
        print(f"response content: {response.text}")

if __name__ == "__main__":
    asyncio.run(main())