import streamlit as st
import streamlit.components.v1 as components
import sys
import os
import re
import PyPDF2

sys.path.append(os.path.dirname(__file__))
from swarm_engine import run_swarm

# ─────────────────────────────────────────────────────────────────────────────
# 1. CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
AGENCY_NAME = "Apex Swarm OS™"
WHATSAPP_NUMBER = "919876543210"  # CHANGE THIS TO YOUR WHATSAPP NUMBER
UPGRADE_MESSAGE = "Hi! I want to buy 10,000 Apex tokens. Please share payment details."
WHATSAPP_LINK = f"https://wa.me/{WHATSAPP_NUMBER}?text={UPGRADE_MESSAGE.replace(' ', '%20')}"

FREE_TRIAL_CODE = "FREETRIAL"
PRO_UNLOCK_CODE = "APEX_PRO_2024"
# NOTE: these access codes are plaintext in source. If this repo (or the
# Streamlit Community Cloud deployment) is public, anyone can read them
# straight out of the code. Worth swapping for env vars / a real auth
# system (Supabase, etc.) before this goes wide -- flagging, not changing,
# since that's a bigger architectural decision than a bug fix.

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
.route-pill { display: inline-flex; align-items: center; gap: 6px; background: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 4px 12px; font-size: 11px; color: #71717a; margin-bottom: 16px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }
.route-dot { width: 6px; height: 6px; border-radius: 50%; background: #f59e0b; display: inline-block; }
.exec-section { margin-top: 20px; padding-top: 16px; border-top: 1px solid #27272a; }
.exec-label { font-size: 12px; font-weight: 600; color: #f59e0b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
[data-testid="stChatInput"] { background: #18181b !important; border: 1px solid #27272a !important; border-radius: 8px !important; }
[data-testid="stChatInput"] textarea { background: transparent !important; color: #e4e4e7 !important; font-size: 15px !important; }
.stButton>button { background: #f59e0b !important; color: #000 !important; border: none !important; font-weight: 600 !important; border-radius: 6px !important; }
.whatsapp-btn { display: inline-block; background: #25D366; color: white !important; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: 600; margin-top: 10px; font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# 2b. RENDERING HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def extract_html(content: str):
    """
    fix: this is the bug from the screenshot. The old code only checked
    `if "```html" in content` to decide whether to render a generated app
    inside an iframe. When a model returns the HTML as the raw string value
    of a tool-call argument (which is normal -- the "wrap in ```html
    fences" instruction in the system prompt is a formatting convention for
    plain chat replies, not something every model bothers adding inside a
    JSON argument string), there's no fence to find. The old code then fell
    through to `st.markdown(content)`, which doesn't render raw HTML and
    instead just prints the literal "<!DOCTYPE html>..." text -- exactly
    what's in the screenshot.

    This function detects HTML several ways, in order, so it works whether
    or not the model bothered with markdown fences:
      1. A proper ```html ... ``` fence.
      2. A generic ``` ... ``` fence that happens to contain a <!DOCTYPE html>.
      3. No fence at all -- raw HTML starting somewhere in the text.
    Returns the HTML string, or None if nothing that looks like an HTML
    document is found.
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
    fix: this single function replaces two copy-pasted blocks (one in the
    chat-history replay loop, one in the live response handler) that had to
    be kept in sync by hand. Both now call this.
    """
    html_code = extract_html(content)
    if html_code:
        with st.expander("💻 View Generated Code"):
            st.code(html_code, language="html")
        components.html(html_code, height=500, scrolling=True)
        return

    display_output = content
    if "EXECUTIVE BOTTOM LINE:" in display_output:
        display_output = display_output.replace("🎯 EXECUTIVE BOTTOM LINE:", "<div class='exec-section'><div class='exec-label'>🎯 Executive Bottom Line</div>")
        display_output = display_output.replace("🧠 STRATEGIC CONTEXT:", "</div><div class='exec-section'><div class='exec-label'>🧠 Strategic Context</div>")
        display_output = display_output.replace("🚨 RISK MATRIX:", "</div><div class='exec-section'><div class='exec-label'>🚨 Risk Matrix</div>")
        display_output = display_output.replace("📊 KEY DATA POINTS:", "</div><div class='exec-section'><div class='exec-label'>📊 Key Data Points</div>")
        display_output += "</div>"
        st.markdown(display_output, unsafe_allow_html=True)
    else:
        st.markdown(display_output)

# ─────────────────────────────────────────────────────────────────────────────
# 3. ACCESS GATE & TOKEN ALLOCATION
# ─────────────────────────────────────────────────────────────────────────────
if "access_tier" not in st.session_state: st.session_state.access_tier = None
if "token_balance" not in st.session_state: st.session_state.token_balance = 0 # START AT 0
if "max_output_tokens" not in st.session_state: st.session_state.max_output_tokens = 4096

if st.session_state.access_tier is None:
    st.markdown(f"""
    <div class="agency-header">
        <div class="agency-logo">⚡</div>
        <p class="agency-title">{AGENCY_NAME}</p>
        <p class="agency-sub">Autonomous Intelligence · SaaS Generation · Research</p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("### 🔒 Private Access Portal")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Free Trial (500 Tokens)")
        free_code = st.text_input("Enter Free Trial Code:", key="free_code")
        if st.button("Unlock Free Trial"):
            if free_code == FREE_TRIAL_CODE:
                st.session_state.access_tier = "free"
                st.session_state.token_balance = 500 # GIVE EXACTLY 500 TOKENS FOR FREE
                st.rerun()
            else: st.error("Invalid Free Trial Code.")
    with col2:
        st.markdown("#### Pro Access (10,000 Tokens)")
        st.markdown(f'<a href="{WHATSAPP_LINK}" target="_blank" class="whatsapp-btn">💬 Buy 10K Tokens via WhatsApp</a>', unsafe_allow_html=True)
        pro_code = st.text_input("Enter Pro Code (sent via WhatsApp):", key="pro_code")
        if st.button("Unlock Pro"):
            if pro_code == PRO_UNLOCK_CODE:
                st.session_state.access_tier = "pro"
                st.session_state.token_balance = 10000 # GIVE 10,000 TOKENS AFTER PAYMENT
                st.rerun()
            else: st.error("Invalid Pro Code.")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# 4. SIDEBAR, TOKEN WALLET & DEAL ROOM
# ─────────────────────────────────────────────────────────────────────────────
if "document_context" not in st.session_state: st.session_state.document_context = ""

with st.sidebar:
    st.markdown(f"**👤 Tier: {st.session_state.access_tier.upper()}**")

    # TOKEN WALLET UI
    st.markdown("---")
    st.markdown("<h3 style='color: #fafafa; font-weight: 600;'>💰 Token Wallet</h3>", unsafe_allow_html=True)

    # Display Balance
    st.metric(label="Remaining Tokens", value=f"{st.session_state.token_balance:,}")

    # Manual Token Limit Slider
    st.markdown("**Manual AI Limit:**")
    st.markdown("<small>Control how many tokens the AI can use per response.</small>", unsafe_allow_html=True)
    st.session_state.max_output_tokens = st.slider(
        "Max Tokens per Response",
        min_value=500,
        max_value=8192,
        value=st.session_state.max_output_tokens,
        step=500
    )

    # Buy More Tokens (WhatsApp)
    if st.session_state.token_balance < 2000:
        st.warning("⚠️ Token balance low!")
    st.markdown(f'<a href="{WHATSAPP_LINK}" target="_blank" class="whatsapp-btn" style="width: 100%; text-align: center; display: block; font-size: 12px;">💬 Buy 10K Tokens</a>', unsafe_allow_html=True)

    st.divider()
    st.markdown("<h3 style='color: #fafafa; font-weight: 600;'>📂 Secure Context Room</h3>", unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload PDFs or Data", type="pdf")
    if uploaded_file:
        try:
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            text = "".join([page.extract_text() + "\n" for page in pdf_reader.pages if page.extract_text()])
            if len(text) > 12000: text = text[:12000] + "\n\n...[Truncated for Memory]"
            st.session_state.document_context = text
            st.success("✅ Loaded")
        except Exception as e: st.error(f"Error: {e}")
    st.divider()
    if st.button("🔒 Log Out"): st.session_state.access_tier = None; st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# 5. MAIN DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="agency-header">
    <div class="agency-logo">⚡</div>
    <p class="agency-title">{AGENCY_NAME}</p>
    <p class="agency-sub">Orchestrator Active · Wallet Connected</p>
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
# 6. CHAT INPUT & TOKEN EXECUTION
# ─────────────────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask for Research, Strategy, or Build an App..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)

    full_prompt = prompt
    if st.session_state.document_context != "":
        full_prompt = f"CONTEXT PROVIDED BY USER:\n\n{st.session_state.document_context}\n\nUSER REQUEST: {prompt}"

    with st.chat_message("assistant"):
        # 1. CHECK IF USER HAS ENOUGH TOKENS
        if st.session_state.token_balance <= 0:
            st.error("🚫 **Out of Tokens!** You do not have enough tokens to generate a response. Please purchase more via the WhatsApp link in the sidebar.")
            st.stop()

        with st.spinner("Apex Swarm is orchestrating..."):
            try:
                result = run_swarm(
                    full_prompt,
                    tier=st.session_state.access_tier,
                    max_output_tokens=st.session_state.max_output_tokens
                )
            except Exception as e:
                result = {"plan": [], "final_answer": f"⚠️ Critical Error: `{e}`", "tokens_used": 0}

        # 2. DEDUCT TOKENS FROM WALLET
        tokens_consumed = result.get("tokens_used", 0)
        st.session_state.token_balance -= tokens_consumed
        if st.session_state.token_balance < 0: st.session_state.token_balance = 0

        clean_route = list(dict.fromkeys(result.get("plan", [])))

        # 3. Display Route and Token Cost
        if clean_route:
            route_text = " ➔ ".join(clean_route)
            st.markdown(f'<div class="route-pill"><span class="route-dot"></span>{route_text} | 💸 Cost: {tokens_consumed} tokens</div>', unsafe_allow_html=True)

        final_output = result.get("final_answer", "Swarm failed.")

        # 4. LIVE ARTIFACT RENDERING ENGINE
        render_assistant_content(final_output)
        st.session_state.messages.append({"role": "assistant", "content": final_output, "route": clean_route})
