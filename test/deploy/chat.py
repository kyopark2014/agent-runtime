import info 

bedrock_region ="us-west-2"

# Default model
model_name = "Claude 3.5 Sonnet"
model_type = "claude"
models = info.get_model_info(model_name)
model_id = models[0]["model_id"]

