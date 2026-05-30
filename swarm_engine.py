"""
Sovereign Swarm Engine v8.0 — Kimi Killer Edition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fixes applied over v7.2:
  [CRITICAL] Unknown entity pre-flight search (stops hallucination)
  [CRITICAL] Smart intent-based routing (research goes to Sigma first)
  [CRITICAL] HTML escape removed (broke prompts with & ' " chars)
  [HIGH]     Sigma forced to search unknown proper nouns always
  [HIGH]     Omega Critic checks for hallucination explicitly
  [HIGH]     Synthesis prompt token budget fixed (was getting cut off)
  [MEDIUM]   Research format auto-detected for comparison questions
  [MEDIUM]   Groq rate-limit retry with backoff
  [MEDIUM]   Memory keyword index improved
  [LOW]      Version banner updated
"""

import numpy as np
import requests
import re
import json
import pathlib
import time
import os
import hashlib
from typing import Optional, List, Tuple
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from duckduckgo_search import DDGS
from groq import Groq

print("[*] Waking the Hive Queen (v8.0 — Kimi Killer)...")

# ── Groq client ───────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise EnvironmentError(
        "GROQ_API_KEY not set! Add it in Streamlit Cloud → Settings → Secrets"
    )
groq_client = Groq(api_key=GROQ_API_KEY)

# ── Config ────────────────────────────────────────────────────────
MAX_PROMPT_LENGTH  = int(os.environ.get("MAX_PROMPT_LENGTH",  "3000"))
MAX_OUTPUT_TOKENS  = int(os.environ.get("MAX_OUTPUT_TOKENS",  "2048"))
REQUEST_TIMEOUT    = int(os.environ.get("REQUEST_TIMEOUT",     "300"))
MAX_SEARCH_RESULTS = int(os.environ.get("MAX_SEARCH_RESULTS",    "3"))

# ── Memory ────────────────────────────────────────────────────────
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
# INPUT SANITIZATION
# FIX: Removed unsafe escaping — it broke prompts with apostrophes
#      apostrophes, quotes, and ampersands
# ─────────────────────────────────────────────────────────────────

INJECTION_PATTERNS = [
    r"<SEARCH>.*?</SEARCH>",
    r"ignore\s+(all\s+)?previous\s+instructions?",
    r"you\s+are\s+now\s+a",
    r"disregard\s+(all\s+)?",
    r"override\s+system",
    r"new\s+system\s+prompt",
    r"jailbreak",
    r"DAN\s+mode",
]

def sanitize_input(text: str) -> str:
    if not text or not text.strip():
        raise ValueError("Empty prompt not allowed.")
    text = text.strip()[:MAX_PROMPT_LENGTH]
    for pattern in INJECTION_PATTERNS:
        text = re.sub(pattern, "[BLOCKED]", text,
                      flags=re.IGNORECASE | re.DOTALL)
    return text

def sanitize_search_results(results: str) -> str:
    results = re.sub(r"<SEARCH>.*?</SEARCH>", "", results, flags=re.DOTALL)
    return results[:2000]

# ─────────────────────────────────────────────────────────────────
# UNKNOWN ENTITY DETECTION
# FIX [CRITICAL]: Detects unknown proper nouns → forces search
# This is the primary anti-hallucination mechanism
# ─────────────────────────────────────────────────────────────────

KNOWN_ENTITIES = {
    # Companies
    "Google","Apple","Microsoft","NVIDIA","AMD","Intel","Meta","Amazon",
    "OpenAI","Anthropic","Groq","IBM","Samsung","Qualcomm","TSMC","ARM",
    "Tesla","Netflix","Stripe","Uber","Airbnb","Spotify","Twitter","X",
    "Zoho","Adobe","Oracle","Salesforce","Cisco","Huawei","Sony",
    # Products / models
    "Python","Linux","Windows","MacOS","Android","iOS","ChatGPT","Claude",
    "Gemini","Llama","Mistral","GPT","BERT","Transformer",
    "TPU","GPU","CPU","ASIC","NPU","M1","M2","M3","M4",
    "PyTorch","TensorFlow","JAX","CUDA","Docker","Kubernetes",
    "React","Vue","Angular","FastAPI","Flask","Django","Streamlit",
    # Common words that get capitalized mid-sentence
    "I","The","What","How","Why","Which","Can","Do","Is","Are",
    "Did","Does","Will","Would","Should","Could","May","Might",
    "My","Your","Their","Our","This","That","These","Those",
    "AI","ML","API","SDK","LLM","NLP","CV","IoT","SaaS","PaaS",
}

def extract_unknown_entities(prompt: str) -> List[str]:
    """Find proper nouns NOT in our known-entities list."""
    candidates = re.findall(
        r'\b[A-Z][a-zA-Z0-9]*(?:[A-Z][a-zA-Z0-9]+)+\b'   # CamelCase
        r'|\b[A-Z][a-zA-Z0-9]{3,}\b',                      # Single cap word >3 chars
        prompt
    )
    unknowns = [
        c for c in candidates
        if c not in KNOWN_ENTITIES and len(c) > 3
    ]
    return list(dict.fromkeys(unknowns))  # deduplicate, preserve order

# ─────────────────────────────────────────────────────────────────
# AGENTS — Domain-Aware + Anti-Hallucination prompts
# ─────────────────────────────────────────────────────────────────

AGENTS = {
    "Node_Alpha_Coder": {
        "description": "Expert software engineer. Writes Python, C++, debugs code, designs architecture.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Alpha_Coder — a senior software engineer with 15 years
at Google, Netflix, and Stripe.

ANTI-HALLUCINATION RULES (highest priority):
- If you are not 100% certain a library/API exists → say so and use a known alternative
- NEVER invent function signatures — only use documented APIs
- If unsure about a version or feature → state your uncertainty explicitly

CODING STANDARDS:
- NEVER hardcode secrets → use os.environ.get()
- NEVER raw SQL → use parameterized queries
- ALWAYS validate and sanitize inputs
- ALWAYS add rate limiting on auth endpoints
- ALWAYS use try/except with meaningful error messages (no stack traces to users)
- ALWAYS add type hints and docstrings
- Code must be COMPLETE and RUNNABLE — no "# TODO" or "..." placeholders
- Add time complexity O(?) and space complexity O(?) after every algorithm

ARCHITECTURE STANDARDS:
- Show full folder structure
- Include dependency list
- Address scalability, failure modes, monitoring
- Cover OWASP Top 10 for security questions
- Reference real-world patterns (Netflix resilience, Stripe idempotency, Uber microservices)"""
    },

    "Node_Beta_Math": {
        "description": "World-class mathematician. Solves calculus, algebra, statistics, ML math.",
        "model_id": "qwen/qwen3-32b",
        "contribution_prompt": """You are Node_Beta_Math — a world-class mathematician and
quantitative analyst.

ANTI-HALLUCINATION RULES (highest priority):
- Show EVERY step — never skip derivations
- State ALL assumptions before solving
- Verify every answer using a SECOND independent method
- If a result seems counterintuitive → explain the intuition carefully
- NEVER approximate without stating the approximation and its error bound

MATH STANDARDS:
- Always derive time AND space complexity for algorithms
- For statistics: state the distribution, assumptions, and confidence intervals
- For proofs: use proper mathematical notation
- For optimization: show objective function, constraints, and solution method
- For financial math: include risk metrics and regulatory context
- After solution: give a one-sentence real-world interpretation

When problem involves code: translate the math into a working Python implementation."""
    },

    "Node_Sigma_Researcher": {
        "description": "Research expert. Finds real-time facts, compares technologies, cites sources.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Sigma_Researcher — the world's most rigorous research analyst.

ANTI-HALLUCINATION PROTOCOL (MANDATORY — follow in order):
STEP 1: Read the question carefully.
STEP 2: Identify every proper noun, product name, company name, or technology you
        are not 100% certain about.
STEP 3: For EACH uncertain entity → output: <SEARCH>entity name</SEARCH>
        DO NOT SKIP THIS STEP. It is better to search unnecessarily than to hallucinate.
STEP 4: After searching, report ONLY what the search results confirm.
STEP 5: If search returns no results → say "Could not verify [entity]. It may be
        very new, private, or not publicly announced yet."

RESEARCH STANDARDS:
- Cite SPECIFIC sources — name the company, paper, or documentation
- Use REAL numbers: "TPU v4: 275 TFLOPS, $2.40/hr on GCP" not "offers high performance"
- Compare at least 2-3 options with concrete criteria before recommending
- Reference industry standards: OWASP, NIST, PCI-DSS, GDPR where relevant
- Reference real company patterns: Netflix, Stripe, Uber, Google, Zoho where relevant
- Always note the year when recency matters
- Distinguish "widely used" from "actually best" — they are often different"""
    },

    "Node_Gamma_Writer": {
        "description": "Master technical writer. Makes complex ideas crystal clear.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Gamma_Writer — the world's finest technical communicator.

ANTI-HALLUCINATION RULES (highest priority):
- Only use facts from the content you are given to refine
- NEVER add new facts, claims, or data that were not in the input
- If the input is missing something important → note the gap, do not invent a fill

WRITING STANDARDS:
- Every paragraph must earn its place — cut anything redundant
- Build simple → complex, never the reverse
- Use concrete analogies for abstract concepts
- For documentation: purpose → usage → parameters → return → errors → examples
- Start with "why" before "how"
- BANNED phrases: "It is important to note", "In conclusion", "As mentioned above",
  "In summary", "It goes without saying", "Needless to say"
- Code comments must explain WHY, not WHAT
- Adapt to audience: developers (terse, precise, examples-first),
  executives (outcomes, risks, no jargon)"""
    },

    "Node_Omega_Critic": {
        "description": "Ruthless quality enforcer. Catches hallucinations, bugs, and logic errors.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Omega_Critic — the most uncompromising reviewer alive.
You are a combined security auditor + senior engineer + fact-checker + hallucination detector.

YOUR MANDATORY 9-POINT AUDIT:
1. HALLUCINATION CHECK — Did the answer invent any product, company, API, or fact
   that cannot be independently verified? Flag EVERY unverifiable claim.
2. FACTUAL ACCURACY — Are all stated facts, numbers, and names correct?
3. SECURITY HOLES — Hardcoded secrets? SQL injection? Missing auth? No rate limiting?
4. CODE CORRECTNESS — Does every code block actually run? Any bugs or logic errors?
5. COMPLETENESS — Does it fully answer the original question? What is missing?
6. DEPTH — Is this surface-level bullet points or genuinely expert insight?
7. CONSISTENCY — Do any sections contradict each other?
8. EDGE CASES — What happens with empty input, huge input, concurrent requests?
9. PRODUCTION READINESS — Can this actually be deployed without changes?

OUTPUT FORMAT:
- Pass ALL 9 → output exactly: APPROVED
- Fail any → list each failure as:
  [POINT N - SEVERITY] Specific problem found → Exact fix required
  SEVERITY: CRITICAL | HIGH | MEDIUM | LOW

CRITICAL RULE: A hallucinated answer that sounds confident is MORE DANGEROUS
than an honest "I don't know." Flag all hallucinations as CRITICAL."""
    },

    "Node_Prime_Synthesizer": {
        "description": "Master editor. Produces Kimi-level structured, beautiful final responses.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Prime_Synthesizer — the world's most elite technical editor.
Transform the verified swarm output into a world-class structured response.

ABSOLUTE RULES:
1. Use ONLY facts from the swarm's verified answer — NEVER add new facts
2. Every section must add value — delete redundant content ruthlessly
3. Code must be complete and runnable — no placeholders
4. Use REAL numbers and SPECIFIC details — never vague statements
5. The output must feel like a senior expert spent 2 hours crafting it"""
    }
}

# ─────────────────────────────────────────────────────────────────
# SMART INTENT-BASED ROUTER
# FIX [CRITICAL]: Research questions now route to Sigma first
# ─────────────────────────────────────────────────────────────────

def get_routing_plan(prompt: str) -> List[str]:
    """
    Determine agent execution order based on question intent.
    Research/comparison questions → Sigma leads (prevents hallucination)
    Code questions → Alpha leads
    Math questions → Beta leads
    """
    p = prompt.lower()

    research_signals = [
        "what is","what are","do you know","tell me about","who made",
        "compare","which one","vs","versus","difference between",
        "news","latest","recent","announced","released","launched",
        "startup","company","product","chip","device","tool","platform",
        "better","best","recommend","should i use","cost","price","worth"
    ]
    code_signals = [
        "write code","write a","implement","build a","create a",
        "function","script","debug","fix this code","algorithm",
        "class","method","api endpoint","backend","frontend"
    ]
    math_signals = [
        "calculate","solve","equation","proof","formula",
        "derivative","integral","probability","statistics",
        "complexity","big o","optimize"
    ]

    if any(s in p for s in research_signals):
        return [
            "Node_Sigma_Researcher",
            "Node_Alpha_Coder",
            "Node_Gamma_Writer",
        ]
    elif any(s in p for s in math_signals):
        return [
            "Node_Beta_Math",
            "Node_Alpha_Coder",
            "Node_Gamma_Writer",
        ]
    elif any(s in p for s in code_signals):
        return [
            "Node_Alpha_Coder",
            "Node_Sigma_Researcher",
            "Node_Gamma_Writer",
        ]
    else:
        # Default: research first to prevent hallucination
        return [
            "Node_Sigma_Researcher",
            "Node_Alpha_Coder",
            "Node_Gamma_Writer",
        ]

# ─────────────────────────────────────────────────────────────────
# GROQ API CALL — With rate-limit retry backoff
# FIX [MEDIUM]: Added exponential backoff for rate limit errors
# ─────────────────────────────────────────────────────────────────

def query_node(model_id: str, prompt: str, label: str = "") -> str:
    if len(prompt) > MAX_PROMPT_LENGTH:
        prompt = prompt[:MAX_PROMPT_LENGTH] + "\n[Context trimmed]"

    for attempt in range(3):
        try:
            response = groq_client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_OUTPUT_TOKENS,
                temperature=0.7,
                timeout=REQUEST_TIMEOUT
            )
            result = response.choices[0].message.content
            if result and result.strip():
                return result
        except Exception as e:
            err = str(e)
            if "rate_limit" in err.lower() or "429" in err:
                wait = (attempt + 1) * 10
                print(f"  [RATE LIMIT] {label} waiting {wait}s...")
                time.sleep(wait)
            elif attempt == 2:
                return f"[ERROR] {label or model_id}: {err[:120]}"
            else:
                time.sleep(3)
    return "[ERROR] No response after 3 attempts."

# ─────────────────────────────────────────────────────────────────
# WEB SEARCH
# ─────────────────────────────────────────────────────────────────

def tool_web_search(query: str) -> str:
    safe_query = re.sub(r"[<>\"'{}|\\^`\[\]]", "", query)[:200]
    print(f"  [SEARCH] '{safe_query}'")
    try:
        results = DDGS().text(safe_query, max_results=MAX_SEARCH_RESULTS)
        if not results:
            return f"No results found for: {safe_query}"
        raw = "\n\n".join([
            f"Source: {r.get('title','?')}\n{r.get('body','')}"
            for r in results
        ])
        return sanitize_search_results(raw)
    except Exception as e:
        return f"Search failed: {str(e)[:100]}"

# ─────────────────────────────────────────────────────────────────
# MEMORY
# ─────────────────────────────────────────────────────────────────

def recall_past_memory(query_text: str, n: int = 2) -> Optional[str]:
    try:
        memories = _load_memory()
        if not memories:
            return None
        query_words = set(query_text.lower().split())
        scored = sorted(
            [(len(query_words & set(m.lower().split())), m)
             for m in memories
             if len(query_words & set(m.lower().split())) > 1],
            reverse=True
        )
        top = [m for _, m in scored[:n]]
        if top:
            print(f"  [MEMORY] Recalled {len(top)} past memories")
            return "\n".join([f"[Memory {i+1}]: {m}" for i, m in enumerate(top)])
        return None
    except Exception:
        return None

def consolidate_memory(prompt: str, final_answer: str):
    try:
        memories = _load_memory()
        uid = hashlib.md5(f"{time.time()}{prompt}".encode()).hexdigest()[:8]
        memories.append(
            f"[{uid}] Q: {prompt[:150]} | A: {final_answer[:200]}"
        )
        _save_memory(memories[-50:])
        print(f"  [MEMORY] Saved #{uid}. Total: {len(memories)}")
    except Exception as e:
        print(f"  [MEMORY] Failed: {e}")

# ─────────────────────────────────────────────────────────────────
# KIMI-LEVEL SYNTHESIZER FORMAT SELECTOR
# ─────────────────────────────────────────────────────────────────

def get_format_rules(prompt: str) -> str:
    p = prompt.lower()
    is_code     = any(w in p for w in ["code","script","function","python","implement","build","debug"])
    is_math     = any(w in p for w in ["solve","calculate","equation","proof","math","formula","derive"])
    is_creative = any(w in p for w in ["write","story","poem","essay","blog","creative"])
    is_compare  = any(w in p for w in ["compare","vs","versus","difference","which","better","best"])

    if is_code:
        return """
## 🎯 What This Does
One sharp paragraph. What problem this code solves.

## 💡 The Approach
- Algorithm / design pattern chosen and why
- Time complexity: O(?) | Space: O(?)
- Key technical decisions

## ⚙️ The Code
```python
# Complete, production-ready, commented code
```

## 🧪 Test Cases
```python
# Concrete inputs → expected outputs
```

## ⚠️ Edge Cases & Security
- What breaks this and how to handle it
- Security considerations

## 🚀 Next Improvement
One concrete upgrade to make it production-grade"""

    elif is_math:
        return """
## 🎯 Problem Statement
One sentence restatement of exactly what is being solved.

## 🧠 Strategy
Mathematical approach chosen and why.

## 📐 Step-by-Step Solution
Every step numbered. No skipped working.

## ✅ Final Answer
Bold and clear.

## 🔍 Verification
Check the answer a different way.

## 🌍 Real-World Meaning
One sentence on practical significance."""

    elif is_compare:
        return """
## 🎯 TL;DR — The Verdict
Two sentences: what was compared and the winner for each use case.

## 📊 Head-to-Head Comparison
| Feature | Option A | Option B | Option C |
|---------|----------|----------|----------|
| Performance | [real number] | [real number] | [real number] |
| Cost | [real price] | [real price] | [real price] |
| Best for | [use case] | [use case] | [use case] |

## 🧠 Deep Dive
Sub-section per option. Specific strengths, specific weaknesses. Real numbers.

## ✅ Recommendation
For [use case A] → choose [X] because [specific reason]
For [use case B] → choose [Y] because [specific reason]

## ⚠️ What Most People Get Wrong
The most common mistake when choosing between these options."""

    elif is_creative:
        return """
## 🎯 Creative Vision
One sentence on approach and tone.

## ✍️ The Work
[Full creative output — no section headers inside]

## 🎨 Craft Notes
Stylistic choices and how they serve the piece."""

    else:
        return """
## 🎯 TL;DR
Two sentences. The complete answer for someone in a hurry.

## 🧠 Full Explanation
Clear sub-sections. Simple → complex. No repetition.

## 📊 Key Facts
| Concept | Detail |
|---------|--------|
| [fact] | [specific detail with real numbers] |

## 🔗 The Big Picture
One paragraph: the "so what" — why this matters.

## ⚠️ Common Misconceptions
What most people get wrong and the correct understanding."""

# ─────────────────────────────────────────────────────────────────
# MAIN SWARM EXECUTION LOOP v8.0
# ─────────────────────────────────────────────────────────────────

def run_swarm(user_prompt: str) -> dict:

    # ── Sanitize ──────────────────────────────────────────────────
    try:
        safe_prompt = sanitize_input(user_prompt)
    except ValueError as e:
        return {"plan": [], "final_answer": f"⚠️ {e}", "history": []}

    print(f"\n{'='*55}")
    print(f"[SWARM v8.0] {safe_prompt[:80]}...")
    print(f"{'='*55}")

    start = time.time()
    history = []

    # ── PRE-FLIGHT: Search unknown entities BEFORE routing ────────
    # This is the primary anti-hallucination mechanism
    unknown_entities = extract_unknown_entities(safe_prompt)
    preflight_context = ""

    if unknown_entities:
        print(f"[PREFLIGHT] Unknown entities: {unknown_entities}")
        for entity in unknown_entities[:3]:
            result = tool_web_search(entity)
            if "No results" not in result and "failed" not in result:
                preflight_context += f"\n[Verified info on {entity}]:\n{result}\n"
                history.append({"node": f"PREFLIGHT:Search({entity})", "output": result})
            else:
                preflight_context += f"\n[{entity}]: Could not verify — not in public sources.\n"
                print(f"  [PREFLIGHT] Could not verify: {entity}")

    # ── Memory ────────────────────────────────────────────────────
    past = recall_past_memory(safe_prompt)

    # ── Build initial context ─────────────────────────────────────
    current_context = safe_prompt
    if preflight_context:
        current_context = (
            f"VERIFIED RESEARCH CONTEXT (from live web search):\n"
            f"{preflight_context}\n\n"
            f"USER QUESTION:\n{safe_prompt}"
        )
    if past:
        current_context = f"PAST MEMORY:\n{past}\n\n{current_context}"

    # ── Smart routing ─────────────────────────────────────────────
    execution_plan = get_routing_plan(safe_prompt)
    print(f"[ROUTER] Plan: {execution_plan}")

    # ── Phase 1: Agent execution ──────────────────────────────────
    for step, node_name in enumerate(execution_plan):
        agent = AGENTS[node_name]
        print(f"[{node_name}] Working...")

        if step == 0:
            agent_prompt = (
                f"{agent['contribution_prompt']}\n\n"
                f"TASK:\n{current_context}"
            )
        else:
            agent_prompt = (
                f"{agent['contribution_prompt']}\n\n"
                f"PREVIOUS WORK TO BUILD ON:\n{current_context}\n\n"
                f"ORIGINAL QUESTION:\n{safe_prompt}\n\n"
                f"Your job: add your unique perspective. Do NOT repeat what was already said well."
            )

        answer = query_node(agent["model_id"], agent_prompt, node_name)

        # Only Sigma can trigger web search
        if node_name == "Node_Sigma_Researcher":
            all_searches = re.findall(r"<SEARCH>(.*?)</SEARCH>", answer)
            for sq in all_searches[:3]:
                live = tool_web_search(sq)
                history.append({"node": "TOOL:WebSearch", "output": sq})
                # Re-run Sigma with search results injected
                answer = query_node(
                    agent["model_id"],
                    f"{agent['contribution_prompt']}\n\n"
                    f"Web search results for '{sq}':\n{live}\n\n"
                    f"ORIGINAL QUESTION:\n{safe_prompt}\n\n"
                    f"Now give your complete, verified answer using this data.\n"
                    f"If the entity was not found in results → say so clearly.",
                    f"{node_name}:AfterSearch"
                )

        history.append({"node": node_name, "output": answer})
        current_context = answer
        print(f"  [{node_name}] Done ({len(answer)} chars)")

    # ── Phase 2: Omega Critic ─────────────────────────────────────
    critic = AGENTS["Node_Omega_Critic"]
    last_model = AGENTS[execution_plan[-1]]["model_id"]

    for attempt in range(2):
        print(f"[Omega_Critic] Review {attempt+1}/2...")
        review = query_node(
            critic["model_id"],
            f"{critic['contribution_prompt']}\n\n"
            f"ORIGINAL QUESTION:\n{safe_prompt}\n\n"
            f"ANSWER TO AUDIT:\n{current_context}",
            "Omega_Critic"
        )
        history.append({"node": f"Critic_Round_{attempt+1}", "output": review})

        if "APPROVED" in review.upper():
            print(f"  [Critic] APPROVED on attempt {attempt+1}")
            break
        else:
            print(f"  [Critic] Rejected — rewriting...")
            current_context = query_node(
                last_model,
                f"The Omega Critic rejected your answer.\n\n"
                f"CRITIC FEEDBACK:\n{review}\n\n"
                f"YOUR PREVIOUS ANSWER:\n{current_context}\n\n"
                f"ORIGINAL QUESTION:\n{safe_prompt}\n\n"
                f"Fix every issue the critic raised. Be specific. No hallucinations.",
                "Rewrite"
            )

    execution_plan.append("Node_Omega_Critic")

    # ── Phase 3: Kimi-Level Synthesizer ───────────────────────────
    print("[Synthesizer] Formatting final answer...")
    synth = AGENTS["Node_Prime_Synthesizer"]
    format_rules = get_format_rules(safe_prompt)

    final_answer = query_node(
        synth["model_id"],
        f"{synth['contribution_prompt']}\n\n"
        f"ORIGINAL USER QUESTION:\n{safe_prompt}\n\n"
        f"SWARM'S VERIFIED ANSWER (use ONLY this — never add new facts):\n"
        f"{current_context}\n\n"
        f"FORMAT STRUCTURE TO USE:\n{format_rules}\n\n"
        f"RULES:\n"
        f"- Use ONLY facts from the verified answer above\n"
        f"- Real numbers and specifics only — no vague claims\n"
        f"- Every section must add value\n"
        f"- If something is unverified → say it is unverified\n"
        f"- Write as if a senior expert spent 2 hours on this\n\n"
        f"WRITE THE FINAL ANSWER NOW:",
        "Synthesizer"
    )

    execution_plan.append("Node_Prime_Synthesizer")

    # ── Save memory ───────────────────────────────────────────────
    consolidate_memory(safe_prompt, final_answer)

    elapsed = time.time() - start
    print(f"[SWARM] Done in {elapsed:.1f}s\n")

    return {
        "plan": execution_plan,
        "final_answer": final_answer,
        "history": history,
        "time_taken": f"{elapsed:.1f}s"
    }
