import streamlit as st
import requests
import json
import uuid
import time
import os
from datetime import datetime
from docx import Document

# Configuration
LABELS = {
    "title": "Erotic Writer Companion",
    "new_chat": "New Chat",
    "preamble": "System Prompt",
    "file_upload": "Attach Files (TXT/DOCX)",
    "temperature": "Temperature",
    "rep_penalty": "Repetition Penalty",
    "api_provider": "API Provider"
}

API_PROVIDERS = {
    "DeepSeek Direct": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "headers": {}
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "deepseek/deepseek-chat-v3-0324:free",
        "headers": {
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "DeepSeek Chat App"
        }
    }
}

HISTORY_DIR = "chat_history"
os.makedirs(HISTORY_DIR, exist_ok=True)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_chat" not in st.session_state:
    st.session_state.current_chat = str(uuid.uuid4())
if "chat_history" not in st.session_state:
    st.session_state.chat_history = {}
if "api_calls" not in st.session_state:
    st.session_state.api_calls = []

def save_chat_history():
    file_path = os.path.join(HISTORY_DIR, f"{st.session_state.current_chat}.json")
    with open(file_path, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "messages": st.session_state.messages
        }, f)

def load_chat_history():
    history = {}
    for file in os.listdir(HISTORY_DIR):
        if file.endswith(".json"):
            with open(os.path.join(HISTORY_DIR, file), "r") as f:
                history[file[:-5]] = json.load(f)
    return history

def read_uploaded_file(file):
    try:
        if file.type == "text/plain":
            return file.read().decode()
        elif file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            doc = Document(file)
            return "\n".join([para.text for para in doc.paragraphs])
        return ""
    except Exception as e:
        st.error(f"Error reading file: {str(e)}")
        return ""

def check_rate_limit():
    now = time.time()
    st.session_state.api_calls = [t for t in st.session_state.api_calls if t > now - 60]
    if len(st.session_state.api_calls) >= 10:
        st.error("Rate limit exceeded: Max 10 requests per minute")
        return False
    st.session_state.api_calls.append(now)
    return True

# Sidebar Configuration
with st.sidebar:
    st.title("Settings")
    api_provider = st.radio(LABELS["api_provider"], list(API_PROVIDERS.keys()))
    provider_config = API_PROVIDERS[api_provider]
    
    api_key = st.text_input(f"{api_provider} API Key", type="password")
    temperature = st.slider(LABELS["temperature"], 0.0, 2.0, 0.7)
    rep_penalty = st.slider(LABELS["rep_penalty"], 0.0, 2.0, 1.1)
    preamble = st.text_area(LABELS["preamble"], "You are a helpful assistant.")

# Main Interface
st.title(LABELS["title"])
st.session_state.chat_history = load_chat_history()

if st.button(LABELS["new_chat"]):
    save_chat_history()
    st.session_state.current_chat = str(uuid.uuid4())
    st.session_state.messages = []
    st.rerun()

uploaded_file = st.file_uploader(LABELS["file_upload"], type=["txt", "docx"])
file_content = read_uploaded_file(uploaded_file) if uploaded_file else ""

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Type your message..."):
    if not check_rate_limit():
        st.stop()
    
    if not api_key:
        st.error("API key is required!")
        st.stop()

    full_prompt = f"{file_content}\n{prompt}" if file_content else prompt
    st.session_state.messages.append({"role": "user", "content": full_prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)
        if file_content:
            st.caption("File content attached")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **provider_config["headers"]
    }
    
    payload = {
        "model": provider_config["model"],
        "messages": [{"role": "system", "content": preamble}] + st.session_state.messages,
        "temperature": temperature,
        "frequency_penalty": rep_penalty,
        "stream": True
    }

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        try:
            response = requests.post(
                f"{provider_config['base_url']}/chat/completions",
                headers=headers,
                json=payload,
                stream=True
            )
            response.raise_for_status()

            chunk_json = ""
            for chunk in response.iter_lines():
                if chunk:
                    # Handle different streaming formats
                    if api_provider == "OpenRouter":
                        chunk_str = chunk.decode().strip()
                        if chunk_str.startswith("data: "):
                            chunk_json = json.loads(chunk_str[6:])
                    else:
                        chunk_json = json.loads(chunk.decode().lstrip("data: "))
                    
                    if "choices" in chunk_json:
                        delta = chunk_json["choices"][0].get("delta", {})
                        if "content" in delta:
                            full_response += delta["content"]
                            response_placeholder.markdown(full_response + "▌")
            
            response_placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
            save_chat_history()

        except requests.exceptions.HTTPError as e:
            error_msg = f"API Error ({api_provider}): {e.response.status_code}"
            try:
                error_data = e.response.json()
                error_details = error_data.get("error", {}).get("message", "")
                if error_details:
                    error_msg += f" - {error_details}"
            except:
                pass
            st.error(error_msg)
            st.session_state.messages.pop()
        except Exception as e:
            st.error(f"Error: {str(e)}")
            st.session_state.messages.pop()
