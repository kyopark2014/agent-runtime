import info 
import utils

import logging
import sys

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("chat")

config = utils.load_config()
logger.info(f"config: {config}")

bedrock_region = config["region"] if "region" in config else "us-west-2"
projectName = config["projectName"] if "projectName" in config else "mcp"
accountId = config["accountId"] if "accountId" in config else None

# Default model (LangGraph chat.py와 동일한 런타임 스위치)
model_name = "Claude 4.6 Sonnet"
model_type = "claude"
models = info.get_model_info(model_name)
number_of_models = len(models)
model_id = models[0]["model_id"]
debug_mode = "Enable"
multi_region = "Disable"
reasoning_mode = "Disable"
agent_type = "strands"
selected_chat = 0
user_id = "agent"

def update(
    modelName=None,
    userId=None,
    debugMode=None,
    multiRegion=None,
    reasoningMode=None,
    agentType=None,
):
    global model_name, models, model_type, model_id, user_id
    global debug_mode, multi_region, reasoning_mode, agent_type
    global number_of_models, selected_chat

    mcp_env = utils.load_mcp_env()

    if modelName is not None and model_name != modelName:
        model_name = modelName
        logger.info(f"model_name: {model_name}")

        models = info.get_model_info(model_name)
        number_of_models = len(models)
        model_id = models[0]["model_id"]
        model_type = models[0]["model_type"]
        if selected_chat >= number_of_models:
            selected_chat = 0
        logger.info(f"model_id: {model_id}")
        logger.info(f"model_type: {model_type}")

    if debugMode is not None and debug_mode != debugMode:
        debug_mode = debugMode
        logger.info(f"debug_mode: {debug_mode}")

    if reasoningMode is not None and reasoning_mode != reasoningMode:
        reasoning_mode = reasoningMode
        logger.info(f"reasoning_mode: {reasoning_mode}")

    if multiRegion is not None and multi_region != multiRegion:
        multi_region = multiRegion
        logger.info(f"multi_region: {multi_region}")
        mcp_env["multi_region"] = multi_region

    if agentType is not None and agent_type != agentType:
        agent_type = agentType
        logger.info(f"agent_type: {agent_type}")
        user_id = agent_type
        logger.info(f"user_id: {user_id}")
        mcp_env["user_id"] = user_id

    if userId is not None and user_id != userId:
        user_id = userId
        logger.info(f"user_id: {user_id}")

    utils.save_mcp_env(mcp_env)

def get_max_output_tokens(model_id: str = "") -> int:
    """Return the max output tokens based on the model ID."""
    if "claude-opus-4-6" in model_id:
        return 128000
    if "claude-opus-4-5" in model_id:
        return 64000
    if "claude-opus-4" in model_id or "claude-4-opus" in model_id:
        return 32000
    if "claude-sonnet-4" in model_id or "claude-4-sonnet" in model_id or "claude-haiku-4" in model_id:
        return 64000
    return 8192
