# app_admin.py - Admin Panel + User Chat System
import streamlit as st
import os
import tempfile
from pathlib import Path
import shutil
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Page config
st.set_page_config(
    page_title="Zeviq AI - Admin Panel",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #00FF88, #00D4FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
    }
    .admin-card {
        background: rgba(30, 30, 50, 0.8);
        border-radius: 15px;
        padding: 1.5rem;
        border: 1px solid rgba(0, 255, 136, 0.2);
        margin: 0.5rem 0;
    }
    .user-card {
        background: rgba(20, 20, 40, 0.6);
        border-radius: 15px;
        padding: 1.5rem;
        border: 1px solid rgba(0, 212, 255, 0.2);
        margin: 0.5rem 0;
    }
    .answer-box {
        background: linear-gradient(135deg, rgba(0, 255, 136, 0.1), rgba(0, 212, 255, 0.1));
        border: 1px solid #00FF88;
        border-radius: 15px;
        padding: 2rem;
        margin: 1rem 0;
    }
    .source-box {
        background: rgba(20, 20, 40, 0.6);
        border-left: 3px solid #00D4FF;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'role' not in st.session_state:
    st.session_state.role = None
if 'messages' not in st.session_state:
    st.session_state.messages = []

# Header
st.markdown('<div class="main-header">🧠 Zeviq AI</div>', unsafe_allow_html=True)

# Login/Logout
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    if not st.session_state.authenticated:
        st.markdown("### 🔐 Login")
        role = st.selectbox("Select Role", ["User", "Admin"])
        password = st.text_input("Password", type="password")
        
        # Simple authentication (in production, use proper auth)
        if st.button("Login"):
            if role == "Admin" and password == "admin123":
                st.session_state.authenticated = True
                st.session_state.role = "Admin"
                st.success("✅ Welcome Admin!")
                st.rerun()
            elif role == "User":
                st.session_state.authenticated = True
                st.session_state.role = "User"
                st.success("✅ Welcome User!")
                st.rerun()
            else:
                st.error("❌ Invalid credentials for Admin")
    else:
        st.info(f"👤 Logged in as: {st.session_state.role}")
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.session_state.role = None
            st.session_state.messages = []
            st.rerun()

if st.session_state.authenticated:
    st.markdown("---")
    
    # Tabs based on role
    if st.session_state.role == "Admin":
        tab1, tab2, tab3 = st.tabs(["📤 Document Management", "📚 Document Library", "👥 User Activity"])
    else:
        tab1, tab2 = st.tabs(["💬 Chat", "📚 About"])
    
    # ADMIN PANEL
    if st.session_state.role == "Admin":
        with tab1:
            st.markdown("### 📤 Admin Dashboard - Document Management")
            st.caption("Upload documents that users can ask questions about")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### 📄 Upload Documents")
                
                # File upload
                uploaded_files = st.file_uploader(
                    "Select documents to add to knowledge base",
                    type=['txt', 'pdf', 'docx', 'csv', 'md'],
                    accept_multiple_files=True
                )
                
                if uploaded_files:
                    doc_type = st.selectbox(
                        "Document Category",
                        ["txt", "pdf", "docx", "csv", "markdown"]
                    )
                    
                    if st.button("📥 Upload and Process", use_container_width=True):
                        with st.spinner("Processing documents..."):
                            # Save files
                            folder_map = {
                                "txt": "data/txt",
                                "pdf": "data/pdf",
                                "docx": "data/docx",
                                "csv": "data/csv",
                                "markdown": "data/markdown"
                            }
                            
                            target_folder = folder_map[doc_type]
                            os.makedirs(target_folder, exist_ok=True)
                            
                            for file in uploaded_files:
                                file_path = os.path.join(target_folder, file.name)
                                with open(file_path, 'wb') as f:
                                    f.write(file.getbuffer())
                            
                            # Run ingestion
                            import subprocess
                            result = subprocess.run(
                                ["python", "ingest.py"],
                                capture_output=True,
                                text=True
                            )
                            
                            if result.returncode == 0:
                                st.success(f"✅ Uploaded and processed {len(uploaded_files)} documents!")
                                st.info("Users can now ask questions about these documents.")
                            else:
                                st.error("❌ Error processing documents")
                                st.code(result.stderr)
            
            with col2:
                st.markdown("#### 📊 System Overview")
                
                # Show stats
                try:
                    import chromadb
                    client = chromadb.PersistentClient(path="./chroma_db")
                    collections = client.list_collections()
                    
                    if collections:
                        collection = client.get_collection(collections[0])
                        total_chunks = collection.count()
                        st.metric("🧩 Total Chunks", total_chunks)
                    else:
                        st.metric("🧩 Total Chunks", 0)
                except:
                    st.metric("🧩 Total Chunks", "N/A")
                
                # Show document count
                doc_count = 0
                for folder in ['data/txt', 'data/pdf', 'data/docx', 'data/csv', 'data/markdown']:
                    if os.path.exists(folder):
                        doc_count += len(list(Path(folder).glob('*.*')))
                st.metric("📄 Documents", doc_count)
                
                st.markdown("---")
                st.markdown("#### 📁 Quick Actions")
                if st.button("🔄 Re-index All Documents"):
                    with st.spinner("Re-indexing..."):
                        subprocess.run(["python", "ingest.py"], capture_output=True)
                    st.success("✅ Re-indexing complete!")
                
                if st.button("🗑️ Clear All Documents",):
                    # Dangerous - confirm
                    if st.checkbox("⚠️ Confirm delete all documents"):
                        for folder in ['data/txt', 'data/pdf', 'data/docx', 'data/csv', 'data/markdown']:
                            if os.path.exists(folder):
                                shutil.rmtree(folder)
                                os.makedirs(folder)
                        st.success("✅ All documents cleared!")
        
        with tab2:
            st.markdown("### 📚 Document Library")
            st.caption("All documents in the system")
            
            # Show all documents
            doc_folders = {
                "📄 Text": "data/txt",
                "📕 PDF": "data/pdf",
                "📘 Word": "data/docx",
                "📊 CSV": "data/csv",
                "📗 Markdown": "data/markdown"
            }
            
            for label, folder in doc_folders.items():
                if os.path.exists(folder):
                    files = list(Path(folder).glob('*.*'))
                    if files:
                        st.markdown(f"#### {label} ({len(files)} files)")
                        for file in files:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.text(f"📎 {file.name}")
                            with col2:
                                if st.button(f"Delete", key=f"del_{file.name}"):
                                    os.remove(file)
                                    st.success(f"Deleted {file.name}")
                                    st.rerun()
        
        with tab3:
            st.markdown("### 👥 User Activity")
            st.caption("Track user interactions")
            
            # Activity stats (simplified)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("💬 Total Questions", len(st.session_state.messages))
            with col2:
                st.metric("👤 Active Users", 1)  # Simplified
            with col3:
                st.metric("📈 Session Length", f"{len(st.session_state.messages)//2} exchanges")
            
            # Show recent activity
            if st.session_state.messages:
                st.markdown("#### Recent Activity")
                for msg in st.session_state.messages[-10:]:
                    if msg["role"] == "user":
                        st.info(f"👤 User asked: {msg['content'][:50]}...")
                    else:
                        st.success(f"🤖 Assistant: {msg['content'][:50]}...")
            else:
                st.info("No activity yet")
    
    # USER PANEL
    else:  # User role
        with tab1:
            st.markdown("### 💬 Chat with Zeviq AI")
            st.caption("Ask questions about the documents. Your questions help improve the system.")
            
            # Chat interface
            chat_container = st.container()
            with chat_container:
                if not st.session_state.messages:
                    st.info("💡 Start by asking a question about the documents!")
                
                for message in st.session_state.messages:
                    if message["role"] == "user":
                        st.markdown(f'<div style="background:rgba(0,212,255,0.1);padding:1rem;border-radius:15px;margin:0.5rem 0;">👤 {message["content"]}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div style="background:rgba(0,255,136,0.05);padding:1rem;border-radius:15px;margin:0.5rem 0;border-left:3px solid #00FF88;">🧠 {message["content"]}</div>', unsafe_allow_html=True)
            
            # Input
            if prompt := st.chat_input("Ask about your documents..."):
                # Add user message
                st.session_state.messages.append({"role": "user", "content": prompt})
                
                with st.spinner("🧠 Thinking..."):
                    try:
                        from langchain_huggingface import HuggingFaceEmbeddings
                        from langchain_community.vectorstores import Chroma
                        from langchain_ollama import OllamaLLM
                        from langchain_classic.chains import RetrievalQA
                        
                        # Load RAG
                        embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
                        vectorstore = Chroma(persist_directory="./chroma_db", embedding_function=embedding_model)
                        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
                        llm = OllamaLLM(model="llama3.2", temperature=0.2)
                        
                        qa_chain = RetrievalQA.from_chain_type(
                            llm=llm,
                            chain_type="stuff",
                            retriever=retriever,
                            return_source_documents=True,
                        )
                        
                        result = qa_chain.invoke({"query": prompt})
                        
                        # Display answer
                        answer = result['result']
                        st.markdown(f'<div style="background:rgba(0,255,136,0.05);padding:1rem;border-radius:15px;margin:0.5rem 0;border-left:3px solid #00FF88;">🧠 {answer}</div>', unsafe_allow_html=True)
                        
                        # Sources
                        with st.expander("📄 View Sources"):
                            for i, doc in enumerate(result['source_documents'], 1):
                                st.markdown(f"""
                                <div class="source-box">
                                    <b>Source {i}</b><br>
                                    <small>📁 {doc.metadata.get('filename', 'Unknown')}</small><br>
                                    {doc.page_content[:200]}...
                                </div>
                                """, unsafe_allow_html=True)
                        
                        st.session_state.messages.append({"role": "assistant", "content": answer})
                        
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
                        st.info("💡 Make sure Ollama is running! Type 'ollama run llama3.2' in a new terminal.")
        
        with tab2:
            st.markdown("### 📚 About Zeviq AI")
            st.markdown("""
            <div class="user-card">
                <h3>🤖 What is Zeviq AI?</h3>
                <p>Zeviq AI is an intelligent document assistant that uses Retrieval-Augmented Generation (RAG) to answer questions based on your documents.</p>
                
                <h3>🔧 How it works</h3>
                <ol>
                    <li>Admins upload documents to the system</li>
                    <li>The documents are processed and indexed</li>
                    <li>You ask questions in natural language</li>
                    <li>The AI finds relevant information and generates accurate answers</li>
                    <li>Sources are provided for verification</li>
                </ol>
                
                <h3>📁 Document Types Supported</h3>
                <ul>
                    <li>Text files (.txt)</li>
                    <li>PDF documents (.pdf)</li>
                    <li>Word documents (.docx)</li>
                    <li>CSV files (.csv)</li>
                    <li>Markdown files (.md)</li>
                </ul>
                
                <h3>💡 Tips</h3>
                <ul>
                    <li>Be specific with your questions</li>
                    <li>Ask follow-up questions for more details</li>
                    <li>The system only answers from uploaded documents</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.8rem;">
    <p>🧠 Zeviq AI - Enterprise RAG System | Admin Panel v2.0</p>
    <p>🔧 Admin login: admin123</p>
</div>
""", unsafe_allow_html=True)