import streamlit as st
import requests

# Set up the webpage
st.set_page_config(page_title="Hive Queen AI", layout="centered")
st.title("🐝 Sovereign Swarm Engine")
st.markdown("Powered by Local Open-Source Models & Dynamic Routing.")

# Initialize chat history in the browser
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# The Chat Input Box
user_prompt = st.chat_input("Ask the Swarm a complex task...")

if user_prompt:
    # 1. Show the user's message on screen
    with st.chat_message("user"):
        st.markdown(user_prompt)
    st.session_state.messages.append({"role": "user", "content": user_prompt})

    # 2. Contact the API (The Nervous System)
    with st.chat_message("assistant"):
        status_text = st.empty()
        status_text.text("The Hive Queen is analyzing the prompt...")
        
        try:
            # Send the prompt to our FastAPI server
            response = requests.post("http://127.0.0.1:8000/orchestrate", json={"prompt": user_prompt})
            data = response.json()
            
            # Show the Execution Plan to the user (Transparency!)
            plan_str = " -> ".join(data["plan"])
            st.info(f"**Execution Plan:** {plan_str}")
            
            # Show the Final Answer
            final_answer = data["final_answer"]
            st.markdown(final_answer)
            
            # Save to history
            st.session_state.messages.append({"role": "assistant", "content": final_answer})
            
        except requests.exceptions.ConnectionError:
            st.error("🚨 Could not connect to the Swarm API. Is the FastAPI server running?")
