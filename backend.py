# backend.py - FastAPI Backend for RAG System
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import shutil
import tempfile
from pathlib import Path
import subprocess
from typing import List, Optional
import uuid
from datetime import datetime

# Import RAG components
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaLLM
from langchain_classic.chains import RetrievalQA

app = FastAPI(title="Zeviq AI API", version="2.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response Models
class ChatRequest(BaseModel):
    question: str
    temperature: Optional[float] = 0.2
    top_k: Optional[int] = 3

class ChatResponse(BaseModel):
    answer: str
    sources: List[dict]
    timestamp: str

class DocumentResponse(BaseModel):
    success: bool
    message: str
    documents: Optional[List[dict]] = None

# Global variable for RAG chain
rag_chain = None

def load_rag_system():
    """Load the RAG system"""
    global rag_chain
    try:
        embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        vectorstore = Chroma(persist_directory="./chroma_db", embedding_function=embedding_model)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
        llm = OllamaLLM(model="llama3.2", temperature=0.2)
        
        rag_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever,
            return_source_documents=True,
        )
        return True
    except Exception as e:
        print(f"Error loading RAG: {e}")
        return False

# Load RAG on startup
@app.on_event("startup")
async def startup_event():
    load_rag_system()

# API Endpoints
@app.get("/")
async def root():
    return {
        "name": "Zeviq AI API",
        "version": "2.0",
        "status": "online",
        "endpoints": [
            "/chat",
            "/upload",
            "/documents",
            "/delete",
            "/reindex"
        ]
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat with the RAG system"""
    global rag_chain
    
    if rag_chain is None:
        if not load_rag_system():
            raise HTTPException(status_code=503, detail="RAG system not available")
    
    try:
        result = rag_chain.invoke({"query": request.question})
        
        sources = []
        for doc in result['source_documents']:
            sources.append({
                "content": doc.page_content,
                "source": doc.metadata.get('source', 'Unknown'),
                "filename": doc.metadata.get('filename', 'Unknown'),
                "file_type": doc.metadata.get('file_type', 'Unknown')
            })
        
        return ChatResponse(
            answer=result['result'],
            sources=sources,
            timestamp=datetime.now().isoformat()
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    """Upload and process documents"""
    try:
        uploaded_files = []
        temp_dir = tempfile.mkdtemp()
        
        # Save uploaded files
        for file in files:
            file_path = os.path.join(temp_dir, file.filename)
            with open(file_path, 'wb') as f:
                content = await file.read()
                f.write(content)
            uploaded_files.append(file.filename)
        
        # Determine file types and move to appropriate folders
        file_types = {
            '.txt': 'data/txt',
            '.pdf': 'data/pdf',
            '.docx': 'data/docx',
            '.csv': 'data/csv',
            '.md': 'data/markdown'
        }
        
        for file in uploaded_files:
            ext = Path(file).suffix.lower()
            if ext in file_types:
                target_folder = file_types[ext]
                os.makedirs(target_folder, exist_ok=True)
                shutil.move(
                    os.path.join(temp_dir, file),
                    os.path.join(target_folder, file)
                )
        
        # Run ingestion
        result = subprocess.run(
            ["python", "ingest.py"],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode == 0:
            # Reload RAG system
            load_rag_system()
            return {
                "success": True,
                "message": f"Uploaded and processed {len(uploaded_files)} documents",
                "documents": uploaded_files
            }
        else:
            return {
                "success": False,
                "message": "Error processing documents",
                "error": result.stderr
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents")
async def get_documents():
    """Get list of all documents"""
    docs = []
    folders = {
        'Text': 'data/txt',
        'PDF': 'data/pdf',
        'Word': 'data/docx',
        'CSV': 'data/csv',
        'Markdown': 'data/markdown'
    }
    
    for category, folder in folders.items():
        if os.path.exists(folder):
            for file in Path(folder).glob('*.*'):
                docs.append({
                    "name": file.name,
                    "category": category,
                    "path": str(file),
                    "size": file.stat().st_size,
                    "modified": datetime.fromtimestamp(file.stat().st_mtime).isoformat()
                })
    
    return {"documents": docs}

@app.delete("/delete/{filename}")
async def delete_document(filename: str):
    """Delete a document"""
    deleted = False
    folders = ['data/txt', 'data/pdf', 'data/docx', 'data/csv', 'data/markdown']
    
    for folder in folders:
        file_path = Path(folder) / filename
        if file_path.exists():
            file_path.unlink()
            deleted = True
            break
    
    if deleted:
        # Re-index after deletion
        load_rag_system()
        return {"success": True, "message": f"Deleted {filename}"}
    else:
        raise HTTPException(status_code=404, detail="Document not found")

@app.post("/reindex")
async def reindex():
    """Re-index all documents"""
    try:
        result = subprocess.run(
            ["python", "ingest.py"],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            load_rag_system()
            return {"success": True, "message": "Re-indexing complete"}
        else:
            return {"success": False, "message": "Re-indexing failed", "error": result.stderr}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status")
async def get_status():
    """Get system status"""
    status = {
        "rag_loaded": rag_chain is not None,
        "ollama_status": "running"  # You can add actual check here
    }
    
    # Check if database exists
    if os.path.exists("./chroma_db"):
        try:
            import chromadb
            client = chromadb.PersistentClient(path="./chroma_db")
            collections = client.list_collections()
            if collections:
                collection = client.get_collection(collections[0])
                status["total_chunks"] = collection.count()
            else:
                status["total_chunks"] = 0
        except:
            status["total_chunks"] = "Error"
    
    return status

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)