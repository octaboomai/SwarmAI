import os
import re
from typing import List, Tuple
from duckduckgo_search import DDGS
from groq import Groq

print("[*] Waking the Hive Queen (v9.2 — Fully Debugged)...")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 1: Validate API key at startup to prevent cryptic mid-query crashes
# ─────────────────────────────────────────────────────────────────────────────
if not os.environ.get("GROQ_API_KEY"):
    raise RuntimeError(
        "FATAL ERROR: GROQ_API_KEY environment variable is not set. "
        "Please add it to your Streamlit Secrets."
    )

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPTS
# ─────────────────────────────────────────────────────────────────────────────

RESEARCHER_SYSTEM = """\
You are Sigma_Researcher. Your function: gather raw evidence about the exact question given.

RULES:
- Research ONLY the exact question. Do not drift to other topics.
- If web data is irrelevant or missing, FALL BACK to your internal training knowledge.
  Never refuse to produce findings — always provide at least 3.
- Label every finding: [LIVE DATA] when sourced from web results, [INTERNAL KNOWLEDGE] otherwise.
- No analysis. No opinion. No conclusions. Raw facts only.

Output: a numbered list of findings. Nothing else."""


SYNTHESIZER_SYSTEM = """\
You are Prime_Synthesizer. Your function: produce a draft that directly answers the original question.

RULES:
- Use research findings as your primary source.
- If findings are sparse, supplement with reliable knowledge — mark it [SUPPLEMENTED].
- Always produce a complete, useful answer. Never refuse.
- No "Introduction", "Conclusion", or "Summary" headers.
- No code unless the question explicitly asked for it.

Required output format — no exceptions:

🎯 The Bottom Line
(2-sentence direct answer to the original question)

🧠 Context
(3–4 sentences on the broader picture)

📊 Key Data Points
- (finding 1)
- (finding 2)
- (finding 3)"""


CRITIC_SYSTEM = """\
You are Omega_Critic. Quality-gate the draft against the original question.

Check in this order:
1. Does the draft attempt to answer the ORIGINAL question?         If NO  → REJECT
2. Are claims clearly fabricated or contradicting known facts?     If YES → REJECT (list each)
3. Off-topic content unrelated to the question?                    If YES → REJECT (identify it)
4. "Introduction"/"Conclusion" headers or unrequested code?        If YES → REJECT

IMPORTANT: Lack of real-time data is NOT a rejection reason.
Answers drawing on internal knowledge are valid — do not reject them for it.

All checks pass → output exactly: APPROVED
Any fundamental failure → output: REJECT — [precise reason]"""


QUEEN_SYSTEM = """\
You are the Hive Queen. Deliver the best possible final answer to the original question.

You receive: research findings, a synthesizer draft, and the critic's feedback.

RULES:
1. Your ONLY output is the answer to the original question. No meta-commentary about agents.
2. Silently fix every issue the Critic raised — correct the content, never name the issue.
3. Pull in research findings the Synthesizer missed.
4. When research is thin, use your own knowledge — mark additions [HQ].
5. Never discuss what went wrong. Just deliver the correct answer.

Required output format:

🎯 The Bottom Line
(2-sentence direct answer)

🧠 Context
(enriched explanation)

📊 Key Data Points
- (point 1)
- (point 2)
- (point 3)"""


CODER_SYSTEM = """\
You are Alpha_Coder. Write clean, working code for the exact request.
Add inline comments only for non-obvious logic.
No prose outside code blocks unless explicitly asked."""


# ─────────────────────────────────────────────────────────────────────────────
# ANGLE DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

ANGLES = [
    # (angle_name,  search_suffix,       llm_focus)
    ("facts",    "",                  "verifiable facts, statistics, and official statements"),
    ("analysis", " analysis",         "expert analysis, second-order implications, and broader context"),
    ("risks",    " risks criticism",  "counterarguments, risks, downsides, and criticism"),
]


# ─────────────────────────────────────────────────────────────────────────────
# TOOL
# ─────────────────────────────────────────────────────────────────────────────

def tool_web_search(query: str) -> str:
    """Run a DuckDuckGo text search. Query must be concise keywords."""
    print(f"    [SEARCH] {query!r}")
    try:
        # Use context manager to prevent connection leaks on Streamlit Cloud
        # Added timeout=10 to prevent the app from hanging if DDG rate-limits the IP
        with DDGS(timeout=10) as ddgs:
            results = ddgs.text(query.strip(), max_results=5)
            
        if not results:
            return "No results found."
        return "\n".join(
            f"[{i+1}] {r.get('title', '')}: {r.get('body', '')}"
            for i, r in enumerate(results)
        )
    except Exception as e:
        return f"Search failed ({e}). Researcher should use internal knowledge."


# ─────────────────────────────────────────────────────────────────────────────
# LLM WRAPPER
# ─────────────────────────────────────────────────────────────────────────────

def call_agent(system_prompt: str, user_content: str, temp: float = 0.3, max_tokens: int = 2000) -> str:
    try:
        r = groq_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            max_tokens=max_tokens,
            temperature=temp,
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"[ERROR] {e}"


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-ANGLE RESEARCH
# ─────────────────────────────────────────────────────────────────────────────

def run_multi_angle_research(user_prompt: str) -> Tuple[str, list]:
    history, findings = [], []

    for angle, search_suffix, llm_focus in ANGLES:
        search_query = (user_prompt + search_suffix).strip()
        live_data = tool_web_search(search_query)

        researcher_input = (
            f"Research angle: {angle} — focus on {llm_focus}\n"
            f"Question: {user_prompt}\n\n"
            f"Live web data:\n{live_data}\n\n"
            "If the web data is irrelevant or unavailable, use your internal "
            "knowledge and label findings [INTERNAL KNOWLEDGE]."
        )
        output = call_agent(RESEARCHER_SYSTEM, researcher_input, temp=0.5, max_tokens=2000)
        findings.append(f"=== [{angle.upper()} ANGLE] ===\n{output}")
        history.append({"node": f"Sigma_Researcher[{angle}]", "output": output})
        print(f"    [Sigma/{angle}] complete.")

    return "\n\n".join(findings), history


# ─────────────────────────────────────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# FIX 4: Tighten router regex to avoid false "code" classification
# Prevents "What is the genetic code?" or "Government program" from triggering Alpha_Coder
# ─────────────────────────────────────────────────────────────────────────────
_CODE_RE = re.compile(
    r'\b(write\s+code|write\s+a\s+script|write\s+a\s+function|implement\s+(a\s+)?(function|class|script)|code\s+this|program\s+this|script\s+this|create\s+a\s+(python|html|javascript)\s+)\b',
    re.IGNORECASE,
)

def get_routing_plan(prompt: str) -> List[str]:
    if _CODE_RE.search(prompt):
        return ["Alpha_Coder"]
    return ["Sigma_Researcher", "Prime_Synthesizer", "Omega_Critic", "Hive_Queen"]


# ─────────────────────────────────────────────────────────────────────────────
# SWARM PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def run_swarm(user_prompt: str) -> dict:
    print(f"\n[SWARM v9.2] Query: {user_prompt[:60]}...")
    history = []

    plan = get_routing_plan(user_prompt)
    print(f"[*] Plan: {plan}")

    # ── Coding fast path ──────────────────────────────────────────────────────
    if plan == ["Alpha_Coder"]:
        print("[Alpha_Coder] Running...")
        output = call_agent(CODER_SYSTEM, user_prompt, max_tokens=4000)
        history.append({"node": "Alpha_Coder", "output": output})
        return {"plan": plan, "final_answer": output, "history": history}

    # ── Phase 1: Research ─────────────────────────────────────────────────────
    print("[Sigma_Researcher] Running 3 cognitive angles...")
    research_output, research_history = run_multi_angle_research(user_prompt)
    history.extend(research_history)

    # ── Phase 2: Synthesis ────────────────────────────────────────────────────
    print("[Prime_Synthesizer] Drafting from research...")
    draft = call_agent(
        SYNTHESIZER_SYSTEM,
        f"Original question: {user_prompt}\n\nResearch findings:\n{research_output}",
        temp=0.3,
        max_tokens=2500,
    )
    history.append({"node": "Prime_Synthesizer", "output": draft})

    # ── Phase 3: Critic ───────────────────────────────────────────────────────
    print("[Omega_Critic] Auditing...")
    critique = call_agent(
        CRITIC_SYSTEM,
        f"Original question: {user_prompt}\n\nDraft to review:\n{draft}",
        temp=0.1,
        max_tokens=500,
    )
    history.append({"node": "Omega_Critic", "output": critique})

    # ── Phase 4: Queen integration ────────────────────────────────────────────
    
    # ─────────────────────────────────────────────────────────────────────────────
    # FIX 3: Hardified "APPROVED/REJECT" detection
    # Prevents "It is not approved" from falsely passing the quality gate.
    # ─────────────────────────────────────────────────────────────────────────────
    critique_normalized = critique.strip().lower()
    is_approved = "approve" in critique_normalized and "reject" not in critique_normalized

    if is_approved and draft and not draft.startswith("[ERROR]"):
        print("[*] Critic APPROVED. Draft is the final answer.")
        final_answer = draft
    else:
        print("[Hive_Queen] Integrating critique into final answer...")
        final_answer = call_agent(
            QUEEN_SYSTEM,
            (
                f"Original question: {user_prompt}\n\n"
                f"Research findings:\n{research_output}\n\n"
                f"Synthesizer draft:\n{draft}\n\n"
                f"Critic's specific issues:\n{critique}\n\n"
                "DIRECTIVE: Silently fix every issue above and deliver a complete, "
                "useful answer to the question. Do NOT mention agents, the critic, "
                "or what went wrong. Just answer."
            ),
            temp=0.3,
            max_tokens=2500,
        )

        # Graceful fallback if the Queen agent itself crashes/errors out
        if not final_answer or final_answer.startswith("[ERROR]"):
            print("[!] Hive Queen failed. Falling back to Synthesizer draft.")
            final_answer = (
                "*(Note: The final integration step encountered an issue, "
                "so the raw draft is provided below)*\n\n" + draft
            )

    history.append({"node": "Hive_Queen", "output": final_answer})
    return {"plan": plan, "final_answer": final_answer, "history": history}
