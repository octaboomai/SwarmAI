import streamlit as st
import requests
import os

# ─── SWARM LOGIC ─────────────────────────────────────────────────
HF_TOKEN = os.environ.get("HF_TOKEN")

MODELS = {
    "coder":   "codellama/CodeLlama-7b-Instruct-hf",
    "math":    "Qwen/Qwen2-Math-7B-Instruct",
    "general": "meta-llama/Meta-Llama-3-8B-Instruct"
}

def call_hf(model_key: str, prompt: str) -> str:
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    url = f"https://api-inference.huggingface.co/models/{MODELS[model_key]}"
    try:
        response = requests.post(url, headers=headers, json={
            "inputs": prompt,
            "parameters": {"max_new_tokens": 500}
        }, timeout=30)
        result = response.json()
        if isinstance(result, list):
            return result[0].get("generated_text", "No response")
        elif isinstance(result, dict) and "error" in result:
            return f"⚠️ Model error: {result['error']}"
        return str(result)
    except Exception as e:
        return f"❌ Error: {str(e)}"

def router(prompt: str):
    p = prompt.lower()
    if any(w in p for w in ["math", "calculate", "equation", "solve"]):
        return ["math", "coder"]
    elif any(w in p for w in ["code", "script", "python", "function"]):
        return ["coder", "general"]
    else:
        return ["general"]

# ─── UI ──────────────────────────────────────────────────────────
st.set_page_config(page_title="SwarmAI", page_icon="🐝")
st.title("🐝 SwarmAI — Multi-Agent System")
st.caption("Powered by Hugging Face Inference API")

if not HF_TOKEN:
    st.error("⚠️ HF_TOKEN is missing! Add it in Streamlit Cloud secrets.")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask your Swarm anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("🐝 Swarm is thinking..."):
            plan = router(prompt)
            result = prompt
            for model_key in plan:
                result = call_hf(model_key, result)
            plan_text = " → ".join(plan)
            full = f"**Route:** `{plan_text}`\n\n{result}"
            st.markdown(full)

    st.session_state.messages.append({"role": "assistant", "content": full})
