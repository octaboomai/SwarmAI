import streamlit as st
import requests
import PyPDF2
import io

st.set_page_config(page_title="Hive Queen AI", layout="wide")

# --- SIDEBAR: DOCUMENT INGESTION ---
with st.sidebar:
    st.header("📂 Secure Document Upload")
    st.write("Upload a private PDF. The Swarm will read it locally.")
    
    uploaded_file = st.file_uploader("Upload PDF", type="pdf")
    
    document_context = ""
    if uploaded_file is not None:
        try:
            # Extract text from the PDF
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                document_context += page.extract_text() + "\n"
            
            # Limit text size to prevent overloading the model's memory
            if len(document_context) > 10000:
                document_context = document_context[:10000] + "\n...[Document Truncated for Memory]..."
                
            st.success("✅ Document securely loaded into Swarm memory.")
            with st.expander("Preview Document Text"):
                st.write(document_context[:500] + "...")
        except Exception as e:
            st.error(f"Error reading PDF: {e}")

# --- MAIN CHAT INTERFACE ---
st.title("🐝 Sovereign Swarm Engine")
st.markdown("Private, Local, Air-Gapped Intelligence.")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Display previous messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# The Chat Input Box
user_prompt = st.chat_input("Ask the Swarm to analyze the document...")

if user_prompt:
    # If a document is uploaded, we secretly inject it into the prompt!
    if document_context != "":
        full_prompt = f"Here is a document:\n\n{document_context}\n\nUSER QUESTION: {user_prompt}"
    else:
        full_prompt = user_prompt

    with st.chat_message("user"):
        st.markdown(user_prompt) # We only show the user their short question
    st.session_state.messages.append({"role": "user", "content": user_prompt})

    with st.chat_message("assistant"):
        status_text = st.empty()
        status_text.text("The Hive Queen is analyzing...")
        
        try:
            # Send the massive prompt to the backend
            response = requests.post("http://127.0.0.1:8000/orchestrate", json={"prompt": full_prompt})
            data = response.json()
            
            plan_str = " -> ".join(data["plan"])
            st.info(f"**Execution Plan:** {plan_str}")
            
            final_answer = data["final_answer"]
            st.markdown(final_answer)
            
            st.session_state.messages.append({"role": "assistant", "content": final_answer})
            
        except requests.exceptions.ConnectionError:
            st.error("🚨 Could not connect to the Swarm API. Is the FastAPI backend running?")
