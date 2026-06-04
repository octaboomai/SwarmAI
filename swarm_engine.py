import os
import re
import time
from typing import List

from duckduckgo_search import DDGS
from groq import Groq

print("[*] Waking the Hive Queen (v9.1 — Fixed Architecture)...")

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPTS
# ─────────────────────────────────────────────────────────────────────────────

RESEARCHER_SYSTEM = """\
You are Sigma_Researcher. Gather raw evidence about the exact question given.

RULES:
- Research ONLY the exact question. Do not drift.
- If live web data is provided and relevant, extract every useful fact from it.
- If web data is off-topic or unavailable, USE YOUR INTERNAL TRAINING KNOWLEDGE.
  NEVER say "Search data not relevant" and stop. You must always produce ≥3 findings.
- Tag claims from internal knowledge with [INTERNAL].
- Tag uncertain claims with [UNVERIFIED].
- No analysis. No opinion. No conclusions. Raw facts only.

Output: a numbered list of findings (minimum 3). Nothing else."""


SYNTHESIZER_SYSTEM = """\
You are Prime_Synthesizer. Convert research findings into a structured draft.

RULES:
- Draw from the research provided; supplement with your own knowledge where coverage is thin.
- NEVER output "no information is available" or any variant — always produce real content.
- Never write: Introduction, Conclusion, or Summary headers.
- Never produce code unless the original question explicitly asked for it.

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

Check in order — stop at the first failure:
1. Does the draft answer the ORIGINAL question with specific, real information?
   A draft that says "no data available", discusses agent failures, or
   narrates process issues instead of answering → REJECT.
2. Does the draft contain obviously false factual claims? If yes → REJECT (list each).
3. Off-topic content unrelated to the question? If yes → REJECT (identify it).
4. Format violations: "Introduction"/"Conclusion" headers, or unrequested code? → REJECT.

NOTE: [INTERNAL] or [UNVERIFIED] tags are acceptable — internal knowledge is allowed.

If all checks pass → output exactly:  APPROVED
If rejecting  → output:  REJECT — [specific reason]"""


# FIX 3: This is the critical fix. The old prompt said "address every objection by name"
# which caused the Queen to literally echo the Critic's rejection message.
# The new prompt explicitly bans that behavior and requires a real answer.
QUEEN_SYSTEM = """\
You are the Hive Queen. Produce the FINAL, CORRECT ANSWER to the user's question.

You receive: original question, research findings, a synthesizer draft, critic objections.

⚠️  NON-NEGOTIABLE RULES:
1. You MUST answer the original question with real, substantive information.
2. If the Critic said the draft "does not answer the question" → ANSWER IT NOW.
   Do NOT say "the draft failed." Do NOT say "the Critic rejected it."
   Do NOT say "no information was provided." Just answer the question directly.
3. Use your own knowledge freely when research is thin.
4. NEVER produce meta-commentary about what other agents did, said, or failed to do.
5. "No information is available" is never an acceptable answer unless you genuinely
   have zero knowledge on the topic whatsoever.

Required output format:

🎯 The Bottom Line
(2-sentence DIRECT factual answer to the original question)

🧠 Context
(real facts and explanation — not commentary about agents or the research process)

📊 Key Data Points
- (concrete fact 1)
- (concrete fact 2)
- (concrete fact 3)"""


CODER_SYSTEM = """\
You are Alpha_Coder. Write clean, working code for the exact request.
Inline comments only for non-obvious logic.
No prose outside code blocks unless explicitly asked."""


# ─────────────────────────────────────────────────────────────────────────────
# TOOL  (FIX 1: context manager + retry-with-backoff)
# ─────────────────────────────────────────────────────────────────────────────

def tool_web_search(query: str, retries: int = 2) -> str:
    """
    DuckDuckGo text search.
    - Uses `with DDGS()` context manager (required by duckduckgo_search ≥ 5.x).
    - Retries up to `retries` times with exponential backoff on any exception.
    - Returns a plain-text fallback message so the Researcher can still use
      internal knowledge instead of crashing.
    """
    print(f"    [SEARCH] {query!r}")
    for attempt in range(retries + 1):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=4))
            if results:
                return "\n".join(
                    f"[{i+1}] {r.get('title', '')}: {r.get('body', '')}"
                    for i, r in enumerate(results)
                )
            return "No results returned. Use your internal knowledge."
        except Exception as e:
            if attempt < retries:
                wait = 1.5 ** attempt          # 1.0 s, then 1.5 s
                print(f"    [SEARCH] attempt {attempt+1} failed ({e}). "
                      f"Retry in {wait:.1f}s…")
                time.sleep(wait)
            else:
                print(f"    [SEARCH] all attempts failed: {e}")
                return "Search unavailable. Use your internal knowledge only."


# ─────────────────────────────────────────────────────────────────────────────
# LLM WRAPPER
# ─────────────────────────────────────────────────────────────────────────────

def call_agent(system_prompt: str, user_content: str, temp: float = 0.3) -> str:
    try:
        r = groq_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            max_tokens=1500,
            temperature=temp,
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"[ERROR] {e}"


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-ANGLE RESEARCH
# ─────────────────────────────────────────────────────────────────────────────

ANGLES = [
    ("facts",    "Find verifiable facts, statistics, and official statements about: "),
    ("analysis", "Find expert analysis, second-order implications, and broader context for: "),
    ("risks",    "Find counterarguments, downsides, risks, and criticism related to: "),
]


def run_multi_angle_research(user_prompt: str) -> tuple[str, list]:
    history, findings = [], []
    for angle, prefix in ANGLES:
        live_data = tool_web_search(prefix + user_prompt)
        researcher_input = (
            f"Research angle: {angle}\n"
            f"Question: {user_prompt}\n\n"
            f"Live web data (use if relevant; fall back to internal knowledge otherwise):\n"
            f"{live_data}"
        )
        output = call_agent(RESEARCHER_SYSTEM, researcher_input, temp=0.5)
        findings.append(f"=== [{angle.upper()} ANGLE] ===\n{output}")
        history.append({"node": f"Sigma_Researcher[{angle}]", "output": output})
        print(f"    [Sigma/{angle}] complete.")
    return "\n\n".join(findings), history


# ─────────────────────────────────────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────────────────────────────────────

_CODE_RE = re.compile(
    r'\b(write code|write a|code|python|script|implement|function|c\+\+|html|css|'
    r'javascript|java|program)\b',
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
    print(f"\n[SWARM v9.1] Query: {user_prompt[:60]}...")
    history = []

    plan = get_routing_plan(user_prompt)
    print(f"[*] Plan: {plan}")

    # ── Coding fast path ──────────────────────────────────────────────────────
    if plan == ["Alpha_Coder"]:
        print("[Alpha_Coder] Running...")
        output = call_agent(CODER_SYSTEM, user_prompt)
        history.append({"node": "Alpha_Coder", "output": output})
        return {"plan": plan, "final_answer": output, "history": history}

    # ── Phase 1: Research ─────────────────────────────────────────────────────
    print("[Sigma_Researcher] Running 3 cognitive angles…")
    research_output, research_history = run_multi_angle_research(user_prompt)
    history.extend(research_history)

    # ── Phase 2: Synthesis ────────────────────────────────────────────────────
    print("[Prime_Synthesizer] Drafting…")
    draft = call_agent(
        SYNTHESIZER_SYSTEM,
        f"Original question: {user_prompt}\n\nResearch findings:\n{research_output}",
        temp=0.3,
    )
    history.append({"node": "Prime_Synthesizer", "output": draft})

    # ── Phase 3: Critic ───────────────────────────────────────────────────────
    print("[Omega_Critic] Auditing…")
    critique = call_agent(
        CRITIC_SYSTEM,
        f"Original question: {user_prompt}\n\nDraft to review:\n{draft}",
        temp=0.1,
    )
    history.append({"node": "Omega_Critic", "output": critique})

    # ── Phase 4: Queen integration ────────────────────────────────────────────
    if "APPROVED" in critique.upper():
        print("[*] Critic APPROVED — draft is the final answer.")
        final_answer = draft
    else:
        print("[Hive_Queen] Integrating critique into final answer…")
        final_answer = call_agent(
            QUEEN_SYSTEM,
            (
                f"Original question: {user_prompt}\n\n"
                f"Research findings:\n{research_output}\n\n"
                f"Synthesizer draft:\n{draft}\n\n"
                f"Critic's objections:\n{critique}"
            ),
            temp=0.3,
        )

    history.append({"node": "Hive_Queen", "output": final_answer})
    return {"plan": plan, "final_answer": final_answer, "history": history}


# ─────────────────────────────────────────────────────────────────────────────
# FIX 5: format_swarm_trace()
# Call this in your Streamlit app to render each agent's output separately.
# That's what makes the UI actually look like a swarm, not a single monologue.
#
# Streamlit usage example:
#
#   result = run_swarm(user_query)
#   for entry in result["history"]:
#       icon = AGENT_ICONS.get(entry["node"], "🤖")
#       with st.expander(f"{icon}  {entry['node']}", expanded=False):
#           st.markdown(entry["output"])
#   st.markdown("---")
#   st.markdown("### 👑 Final Answer")
#   st.markdown(result["final_answer"])
# ─────────────────────────────────────────────────────────────────────────────

AGENT_ICONS = {
    "Sigma_Researcher[facts]":    "🔎",
    "Sigma_Researcher[analysis]": "🧩",
    "Sigma_Researcher[risks]":    "⚠️ ",
    "Prime_Synthesizer":          "📝",
    "Omega_Critic":               "🛡️ ",
    "Hive_Queen":                 "👑",
    "Alpha_Coder":                "💻",
}


def format_swarm_trace(result: dict) -> str:
    """
    Returns the full swarm trace as a formatted string for terminal output.
    For Streamlit, use the st.expander() pattern shown above instead.
    """
    BAR  = "─" * 54
    WIDE = "═" * 54
    sections = [f"\n{WIDE}\n  🐝  SWARM TRACE\n{WIDE}"]
    for entry in result["history"]:
        icon = AGENT_ICONS.get(entry["node"], "🤖")
        sections.append(f"\n{icon}  {entry['node']}\n{BAR}\n{entry['output']}")
    sections.append(f"\n{WIDE}")
    return "\n".join(sections)
