import streamlit as st
import streamlit.components.v1 as components
import sys
import os
import re
import datetime

sys.path.append(os.path.dirname(__file__))
from swarm_engine import run_swarm

# ─────────────────────────────────────────────────────────────────────────────
# 1. CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
AGENCY_NAME = "Apex Swarm OS™"

# Usage limits instead of a paid token wallet. Every visitor gets the same
# allowance, no codes, no payment links.
RESET_WINDOW_HOURS = 4
LONG_CONTEXT_LIMIT = 3      # deep, max-token runs
SHORT_CONTEXT_LIMIT = 4     # quick, lightweight runs

# "Long context" = let the swarm use its maximum output budget, and route to
# the more capable (NVIDIA/"pro") models. "Short context" = a small output
# budget on the fast/cheap ("free"/Groq) models. This reuses the two model
# tiers that already exist in swarm_engine.py instead of inventing a third
# routing path.
LONG_CONTEXT_MAX_TOKENS = 8192
SHORT_CONTEXT_MAX_TOKENS = 1024

st.set_page_config(page_title=AGENCY_NAME, layout="centered", initial_sidebar_state="expanded")

# ─────────────────────────────────────────────────────────────────────────────
# 2. PREMIUM UI STYLING
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap');
#MainMenu, header, footer, [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"] { display: none !important; }
html, body, [data-testid="stAppViewContainer"] { background: #09090b !important; font-family: 'Inter', sans-serif !important; }
[data-testid="stMain"] > div { max-width: 800px !important; margin: 0 auto !important; padding: 0 24px !important; }
.agency-header { text-align: center; padding: 48px 0 32px; border-bottom: 1px solid #27272a; margin-bottom: 32px; }
.agency-logo { font-size: 40px; margin-bottom: 8px; }
.agency-title { font-size: 22px; font-weight: 600; color: #fafafa; letter-spacing: -0.5px; margin: 0; }
.agency-sub { font-size: 13px; color: #71717a; margin-top: 6px; text-transform: uppercase; letter-spacing: 1px; }
[data-testid="stChatMessage"] { background: transparent !important; border: none !important; padding: 0 !important; margin-bottom: 32px !important; gap: 12px !important; }
[data-testid="chatAvatarIcon-user"] { background: #27272a !important; color: #a1a1aa !important; width: 28px !important; height: 28px !important; border-radius: 4px !important; }
[data-testid="chatAvatarIcon-assistant"] { background: #f59e0b !important; color: #000 !important; width: 28px !important; height: 28px !important; border-radius: 4px !important; }
[data-testid="stMarkdownContainer"] p { font-size: 15px !important; line-height: 1.8 !important; color: #d4d4d8 !important; margin: 0 0 8px !important; }

/* fix: these replace the old brittle "EXECUTIVE BOTTOM LINE:" string-replace
   hack in render_assistant_content(). The agent now just writes real
   Markdown (## headers, **bold**, tables) and these rules make it match
   the dark amber theme automatically -- for ANY well-structured answer,
   not only four hardcoded section labels. */
[data-testid="stMarkdownContainer"] h2 { font-size: 13px !important; font-weight: 600 !important; color: #f59e0b !important; text-transform: uppercase; letter-spacing: 0.8px; margin-top: 28px !important; margin-bottom: 12px !important; padding-top: 18px !important; border-top: 1px solid #27272a !important; }
[data-testid="stMarkdownContainer"] h2:first-child { margin-top: 0 !important; padding-top: 0 !important; border-top: none !important; }
[data-testid="stMarkdownContainer"] h3 { font-size: 14px !important; font-weight: 600 !important; color: #e4e4e7 !important; margin-top: 16px !important; }
[data-testid="stMarkdownContainer"] strong { color: #fafafa !important; font-weight: 600 !important; }
[data-testid="stMarkdownContainer"] ul, [data-testid="stMarkdownContainer"] ol { margin: 4px 0 12px 0 !important; padding-left: 22px !important; }
[data-testid="stMarkdownContainer"] li { color: #d4d4d8 !important; line-height: 1.8 !important; margin-bottom: 4px !important; font-size: 15px !important; }
[data-testid="stMarkdownContainer"] table { border-collapse: collapse !important; width: 100% !important; margin: 8px 0 16px 0 !important; }
[data-testid="stMarkdownContainer"] th { background: #18181b !important; color: #f59e0b !important; text-transform: uppercase; font-size: 11px !important; letter-spacing: 0.5px; padding: 8px 12px !important; border-bottom: 1px solid #27272a !important; text-align: left !important; }
[data-testid="stMarkdownContainer"] td { padding: 8px 12px !important; border-bottom: 1px solid #27272a !important; color: #d4d4d8 !important; font-size: 14px !important; }

.route-pill { display: inline-flex; align-items: center; gap: 6px; background: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 4px 12px; font-size: 11px; color: #71717a; margin-bottom: 16px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }
.route-dot { width: 6px; height: 6px; border-radius: 50%; background: #f59e0b; display: inline-block; }
[data-testid="stChatInput"] { background: #18181b !important; border: 1px solid #27272a !important; border-radius: 8px !important; }
[data-testid="stChatInput"] textarea { background: transparent !important; color: #e4e4e7 !important; font-size: 15px !important; }
.stButton>button { background: #f59e0b !important; color: #000 !important; border: none !important; font-weight: 600 !important; border-radius: 6px !important; }
div[role="radiogroup"] { gap: 8px !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# 3. RENDERING HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def extract_html(content: str):
    """
    Finds generated app HTML whether or not the model wrapped it in
    ```html fences -- many models put raw HTML straight into a tool-call
    argument with no fence at all.
    """
    if not content:
        return None

    fence_match = re.search(r"```html\s*\n?(.*?)```", content, re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    generic_fence = re.search(r"```\s*\n?(<!DOCTYPE html.*?)```", content, re.DOTALL | re.IGNORECASE)
    if generic_fence:
        return generic_fence.group(1).strip()

    doctype_match = re.search(r"<!DOCTYPE html.*", content, re.DOTALL | re.IGNORECASE)
    if doctype_match:
        return doctype_match.group(0).strip()

    html_tag_match = re.search(r"<html[\s>].*", content, re.DOTALL | re.IGNORECASE)
    if html_tag_match:
        return html_tag_match.group(0).strip()

    return None


def render_assistant_content(content: str):
    """
    fix: no more hand-rolled string replacement for "EXECUTIVE BOTTOM LINE:"
    etc. The Apex_Strategist prompt now produces real Markdown (## headers,
    **bold**, tables, bullets), and Streamlit renders that natively -- the
    CSS block above just themes it. This works for any well-structured
    answer, not only four hardcoded labels.
    """
    html_code = extract_html(content)
    if html_code:
        with st.expander("💻 View Generated Code"):
            st.code(html_code, language="html")
        components.html(html_code, height=500, scrolling=True)
        return
    st.markdown(content)

# ─────────────────────────────────────────────────────────────────────────────
# 4. USAGE LIMITS (replaces the access-code gate + token wallet)
# ─────────────────────────────────────────────────────────────────────────────
def _init_usage_state():
    if "usage_window_start" not in st.session_state:
        st.session_state.usage_window_start = datetime.datetime.now()
        st.session_state.long_used = 0
        st.session_state.short_used = 0


def _maybe_reset_usage_window():
    elapsed = datetime.datetime.now() - st.session_state.usage_window_start
    if elapsed >= datetime.timedelta(hours=RESET_WINDOW_HOURS):
        st.session_state.usage_window_start = datetime.datetime.now()
        st.session_state.long_used = 0
        st.session_state.short_used = 0


def _time_until_reset() -> datetime.timedelta:
    elapsed = datetime.datetime.now() - st.session_state.usage_window_start
    remaining = datetime.timedelta(hours=RESET_WINDOW_HOURS) - elapsed
    return remaining if remaining.total_seconds() > 0 else datetime.timedelta(0)


_init_usage_state()
_maybe_reset_usage_window()

# ─────────────────────────────────────────────────────────────────────────────
# 5. SIDEBAR -- USAGE STATUS
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<h3 style='color: #fafafa; font-weight: 600;'>📊 Usage This Window</h3>", unsafe_allow_html=True)

    long_left = max(0, LONG_CONTEXT_LIMIT - st.session_state.long_used)
    short_left = max(0, SHORT_CONTEXT_LIMIT - st.session_state.short_used)
    st.markdown(f"🧠 **Long Context:** {long_left} / {LONG_CONTEXT_LIMIT} left")
    st.markdown(f"⚡ **Short Context:** {short_left} / {SHORT_CONTEXT_LIMIT} left")

    remaining = _time_until_reset()
    hrs, rem_secs = divmod(int(remaining.total_seconds()), 3600)
    mins = rem_secs // 60
    st.caption(f"🔁 Resets in {hrs}h {mins}m")

    st.divider()
    st.caption("**Long Context** lets the swarm think with its full token budget on the stronger model tier. **Short Context** is a fast, lightweight pass on the quicker tier.")

# ─────────────────────────────────────────────────────────────────────────────
# 6. MAIN DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="agency-header">
    <div class="agency-logo">⚡</div>
    <p class="agency-title">{AGENCY_NAME}</p>
    <p class="agency-sub">Orchestrator Active</p>
</div>
""", unsafe_allow_html=True)

if "messages" not in st.session_state: st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and msg.get("route"):
            route_text = " ➔ ".join(msg["route"])
            st.markdown(f'<div class="route-pill"><span class="route-dot"></span>{route_text}</div>', unsafe_allow_html=True)
        if msg["role"] == "assistant":
            render_assistant_content(msg["content"])
        else:
            st.markdown(msg["content"])

# ─────────────────────────────────────────────────────────────────────────────
# 7. MODE SELECTOR + CHAT INPUT
# ─────────────────────────────────────────────────────────────────────────────
mode_choice = st.radio(
    "Response depth",
    options=["⚡ Short Context", "🧠 Long Context"],
    horizontal=True,
    key="context_mode",
    label_visibility="collapsed",
)
is_long = mode_choice.startswith("🧠")

if prompt := st.chat_input("Ask for Research, Strategy, or Build an App..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    with st.chat_message("assistant"):
        _maybe_reset_usage_window()

        # 1. CHECK USAGE LIMITS FOR THE SELECTED MODE
        if is_long and st.session_state.long_used >= LONG_CONTEXT_LIMIT:
            remaining = _time_until_reset()
            hrs, rem_secs = divmod(int(remaining.total_seconds()), 3600)
            mins = rem_secs // 60
            st.error(f"🚫 You've used all {LONG_CONTEXT_LIMIT} Long Context requests for this window. Resets in {hrs}h {mins}m, or switch to Short Context.")
            st.stop()
        if (not is_long) and st.session_state.short_used >= SHORT_CONTEXT_LIMIT:
            remaining = _time_until_reset()
            hrs, rem_secs = divmod(int(remaining.total_seconds()), 3600)
            mins = rem_secs // 60
            st.error(f"🚫 You've used all {SHORT_CONTEXT_LIMIT} Short Context requests for this window. Resets in {hrs}h {mins}m.")
            st.stop()

        max_output_tokens = LONG_CONTEXT_MAX_TOKENS if is_long else SHORT_CONTEXT_MAX_TOKENS
        tier = "pro" if is_long else "free"
        mode_label = "🧠 Long" if is_long else "⚡ Short"

        with st.spinner("Apex Swarm is orchestrating..."):
            try:
                result = run_swarm(prompt, tier=tier, max_output_tokens=max_output_tokens)
            except Exception as e:
                result = {"plan": [], "final_answer": f"⚠️ Critical Error: `{e}`", "tokens_used": 0}

        # 2. RECORD THE USE (counts whether the run succeeded or errored --
        # the request still happened either way)
        if is_long:
            st.session_state.long_used += 1
        else:
            st.session_state.short_used += 1

        tokens_consumed = result.get("tokens_used", 0)
        clean_route = list(dict.fromkeys(result.get("plan", [])))

        # 3. Display route + mode + token count
        if clean_route:
            route_text = " ➔ ".join(clean_route)
            st.markdown(f'<div class="route-pill"><span class="route-dot"></span>{mode_label} · {route_text} · {tokens_consumed} tokens</div>', unsafe_allow_html=True)

        final_output = result.get("final_answer", "Swarm failed.")

        # 4. RENDER
        render_assistant_content(final_output)
        st.session_state.messages.append({"role": "assistant", "content": final_output, "route": clean_route})
