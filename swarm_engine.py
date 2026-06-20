import os
import json
from typing import List, Dict
from duckduckgo_search import DDGS
from groq import Groq

print("[*] Initializing Sovereign Swarm Enterprise Core (v12.0 - Final)...")

if not os.environ.get("GROQ_API_KEY"):
    raise RuntimeError("FATAL ERROR: GROQ_API_KEY environment variable is not set.")

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

# ==============================================================================
# 1. SHARED WORKSPACE
# ==============================================================================
class SwarmState:
    def __init__(self, query: str):
        self.query = query
        self.plan = []
        self.artifacts = {}
        self.messages = []
        self.current_agent = None

    def add_artifact(self, key: str, value: str):
        self.artifacts[key] = value

    def get_artifact(self, key: str) -> str:
        return self.artifacts.get(key, "No data available.")

    def to_dict(self):
        return {
            "plan": self.plan, 
            "final_answer": self.artifacts.get("final_answer", "Error: No final answer generated."), 
            "history": self.messages
        }

# ==============================================================================
# 2. AGENT DEFINITIONS (STRICT PROMPTS)
# ==============================================================================
AGENT_DEFS = {
    "Orchestrator": {
        "system_prompt": "You are the Master Orchestrator. Analyze the user's request and delegate it to the correct specialist. If code, delegate to IT_Coder. If research/facts/news, delegate to Research_Analyst. Otherwise, General_Synthesizer.",
        "tools": ["delegate_to_agent"],
        "allowed_transitions": ["Research_Analyst", "IT_Coder", "General_Synthesizer"]
    },
    "Research_Analyst": {
        "system_prompt": (
            "You are a Senior Research Analyst. Your job is to gather raw evidence and delegate to General_Synthesizer.\n"
            "WORKFLOW:\n"
            "1. Call `tool_web_search`.\n"
            "2. If search returns specific results, extract the specific facts, names, and events. DO NOT summarize. Extract raw data.\n"
            "3. If search FAILS or returns 'No results', you MUST save an artifact saying: 'LIVE SEARCH FAILED. The Synthesizer must inform the user that live web search is currently unavailable and provide a general historical overview instead.'\n"
            "4. Save your findings using `save_artifact` with key 'research'.\n"
            "5. Delegate to 'General_Synthesizer'.\n"
            "NEVER delegate to yourself. NEVER output generic fluff like 'advances in AI and quantum computing'. Be specific or report the failure."
        ),
        "tools": ["tool_web_search", "save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["General_Synthesizer"]
    },
    "IT_Coder": {
        "system_prompt": "You are a Senior Software Engineer. Write clean, working code. Save as 'draft' and delegate to QA_Auditor. Do NOT delegate to yourself.",
        "tools": ["save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["QA_Auditor"]
    },
    "General_Synthesizer": {
        "system_prompt": (
            "You are a Synthesizer. Read 'research' from workspace using `read_artifact`.\n"
            "RULES:\n"
            "- If research contains specific facts, write a detailed answer using EXACTLY this format:\n"
            "🎯 BOTTOM LINE:\n(2-sentence direct answer)\n\n🧠 CONTEXT:\n(3-4 sentences)\n\n📊 DATA POINTS:\n- (fact 1)\n- (fact 2)\n- (fact 3)\n\n"
            "- If research says 'LIVE SEARCH FAILED', you MUST tell the user: 'I apologize, but my live web search is currently unavailable due to API rate limits. I cannot provide today's live news.' Then provide a very brief, specific historical fact if possible, but DO NOT pretend to have live news.\n"
            "- NEVER be generic. NEVER use fluff.\n"
            "Save draft as 'draft' and delegate to QA_Auditor."
        ),
        "tools": ["read_artifact", "save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["QA_Auditor"]
    },
    "QA_Auditor": {
        "system_prompt": (
            "You are the QA Auditor. Read 'draft' from workspace.\n"
            "CHECKS:\n"
            "1. Is it generic fluff (e.g., 'advances in AI')? If yes, REJECT and delegate back to General_Synthesizer with note: 'Too generic, be specific or state live data is unavailable'.\n"
            "2. Does it follow the required format? If no, REJECT.\n"
            "If perfect, delegate to Hive_Queen. DO NOT delegate to yourself."
        ),
        "tools": ["read_artifact", "save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["General_Synthesizer", "IT_Coder", "Hive_Queen"]
    },
    "Hive_Queen": {
        "system_prompt": "You are the Hive Queen. Read 'draft' using `read_artifact`. Polish it slightly if needed, save as 'final_answer', and call `finish_task`. DO NOT rewrite the core content.",
        "tools": ["read_artifact", "save_artifact", "finish_task"],
        "allowed_transitions": []
    }
}

# ==============================================================================
# 3. TOOL IMPLEMENTATIONS (HARDENED)
# ==============================================================================
def tool_web_search(query: str) -> str:
    # Strip conversational filler to improve DDGS success rate
    clean_query = query.replace("top 3", "").replace("today", "").replace("latest", "").strip()
    if not clean_query:
        clean_query = "technology news"
        
    print(f"    [TOOL_EXEC] Searching: {clean_query!r}")
    try:
        with DDGS(timeout=10) as ddgs:
            # Added region and safesearch to improve result quality
            results = list(ddgs.text(clean_query, region="wt-wt", safesearch="off", max_results=5))
            
        if not results:
            return "LIVE SEARCH FAILED: No results found."
            
        formatted = "\n".join(
            f"[{i+1}] {r.get('title', '')}: {r.get('body', '')}"
            for i, r in enumerate(results)
        )
        return formatted
    except Exception as e:
        return f"LIVE SEARCH FAILED: Search engine error ({e})."

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "delegate_to_agent",
            "description": "Hand off the current task to another agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "enum": list(AGENT_DEFS.keys()), "description": "The agent to hand control to."},
                    "message": {"type": "string", "description": "Tell the next agent what they need to do."}
                },
                "required": ["agent_name", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tool_web_search",
            "description": "Search the web for real-time data, facts, or news.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search keywords"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_artifact",
            "description": "Save your work (research, draft, code) to the shared workspace so other agents can read it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "enum": ["research", "draft", "code", "final_answer"], "description": "The name of the artifact."},
                    "content": {"type": "string", "description": "The full text of the artifact."}
                },
                "required": ["key", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_artifact",
            "description": "Read an artifact from the shared workspace (e.g., research data or a draft).",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string", "enum": ["research", "draft", "code"], "description": "The name of the artifact to read."}},
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finish_task",
            "description": "End the swarm process because the task is fully complete.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

# ==============================================================================
# 4. THE AGENTIC EXECUTION LOOP
# ==============================================================================
def execute_agent_loop(state: SwarmState, max_steps: int = 10) -> dict:
    step = 0
    
    while step < max_steps:
        step += 1
        agent_name = state.current_agent
        agent_def = AGENT_DEFS[agent_name]
        
        print(f"\n[STEP {step}] Executing Agent: {agent_name}")
        state.plan.append(agent_name)

        api_messages = [{"role": "system", "content": agent_def["system_prompt"]}] + state.messages

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=api_messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                max_tokens=2000,
                temperature=0.3
            )
        except Exception as e:
            print(f"[ERROR] Groq API failed: {e}")
            state.add_artifact("final_answer", f"⚠️ Swarm API Error: {e}")
            return state.to_dict()

        choice = response.choices[0]
        
        if choice.finish_reason == "tool_calls":
            state.messages.append(choice.message)
            
            for tool_call in choice.message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                print(f"    [ACTION] {func_name}({func_args})")

                if func_name == "delegate_to_agent":
                    next_agent = func_args["agent_name"]
                    
                    # ANTI-LOOP: Prevent self-delegation
                    if next_agent == agent_name:
                        observation = f"CRITICAL ERROR: You cannot delegate to yourself! You are {agent_name}. You MUST delegate to: {agent_def['allowed_transitions']}."
                    elif next_agent not in agent_def["allowed_transitions"]:
                        observation = f"ERROR: You cannot delegate to {next_agent}. You MUST delegate to: {agent_def['allowed_transitions']}."
                    else:
                        state.current_agent = next_agent
                        observation = f"Control handed over to {next_agent}."
                        state.messages.append({"role": "user", "content": f"Message from {agent_name}: {func_args['message']}"})

                elif func_name == "save_artifact":
                    state.add_artifact(func_args["key"], func_args["content"])
                    observation = f"Artifact '{func_args['key']}' saved successfully."

                elif func_name == "read_artifact":
                    observation = state.get_artifact(func_args["key"])

                elif func_name == "finish_task":
                    if "final_answer" not in state.artifacts:
                        state.add_artifact("final_answer", "Task finished, but no final answer was saved by the Queen.")
                    return state.to_dict()

                elif func_name == "tool_web_search":
                    observation = tool_web_search(**func_args)

                else:
                    observation = f"Error: Tool {func_name} not found."

                state.messages.append({
                    "role": "tool",
                    "name": func_name,
                    "content": str(observation),
                    "tool_call_id": tool_call.id
                })
        
        elif choice.finish_reason == "stop":
            state.messages.append({"role": "assistant", "content": choice.message.content})
            state.messages.append({"role": "user", "content": "You must use a tool to proceed. Either delegate, save your work, or finish the task."})
        
        else:
            break

    state.add_artifact("final_answer", "⚠️ Swarm exceeded maximum steps. Task aborted to prevent infinite loops.")
    return state.to_dict()

# ==============================================================================
# 5. ENTRY POINT
# ==============================================================================
def run_swarm(user_prompt: str) -> dict:
    print(f"\n[SWARM v12.0] Query: {user_prompt[:60]}...")
    
    state = SwarmState(query=user_prompt)
    state.current_agent = "Orchestrator"
    
    state.messages.append({"role": "user", "content": f"User Request: {user_prompt}\n\nPlease delegate this to the appropriate agent."})

    return execute_agent_loop(state)
