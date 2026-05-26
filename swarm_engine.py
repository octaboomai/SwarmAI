"""
╔══════════════════════════════════════════════════════════════════╗
║          SOVEREIGN SWARM ENGINE v6.2 - GROQ EDITION        ║
║   All agents communicate, debate, and build on each other's work ║
║   8B parameters × 5 agents = Team-level intelligence             ║
║   v6.3: Fixed decommissioned models — qwen/qwen3-32b + llama-3.3-70b-versatile   ║
╚══════════════════════════════════════════════════════════════════╝
"""

import numpy as np
import requests
import re
import json
import pathlib
import json
import time
import os
from groq import Groq
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from duckduckgo_search import DDGS
from datetime import datetime
from typing import Optional, Tuple, List

print("[*] Waking the Hive Queen (Collaborative Swarm v6.2 — Groq Edition)...")

# ── Groq client — replaces local Ollama ──────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)

# ── Simple JSON Memory (no external dependencies) ──────────────────
MEMORY_FILE = pathlib.Path("swarm_memory.json")

def _load_memory() -> list:
    """Load memory from JSON file."""
    try:
        if MEMORY_FILE.exists():
            return json.loads(MEMORY_FILE.read_text())
    except Exception:
        pass
    return []

def _save_memory(memories: list):
    """Save memory to JSON file."""
    try:
        MEMORY_FILE.write_text(json.dumps(memories, indent=2))
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────
# 1. AGENT DEFINITIONS
#    Every agent contributes to EVERY problem.
#    Primary agent leads. Others assist from their angle.
# ─────────────────────────────────────────────────────────────────

AGENTS = {
    "Alpha_Coder": {
        "description": "Expert software engineer. Writes optimized, production-ready code.",
        "perspective": "As a senior software engineer, I see this problem as",
        "contribution_prompt": (
            "You are Alpha_Coder, an elite software engineer with 20 years experience.\n"
            "Your job: Contribute the CODING and ALGORITHMIC perspective.\n"
            "Even if this isn't a coding problem, find how programming concepts apply.\n"
            "Be specific. Write actual code snippets where relevant. Never be vague."
        ),
        "model_id": "llama-3.3-70b-versatile",
        "strengths": ["code", "algorithm", "debug", "script", "function", "programming", "software"]
    },
    "Beta_Math": {
        "description": "Mathematical genius. Handles proofs, optimization, complexity analysis.",
        "perspective": "From a mathematical and analytical standpoint",
        "contribution_prompt": (
            "You are Beta_Math, a world-class mathematician and analyst.\n"
            "Your job: Contribute the MATHEMATICAL and LOGICAL perspective.\n"
            "Even if this isn't a math problem, find numerical patterns, complexity, or logic.\n"
            "Show calculations. Prove correctness. Analyze trade-offs quantitatively."
        ),
        "model_id": "qwen/qwen3-32b",
        "strengths": ["math", "calculate", "equation", "proof", "complexity", "statistics", "numbers"]
    },
    "Sigma_Researcher": {
        "description": "Research specialist. Finds best practices, patterns, and real-world solutions.",
        "perspective": "From a research and industry best-practices perspective",
        "contribution_prompt": (
            "You are Sigma_Researcher, an expert at finding the best existing solutions.\n"
            "Your job: Contribute RESEARCH and CONTEXT.\n"
            "Find real-world patterns, industry standards, and existing solutions.\n"
            "If you need live data, output: <SEARCH>query</SEARCH>\n"
            "Reference specific papers, libraries, or techniques that apply."
        ),
        "model_id": "llama-3.3-70b-versatile",
        "strengths": ["research", "find", "latest", "news", "best practice", "approach", "compare"]
    },
    "Gamma_Writer": {
        "description": "Technical communicator. Makes complex things crystal clear and well documented.",
        "perspective": "From a clarity, documentation, and communication perspective",
        "contribution_prompt": (
            "You are Gamma_Writer, an expert technical writer and explainer.\n"
            "Your job: Improve CLARITY and add DOCUMENTATION.\n"
            "Take the current solution and make it clearer, better explained, and complete.\n"
            "Add comments to code. Simplify complex reasoning. Fill in missing explanations.\n"
            "If something is confusing or underdocumented, FIX IT."
        ),
        "model_id": "llama-3.3-70b-versatile",
        "strengths": ["explain", "document", "write", "describe", "clarify", "summarize"]
    },
    "Omega_Critic": {
        "description": "Ruthless quality enforcer. Finds bugs, flaws, and gaps. Demands perfection.",
        "perspective": "As a ruthless quality critic",
        "contribution_prompt": (
            "You are Omega_Critic, the most demanding reviewer in existence.\n"
            "Your job: FIND EVERYTHING WRONG with the current answer.\n"
            "Check for: hallucinations, logical errors, missing edge cases, bugs, shallow reasoning.\n"
            "Be specific about what is wrong and DEMAND a specific fix.\n"
            "If and ONLY IF the answer is truly flawless, output exactly: APPROVED\n"
            "Otherwise, list every flaw and what must change."
        ),
        "model_id": "llama-3.3-70b-versatile",
        "strengths": ["review", "check", "verify", "validate", "test", "critique"]
    }
}

router_brain = SentenceTransformer('all-MiniLM-L6-v2')

# Pre-compute agent embeddings for routing
agent_names = list(AGENTS.keys())
agent_descriptions = [AGENTS[name]["description"] for name in agent_names]
agent_embeddings = router_brain.encode(agent_descriptions)

# ─────────────────────────────────────────────────────────────────
# 2. MEMORY CORE (Simple JSON — works everywhere, no dependencies)
# ─────────────────────────────────────────────────────────────────

def recall_past_memory(query_text: str, n: int = 3) -> Optional[str]:
    """Search JSON memory for past relevant knowledge using keyword matching."""
    try:
        memories = _load_memory()
        if not memories:
            return None
        # Simple keyword match — find memories related to the query
        query_words = set(query_text.lower().split())
        scored = []
        for mem in memories:
            mem_words = set(mem.lower().split())
            score = len(query_words & mem_words)
            if score > 0:
                scored.append((score, mem))
        scored.sort(reverse=True)
        top = [m for _, m in scored[:n]]
        if top:
            print(f"[MEMORY] Recalled {len(top)} related past experiences.")
            return "\n".join([f"[Past Memory {i+1}]: {m}" for i, m in enumerate(top)])
        return None
    except Exception:
        return None

def consolidate_memory(prompt: str, final_answer: str, agent_contributions: dict):
    """Save the completed task to simple JSON long-term memory."""
    try:
        memories = _load_memory()
        contributions_summary = " | ".join(
            [f"{agent}: {contrib[:100]}..." for agent, contrib in agent_contributions.items()]
        )
        memory_text = (
            f"Task: {prompt} | "
            f"Answer: {final_answer[:300]} | "
            f"Agents: {contributions_summary}"
        )
        memories.append(memory_text)
        # Keep only last 50 memories to avoid file bloat
        memories = memories[-50:]
        _save_memory(memories)
        print(f"[MEMORY] Saved. Total memories: {len(memories)}")
    except Exception as e:
        print(f"[MEMORY] Save failed: {e}")

# ─────────────────────────────────────────────────────────────────
# 3. TOOLS
# ─────────────────────────────────────────────────────────────────

def tool_web_search(query: str) -> str:
    """Live web search via DuckDuckGo."""
    print(f"[TOOL] Web search: '{query}'")
    try:
        results = DDGS().text(query, max_results=3)
        return "\n".join([
            f"Source: {r['title']}\nInfo: {r['body']}" for r in results
        ])
    except Exception as e:
        return f"Search failed: {e}"

# ─────────────────────────────────────────────────────────────────
# 4. GROQ API COMMUNICATION (replaces Ollama — no GPU needed!)
#    Free models used:
#    - llama3-70b-8192  → 70B params, replaces codellama + llama3
#    - qwen-qwq-32b     → Qwen-based, replaces qwen2-math (your node!)
# ─────────────────────────────────────────────────────────────────

def query_node(model_id: str, prompt: str, max_retries: int = 2) -> str:
    """Call Groq API instead of local Ollama. No GPU needed, much faster."""

    # Trim prompt to stay within Groq context limits
    if len(prompt) > 3000:
        prompt = prompt[:3000] + "\n[Context trimmed for performance]\n"

    for attempt in range(max_retries):
        try:
            response = groq_client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.7
            )
            result = response.choices[0].message.content
            if result and result.strip():
                return result
        except Exception as e:
            print(f"  [GROQ ERROR] {model_id} attempt {attempt+1}: {e}")
            if attempt == max_retries - 1:
                return f"[ERROR] {model_id} failed after {max_retries} attempts: {e}"
            time.sleep(2)
    return "[ERROR] No response after retries."

def handle_search_in_response(agent_name: str, model_id: str, answer: str, context: str) -> str:
    """Intercept <SEARCH> tags and execute web searches for the agent."""
    match = re.search(r'<SEARCH>(.*?)</SEARCH>', answer)
    if match:
        query = match.group(1)
        live_data = tool_web_search(query)
        print(f"[{agent_name}] Used web search → injecting results")
        follow_up = (
            f"Live web search results for '{query}':\n{live_data}\n\n"
            f"Now answer the original prompt using this data:\n{context}"
        )
        return query_node(model_id, follow_up)
    return answer

# ─────────────────────────────────────────────────────────────────
# 5. DETERMINE PRIMARY AGENT
#    The most relevant agent leads. Others assist.
# ─────────────────────────────────────────────────────────────────

def determine_primary_agent(prompt: str) -> Tuple[str, List[str]]:
    """
    Returns (primary_agent, [supporting_agents])
    Primary agent leads the solution. All others support.
    """
    prompt_embedding = router_brain.encode([prompt])
    similarities = cosine_similarity(prompt_embedding, agent_embeddings)[0]
    
    # Rank all agents by relevance
    ranked = sorted(
        zip(agent_names, similarities),
        key=lambda x: x[1],
        reverse=True
    )
    
    primary = ranked[0][0]
    # Exclude Omega_Critic from support (it's always the final reviewer)
    supporting = [
        name for name, _ in ranked[1:]
        if name != "Omega_Critic" and name != primary
    ]
    
    print(f"\n[ROUTER] Primary Agent: {primary}")
    print(f"[ROUTER] Support Team: {supporting}")
    
    return primary, supporting

# ─────────────────────────────────────────────────────────────────
# 6. COLLABORATIVE BLACKBOARD
#    Shared workspace where all agents write and read each other's work
# ─────────────────────────────────────────────────────────────────

class CollaborativeBlackboard:
    """
    The shared workspace. Every agent reads what others wrote
    and builds on top of it. Like a team whiteboard.
    """
    def __init__(self, original_prompt: str):
        self.original_prompt = original_prompt
        self.contributions = {}  # {agent_name: contribution_text}
        self.rounds = []         # List of round summaries
        self.final_answer = ""
    
    def add_contribution(self, agent_name: str, contribution: str):
        self.contributions[agent_name] = contribution
    
    def get_team_context(self, exclude_agent: str = None, max_chars: int = 600) -> str:
        """
        Get all contributions trimmed per agent to avoid
        overloading 8B models with huge Phase 2 prompts.
        Each agent contribution is capped at max_chars.
        """
        lines = [f"ORIGINAL PROBLEM:\n{self.original_prompt}\n"]
        for agent, contrib in self.contributions.items():
            if agent != exclude_agent and contrib:
                trimmed = (
                    contrib[:max_chars] + "...[trimmed]"
                    if len(contrib) > max_chars
                    else contrib
                )
                lines.append(f"\n{'─'*40}\n[{agent}]:\n{trimmed}")
        return "\n".join(lines)

    def get_summary(self) -> str:
        """One-paragraph summary of all contributions so far."""
        return self.get_team_context()


# ─────────────────────────────────────────────────────────────────
# 7. PHASE 1: INDIVIDUAL ANALYSIS
#    Every agent analyzes the problem independently
# ─────────────────────────────────────────────────────────────────

def phase_1_individual_analysis(
    board: CollaborativeBlackboard,
    primary: str,
    supporting: List[str],
    memory_context: Optional[str]
) -> dict:
    """
    Phase 1: Each agent independently analyzes the problem.
    They don't see each other's work yet — fresh perspectives.
    """
    print("\n[PHASE 1] Individual Analysis — All agents analyzing independently...")
    contributions = {}
    
    all_agents_this_round = [primary] + supporting  # Omega_Critic excluded from phase 1
    
    for agent_name in all_agents_this_round:
        agent = AGENTS[agent_name]
        print(f"  [{agent_name}] Analyzing...")
        
        is_primary = (agent_name == primary)
        role_instruction = (
            "You are the LEAD AGENT for this problem. Give your best, most complete answer."
            if is_primary else
            f"You are a SUPPORT AGENT. Give your unique {agent_name.split('_')[1]} perspective."
        )
        
        # Trim memory to avoid blowing up prompt size
        trimmed_memory = (
            memory_context[:400] + "...[trimmed]"
            if memory_context and len(memory_context) > 400
            else memory_context
        )
        memory_block = (
            f"\nRELEVANT PAST MEMORY:\n{trimmed_memory}\n"
            if trimmed_memory else ""
        )
        
        prompt = (
            f"{agent['contribution_prompt']}\n\n"
            f"{role_instruction}\n"
            f"{memory_block}\n"
            f"PROBLEM TO SOLVE:\n{board.original_prompt}\n\n"
            f"Give your best contribution from your unique perspective. Be specific and thorough."
        )
        
        raw_answer = query_node(agent["model_id"], prompt)
        
        # Handle web search if Sigma_Researcher needs it
        answer = handle_search_in_response(
            agent_name, agent["model_id"], raw_answer, board.original_prompt
        )
        
        contributions[agent_name] = answer
        board.add_contribution(agent_name, answer)
        print(f"  [{agent_name}] ✓ Contributed ({len(answer)} chars)")
    
    return contributions


# ─────────────────────────────────────────────────────────────────
# 8. PHASE 2: CROSS-AGENT COLLABORATION
#    Every agent sees what others said and BUILDS on it
# ─────────────────────────────────────────────────────────────────

def phase_2_cross_collaboration(
    board: CollaborativeBlackboard,
    primary: str,
    supporting: List[str]
) -> dict:
    """
    Phase 2: Agents see each other's Phase 1 work and refine.
    This is where real team intelligence emerges.
    """
    print("\n[PHASE 2] Cross-Agent Collaboration — Agents building on each other's work...")
    refined_contributions = {}
    
    all_agents = [primary] + supporting
    
    for agent_name in all_agents:
        agent = AGENTS[agent_name]
        print(f"  [{agent_name}] Reading teammates' work and refining...")
        
        # This agent sees EVERYONE ELSE's Phase 1 work
        team_context = board.get_team_context(exclude_agent=agent_name)
        my_phase1 = board.contributions.get(agent_name, "")
        
        prompt = (
            f"{agent['contribution_prompt']}\n\n"
            f"You have seen your teammates' analysis. Now BUILD ON IT.\n\n"
            f"━━━ WHAT YOUR TEAM CONTRIBUTED ━━━\n"
            f"{team_context}\n\n"
            f"━━━ YOUR PHASE 1 CONTRIBUTION ━━━\n"
            f"{my_phase1}\n\n"
            f"━━━ YOUR TASK ━━━\n"
            f"1. Identify what your teammates got RIGHT — acknowledge it\n"
            f"2. Identify what they MISSED from your perspective\n"
            f"3. Add YOUR unique contribution that makes the team answer stronger\n"
            f"4. If you see a bug, fix it. If you see a gap, fill it.\n"
            f"5. Do NOT repeat what others already said well.\n\n"
            f"ORIGINAL PROBLEM: {board.original_prompt}"
        )
        
        answer = query_node(agent["model_id"], prompt)
        answer = handle_search_in_response(
            agent_name, agent["model_id"], answer, board.original_prompt
        )
        
        refined_contributions[agent_name] = answer
        print(f"  [{agent_name}] ✓ Refined ({len(answer)} chars)")
    
    return refined_contributions


# ─────────────────────────────────────────────────────────────────
# 9. PHASE 3: PRIMARY AGENT INTEGRATION
#    The lead agent synthesizes all contributions into one answer
# ─────────────────────────────────────────────────────────────────

def phase_3_integration(
    board: CollaborativeBlackboard,
    primary: str,
    phase1: dict,
    phase2: dict
) -> str:
    """
    Phase 3: Primary agent integrates all perspectives into one
    complete, coherent, high-quality answer.
    """
    print(f"\n[PHASE 3] Integration — {primary} synthesizing all contributions...")
    
    agent = AGENTS[primary]
    
    # Build a full picture of all contributions
    all_work = []
    for agent_name in phase1:
        all_work.append(
            f"\n[{agent_name}] Phase 1:\n{phase1[agent_name]}\n"
            f"[{agent_name}] Phase 2 Refinement:\n{phase2.get(agent_name, 'N/A')}"
        )
    
    full_team_work = "\n".join(all_work)
    
    prompt = (
        f"{agent['contribution_prompt']}\n\n"
        f"You are the PRIMARY AGENT. Your job is to INTEGRATE all team contributions.\n\n"
        f"━━━ ALL TEAM CONTRIBUTIONS ━━━\n"
        f"{full_team_work}\n\n"
        f"━━━ YOUR INTEGRATION TASK ━━━\n"
        f"Synthesize ALL of this into ONE perfect, complete answer.\n"
        f"Rules:\n"
        f"1. Take the BEST parts from each agent\n"
        f"2. Fix any bugs or errors the team made\n"
        f"3. Add your own expertise where the team was weak\n"
        f"4. Structure it clearly: explanation → solution → code/proof → conclusion\n"
        f"5. This is the FINAL DELIVERABLE — make it excellent\n\n"
        f"ORIGINAL PROBLEM: {board.original_prompt}"
    )
    
    integrated = query_node(agent["model_id"], prompt)
    print(f"[PHASE 3] ✓ Integration complete ({len(integrated)} chars)")
    return integrated


# ─────────────────────────────────────────────────────────────────
# 10. PHASE 4: PEER REVIEW
#     Supporting agents review the integrated answer
# ─────────────────────────────────────────────────────────────────

def phase_4_peer_review(
    board: CollaborativeBlackboard,
    primary: str,
    supporting: List[str],
    integrated_answer: str
) -> str:
    """
    Phase 4: Supporting agents review the integrated answer.
    They can suggest specific improvements from their angle.
    """
    print("\n[PHASE 4] Peer Review — Supporting agents reviewing integration...")
    
    current_answer = integrated_answer
    
    # Only take top 2 supporters for peer review (efficiency)
    reviewers = supporting[:2]
    
    for agent_name in reviewers:
        agent = AGENTS[agent_name]
        print(f"  [{agent_name}] Peer reviewing...")
        
        prompt = (
            f"{agent['contribution_prompt']}\n\n"
            f"The primary agent integrated the team's work. Review it from YOUR perspective.\n\n"
            f"━━━ INTEGRATED ANSWER TO REVIEW ━━━\n"
            f"{current_answer}\n\n"
            f"━━━ YOUR REVIEW TASK ━━━\n"
            f"From your unique {agent_name.split('_')[1]} perspective:\n"
            f"1. Is anything WRONG that needs fixing?\n"
            f"2. Is anything MISSING that would make this better?\n"
            f"3. If yes → output the IMPROVED VERSION of the full answer\n"
            f"4. If it's solid from your angle → output: PEER APPROVED\n\n"
            f"ORIGINAL PROBLEM: {board.original_prompt}"
        )
        
        review = query_node(agent["model_id"], prompt)
        
        if "PEER APPROVED" not in review.upper():
            print(f"  [{agent_name}] Suggested improvements → updating answer")
            current_answer = review
        else:
            print(f"  [{agent_name}] ✓ Approved")
    
    return current_answer


# ─────────────────────────────────────────────────────────────────
# 11. PHASE 5: OMEGA CRITIC FINAL CHECK
#     Ruthless quality gate — must be APPROVED to pass
# ─────────────────────────────────────────────────────────────────

def phase_5_omega_critic(
    board: CollaborativeBlackboard,
    primary_model: str,
    current_answer: str,
    max_attempts: int = 3
) -> Tuple[str, List[dict]]:
    """
    Phase 5: Omega Critic does final quality check.
    Forces rewrites until the answer is truly excellent or max attempts reached.
    """
    print("\n[PHASE 5] Omega Critic — Final quality gate...")
    
    omega = AGENTS["Omega_Critic"]
    history = []
    
    for attempt in range(max_attempts):
        print(f"  [Omega_Critic] Review attempt {attempt + 1}/{max_attempts}...")
        
        critic_prompt = (
            f"{omega['contribution_prompt']}\n\n"
            f"━━━ ORIGINAL PROBLEM ━━━\n"
            f"{board.original_prompt}\n\n"
            f"━━━ SWARM'S ANSWER TO REVIEW ━━━\n"
            f"{current_answer}\n\n"
            f"━━━ YOUR 5-POINT AUDIT ━━━\n"
            f"1. FACTUAL ACCURACY: Any hallucinations or false claims?\n"
            f"2. LOGICAL CORRECTNESS: Any reasoning errors or contradictions?\n"
            f"3. CODE QUALITY: Any bugs, edge cases, or inefficiencies? (if applicable)\n"
            f"4. COMPLETENESS: Does it fully answer the original problem?\n"
            f"5. DEPTH: Is this surface-level or genuinely insightful?\n\n"
            f"If it fails ANY point, state EXACTLY what is wrong and demand a specific fix.\n"
            f"If ALL 5 points pass, output: APPROVED"
        )
        
        review = query_node(omega["model_id"], critic_prompt)
        history.append({
            "phase": f"Omega_Critic Round {attempt + 1}",
            "review": review
        })
        
        if "APPROVED" in review.upper():
            print(f"  [Omega_Critic] ✓ APPROVED on attempt {attempt + 1}")
            break
        else:
            print(f"  [Omega_Critic] ✗ Rejected. Forcing rewrite...")
            rewrite_prompt = (
                f"The Omega Critic rejected your answer.\n\n"
                f"━━━ CRITIC'S SPECIFIC FEEDBACK ━━━\n"
                f"{review}\n\n"
                f"━━━ YOUR PREVIOUS ANSWER ━━━\n"
                f"{current_answer}\n\n"
                f"Fix EVERY issue the Critic mentioned. Be thorough.\n"
                f"ORIGINAL PROBLEM: {board.original_prompt}"
            )
            current_answer = query_node(primary_model, rewrite_prompt)
    
    return current_answer, history


# ─────────────────────────────────────────────────────────────────
# 12. MAIN SWARM EXECUTION LOOP
# ─────────────────────────────────────────────────────────────────

def run_swarm(user_prompt: str) -> dict:
    """
    Main entry point. Runs the full 5-phase collaborative swarm.
    
    Returns dict with:
    - plan: list of agents involved
    - final_answer: the best answer after all phases
    - history: full log of every agent's contribution
    - phases: breakdown by phase
    """
    
    print("\n" + "═"*60)
    print(f"[SWARM] New Task: {user_prompt[:80]}...")
    print("═"*60)
    
    start_time = time.time()
    history = []
    
    # ── STEP A: RECALL MEMORY ──────────────────────────────────
    memory_context = recall_past_memory(user_prompt)
    
    # ── STEP B: INITIALIZE BLACKBOARD ─────────────────────────
    board = CollaborativeBlackboard(user_prompt)
    
    # ── STEP C: ROUTE — DETERMINE PRIMARY + SUPPORT TEAM ──────
    primary, supporting = determine_primary_agent(user_prompt)
    
    history.append({
        "phase": "Routing",
        "primary": primary,
        "support_team": supporting,
        "memory_found": memory_context is not None
    })
    
    # ── STEP D: PHASE 1 — INDIVIDUAL ANALYSIS ─────────────────
    phase1_contributions = phase_1_individual_analysis(
        board, primary, supporting, memory_context
    )
    
    for agent_name, contrib in phase1_contributions.items():
        history.append({
            "phase": "Phase 1 - Individual Analysis",
            "agent": agent_name,
            "output": contrib
        })
    
    # ── STEP E: PHASE 2 — CROSS-AGENT COLLABORATION ───────────
    phase2_contributions = phase_2_cross_collaboration(
        board, primary, supporting
    )
    
    for agent_name, contrib in phase2_contributions.items():
        history.append({
            "phase": "Phase 2 - Cross Collaboration",
            "agent": agent_name,
            "output": contrib
        })
    
    # ── STEP F: PHASE 3 — INTEGRATION ─────────────────────────
    integrated_answer = phase_3_integration(
        board, primary, phase1_contributions, phase2_contributions
    )
    
    history.append({
        "phase": "Phase 3 - Integration",
        "agent": primary,
        "output": integrated_answer
    })
    
    # ── STEP G: PHASE 4 — PEER REVIEW ─────────────────────────
    peer_reviewed_answer = phase_4_peer_review(
        board, primary, supporting, integrated_answer
    )
    
    history.append({
        "phase": "Phase 4 - Peer Review",
        "output": peer_reviewed_answer
    })
    
    # ── STEP H: PHASE 5 — OMEGA CRITIC ────────────────────────
    primary_model = AGENTS[primary]["model_id"]
    final_answer, critic_history = phase_5_omega_critic(
        board, primary_model, peer_reviewed_answer
    )
    
    history.extend(critic_history)
    
    # ── STEP I: SAVE MEMORY ────────────────────────────────────
    all_contributions = {**phase1_contributions, **phase2_contributions}
    consolidate_memory(user_prompt, final_answer, all_contributions)
    
    elapsed = time.time() - start_time
    
    # ── BUILD FINAL PLAN ───────────────────────────────────────
    plan = [primary] + supporting + ["Omega_Critic"]
    
    result = {
        "plan": plan,
        "primary_agent": primary,
        "support_team": supporting,
        "final_answer": final_answer,
        "history": history,
        "time_taken": f"{elapsed:.1f}s",
        "phases_completed": 5,
        "memory_used": memory_context is not None
    }
    
    print(f"\n[SWARM] ✓ Complete in {elapsed:.1f}s")
    print("═"*60 + "\n")
    
    return result


# ─────────────────────────────────────────────────────────────────
# 13. INTERACTIVE CLI (for testing without Streamlit)
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════╗
    ║     SOVEREIGN SWARM ENGINE v6.0          ║
    ║     5 Agents × 8B Params = Hive Mind     ║
    ╚══════════════════════════════════════════╝
    Type 'exit' to quit. Type 'history' to see memory.
    """)
    
    while True:
        user_input = input("\n🐝 Swarm > ").strip()
        
        if not user_input:
            continue
        elif user_input.lower() == "exit":
            print("Hive Queen going to sleep. Goodbye.")
            break
        elif user_input.lower() == "history":
            mems = memory_collection.get()
            if mems['documents']:
                print(f"\n[MEMORY] {len(mems['documents'])} memories stored:")
                for i, doc in enumerate(mems['documents'][-5:]):  # Show last 5
                    print(f"  [{i+1}] {doc[:120]}...")
            else:
                print("[MEMORY] No memories yet.")
            continue
        
        result = run_swarm(user_input)
        
        print("\n" + "═"*60)
        print("FINAL ANSWER:")
        print("═"*60)
        print(result["final_answer"])
        print("═"*60)
        print(f"Route: {' → '.join(result['plan'])}")
        print(f"Time: {result['time_taken']}")
        print(f"Memory used: {'Yes' if result['memory_used'] else 'No'}")
        print("═"*60)
