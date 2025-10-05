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
print(f"config: {config}")

bedrock_region = config["region"] if "region" in config else "us-west-2"
projectName = config["projectName"] if "projectName" in config else "mcp"
accountId = config["accountId"] if "accountId" in config else None

# Default model
model_name = "Claude 3.7 Sonnet"
model_type = "claude"
models = info.get_model_info(model_name)
model_id = models[0]["model_id"]

reasoning_mode = 'Disable'
user_id = 'langgraph'

def update(modelName, userId):
    global model_name, models, model_type, model_id, user_id
    global checkpointer, memorystore

    if modelName is not model_name:
        model_name = modelName
        logger.info(f"modelName: {modelName}")

        models = info.get_model_info(model_name)
        model_type = models[0]["model_type"]
        model_id = models[0]["model_id"]
        logger.info(f"model_id: {model_id}")
        logger.info(f"model_type: {model_type}")
    
    if userId is not user_id:
        user_id = userId
        logger.info(f"user_id: {user_id}")

