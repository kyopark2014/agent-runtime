from flask import Flask, request, jsonify, render_template, send_from_directory, Response, stream_with_context
import os
import sys
import openai
import anthropic
from datetime import datetime
import json
import logging
import queue
import threading

# Add project root to path for application package import
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from application import agentcore_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Initialize API clients (you'll need to set up API keys)
# openai.api_key = os.getenv('OPENAI_API_KEY')
# anthropic_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/favicon.ico')
def favicon():
    # Return 204 No Content for favicon requests
    return '', 204

@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('.', filename)

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()

        if not data or 'message' not in data:
            return jsonify({'error': 'Message is required'}), 400

        message = data['message']
        model = data.get('model', 'gpt-3.5-turbo')
        temperature = data.get('temperature', 0.7)
        history = data.get('history', [])
        stream = data.get('stream', True)  # Enable streaming by default

        logger.info(f"Received request: model={model}, message_length={len(message)}, stream={stream}")

        if stream:
            return Response(
                stream_with_context(stream_chat_request(message, model, temperature, history)),
                mimetype='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no'
                }
            )
        else:
            response = handle_chat_request(message, model, temperature, history)
            return jsonify({
                'response': response,
                'model': model,
                'timestamp': datetime.now().isoformat()
            })

    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}")
        return jsonify({'error': str(e)}), 500

def stream_chat_request(message, model, temperature, history):
    """
    Stream chat responses using Server-Sent Events (SSE)
    """
    try:
        # Use model name directly if it's in AgentCore format, otherwise use default
        agentcore_models = [
            'Claude 4.5 Haiku', 'Claude 4.5 Sonnet', 'Claude 4.5 Opus',
            'Claude 4 Opus', 'Claude 4 Sonnet', 'Claude 3.7 Sonnet',
            'Claude 3.5 Sonnet', 'Claude 3.0 Sonnet', 'Claude 3.5 Haiku',
            'OpenAI OSS 120B', 'OpenAI OSS 20B',
            'Nova 2 Lite', 'Nova Premier', 'Nova Pro', 'Nova Lite', 'Nova Micro'
        ]
        
        model_name = model if model in agentcore_models else 'Claude 4.5 Haiku'
        
        # Default settings for agent
        agent_type = 'langgraph'
        history_mode = 'Enable' if len(history) > 0 else 'Disable'
        mcp_servers = ['kb-retriever', 'use-aws']
        
        logger.info(f"Streaming with model={model_name}, agent_type={agent_type}")
        
        # Create a queue-based container for streaming
        message_queue = queue.Queue()
        
        class StreamContainer:
            def __init__(self, q):
                self.queue = q
                self.notification_counter = 0
                
            def get_notification(self, index):
                return StreamNotification(self.queue, index)
        
        class StreamNotification:
            def __init__(self, q, index):
                self.queue = q
                self.index = index
                
            def info(self, message):
                self.queue.put({'type': 'info', 'data': message, 'index': self.index})
                
            def markdown(self, message):
                self.queue.put({'type': 'markdown', 'data': message, 'index': self.index})
        
        containers = {
            'notification': [StreamContainer(message_queue).get_notification(i) for i in range(1000)],
            'result': None
        }
        
        # Run agent in a separate thread
        result_holder = {'response': None, 'image_url': [], 'error': None}
        
        def run_agent_thread():
            try:
                response, image_url = agentcore_client.run_agent(
                    prompt=message,
                    agent_type=agent_type,
                    history_mode=history_mode,
                    mcp_servers=mcp_servers,
                    model_name=model_name,
                    containers=containers
                )
                result_holder['response'] = response
                result_holder['image_url'] = image_url
                message_queue.put({'type': 'done', 'data': response})
            except Exception as e:
                logger.error(f"Error in agent thread: {str(e)}", exc_info=True)
                result_holder['error'] = str(e)
                message_queue.put({'type': 'error', 'data': str(e)})
        
        # Start agent thread
        agent_thread = threading.Thread(target=run_agent_thread)
        agent_thread.daemon = True
        agent_thread.start()
        
        # Stream messages from queue
        while True:
            try:
                msg = message_queue.get(timeout=1)
                
                if msg['type'] == 'done':
                    yield f"data: {json.dumps({'type': 'done', 'content': msg['data']})}\n\n"
                    break
                elif msg['type'] == 'error':
                    yield f"data: {json.dumps({'type': 'error', 'content': msg['data']})}\n\n"
                    break
                elif msg['type'] == 'info':
                    yield f"data: {json.dumps({'type': 'info', 'content': msg['data']})}\n\n"
                elif msg['type'] == 'markdown':
                    yield f"data: {json.dumps({'type': 'chunk', 'content': msg['data']})}\n\n"
                    
            except queue.Empty:
                # Send keepalive
                yield f": keepalive\n\n"
                
                # Check if thread is still alive
                if not agent_thread.is_alive() and message_queue.empty():
                    break
        
        # Wait for thread to complete
        agent_thread.join(timeout=5)
        
    except Exception as e:
        logger.error(f"Error in streaming: {str(e)}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'content': f'오류가 발생했습니다: {str(e)}'})}\n\n"


def handle_chat_request(message, model, temperature, history):
    """
    Handle chat requests using agentcore_client.run_agent (non-streaming)
    """
    try:
        # Use model name directly if it's in AgentCore format, otherwise use default
        agentcore_models = [
            'Claude 4.5 Haiku', 'Claude 4.5 Sonnet', 'Claude 4.5 Opus',
            'Claude 4 Opus', 'Claude 4 Sonnet', 'Claude 3.7 Sonnet',
            'Claude 3.5 Sonnet', 'Claude 3.0 Sonnet', 'Claude 3.5 Haiku',
            'OpenAI OSS 120B', 'OpenAI OSS 20B',
            'Nova 2 Lite', 'Nova Premier', 'Nova Pro', 'Nova Lite', 'Nova Micro'
        ]
        
        model_name = model if model in agentcore_models else 'Claude 4.5 Haiku'
        
        # Default settings for agent
        agent_type = 'langgraph'
        history_mode = 'Enable' if len(history) > 0 else 'Disable'
        mcp_servers = ['kb-retriever', 'use-aws']
        
        logger.info(f"Calling agentcore_client.run_agent with model={model_name}, agent_type={agent_type}")
        
        # Call agentcore_client.run_agent (containers=None for Flask)
        response, image_url = agentcore_client.run_agent(
            prompt=message,
            agent_type=agent_type,
            history_mode=history_mode,
            mcp_servers=mcp_servers,
            model_name=model_name,
            containers=None
        )
        
        logger.info(f"Received response from agentcore_client: {len(response)} characters")
        
        return response
        
    except Exception as e:
        logger.error(f"Error calling agentcore_client.run_agent: {str(e)}", exc_info=True)
        return f"오류가 발생했습니다: {str(e)}"


def call_openai_api(message, model, temperature, history):
    """
    Call OpenAI API (uncomment and configure when ready)
    """
    try:
        messages = []

        # Add history
        for msg in history[-10:]:  # Last 10 messages
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })

        # Add current message
        messages.append({"role": "user", "content": message})

        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=1000
        )

        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        raise

@app.route('/api/models', methods=['GET'])
def get_models():
    """Get available models from application/app.py configuration"""
    models = {
        'claude': [
            'Claude 4.5 Haiku',
            'Claude 4.5 Sonnet',
            'Claude 4.5 Opus',
            'Claude 4 Opus',
            'Claude 4 Sonnet',
            'Claude 3.7 Sonnet',
            'Claude 3.5 Sonnet',
            'Claude 3.0 Sonnet',
            'Claude 3.5 Haiku'
        ],
        'openai': [
            'OpenAI OSS 120B',
            'OpenAI OSS 20B'
        ],
        'nova': [
            'Nova 2 Lite',
            'Nova Premier',
            'Nova Pro',
            'Nova Lite',
            'Nova Micro'
        ]
    }
    return jsonify(models)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('DEBUG', 'True').lower() == 'true'

    print(f"Starting LLM Chat UI server on port {port}")
    print(f"Open your browser to: http://localhost:{port}")

    app.run(host='0.0.0.0', port=port, debug=debug)