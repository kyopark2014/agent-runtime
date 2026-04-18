"""
Flask app for chat_ui: invokes application/agentcore_client.run_agent.
"""
from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
import os
import sys
import json
import logging
import queue
import threading
from datetime import datetime

# Import path: application/chat.py uses `import utils`, so include the application directory.
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_application_dir = os.path.join(project_root, "application")
sys.path.insert(0, project_root)
sys.path.insert(0, _application_dir)

import info
import chat
import agentcore_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default MCP servers (fixed for this UI).
DEFAULT_MCP_SERVERS = ["kb-retriever", "use-aws", "aws document"]

# chat.debug_mode: when "Enable", stream SSE info/chunk events for agentcore_client output.
_DEFAULT_DEBUG = "Enable"
_FALLBACK_MODEL = "Claude 4.5 Sonnet"

app = Flask(__name__)


@app.after_request
def _cors_headers(response):
    """Dev CORS for browsers calling /api from file:// or another origin."""
    if request.path.startswith("/api") or request.path == "/health":
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def _resolve_model(name: str) -> str:
    m = info.get_model_info(name)
    if isinstance(m, dict) and m.get("model_id"):
        return name
    logger.warning("Unknown model %r, fallback to %s", name, _FALLBACK_MODEL)
    return _FALLBACK_MODEL


def _normalize_history(raw):
    out = []
    if not raw:
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in ("user", "assistant") and content is not None:
            out.append({"role": role, "content": str(content)})
    return out


class FlaskNotificationQueue:
    """NotificationQueue-compatible sink: push markdown/info to an SSE queue without Streamlit."""

    def __init__(self, q: "queue.Queue"):
        self._q = q
        self._streaming_slot = None
        self._tool_slots = {}
        self._tool_names = {}

    def reset(self):
        self._streaming_slot = None
        self._tool_slots = {}
        self._tool_names = {}

    def notify(self, message: str):
        self._streaming_slot = None
        self._q.put({"type": "info", "data": message})

    def respond(self, message: str):
        self._streaming_slot = None
        self._q.put({"type": "markdown", "data": message})

    def stream(self, message: str):
        if self._streaming_slot is None:
            self._streaming_slot = object()
        self._q.put({"type": "markdown", "data": message})

    def result(self, message: str):
        self._q.put({"type": "markdown", "data": message})
        self._streaming_slot = None

    def tool_update(self, tool_use_id: str, message: str):
        if tool_use_id not in self._tool_slots:
            self._streaming_slot = None
            self._tool_slots[tool_use_id] = object()
        self._q.put({"type": "info", "data": message})

    def register_tool(self, tool_use_id: str, name: str):
        self._tool_names[tool_use_id] = name

    def get_tool_name(self, tool_use_id: str) -> str:
        return self._tool_names.get(tool_use_id, "")


@app.route("/")
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "index.html")


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), filename)


@app.route("/api/chat", methods=["POST", "OPTIONS"])
def chat_endpoint():
    if request.method == "OPTIONS":
        return ("", 204)

    try:
        data = request.get_json()
        if not data or "message" not in data:
            return jsonify({"error": "Message is required"}), 400

        message = data["message"]
        model_raw = data.get("model", _FALLBACK_MODEL)
        history = _normalize_history(data.get("history", []))
        stream = data.get("stream", True)

        model_name = _resolve_model(model_raw)
        chat.update(model_name)
        chat.debug_mode = _DEFAULT_DEBUG

        history_mode = "Enable" if len(history) > 0 else "Disable"
        logger.info(
            "chat request model=%s history_mode=%s mcp=%s",
            model_name,
            history_mode,
            DEFAULT_MCP_SERVERS,
        )

        if stream:
            return Response(
                stream_with_context(
                    stream_agent(
                        message,
                        history_mode,
                        model_name,
                    )
                ),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        response_text, _artifacts = _run_agent_sync(
            message, history_mode, model_name, notification_queue=None
        )
        return jsonify(
            {
                "response": response_text,
                "model": model_name,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error("Error processing chat request: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


def _run_agent_sync(message, history_mode, model_name, notification_queue):
    return agentcore_client.run_agent(
        message,
        "langgraph",
        history_mode,
        DEFAULT_MCP_SERVERS,
        model_name,
        notification_queue,
    )


def stream_agent(message, history_mode, model_name):
    """SSE stream: markdown chunks, then final done or error."""
    message_queue: queue.Queue = queue.Queue()

    def worker():
        try:
            nq = (
                FlaskNotificationQueue(message_queue)
                if chat.debug_mode == "Enable"
                else None
            )
            response, _artifacts = _run_agent_sync(message, history_mode, model_name, nq)
            message_queue.put({"type": "done", "data": response})
        except Exception as e:
            logger.error("Error in agent worker: %s", e, exc_info=True)
            message_queue.put({"type": "error", "data": str(e)})

    t = threading.Thread(target=worker)
    t.daemon = True
    t.start()

    while True:
        try:
            msg = message_queue.get(timeout=1.0)
        except queue.Empty:
            yield ": keepalive\n\n"
            if not t.is_alive() and message_queue.empty():
                yield f"data: {json.dumps({'type': 'error', 'content': '응답 시간이 초과되었습니다.'})}\n\n"
                break
            continue

        mtype = msg.get("type")
        if mtype == "done":
            yield f"data: {json.dumps({'type': 'done', 'content': msg['data']})}\n\n"
            break
        if mtype == "error":
            yield f"data: {json.dumps({'type': 'error', 'content': msg['data']})}\n\n"
            break
        if mtype == "info":
            yield f"data: {json.dumps({'type': 'info', 'content': msg['data']})}\n\n"
        elif mtype == "markdown":
            yield f"data: {json.dumps({'type': 'chunk', 'content': msg['data']})}\n\n"

    t.join(timeout=30)


@app.route("/api/models", methods=["GET"])
def get_models():
    models = {
        "claude": [
            "Claude 4.6 Sonnet",
            "Claude 4.6 Opus",
            "Claude 4.5 Haiku",
            "Claude 4.5 Sonnet",
            "Claude 4.5 Opus",
            "Claude 4 Opus",
            "Claude 4 Sonnet",
            "Claude 3.7 Sonnet",
            "Claude 3.5 Sonnet",
            "Claude 3.0 Sonnet",
            "Claude 3.5 Haiku",
        ],
        "openai": ["OpenAI OSS 120B", "OpenAI OSS 20B"],
        "nova": [
            "Nova 2 Lite",
            "Nova Premier",
            "Nova Pro",
            "Nova Lite",
            "Nova Micro",
        ],
    }
    return jsonify(models)


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("DEBUG", "True").lower() == "true"
    print(f"Starting Chat UI (agentcore run_agent) on port {port}")
    print(f"Open http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
