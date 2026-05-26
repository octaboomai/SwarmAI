"""
Sovereign Swarm Engine — Clean Chat UI
Minimal, conversation-first design. No clutter.
"""

import streamlit as st
import sys, os
sys.path.append(os.path.dirname(__file__))
from swarm_engine import run_swarm

# ── PAGE CONFIG ───────────────────────────────────────────────────
st.set_page_config(page_title="Hive Queen AI", layout="centered")
st.title("🐝 Sovereign Swarm Engine")
st.markdown("Powered by Local Open-Source Models, Dynamic Routing, & Self-Evolution.")

# ── CLEAN MINIMAL CSS ─────────────────────────────────────────────
st.markdown("""
<style>
/* Import clean font */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500&display=swap');

/* Hide all Streamlit chrome */
#MainMenu, header, footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"]          { display: none !important; }

/* Full page background */
html, body, [data-testid="stAppViewContainer"] {
    background: #0e0e0f !important;
    font-family: 'DM Sans', sans-serif !important;
}

/* Remove sidebar entirely */
[data-testid="stSidebar"] { display: none !important; }

/* Main content container */
[data-testid="stMain"] > div {
    max-width: 720px !important;
    margin: 0 auto !important;
    padding: 0 16px !important;
}

/* ── Header ── */
.swarm-header {
    text-align: center;
    padding: 48px 0 32px;
    border-bottom: 1px solid #1e1e20;
    margin-bottom: 32px;
}
.swarm-logo {
    font-size: 36px;
    margin-bottom: 8px;
}
.swarm-title {
    font-size: 20px;
    font-weight: 500;
    color: #f0f0f0;
    letter-spacing: -0.3px;
    margin: 0;
}
.swarm-sub {
    font-size: 13px;
    color: #555;
    margin-top: 4px;
}

/* ── Messages ── */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin-bottom: 28px !important;
    gap: 12px !important;
}

/* User bubble */
[data-testid="stChatMessage"][data-testid*="user"] > div:last-child,
.stChatMessage:has([data-testid="chatAvatarIcon-user"]) [data-testid="stMarkdownContainer"] p {
    color: #e0e0e0 !important;
}

/* Hide default avatars, replace with minimal dots */
[data-testid="chatAvatarIcon-user"],
[data-testid="chatAvatarIcon-assistant"] {
    width: 24px !important;
    height: 24px !important;
    min-width: 24px !important;
    border-radius: 50% !important;
    font-size: 12px !important;
}
[data-testid="chatAvatarIcon-user"] {
    background: #2a2a2e !important;
}
[data-testid="chatAvatarIcon-assistant"] {
    background: #1a1a1e !important;
}

/* Message text */
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

/* ── Route pill (tiny, subtle) ── */
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
    font-family: 'DM Sans', monospace;
}
.route-dot {
    width: 5px; height: 5px;
    border-radius: 50%;
    background: #f5a623;
    display: inline-block;
}

/* ── Thinking indicator ── */
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

/* ── Chat input ── */
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
[data-testid="stChatInput"] textarea::placeholder {
    color: #3a3a3e !important;
}

/* ── Clear button ── */
.clear-btn button {
    background: transparent !important;
    border: 1px solid #222 !important;
    color: #444 !important;
    font-size: 12px !important;
    border-radius: 8px !important;
    padding: 2px 12px !important;
}
.clear-btn button:hover {
    border-color: #444 !important;
    color: #888 !important;
}

/* ── Spinner override ── */
[data-testid="stSpinner"] { display: none !important; }

/* ── Divider ── */
hr { border-color: #1a1a1c !important; margin: 24px 0 !important; }
</style>
""", unsafe_allow_html=True)

# ── HEADER ────────────────────────────────────────────────────────
st.markdown("""
<div class="swarm-header">
    <div class="swarm-logo">🐝</div>
    <p class="swarm-title">Sovereign Swarm</p>
    <p class="swarm-sub">5 agents · collaborative intelligence</p>
</div>
""", unsafe_allow_html=True)

# ── CLEAR BUTTON (top right, minimal) ─────────────────────────────
col1, col2 = st.columns([6, 1])
with col2:
    st.markdown('<div class="clear-btn">', unsafe_allow_html=True)
    if st.button("clear"):
        st.session_state.messages = []
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ── CHAT STATE ────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── RENDER HISTORY ────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        # Show tiny route pill for assistant messages
        if msg["role"] == "assistant" and "route" in msg:
            route_text = " · ".join(msg["route"])
            st.markdown(
                f'<div class="route-pill"><span class="route-dot"></span>{route_text}</div>',
                unsafe_allow_html=True
            )
        st.markdown(msg["content"])

# ── CHAT INPUT ────────────────────────────────────────────────────
if prompt := st.chat_input("Ask anything..."):

    # User message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Assistant response
    with st.chat_message("assistant"):
        # Minimal thinking animation
        thinking = st.markdown("""
<div class="thinking-wrap">
    <div class="thinking-dot"></div>
    <div class="thinking-dot"></div>
    <div class="thinking-dot"></div>
</div>
""", unsafe_allow_html=True)

        # Run the swarm
        result = run_swarm(prompt)

        # Clear thinking animation
        thinking.empty()

        # Route pill — tiny and subtle
        route = result.get("plan", [])
        if route:
            route_text = " · ".join(route)
            st.markdown(
                f'<div class="route-pill"><span class="route-dot"></span>{route_text}</div>',
                unsafe_allow_html=True
            )

        # Final answer — just the text
        st.markdown(result["final_answer"])

    # Save to state
    st.session_state.messages.append({
        "role": "assistant",
        "content": result["final_answer"],
        "route": route
    })
