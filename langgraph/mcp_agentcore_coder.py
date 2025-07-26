import logging
import sys
import boto3
import time
import os

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("agentcore-coder")

aws_region = os.environ.get('AWS_DEFAULT_REGION', 'us-west-2')

client = boto3.client(
    "bedrock-agentcore", 
    region_name=aws_region,
    endpoint_url=f"https://bedrock-agentcore.{aws_region}.amazonaws.com"
)
sessionId = None

def get_code_interpreter_sessionId():
    session_id = None
    response = client.list_code_interpreter_sessions(
        codeInterpreterIdentifier='aws.codeinterpreter.v1',
        maxResults=5,
        status='READY'
    )
    items = response['items']

    if items is not None:
        for item in items:
            session_id = item['sessionId']
            break
    
    if session_id is None:  # still no sessionId
        logger.info("No ready sessions found")
        response = client.start_code_interpreter_session(
            codeInterpreterIdentifier='aws.codeinterpreter.v1',
            name="agentcore-code-session",
            sessionTimeoutSeconds=900
        )
        logger.info(f"response of start_code_interpreter_session: {response}")
        session_id = response['sessionId']

    return session_id

def agentcore_coder(code):
    """
    Use this to execute python code and do math. 
    If you want to see the output of a value, you should print it out with `print(...)`. This is visible to the user.
    code: the Python code was written in English
    """

    # get the sessionId
    global sessionId
    if sessionId is None:
        sessionId = get_code_interpreter_sessionId()
        logger.info(f"sessionId: {sessionId}")
    else:
        logger.info(f"sessionId: {sessionId}")
        try:
            response = client.get_code_interpreter_session(
                codeInterpreterIdentifier='aws.codeinterpreter.v1',
                sessionId=sessionId
            )
            logger.info(f"response of get_code_interpreter_session: {response}")        

            status = response['status']
            logger.info(f"status: {status}")
            if status != 'READY':
                logger.info(f"sessionId: {sessionId} is not ready")
                sessionId = get_code_interpreter_sessionId()
                time.sleep(5)
        except Exception as e:
            logger.info(f"error of get_code_interpreter_session: {e}")
            sessionId = get_code_interpreter_sessionId()

    execute_response = client.invoke_code_interpreter(
        codeInterpreterIdentifier="aws.codeinterpreter.v1",
        sessionId=sessionId,
        name="executeCode",
        arguments={
            "language": "python",
            "code": code
        }
    )
    logger.info(f"execute_response: {execute_response}")

    # Extract and print the text output from the stream
    result_text = ""
    for event in execute_response['stream']:
        if 'result' in event:
            result = event['result']
            if 'content' in result:
                for content_item in result['content']:
                    if content_item['type'] == 'text':
                        result_text = content_item['text']
                        logger.info(f"result: {result_text}")

    # stop the session
    # client.stop_code_interpreter_session(
    #     codeInterpreterIdentifier="aws.codeinterpreter.v1",
    #     sessionId=sessionId
    # )
    return result_text