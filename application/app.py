import streamlit as st 
import chat
import logging
import sys
import os
import agentcore_client

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("streamlit")

os.environ["DEV"] = "true"  # Skip user confirmation of get_user_input

# title
st.set_page_config(page_title='AgentCore', page_icon=None, layout="centered", initial_sidebar_state="auto", menu_items=None)

mode_descriptions = {
    "Agent": [
        "MCP를 활용한 Agent를 이용합니다. 왼쪽 메뉴에서 필요한 MCP를 선택하세요."
    ],
    "Agent (Chat)": [
        "MCP를 활용한 Agent를 이용합니다. 채팅 히스토리를 이용해 interative한 대화를 즐길 수 있습니다."
    ]
}

with st.sidebar:
    st.title("🔮 Menu")
    
    st.markdown(
        "Amazon의 AgentCore을 이용해 Agent를 구현합니다." 
        "상세한 코드는 [Github](https://github.com/kyopark2014/agentCore-langgraph)을 참조하세요."
    )

    st.subheader("🐱 대화 형태")
    
    # radio selection
    mode = st.radio(
        label="원하는 대화 형태를 선택하세요. ",options=["Agent", "Agent (Chat)"], index=0
    )   
    st.info(mode_descriptions[mode][0])
    
    # mcp selection    
    if mode=='Agent' or mode=='Agent (Chat)':
        # MCP Config JSON input
        st.subheader("⚙️ MCP Config")

        # Change radio to checkbox
        mcp_options = [
            "kb-retriever", "use-aws", "aws document", "사용자 설정"
        ]
        mcp_selections = {}
        default_selections = ["kb-retriever", "use-aws"]

        with st.expander("MCP 옵션 선택", expanded=True):            
            # Create two columns
            col1, col2 = st.columns(2)
            
            # Split options into two groups
            mid_point = len(mcp_options) // 2
            first_half = mcp_options[:mid_point]
            second_half = mcp_options[mid_point:]
            
            # Display first group in the first column
            with col1:
                for option in first_half:
                    default_value = option in default_selections
                    mcp_selections[option] = st.checkbox(option, key=f"mcp_{option}", value=default_value)
            
            # Display second group in the second column
            with col2:
                for option in second_half:
                    default_value = option in default_selections
                    mcp_selections[option] = st.checkbox(option, key=f"mcp_{option}", value=default_value)
        
        # if not any(mcp_selections.values()):
        #     mcp_selections["basic"] = True

        mcp_servers = [server for server, is_selected in mcp_selections.items() if is_selected]
    else:
        mcp_servers = []

    # model selection box
    modelName = st.selectbox(
        '🖊️ 사용 모델을 선택하세요',
        (
            "Claude 4.5 Haiku",
            "Claude 4.5 Sonnet",
            "Claude 4.5 Opus",  
            "Claude 4 Opus", 
            "Claude 4 Sonnet", 
            "Claude 3.7 Sonnet", 
            "Claude 3.5 Sonnet", 
            "Claude 3.0 Sonnet", 
            "Claude 3.5 Haiku", 
            "OpenAI OSS 120B",
            "OpenAI OSS 20B",
            "Nova 2 Lite",
            "Nova Premier", 
            "Nova Pro", 
            "Nova Lite", 
            "Nova Micro",       
        ), index=0
    )
    chat.update(modelName)

    # platform selection box
    platform = st.radio(
        label="사용 플렛폼을 선택하세요. ",options=["AgentCore","Docker"], index=0
    )   

    agent_type = st.radio(
        label="Agent 타입을 선택하세요. ",options=["langgraph", "strands", "claude"], index=0
    )
    
    st.success(f"Connected to {modelName}", icon="💚")
    clear_button = st.button("대화 초기화", key="clear")
    # logger.info(f"clear_button: {clear_button}")


st.title('🔮 '+ mode)

if clear_button or "messages" not in st.session_state:
    st.session_state.messages = []        
    uploaded_file = None
    
    st.session_state.greetings = False
    st.rerun()  

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.greetings = False

# Display chat messages from history on app rerun
def display_chat_messages() -> None:
    """Print message history
    @returns None
    """
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if "images" in message:                
                for url in message["images"]:
                    logger.info(f"url: {url}")

                    file_name = url[url.rfind('/')+1:]
                    st.image(url, caption=file_name, use_container_width=True)
            st.markdown(message["content"])

display_chat_messages()

# Greet user
if not st.session_state.greetings:
    with st.chat_message("assistant"):
        intro = "아마존 베드락을 이용하여 주셔서 감사합니다. 편안한 대화를 즐기실수 있으며, 파일을 업로드하면 요약을 할 수 있습니다."
        st.markdown(intro)
        # Add assistant response to chat history
        st.session_state.messages.append({"role": "assistant", "content": intro})
        st.session_state.greetings = True

if clear_button or "messages" not in st.session_state:
    st.session_state.messages = []        
    uploaded_file = None
    
    st.session_state.greetings = False
    chat.initiate()
    st.rerun()    

# Always show the chat input
if prompt := st.chat_input("메시지를 입력하세요."):
    with st.chat_message("user"):  # display user message in chat message container
        st.markdown(prompt)

    st.session_state.messages.append({"role": "user", "content": prompt})  # add user message to chat history
    prompt = prompt.replace('"', "").replace("'", "")
    logger.info(f"prompt: {prompt}")

    with st.chat_message("assistant"):
        if mode == 'Agent' or mode == 'Agent (Chat)':            
            sessionState = ""
            if mode == 'Agent':
                history_mode = "Disable"
            else:
                history_mode = "Enable"

            with st.status("thinking...", expanded=True, state="running") as status:
                logger.info(f"mcp_servers: {mcp_servers}")

                containers = {                        
                    "notification": [st.empty() for _ in range(1000)],
                    "result": st.empty()
                } 
                if platform == 'AgentCore':
                    response, image_url = agentcore_client.run_agent(prompt, agent_type, history_mode, mcp_servers, modelName, containers)
                else:                    
                    response, image_url = agentcore_client.run_agent_in_docker(prompt, agent_type, history_mode, mcp_servers, modelName, containers)

            st.session_state.messages.append({
                "role": "assistant", 
                "content": response,
                "images": image_url if image_url else []
            })

            for url in image_url:
                    logger.info(f"url: {url}")
                    file_name = url[url.rfind('/')+1:]
                    st.image(url, caption=file_name, use_container_width=True)

        