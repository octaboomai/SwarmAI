import os
import json
from typing import List, Dict
from duckduckgo_search import DDGS
from groq import Groq

print("[*] Initializing Sovereign Swarm Enterprise Core (v11.0)...")

if not os.environ.get("GROQ_API_KEY"):
    raise RuntimeError("FATAL ERROR: GROQ_API_KEY environment variable is not set.")

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

# ==============================================================================
# 1. SHARED WORKSPACE (The "Blackboard" Pattern)
# ==============================================================================
class SwarmState:
    def __init__(self, query: str):
        self.query = query
        self.plan = []
        self.artifacts = {}      # e.g., {"research": "...", "draft": "..."}
        self.messages = []       # The main conversation history
        self.current_agent = None

    def add_artifact(self, key: str, value: str):
        self.artifacts[key] = value

    def get_artifact(self, key: str) -> str:
        return self.artifacts.get(key, "No data available.")

    def to_dict(self):
        return {
            "plan": self.plan, 
            "final_answer": self.artifacts.get("final_answer", "Error: No final answer generated. The swarm may have stalled."), 
            "history": self.messages
        }

# ==============================================================================
# 2. AGENT REGISTRY & DEFINITIONS
# ==============================================================================
AGENT_DEFS = {
    "Orchestrator": {
        "system_prompt": "You are the Master Orchestrator. Analyze the user's request and delegate it to the correct specialist. You do no work yourself. If the user asks for code, delegate to IT_Coder. If they ask for research or facts, delegate to Research_Analyst. Otherwise, delegate to General_Synthesizer.",
        "tools": ["delegate_to_agent"],
        "allowed_transitions": ["Research_Analyst", "IT_Coder", "General_Synthesizer"]
    },
    "Research_Analyst": {
        "system_prompt": (
            "You are a Senior Research Analyst. Your only job is to gather raw evidence. "
            "If the user asks for current data, news, or facts, you MUST use the `tool_web_search` function. "
            "CRITICAL: Do NOT output text like '<function=...>'. Only use the standard JSON tool calling format provided by the API. "
            "Do not answer from memory if live data is requested. Call the search tool. "
            "After you receive the search results, use `save_artifact` to save your findings, and then use `delegate_to_agent` to pass the task to the General_Synthesizer."
        ),
        "tools": ["tool_web_search", "save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["General_Synthesizer"]
    },
    "IT_Coder": {
        "system_prompt": "You are a Senior Software Engineer. Write clean, working code for the request. Save your code to the workspace as 'draft' and delegate to the QA_Auditor for review. Do NOT output XML tags like <function=...>. Only use the provided JSON tool format.",
        "tools": ["save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["QA_Auditor"]
    },
    "General_Synthesizer": {
        "system_prompt": "You are a Synthesizer. Read the research from the workspace (if any). Write a comprehensive answer using the required format (🎯 Bottom Line, 🧠 Context, 📊 Data Points). Save the draft and delegate to the QA_Auditor. Do NOT output XML tags like <function=...>. Only use the provided JSON tool format.",
        "tools": ["read_artifact", "save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["QA_Auditor"]
    },
    "QA_Auditor": {
        "system_prompt": "You are the QA Auditor. Read the draft from the workspace. Check for hallucinations, off-topic content, and quality. If it is perfect, delegate to the Hive_Queen. If it needs fixes, delegate BACK to the agent who created it with instructions to fix it. Do NOT output XML tags like <function=...>. Only use the provided JSON tool format.",
        "tools": ["read_artifact", "save_artifact", "delegate_to_agent"],
        "allowed_transitions": ["General_Synthesizer", "IT_Coder", "Hive_Queen"]
    },
    "Hive_Queen": {
        "system_prompt": "You are the Hive Queen. You receive the final approved draft. Format it beautifully and save it as 'final_answer'. Then use the finish_task tool to end the swarm process. Do NOT output XML tags like <function=...>. Only use the provided JSON tool format.",
        "tools": ["read_artifact", "save_artifact", "finish_task"],
        "allowed_transitions": []
    }
}
# ==============================================================================
# 3. TOOL IMPLEMENTATIONS
# ==============================================================================
def tool_web_search(query: str) -> str:
    print(f"    [TOOL] Web Search: {query}")
    try:
        with DDGS(timeout=10) as ddgs:
            results = ddgs.text(query.strip(), max_results=5)
        if not results: return "No results found."
        return "\n".join(f"[{i+1}] {r.get('title', '')}: {r.get('body', '')}" for i, r in enumerate(results))
    except Exception as e:
        return f"Search failed ({e})."

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
# 4. THE AGENTIC EXECUTION LOOP (FIXED)
# ==============================================================================

def execute_agent_loop(state: SwarmState, max_steps: int = 10) -> dict:
    step = 0
    
    while step < max_steps:
        step += 1
        agent_name = state.current_agent
        agent_def = AGENT_DEFS[agent_name]
        
        print(f"\n[STEP {step}] Executing Agent: {agent_name}")
        state.plan.append(agent_name)

        # FIX: Groq requires the system prompt to be INSIDE the messages array.
        # We dynamically prepend the current agent's system prompt to the history.
        api_messages = [{"role": "system", "content": agent_def["system_prompt"]}] + state.messages

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=api_messages, # Use the modified list
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
        
        # If the agent wants to call a tool
        if choice.finish_reason == "tool_calls":
            # Add the assistant's tool call request to history
            state.messages.append(choice.message)
            
            for tool_call in choice.message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                print(f"    [ACTION] {func_name}({func_args})")

                # --- EXECUTE TOOLS ---
                if func_name == "delegate_to_agent":
                    next_agent = func_args["agent_name"]
                    # Security: Ensure the agent is allowed to delegate there
                    if next_agent not in agent_def["allowed_transitions"]:
                        observation = f"Error: You are not allowed to delegate to {next_agent}. Allowed: {agent_def['allowed_transitions']}"
                    else:
                        state.current_agent = next_agent
                        observation = f"Control handed over to {next_agent}."
                        # Add the message to the history for the next agent
                        state.messages.append({"role": "user", "content": f"Message from {agent_name}: {func_args['message']}"})

                elif func_name == "save_artifact":
                    state.add_artifact(func_args["key"], func_args["content"])
                    observation = f"Artifact '{func_args['key']}' saved to workspace successfully."

                elif func_name == "read_artifact":
                    observation = state.get_artifact(func_args["key"])

                elif func_name == "finish_task":
                    # End the loop immediately
                    if "final_answer" not in state.artifacts:
                        state.add_artifact("final_answer", "Task finished, but no final answer was saved.")
                    return state.to_dict()

                elif func_name == "tool_web_search":
                    observation = tool_web_search(**func_args)

                else:
                    observation = f"Error: Tool {func_name} not found."

                # Append the tool result back to the LLM
                state.messages.append({
                    "role": "tool",
                    "name": func_name,
                    "content": str(observation),
                    "tool_call_id": tool_call.id
                })
        
        elif choice.finish_reason == "stop":
            # If the agent stops without calling a tool, force a delegation or end
            state.messages.append({"role": "assistant", "content": choice.message.content})
            state.messages.append({"role": "user", "content": "You must use a tool to proceed. Either delegate to another agent, save your work, or finish the task."})
        
        else:
            break

    state.add_artifact("final_answer", "⚠️ Swarm exceeded maximum steps. Task aborted to prevent infinite loops.")
    return state.to_dict()
# ==============================================================================
# 5. ENTRY POINT
# ==============================================================================
def run_swarm(user_prompt: str) -> dict:
    print(f"\n[SWARM v11.0] Query: {user_prompt[:60]}...")
    
    state = SwarmState(query=user_prompt)
    state.current_agent = "Orchestrator"
    
    state.messages.append({"role": "user", "content": f"User Request: {user_prompt}\n\nPlease delegate this to the appropriate agent."})

    return execute_agent_loop(state)
