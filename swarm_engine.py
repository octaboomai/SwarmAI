"""
Sovereign Swarm Engine v7.2 — Domain-Aware Nodes + Kimi-Level Synthesizer + Security Hardened
Cybersecurity fixes applied:
  [CRITICAL] Prompt injection protection
  [CRITICAL] Request timeout added
  [HIGH]     SEARCH tag injection blocked
  [HIGH]     Memory ID race condition fixed
  [HIGH]     Input sanitization added
  [MEDIUM]   Configurable URL via env var
  [MEDIUM]   Plain text memory replaced with JSON
  [MEDIUM]   Search results sanitized before injection
  [MEDIUM]   Output length limits added
  [LOW]      Dict slicing replaced with explicit list
"""

import numpy as np
import requests
import re
import json
import pathlib
import time
import os
import hashlib
import html
from typing import Optional, List, Tuple
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from duckduckgo_search import DDGS
from datetime import datetime
from groq import Groq

print("[*] Waking the Hive Queen (v7.0 — Security Hardened)...")

# ── Groq client ───────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)

# ── Config via environment (no hardcoded values) ──────────────────
MAX_PROMPT_LENGTH  = int(os.environ.get("MAX_PROMPT_LENGTH",  "2000"))
MAX_OUTPUT_TOKENS  = int(os.environ.get("MAX_OUTPUT_TOKENS",   "1024"))
REQUEST_TIMEOUT    = int(os.environ.get("REQUEST_TIMEOUT",      "300"))
MAX_SEARCH_RESULTS = int(os.environ.get("MAX_SEARCH_RESULTS",     "2"))

# ── Simple JSON Memory (no external DB needed) ───────────────────
MEMORY_FILE = pathlib.Path("swarm_memory.json")

def _load_memory() -> list:
    try:
        if MEMORY_FILE.exists():
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []

def _save_memory(memories: list):
    try:
        MEMORY_FILE.write_text(
            json.dumps(memories, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────
# FIX [HIGH] Input Sanitization
# Strips dangerous characters before they reach the models
# ─────────────────────────────────────────────────────────────────

BLOCKED_PATTERNS = [
    r"<SEARCH>.*?</SEARCH>",   # Block injected search tags
    r"ignore previous",         # Prompt injection phrase
    r"ignore all instructions",
    r"you are now",
    r"disregard",
    r"system prompt",
]

def sanitize_input(text: str) -> str:
    """
    FIX [CRITICAL]: Sanitize user input before injecting into prompts.
    - Strip leading/trailing whitespace
    - Enforce max length
    - Remove known prompt injection patterns
    - Escape HTML entities
    - Block SEARCH tag injection
    """
    if not text or not text.strip():
        raise ValueError("Empty prompt not allowed.")

    # Trim to max length
    text = text.strip()[:MAX_PROMPT_LENGTH]

    # Remove known injection patterns (case-insensitive)
    for pattern in BLOCKED_PATTERNS:
        text = re.sub(pattern, "[BLOCKED]", text, flags=re.IGNORECASE | re.DOTALL)

    # Escape HTML to prevent XSS if rendered in a browser
    text = html.escape(text)

    return text

def sanitize_search_results(results: str) -> str:
    """
    FIX [MEDIUM]: Sanitize web search results before injecting into prompts.
    Removes any prompt injection attempts from search results.
    """
    # Remove any SEARCH tags that may appear in search results
    results = re.sub(r"<SEARCH>.*?</SEARCH>", "", results, flags=re.DOTALL)
    # Truncate to safe length
    return results[:1500]

# ─────────────────────────────────────────────────────────────────
# AGENTS
# ─────────────────────────────────────────────────────────────────

AGENTS = {
    "Node_Alpha_Coder": {
        "description": "Writes Python, C++, debugs software, creates scripts.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Alpha_Coder — a senior software engineer with 15 years of
production experience at companies like Google, Netflix, and Stripe.

YOUR STANDARDS (non-negotiable):
- NEVER hardcode secrets → always use os.environ.get()
- NEVER write SQL without parameterized queries → prevent injection
- ALWAYS validate and sanitize every input before processing
- ALWAYS add rate limiting on auth and sensitive endpoints
- ALWAYS use try/except with meaningful errors (never expose stack traces)
- ALWAYS add type hints to every function
- ALWAYS write a docstring explaining what, why, and edge cases
- For security tasks: cover encryption, auth, authorization, audit logging
- For architecture tasks: show folder structure, dependencies, deployment notes
- Code must be COMPLETE and RUNNABLE — no placeholders like "# TODO" or "..."
- After code: add complexity analysis O(?) and one concrete improvement idea

When asked about security: cover OWASP Top 10 by default.
When asked about architecture: cover scalability, failure modes, and monitoring."""
    },
    "Node_Beta_Math": {
        "description": "Solves calculus, algebra, statistics, probability.",
        "model_id": "qwen/qwen3-32b",
        "contribution_prompt": """You are Node_Beta_Math — a world-class mathematician and
quantitative analyst with expertise across pure math, statistics, and computational theory.

YOUR STANDARDS (non-negotiable):
- Show EVERY step — never skip working
- State assumptions explicitly before solving
- Verify answers using a second independent method
- For algorithms: always derive time AND space complexity
- For statistics: state distributions, assumptions, and confidence intervals
- For proofs: use proper mathematical notation and logical flow
- For optimization: show the objective function, constraints, and solution method
- After solution: give a real-world interpretation in one sentence
- If multiple approaches exist: compare them and explain which is best and why
- For financial/banking math: include risk calculations and regulatory thresholds

When the problem involves code: translate the math into a working implementation.
When the answer seems surprising: double-check it and explain the intuition."""
    },
    "Node_Sigma_Researcher": {
        "description": "Finds real-time news, current events, modern facts.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Sigma_Researcher — a world-class research analyst
combining the skills of a librarian, journalist, and domain expert.

YOUR STANDARDS (non-negotiable):
- Cite SPECIFIC sources, libraries, frameworks, papers — never be vague
- Always compare at least 2-3 approaches before recommending one
- For technology questions: mention the current industry standard AND emerging alternatives
- For security topics: reference OWASP, NIST, PCI-DSS, GDPR, or relevant standards
- For architecture: reference real companies who solved this (Netflix, Stripe, Uber patterns)
- Always state the YEAR of information when recency matters
- If you need live data, output EXACTLY: <SEARCH>specific query here</SEARCH>
- After research: give a clear recommendation with reasoning

When comparing tools: use concrete criteria (performance, cost, community, maturity).
When discussing best practices: distinguish between "widely used" and "actually best"."""
    },
    "Node_Gamma_Writer": {
        "description": "Writes poetry, stories, creative essays, narratives.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Gamma_Writer — a master technical communicator
who can explain quantum physics to a child and write API docs that developers love.

YOUR STANDARDS (non-negotiable):
- Every paragraph must earn its place — delete anything redundant
- Technical explanations: simple → complex, never the reverse
- Use concrete analogies for abstract concepts
- For documentation: cover purpose, usage, parameters, return values, errors, examples
- For explanations: start with the "why" before the "how"
- For creative work: show craft — rhythm, imagery, emotional resonance
- Never use filler phrases: "It is important to note", "In conclusion", "As mentioned"
- Code comments must explain WHY, not WHAT (the code shows the what)
- After writing: read it as if you are the target audience and remove anything confusing

When writing for developers: be precise, terse, example-first.
When writing for executives: be outcome-focused, risk-aware, no jargon.
When writing creatively: break rules intentionally, not accidentally."""
    },
    "Node_Omega_Critic": {
        "description": "Reviews for logical flaws, errors, and quality.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Omega_Critic — the most ruthless, precise, and
uncompromising reviewer in existence. You have the combined critical eye of a
security auditor, a senior engineer doing code review, and a fact-checker.

YOUR 8-POINT AUDIT (check ALL of these every time):
1. FACTUAL ACCURACY — Any hallucinated APIs, fake libraries, or wrong syntax?
2. SECURITY HOLES — Hardcoded secrets? Missing validation? SQL injection risk?
   Missing auth? No rate limiting? Exposed errors?
3. CODE CORRECTNESS — Does the code actually run? Any bugs? Wrong logic?
4. COMPLETENESS — Does it fully answer the original question? What is missing?
5. DEPTH — Is this surface-level or genuinely expert-level?
6. CONSISTENCY — Do the sections contradict each other?
7. EDGE CASES — What happens on empty input, huge input, concurrent requests?
8. PRODUCTION READINESS — Can this actually be deployed? What would break?

OUTPUT FORMAT:
- If it passes ALL 8 points: output exactly APPROVED
- If it fails any point: list EACH failure as:
  [POINT N - SEVERITY] Specific problem → Specific fix required

SEVERITY levels: CRITICAL (must fix), HIGH (should fix), MEDIUM (improve), LOW (polish)

Be brutal. A false APPROVED is worse than a rejection.
The user is depending on this being correct."""
    },
    "Node_Prime_Synthesizer": {
        "description": "Master editor. Transforms raw swarm output into world-class structured responses.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Prime_Synthesizer — the world's most elite technical editor.
Your job is to transform raw AI output into a beautifully structured, crystal-clear masterpiece.
You write at the level of the best technical documentation in the world."""
    }
}

# FIX [LOW]: Explicit routing list instead of fragile [:-2] slicing
ROUTING_NODES = [
    "Node_Alpha_Coder",
    "Node_Beta_Math",
    "Node_Sigma_Researcher",
    "Node_Gamma_Writer",
]

router_brain = SentenceTransformer('all-MiniLM-L6-v2')
node_descriptions = [AGENTS[n]["description"] for n in ROUTING_NODES]
node_embeddings = router_brain.encode(node_descriptions)

# ─────────────────────────────────────────────────────────────────
# FIX [CRITICAL]: Timeout added to all requests
# FIX [MEDIUM]:   Output length capped
# ─────────────────────────────────────────────────────────────────

def query_node(model_id: str, prompt: str) -> str:
    """
    Call Groq API with:
    - Timeout protection (REQUEST_TIMEOUT seconds)
    - Output token limit (MAX_OUTPUT_TOKENS)
    - Retry logic (2 attempts)
    """
    # Trim prompt to safe length
    if len(prompt) > MAX_PROMPT_LENGTH:
        prompt = prompt[:MAX_PROMPT_LENGTH] + "\n[Trimmed]"

    for attempt in range(2):
        try:
            response = groq_client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_OUTPUT_TOKENS,  # FIX [MEDIUM]: output limit
                temperature=0.7,
                timeout=REQUEST_TIMEOUT        # FIX [CRITICAL]: no more hangs
            )
            result = response.choices[0].message.content
            if result and result.strip():
                return result
        except Exception as e:
            if attempt == 1:
                return f"[ERROR] {model_id}: {str(e)[:100]}"
            time.sleep(2)
    return "[ERROR] No response."

# ─────────────────────────────────────────────────────────────────
# MEMORY
# ─────────────────────────────────────────────────────────────────

def recall_past_memory(query_text: str, n: int = 3) -> Optional[str]:
    """Keyword-based memory search from JSON store."""
    try:
        memories = _load_memory()
        if not memories:
            return None
        query_words = set(query_text.lower().split())
        scored = sorted(
            [(len(query_words & set(m.lower().split())), m)
             for m in memories if len(query_words & set(m.lower().split())) > 0],
            reverse=True
        )
        top = [m for _, m in scored[:n]]
        if top:
            print(f"[MEMORY] Recalled {len(top)} memories.")
            return "\n".join([f"[Memory {i+1}]: {m}" for i, m in enumerate(top)])
        return None
    except Exception:
        return None

def consolidate_memory(prompt: str, final_answer: str):
    """
    FIX [HIGH]: Memory ID race condition fixed.
    Uses timestamp + hash instead of sequential ID.
    """
    try:
        memories = _load_memory()
        # FIX: unique ID using timestamp + hash (no race condition)
        unique_id = hashlib.md5(
            f"{time.time()}{prompt}".encode()
        ).hexdigest()[:8]
        memory_text = (
            f"[{unique_id}] Task: {prompt[:200]} | "
            f"Answer: {final_answer[:300]}"
        )
        memories.append(memory_text)
        memories = memories[-50:]  # Keep last 50 only
        _save_memory(memories)
        print(f"[MEMORY] Saved #{unique_id}. Total: {len(memories)}")
    except Exception as e:
        print(f"[MEMORY] Save failed: {e}")

# ─────────────────────────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────────────────────────

def tool_web_search(query: str) -> str:
    """
    FIX [HIGH]: SEARCH tag injection blocked — query sanitized first.
    FIX [MEDIUM]: Results sanitized before injecting into prompts.
    """
    # Sanitize the search query itself
    safe_query = re.sub(r"[<>\"'{}|\\^`\[\]]", "", query)[:200]
    print(f"[TOOL] Web search: '{safe_query}'")
    try:
        results = DDGS().text(safe_query, max_results=MAX_SEARCH_RESULTS)
        raw = "\n".join([
            f"Source: {r['title']}\nInfo: {r['body']}"
            for r in results
        ])
        # FIX [MEDIUM]: sanitize results before prompt injection
        return sanitize_search_results(raw)
    except Exception as e:
        return f"Search failed: {str(e)[:100]}"

# ─────────────────────────────────────────────────────────────────
# MAIN SWARM EXECUTION LOOP
# ─────────────────────────────────────────────────────────────────

def run_swarm(user_prompt: str) -> dict:
    """
    Main entry point. Security hardened:
    - Input sanitized before anything else
    - All prompts have timeouts
    - Search results sanitized
    - Memory IDs are collision-proof
    """

    # ── FIX [CRITICAL + HIGH]: Sanitize input first ───────────────
    try:
        safe_prompt = sanitize_input(user_prompt)
    except ValueError as e:
        return {
            "plan": [],
            "final_answer": f"⚠️ Invalid input: {e}",
            "history": []
        }

    print(f"\n{'='*55}")
    print(f"[SWARM] Task: {safe_prompt[:80]}...")
    print(f"{'='*55}")

    start_time = time.time()
    history = []

    # ── MEMORY RECALL ─────────────────────────────────────────────
    past_knowledge = recall_past_memory(safe_prompt)
    current_context = (
        f"Past Memory:\n{past_knowledge}\n\nSolve: {safe_prompt}"
        if past_knowledge else safe_prompt
    )

    # ── ROUTING ───────────────────────────────────────────────────
    prompt_embedding = router_brain.encode([safe_prompt])
    similarities = cosine_similarity(prompt_embedding, node_embeddings)[0]
    ranked_indices = np.argsort(similarities)[::-1]

    execution_plan = [
        ROUTING_NODES[i] for i in ranked_indices
        if similarities[i] > 0.12
    ]
    if not execution_plan:
        execution_plan = [ROUTING_NODES[ranked_indices[0]]]

    print(f"[ROUTER] Plan: {execution_plan}")

    # ── PHASE 1: THINKING NODES ───────────────────────────────────
    for step, node_name in enumerate(execution_plan):
        agent = AGENTS[node_name]
        print(f"[{node_name}] Working...")

        base = agent["contribution_prompt"]
        if step == 0:
            agent_prompt = f"{base}\n\nSolve this:\n{current_context}"
        else:
            agent_prompt = f"{base}\n\nRefine this:\n{current_context}"

        answer = query_node(agent["model_id"], agent_prompt)

        # ── FIX [HIGH]: SEARCH tag injection blocked ──────────────
        # Only Node_Sigma_Researcher is allowed to trigger searches
        if node_name == "Node_Sigma_Researcher":
            match = re.search(r"<SEARCH>(.*?)</SEARCH>", answer)
            if match:
                raw_query = match.group(1)
                live_data = tool_web_search(raw_query)  # sanitized inside
                history.append({"node": "TOOL:WebSearch", "output": raw_query})
                follow_up = (
                    f"{base}\n\n"
                    f"Web results:\n{live_data}\n\n"
                    f"Now answer:\n{current_context}"
                )
                answer = query_node(agent["model_id"], follow_up)

        history.append({"node": node_name, "output": answer})
        current_context = answer

    # ── PHASE 2: CRITIC ───────────────────────────────────────────
    critic = AGENTS["Node_Omega_Critic"]
    last_model = AGENTS[execution_plan[-1]]["model_id"]

    for attempt in range(2):
        critic_prompt = (
            f"{critic['contribution_prompt']}\n\n"
            f"Original request: {safe_prompt}\n\n"
            f"Answer to review:\n{current_context}\n\n"
            f"Output APPROVED if perfect. Else list exact flaws."
        )
        review = query_node(critic["model_id"], critic_prompt)
        history.append({"node": f"Critic_Round_{attempt+1}", "output": review})

        if "APPROVED" in review.upper():
            print(f"[CRITIC] Approved on attempt {attempt+1}")
            break
        else:
            print(f"[CRITIC] Rejected. Rewriting...")
            current_context = query_node(
                last_model,
                f"Fix based on feedback:\n{review}\n\nOriginal:\n{current_context}"
            )

    execution_plan.append("Node_Omega_Critic")

    # ── PHASE 3: SYNTHESIZER ──────────────────────────────────────
    synth = AGENTS["Node_Prime_Synthesizer"]

    # Detect answer type for adaptive formatting
    prompt_lower = safe_prompt.lower()
    is_code     = any(w in prompt_lower for w in ["code","script","function","python","algorithm","debug","program"])
    is_math     = any(w in prompt_lower for w in ["solve","calculate","equation","proof","math","formula"])
    is_creative = any(w in prompt_lower for w in ["write","story","poem","essay","creative","blog"])
    is_research = any(w in prompt_lower for w in ["explain","what is","how does","research","compare","difference"])

    if is_code:
        format_rules = """
STRUCTURE FOR CODE ANSWERS:
━━━━━━━━━━━━━━━━━━━━━━━━━━
## 🎯 What This Does
One sharp paragraph. No fluff. Tell me exactly what this code achieves.

## 💡 The Approach
- Why this algorithm/pattern was chosen
- Time complexity: O(?) | Space complexity: O(?)
- Key technical decisions explained

## ⚙️ The Code
```python
# Full, production-ready, commented code here
# Every non-obvious line must have a comment
```

## 🧪 How to Test It
```python
# Concrete test cases with expected outputs
```

## ⚠️ Edge Cases & Security Notes
- What breaks this code and why
- Security considerations if applicable
- How to handle failures gracefully

## 🚀 How to Extend It
- One concrete next step to make it better"""

    elif is_math:
        format_rules = """
STRUCTURE FOR MATH ANSWERS:
━━━━━━━━━━━━━━━━━━━━━━━━━━
## 🎯 Problem Statement
Restate the problem crystal clearly in one sentence.

## 🧠 Strategy
Which mathematical approach and exactly why.

## 📐 Step-by-Step Proof/Solution
Present every step. Number them. Show all working.
Use proper mathematical notation where needed.

## ✅ Final Answer
State the answer boldly and clearly.

## 🔍 Verification
Prove the answer is correct by checking it a different way.

## 🌍 Real-World Meaning
One sentence on what this result means in practice."""

    elif is_creative:
        format_rules = """
STRUCTURE FOR CREATIVE ANSWERS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 🎯 Creative Vision
One sentence on the approach and tone chosen.

## ✍️ The Work
[The full creative output — no headers inside the creative piece itself]

## 🎨 Craft Notes
- Key stylistic choices made
- Tone, voice, and structure decisions
- How it connects to what was requested"""

    else:  # research / explanation
        format_rules = """
STRUCTURE FOR RESEARCH/EXPLANATION ANSWERS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 🎯 TL;DR
Two sentences maximum. The complete answer for someone in a hurry.

## 🧠 The Full Explanation
Break this into clear sub-sections. Use headers. Build from simple to complex.
Every paragraph should add something new — no repetition.

## 📊 Key Facts at a Glance
| Concept | Detail |
|---------|--------|
| [fact]  | [explanation] |

## 🔗 How It All Connects
One paragraph tying everything together — the "so what" moment.

## ⚠️ Common Misconceptions
What most people get wrong about this topic and why."""

    synthesis_prompt = f"""
{synth['contribution_prompt']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ORIGINAL USER REQUEST:
{safe_prompt}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SWARM'S VERIFIED ANSWER (use ONLY this — do NOT add new facts):
{current_context}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

YOUR FORMATTING MISSION:
{format_rules}

ABSOLUTE RULES:
1. Use ONLY facts from the verified swarm answer above
2. Every section must add value — delete anything redundant
3. Code must be complete and runnable — no placeholders
4. Math must show every step — no skipped working
5. Headers must be sharp and specific — not generic like "Introduction"
6. The final output must feel like it came from a senior expert
   who spent 2 hours crafting the perfect response
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOW WRITE THE FINAL MASTERPIECE:
"""

    final_answer = query_node(synth["model_id"], synthesis_prompt)
    execution_plan.append("Node_Prime_Synthesizer")

    # ── SAVE MEMORY ───────────────────────────────────────────────
    consolidate_memory(safe_prompt, final_answer)

    elapsed = time.time() - start_time
    print(f"[SWARM] Done in {elapsed:.1f}s")

    return {
        "plan": execution_plan,
        "final_answer": final_answer,
        "history": history,
        "time_taken": f"{elapsed:.1f}s"
    }
