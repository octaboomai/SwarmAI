import streamlit as st
import sys
import os
import PyPDF2
import io

sys.path.append(os.path.dirname(__file__))
from swarm_engine import run_swarm

st.set_page_config(page_title="Hive Queen AI", layout="centered", initial_sidebar_state="expanded")

# --- UI STYLING ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500&display=swap');
#MainMenu, header, footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] { display: none !important; }
html, body, [data-testid="stAppViewContainer"] {
    background: #0e0e0f !important;
    font-family: 'DM Sans', sans-serif !important;
}
[data-testid="stMain"] > div {
    max-width: 720px !important;
    margin: 0 auto !important;
    padding: 0 16px !important;
}
.swarm-header {
    text-align: center;
    padding: 48px 0 32px;
    border-bottom: 1px solid #1e1e20;
    margin-bottom: 32px;
}
.swarm-logo { font-size: 36px; margin-bottom: 8px; }
.swarm-title {
    font-size: 20px;
    font-weight: 500;
    color: #f0f0f0;
    letter-spacing: -0.3px;
    margin: 0;
}
.swarm-sub { font-size: 13px; color: #555; margin-top: 4px; }
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin-bottom: 28px !important;
    gap: 12px !important;
}
[data-testid="chatAvatarIcon-user"],
[data-testid="chatAvatarIcon-assistant"] {
    width: 24px !important;
    height: 24px !important;
    min-width: 24px !important;
    border-radius: 50% !important;
    font-size: 12px !important;
}
[data-testid="chatAvatarIcon-user"]      { background: #2a2a2e !important; }
[data-testid="chatAvatarIcon-assistant"] { background: #f5a623 !important; color: black !important; }
[data-testid="stMarkdownContainer"] p {
    font-size: 15px !important;
    line-height: 1.7 !important;
    color: #d4d4d4 !important;
    margin: 0 0 8px !important;
}
[data-testid="stMarkdownContainer"] code {
    background: #1a1a1e !important;
    border: 1px solid #2a2a2e !important;
    border-radius: 4px !important;
    padding: 1px 6px !important;
    font-size: 13px !important;
    color: #a8d8a8 !important;
}
[data-testid="stMarkdownContainer"] pre {
    background: #141416 !important;
    border: 1px solid #222224 !important;
    border-radius: 8px !important;
    padding: 16px !important;
}
.route-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #141416;
    border: 1px solid #222;
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 11px;
    color: #555;
    margin-bottom: 12px;
}
.route-dot {
    width: 5px; height: 5px;
    border-radius: 50%;
    background: #f5a623;
    display: inline-block;
}
.thinking-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #444;
    font-size: 13px;
    padding: 8px 0;
}
.thinking-dot {
    width: 5px; height: 5px;
    border-radius: 50%;
    background: #f5a623;
    animation: pulse 1.2s infinite;
}
.thinking-dot:nth-child(2) { animation-delay: 0.2s; }
.thinking-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes pulse {
    0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
    40%            { opacity: 1;   transform: scale(1);   }
}
[data-testid="stChatInput"] {
    background: #141416 !important;
    border: 1px solid #222 !important;
    border-radius: 12px !important;
    padding: 4px 8px !important;
}
[data-testid="stChatInput"] textarea {
    background: transparent !important;
    color: #e0e0e0 !important;
    font-size: 15px !important;
    font-family: 'DM Sans', sans-serif !important;
}
[data-testid="stChatInput"] textarea::placeholder { color: #3a3a3e !important; }
.clear-btn button {
    background: transparent !important;
    border: 1px solid #222 !important;
    color: #444 !important;
    font-size: 12px !important;
    border-radius: 8px !important;
    padding: 2px 12px !important;
}
[data-testid="stSpinner"] { display: none !important; }
hr { border-color: #1a1a1c !important; margin: 24px 0 !important; }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR: SECURE PDF UPLOAD ---
if "document_context" not in st.session_state:
    st.session_state.document_context = ""

with st.sidebar:
    st.markdown("<h3 style='color: #f0f0f0;'>📂 Secure Vault</h3>", unsafe_allow_html=True)
    st.markdown("<p style='color: #888; font-size: 13px;'>Upload a private PDF. The Swarm will analyze it locally.</p>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("", type="pdf")
    
    if uploaded_file is not None:
        try:
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            text = ""
            for page in pdf_reader.pages:
                if page.extract_text():
                    text += page.extract_text() + "\n"
            
            # Limit to 12,000 characters to prevent Groq API Token crashes
            if len(text) > 12000:
                text = text[:12000] + "\n\n...[Document Truncated to fit Swarm Memory]..."
                
            st.session_state.document_context = text  # SAVE TO STATE
            st.success("✅ Securely Loaded")
            with st.expander("Preview Text"):
                st.write(text[:300] + "...")
        except Exception as e:
            st.error(f"Error reading PDF: {e}")

# --- MAIN HEADER ---
st.markdown("""
<div class="swarm-header">
    <div class="swarm-logo">🐝</div>
    <p class="swarm-title">Sovereign Swarm</p>
    <p class="swarm-sub">5 agents · collaborative intelligence · document analyst</p>
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns([6, 1])
with col2:
    if st.button("clear"):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        # Only show the route pill if it's an assistant AND route exists and isn't empty
        if msg["role"] == "assistant" and msg.get("route"):
            route_text = " · ".join(msg["route"])
            st.markdown(
                f'<div class="route-pill"><span class="route-dot"></span>{route_text}</div>',
                unsafe_allow_html=True
            )
        st.markdown(msg["content"])

# --- CHAT INPUT & EXECUTION ---
if prompt := st.chat_input("Ask the Swarm anything..."):
    
    # 1. Show the user their short prompt on screen
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Secretly build the massive prompt with the PDF text
    full_prompt = prompt
    if st.session_state.document_context != "":
        full_prompt = f"HERE IS A PRIVATE DOCUMENT FOR CONTEXT:\n\n{st.session_state.document_context}\n\nUSER QUESTION REGARDING THE DOCUMENT: {prompt}"

    # 3. Process with the Swarm
    with st.chat_message("assistant"):
        thinking = st.markdown("""
        <div class="thinking-wrap">
            <div class="thinking-dot"></div>
            <div class="thinking-dot"></div>
            <div class="thinking-dot"></div>
        </div>
        """, unsafe_allow_html=True)

        # Send the hidden massive prompt to the backend
        try:
            result = run_swarm(full_prompt)
        except Exception as e:
            result = {
                "plan": [],
                "final_answer": f"⚠️ **Swarm Error:** The agents encountered an issue: `{e}`",
                "history": []
            }
        finally:
            # This ensures the thinking animation goes away even if it crashes
            thinking.empty()

        route = result.get("plan", [])
        if route:
            route_text = " · ".join(route)
            st.markdown(
                f'<div class="route-pill"><span class="route-dot"></span>{route_text}</div>',
                unsafe_allow_html=True
            )

        st.markdown(result["final_answer"])

    st.session_state.messages.append({
        "role": "assistant",
        "content": result["final_answer"],
        "route": route
    })
