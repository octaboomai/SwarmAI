import os
import re
from typing import List
from duckduckgo_search import DDGS
from groq import Groq

print("[*] Waking the Hive Queen (v9.0 — Clean Architecture)...")

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPTS
# Topic-agnostic. Role-pure. These go in {"role": "system"} — NEVER
# concatenated into the user message.
# ─────────────────────────────────────────────────────────────────────────────

RESEARCHER_SYSTEM = """\
You are Sigma_Researcher. Your function: gather raw evidence about the exact question given.

RULES:
- Research ONLY the exact question. Do not drift to other topics.
- If search results are off-topic, state "Search data not relevant" and use internal knowledge.
- Mark uncertain claims [UNVERIFIED].
- No analysis. No opinion. No conclusions. Raw facts only.

Output format: a numbered list of findings. Nothing else."""


SYNTHESIZER_SYSTEM = """\
You are Prime_Synthesizer. Your function: turn research findings into a structured draft.

RULES:
- Work ONLY from the research provided. Never hallucinate facts.
- If coverage on a point is thin, write "Coverage limited here."
- Never write: Introduction, Conclusion, or Summary.
- Never produce code unless the original question asked for it.

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
You are Omega_Critic. Your function: quality-gate a draft against the original question.

Check in this order — stop at first failure:
1. Does the draft answer the ORIGINAL question?  If not  → REJECT
2. Claims not present in the research?           If yes  → REJECT (list each one)
3. Off-topic content unrelated to question?      If yes  → REJECT (identify it)
4. "Introduction" / "Conclusion" / unrequested code?  If yes → REJECT

If all 4 checks pass, output exactly:  APPROVED
If rejecting, output:  REJECT — [specific reason]"""


QUEEN_SYSTEM = """\
You are the Hive Queen. Your function: produce the final answer by integrating all agent outputs.

You receive: research findings, a synthesizer draft, and the critic's specific objections.

RULES:
1. Address every objection the Critic raised — explicitly, by name.
2. Add research findings the Synthesizer missed.
3. Resolve contradictions between the research and the draft.
4. Output must be strictly better than the draft alone — not a copy of it.

Required output format:

🎯 The Bottom Line
(2-sentence direct answer)

🧠 Context
(enriched explanation using all three agent inputs)

📊 Key Data Points
- (point 1)
- (point 2)
- (point 3)"""


CODER_SYSTEM = """\
You are Alpha_Coder. Write clean, working code for the exact request.
Add inline comments only for non-obvious logic.
No prose outside code blocks unless explicitly asked."""


# ─────────────────────────────────────────────────────────────────────────────
# TOOL
# ─────────────────────────────────────────────────────────────────────────────

def tool_web_search(query: str) -> str:
    print(f"    [SEARCH] {query!r}")
    try:
        results = DDGS().text(query, max_results=3)
        if not results:
            return "No results found."
        return "\n".join(
            f"[{i+1}] {r.get('title', '')}: {r.get('body', '')}"
            for i, r in enumerate(results)
        )
    except Exception as e:
        return f"Search failed ({e}). Use internal knowledge only."


# ─────────────────────────────────────────────────────────────────────────────
# LLM WRAPPER
# Critical fix: system prompt goes in {"role": "system"}, user content goes in
# {"role": "user"} — never merged into a single user message.
# ─────────────────────────────────────────────────────────────────────────────

def call_agent(system_prompt: str, user_content: str, temp: float = 0.3) -> str:
    try:
        r = groq_client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},  # role enforcement
                {"role": "user",   "content": user_content},   # scoped task input only
            ],
            max_tokens=1500,
            temperature=temp,
        )
        return r.choices[0].message.content
    except Exception as e:
        return f"[ERROR] {e}"


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-ANGLE RESEARCH
# This is where swarm diversity actually comes from.
# Same researcher, three different cognitive mandates → three different lenses.
# Kimi does this with parallel sub-agents. We do it with sequential angle calls.
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
        # Researcher context: query + live data. NOTHING ELSE — no dossier, no history.
        researcher_input = (
            f"Research angle: {angle}\n"
            f"Question: {user_prompt}\n\n"
            f"Live web data (use only if relevant to the question above):\n{live_data}"
        )
        output = call_agent(RESEARCHER_SYSTEM, researcher_input, temp=0.5)  # higher temp for coverage
        findings.append(f"=== [{angle.upper()} ANGLE] ===\n{output}")
        history.append({"node": f"Sigma_Researcher[{angle}]", "output": output})
        print(f"    [Sigma/{angle}] complete.")
    return "\n\n".join(findings), history


# ─────────────────────────────────────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────────────────────────────────────

_CODE_RE = re.compile(
    r'\b(write code|write a|code|python|script|implement|function|c\+\+|html|css|javascript|java|program)\b',
    re.IGNORECASE,
)

def get_routing_plan(prompt: str) -> List[str]:
    if _CODE_RE.search(prompt):
        return ["Alpha_Coder"]
    return ["Sigma_Researcher", "Prime_Synthesizer", "Omega_Critic", "Hive_Queen"]


# ─────────────────────────────────────────────────────────────────────────────
# SWARM PIPELINE
# Context isolation is enforced per phase. Each agent sees ONLY what it needs.
# The dossier never bleeds across sessions or across unrelated queries.
# External API is identical to v8.5 — Streamlit frontend needs zero changes.
# ─────────────────────────────────────────────────────────────────────────────

def run_swarm(user_prompt: str) -> dict:
    print(f"\n[SWARM v9.0] Query: {user_prompt[:60]}...")
    history = []

    plan = get_routing_plan(user_prompt)
    print(f"[*] Plan: {plan}")

    # ── Coding fast path ─────────────────────────────────────────────────────
    if plan == ["Alpha_Coder"]:
        print("[Alpha_Coder] Running...")
        output = call_agent(CODER_SYSTEM, user_prompt)
        history.append({"node": "Alpha_Coder", "output": output})
        return {"plan": plan, "final_answer": output, "history": history}

    # ── Phase 1: Research ─────────────────────────────────────────────────────
    # Each angle call receives: (query + live search). Nothing from prior sessions.
    print("[Sigma_Researcher] Running 3 cognitive angles...")
    research_output, research_history = run_multi_angle_research(user_prompt)
    history.extend(research_history)

    # ── Phase 2: Synthesis ───────────────────────────────────────────────────
    # Synthesizer receives: original question + research output.
    # It does NOT receive the raw dossier, prior history, or unrelated context.
    print("[Prime_Synthesizer] Drafting from research...")
    draft = call_agent(
        SYNTHESIZER_SYSTEM,
        f"Original question: {user_prompt}\n\nResearch findings:\n{research_output}",
        temp=0.3,
    )
    history.append({"node": "Prime_Synthesizer", "output": draft})

    # ── Phase 3: Critic ──────────────────────────────────────────────────────
    # Critic receives: original question + draft.
    # NOT the raw research — prevents confirmation bias in the quality gate.
    print("[Omega_Critic] Auditing...")
    critique = call_agent(
        CRITIC_SYSTEM,
        f"Original question: {user_prompt}\n\nDraft to review:\n{draft}",
        temp=0.1,  # lowest temp — strict binary judgement
    )
    history.append({"node": "Omega_Critic", "output": critique})

    # ── Phase 4: Queen integration ───────────────────────────────────────────
    # Queen is the ONE place where all outputs merge.
    # If Critic approved, the draft was clean — skip the extra LLM call.
    if "APPROVED" in critique.upper():
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
                f"Critic's objections:\n{critique}"
            ),
            temp=0.3,
        )

    history.append({"node": "Hive_Queen", "output": final_answer})
    return {"plan": plan, "final_answer": final_answer, "history": history}
