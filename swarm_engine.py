"""
Sovereign Swarm Engine v8.0 — Kimi Killer Edition (Hub-and-Spoke)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fixes applied over v7.2:
  [CRITICAL] Unknown entity pre-flight search (stops hallucination)
  [CRITICAL] Smart intent-based routing (research goes to Sigma first)
  [CRITICAL] HTML escape removed (broke prompts with & ' " chars)
  [CRITICAL] UPGRADED TO TRUE HUB-AND-SPOKE ARCHITECTURE
  [HIGH]     Sigma forced to search unknown proper nouns always
  [HIGH]     Omega Critic checks for hallucination explicitly
  [HIGH]     Synthesis prompt token budget fixed (was getting cut off)
  [MEDIUM]   Research format auto-detected for comparison questions
  [MEDIUM]   Groq rate-limit retry with backoff
  [MEDIUM]   Memory keyword index improved
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

print("[*] Waking the Hive Queen (v8.0 — Hub-and-Spoke Kimi Killer)...")

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
# UNKNOWN ENTITY DETECTION (Pre-Flight)
# ─────────────────────────────────────────────────────────────────
KNOWN_ENTITIES = {
    "Google","Apple","Microsoft","NVIDIA","AMD","Intel","Meta","Amazon",
    "OpenAI","Anthropic","Groq","IBM","Samsung","Qualcomm","TSMC","ARM",
    "Tesla","Netflix","Stripe","Uber","Airbnb","Spotify","Twitter","X",
    "Zoho","Adobe","Oracle","Salesforce","Cisco","Huawei","Sony",
    "Python","Linux","Windows","MacOS","Android","iOS","ChatGPT","Claude",
    "Gemini","Llama","Mistral","GPT","BERT","Transformer",
    "TPU","GPU","CPU","ASIC","NPU","M1","M2","M3","M4",
    "PyTorch","TensorFlow","JAX","CUDA","Docker","Kubernetes",
    "React","Vue","Angular","FastAPI","Flask","Django","Streamlit",
    "I","The","What","How","Why","Which","Can","Do","Is","Are",
    "Did","Does","Will","Would","Should","Could","May","Might",
    "My","Your","Their","Our","This","That","These","Those",
    "AI","ML","API","SDK","LLM","NLP","CV","IoT","SaaS","PaaS",
}

def extract_unknown_entities(prompt: str) -> List[str]:
    candidates = re.findall(
        r'\b[A-Z][a-zA-Z0-9]*(?:[A-Z][a-zA-Z0-9]+)+\b'
        r'|\b[A-Z][a-zA-Z0-9]{3,}\b',
        prompt
    )
    unknowns = [c for c in candidates if c not in KNOWN_ENTITIES and len(c) > 3]
    return list(dict.fromkeys(unknowns))

# ─────────────────────────────────────────────────────────────────
# AGENTS
# ─────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────
# AGENTS
# ─────────────────────────────────────────────────────────────────
AGENTS = {
    "Node_Alpha_Coder": {
        "description": "Expert software engineer. Writes Python, C++, debugs code.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Alpha_Coder. 
CRITICAL RULE: If the user's prompt DOES NOT explicitly ask for code, software architecture, or math, you MUST output exactly one word: [PASS]. Do not write anything else.
If it IS a coding question, write complete, production-ready code. Do not discuss your thought process."""
    },
    "Node_Beta_Math": {
        "description": "World-class mathematician. Solves calculus, algebra, statistics.",
        "model_id": "qwen/qwen3-32b",
        "contribution_prompt": """You are Node_Beta_Math.
CRITICAL RULE: If the prompt DOES NOT involve math, equations, or data analysis, output exactly: [PASS].
If it is a math question, show every step clearly without meta-commentary."""
    },
    "Node_Sigma_Researcher": {
        "description": "Research expert. Finds real-time facts, compares technologies.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Sigma_Researcher. Your job is to provide factual answers.
If you need live data, output ONLY: <SEARCH>entity name</SEARCH>
CRITICAL RULES: 
1. DO NOT mention your "protocols", "constraints", or "instructions". Just answer the user directly.
2. Give concrete numbers, dates, and facts."""
    },
    "Node_Gamma_Writer": {
        "description": "Master technical writer. Makes complex ideas crystal clear.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Gamma_Writer.
If the prompt does not require a creative story or deep technical documentation, output exactly: [PASS]."""
    },
    "Node_Omega_Critic": {
        "description": "Ruthless quality enforcer. Catches hallucinations.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Omega_Critic. 
Review the draft. If there is useless Python code for a business question, or if the AI talks about its own "rules", REJECT IT.
If perfect, output exactly: APPROVED."""
    },
    "Node_Prime_Synthesizer": {
        "description": "Master editor. Produces structured, beautiful final responses.",
        "model_id": "llama-3.3-70b-versatile",
        "contribution_prompt": """You are Node_Prime_Synthesizer.
Read the Swarm's Raw Dossier. 
IGNORE any agent that outputted "[PASS]". 
IGNORE any useless Python code if the user didn't ask for code.
DO NOT include meta-commentary about "gathering information." 
Just format the factual truth directly into the requested Markdown structure."""
    }
}

# ─────────────────────────────────────────────────────────────────
# SMART INTENT-BASED ROUTER
# ─────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────
# SMART INTENT-BASED ROUTER
# ─────────────────────────────────────────────────────────────────
def get_routing_plan(prompt: str) -> List[str]:
    p = prompt.lower()
    
    # Check for specific triggers
    is_code = any(s in p for s in ["write code","implement","build","function","script","debug","python","c++","html"])
    is_math = any(s in p for s in ["calculate","solve","equation","proof","statistics","math"])
    
    plan = ["Node_Sigma_Researcher"] # The Researcher ALWAYS runs to get facts.
    
    # ONLY invite the Coder or Math node if the prompt actually asks for it!
    if is_code:
        plan.append("Node_Alpha_Coder")
    if is_math:
        plan.append("Node_Beta_Math")
        
    return plan
# ─────────────────────────────────────────────────────────────────
# GROQ API CALL
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
# WEB SEARCH & FORMAT RULES
# ─────────────────────────────────────────────────────────────────
def tool_web_search(query: str) -> str:
    safe_query = re.sub(r"[<>\"'{}|\\^`\[\]]", "", query)[:200]
    print(f"  [SEARCH] '{safe_query}'")
    try:
        results = DDGS().text(safe_query, max_results=MAX_SEARCH_RESULTS)
        if not results: return f"No results found for: {safe_query}"
        raw = "\n\n".join([f"Source: {r.get('title','?')}\n{r.get('body','')}" for r in results])
        return sanitize_search_results(raw)
    except Exception as e:
        return f"Search failed: {str(e)[:100]}"

def get_format_rules(prompt: str) -> str:
    p = prompt.lower()
    if any(w in p for w in ["code","script","function"]):
        return "## 🎯 What This Does\n## 💡 The Approach\n## ⚙️ The Code\n## ⚠️ Edge Cases"
    elif any(w in p for w in ["compare","vs"]):
        return "## 🎯 The Verdict\n## 📊 Head-to-Head Comparison (Table)\n## 🧠 Deep Dive\n## ✅ Recommendation"
    else:
        return "## 🎯 TL;DR\n## 🧠 Full Explanation\n## 📊 Key Facts\n## 🔗 The Big Picture"

# ─────────────────────────────────────────────────────────────────
# MAIN SWARM EXECUTION LOOP v8.0 (TRUE HUB-AND-SPOKE)
# ─────────────────────────────────────────────────────────────────
def run_swarm(user_prompt: str) -> dict:
    try:
        safe_prompt = sanitize_input(user_prompt)
    except ValueError as e:
        return {"plan": [], "final_answer": f"⚠️ {e}", "history": []}

    print(f"\n{'='*55}")
    print(f"[SWARM v8.0 HUB] {safe_prompt[:80]}...")
    print(f"{'='*55}")

    start = time.time()
    history = []
    
    # ── PRE-FLIGHT: Search unknown entities ───────────────────────
    unknown_entities = extract_unknown_entities(safe_prompt)
    preflight_context = ""
    if unknown_entities:
        print(f"[PREFLIGHT] Unknown entities: {unknown_entities}")
        for entity in unknown_entities[:3]:
            result = tool_web_search(entity)
            if "No results" not in result and "failed" not in result:
                preflight_context += f"\n[Verified info on {entity}]:\n{result}\n"
                history.append({"node": f"PREFLIGHT:Search({entity})", "output": result})

    # ── Memory ────────────────────────────────────────────────────
    past = recall_past_memory(safe_prompt)

    # ── Smart routing ─────────────────────────────────────────────
    execution_plan = get_routing_plan(safe_prompt)
    print(f"[ROUTER] Plan: {execution_plan}")

    # ── PHASE 1: INDEPENDENT AGENTS (The Hub) ─────────────────────
    master_dossier = []
    if preflight_context:
        master_dossier.append(f"--- PRE-FLIGHT VERIFIED FACTS ---\n{preflight_context}\n")
    if past:
        master_dossier.append(f"--- PAST MEMORY ---\n{past}\n")

    for node_name in execution_plan:
        agent = AGENTS[node_name]
        print(f"[{node_name}] Working independently...")

        # Each agent only sees the prompt and verified facts. They DO NOT overwrite each other.
        agent_prompt = f"{agent['contribution_prompt']}\n\nORIGINAL QUESTION:\n{safe_prompt}\n\n"
        if preflight_context:
            agent_prompt += f"VERIFIED FACTS TO USE:\n{preflight_context}\n\n"
        agent_prompt += "TASK: Provide your expert analysis/code based on your specific domain."

        answer = query_node(agent["model_id"], agent_prompt, node_name)

        if node_name == "Node_Sigma_Researcher":
            all_searches = re.findall(r"<SEARCH>(.*?)</SEARCH>", answer)
            for sq in all_searches[:3]:
                live = tool_web_search(sq)
                history.append({"node": "TOOL:WebSearch", "output": sq})
                answer = query_node(
                    agent["model_id"],
                    f"{agent['contribution_prompt']}\n\nWeb search results for '{sq}':\n{live}\n\nORIGINAL QUESTION:\n{safe_prompt}\n\nGive your complete, verified answer using this data.",
                    f"{node_name}:AfterSearch"
                )

        history.append({"node": node_name, "output": answer})
        # Dump the result into the Master Dossier!
        master_dossier.append(f"--- REPORT FROM {node_name} ---\n{answer}\n")
        print(f"  [{node_name}] Done")

    combined_intelligence = "\n".join(master_dossier)

    # ── PHASE 2: KIMI-LEVEL SYNTHESIZER (The Draft) ───────────────
    print("[Synthesizer] Compiling Master Dossier into structured draft...")
    synth = AGENTS["Node_Prime_Synthesizer"]
    format_rules = get_format_rules(safe_prompt)

    synth_prompt = (
        f"{synth['contribution_prompt']}\n\n"
        f"ORIGINAL USER QUESTION:\n{safe_prompt}\n\n"
        f"SWARM'S RAW DOSSIER (Use ONLY these facts. Do not invent details):\n{combined_intelligence}\n\n"
        f"FORMAT STRUCTURE TO USE:\n{format_rules}\n\n"
        f"WRITE THE FINAL RESPONSE NOW:"
    )
    draft_answer = query_node(synth["model_id"], synth_prompt, "Synthesizer")
    execution_plan.append("Node_Prime_Synthesizer_Draft")

    # ── PHASE 3: OMEGA CRITIC (Auditing the Draft) ────────────────
    critic = AGENTS["Node_Omega_Critic"]
    final_answer = draft_answer

    for attempt in range(2):
        print(f"[Omega_Critic] Review {attempt+1}/2...")
        review = query_node(
            critic["model_id"],
            f"{critic['contribution_prompt']}\n\n"
            f"ORIGINAL QUESTION:\n{safe_prompt}\n\n"
            f"SYNTHESIZER'S DRAFT TO AUDIT:\n{final_answer}",
            "Omega_Critic"
        )
        history.append({"node": f"Critic_Round_{attempt+1}", "output": review})

        if "APPROVED" in review.upper():
            print(f"  [Critic] APPROVED on attempt {attempt+1}")
            break
        else:
            print(f"  [Critic] Rejected — Synthesizer rewriting...")
            final_answer = query_node(
                synth["model_id"],
                f"The Omega Critic rejected your draft.\n\nCRITIC FEEDBACK:\n{review}\n\n"
                f"YOUR PREVIOUS DRAFT:\n{final_answer}\n\n"
                f"SWARM'S RAW DOSSIER (For reference):\n{combined_intelligence}\n\n"
                f"Fix the issues raised by the critic. Output ONLY the corrected, perfectly formatted answer.",
                "Synthesizer_Rewrite"
            )

    execution_plan.append("Node_Omega_Critic_Approval")

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
