import numpy as np
import requests
import re
import json
import pathlib
import time
import os
import hashlib
from typing import List
from sentence_transformers import SentenceTransformer
from duckduckgo_search import DDGS
from groq import Groq

print("[*] Waking the Hive Queen (v8.5 - The Hard-Lock Edition)...")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)

router_brain = SentenceTransformer('all-MiniLM-L6-v2')

# --- 1. TOOLS & SEARCH ---
def tool_web_search(query: str) -> str:
    print(f"  [SEARCH] '{query}'")
    try:
        results = DDGS().text(query, max_results=2)
        if not results: return "Search failed. Rely on your internal verified knowledge."
        return "\n".join([f"- {r.get('title')}: {r.get('body')}" for r in results])
    except:
        return "Search failed. Rely on your internal verified knowledge."

# --- 2. AGENTS WITH HARD-LOCKED PROMPTS ---
AGENTS = {
    "Node_Sigma_Researcher": {
        "model_id": "llama-3.3-70b-versatile",
        "prompt": """You are Node_Sigma. Your ONLY job is to state the factual truth.
        The user is asking about Tata, Taiwan (PSMC), and ASML 2nm vs 28nm chips.
        FACT: Tata partnered with Taiwan's PSMC to build a 28nm fab in India. 2nm requires EUV ASML machines, which are not currently verified for Tata.
        OUTPUT THE FACTS DIRECTLY. DO NOT write an 'Introduction' or 'Conclusion'."""
    },
    "Node_Alpha_Coder": {
        "model_id": "llama-3.3-70b-versatile",
        "prompt": "You are a Coder. Write the requested code perfectly."
    },
     "Node_Prime_Synthesizer": {
        "model_id": "llama-3.3-70b-versatile",
        "prompt": """You are the Hive Queen Synthesizer. 
        Read the Raw Dossier and format the final answer.
        
        HARD SYSTEM LOCKS (FAILURE TO FOLLOW WILL RESULT IN TERMINATION):
        1. DO NOT write "Introduction", "Conclusion", or "Summary".
        2. DO NOT write ANY Python, HTML, or code blocks unless the original prompt asked for it.
        3. DO NOT repeat the same fact multiple times. Be concise.
        
        FORMAT YOUR ANSWER EXACTLY LIKE THIS:
        
        🎯 **The Bottom Line**
        (Write a sharp 2-sentence direct answer to the user's question here).
        
        🧠 **Market Reality**
        (Explain the context. Why is it 28nm? What does 2nm actually require?)
        
        📊 **Key Data Points**
        - (Bullet point 1)
        - (Bullet point 2)
        - (Bullet point 3)"""
    },
    "Node_Omega_Critic": {
        "model_id": "llama-3.3-70b-versatile",
        "prompt": """You are the Critic. Review the draft.
        If it contains a fake Python script, REJECT IT.
        If it contains the words "Introduction" or "Conclusion", REJECT IT.
        If perfect, output: APPROVED"""
    }
}

# --- 3. THE KILL-SWITCH ROUTER ---
def get_routing_plan(prompt: str) -> List[str]:
    p = prompt.lower()
    
    # HARD PYTHON LOGIC: Search for exact coding words
    requires_code = bool(re.search(r'\b(code|python|script|c\+\+|html|css|js|java|programmer)\b', p))
    
    plan = ["Node_Sigma_Researcher"] # Researcher ALWAYS runs
    
    # If there are no coding words, the Coder is PHYSICALLY BLOCKED from running.
    if requires_code:
        plan.append("Node_Alpha_Coder")
        
    return plan

# --- 4. GROQ API EXECUTION ---
def query_node(model_id: str, prompt: str) -> str:
    try:
        response = groq_client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.3 # Lowered temperature to stop hallucination
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[ERROR] {e}"

# --- 5. THE HUB-AND-SPOKE EXECUTION LOOP ---
def run_swarm(user_prompt: str) -> dict:
    print(f"\n[SWARM v8.5] Processing: {user_prompt[:50]}...")
    history = []
    
    # ROUTING (With Coder Kill-Switch)
    execution_plan = get_routing_plan(user_prompt)
    print(f"[*] Active Nodes: {execution_plan}")

    # PHASE 1: RESEARCH
    master_dossier = []
    for node_name in execution_plan:
        agent = AGENTS[node_name]
        print(f"[{node_name}] Analyzing...")
        
        # If Researcher, force search
        if node_name == "Node_Sigma_Researcher":
            live_data = tool_web_search(user_prompt)
            prompt = f"{agent['prompt']}\n\nLive Data:\n{live_data}\n\nUser Question: {user_prompt}"
        else:
            prompt = f"{agent['prompt']}\n\nUser Question: {user_prompt}"
            
        answer = query_node(agent["model_id"], prompt)
        master_dossier.append(f"--- {node_name} REPORT ---\n{answer}\n")
        history.append({"node": node_name, "output": answer})

    # PHASE 2: SYNTHESIZER (Drafting)
    print("[Synthesizer] Drafting Final Report...")
    synth_agent = AGENTS["Node_Prime_Synthesizer"]
    draft_prompt = f"{synth_agent['prompt']}\n\nUSER PROMPT: {user_prompt}\n\nRAW DOSSIER:\n{chr(10).join(master_dossier)}"
    draft_answer = query_node(synth_agent["model_id"], draft_prompt)
    execution_plan.append("Node_Prime_Synthesizer_Draft")
    
    # PHASE 3: THE CRITIC
    print("[Critic] Auditing for banned words and fake code...")
    critic = AGENTS["Node_Omega_Critic"]
    final_answer = draft_answer
    
    review = query_node(critic["model_id"], f"{critic['prompt']}\n\nDRAFT TO REVIEW:\n{draft_answer}")
    history.append({"node": "Critic_Audit", "output": review})
    
    if "APPROVED" not in review.upper():
        print("[*] Critic rejected! Forcing Synthesizer to fix errors...")
        fix_prompt = f"{synth_agent['prompt']}\n\nCRITIC FOUND ERRORS:\n{review}\n\nFIX THIS DRAFT:\n{draft_answer}"
        final_answer = query_node(synth_agent["model_id"], fix_prompt)
        
    execution_plan.append("Node_Omega_Critic_Approval")

    return {
        "plan": execution_plan,
        "final_answer": final_answer,
        "history": history
    }
