from fastapi import FastAPI
from pydantic import BaseModel
from swarm_engine import run_swarm

# Initialize the API Server
app = FastAPI(title="Sovereign Swarm API")

# Define the data format we expect from the user
class UserRequest(BaseModel):
    prompt: str

# Open an endpoint to accept tasks
@app.post("/orchestrate")
def orchestrate_task(request: UserRequest):
    print(f"[*] API Received Task: {request.prompt}")
    
    # Send the task to our Python logic in swarm_engine.py
    result = run_swarm(request.prompt)
    
    return result