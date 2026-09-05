import logging
import sys
import json
import traceback
import boto3
import os

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("utils")

# Huge MCP/tool payloads (e.g. raw HTML) overwhelm non-blocking stdout and SSE.
LOG_TRUNCATE_CHARS = 2_000
STREAM_TRUNCATE_CHARS = 8_000
_TRUNCATE_SUFFIX = "\n...[truncated {omitted} chars]"


def truncate_text(text: object, max_chars: int, *, suffix_template: str = _TRUNCATE_SUFFIX) -> str:
    """Return a string capped at max_chars for safe logging / SSE display."""
    if text is None:
        return ""
    if not isinstance(text, str):
        try:
            text = json.dumps(text, ensure_ascii=False, default=str)
        except TypeError:
            text = str(text)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    suffix = suffix_template.format(omitted=omitted)
    keep = max(0, max_chars - len(suffix))
    return text[:keep] + suffix


def truncate_for_log(text: object, max_chars: int = LOG_TRUNCATE_CHARS) -> str:
    return truncate_text(text, max_chars)


def truncate_for_stream(text: object, max_chars: int = STREAM_TRUNCATE_CHARS) -> str:
    return truncate_text(text, max_chars)

def load_config():
    config = None
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    return config

config = load_config()

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")

bedrock_region = config['region']
accountId = config['accountId']
projectName = config['projectName']
agent_runtime_role = config['agent_runtime_role']

def load_mcp_env():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mcp_env_path = os.path.join(script_dir, "mcp.env")
    
    with open(mcp_env_path, "r", encoding="utf-8") as f:
        mcp_env = json.load(f)
    return mcp_env

def save_mcp_env(mcp_env):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mcp_env_path = os.path.join(script_dir, "mcp.env")
    
    with open(mcp_env_path, "w", encoding="utf-8") as f:
        json.dump(mcp_env, f)

