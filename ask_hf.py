# ask_hf.py - SIMPLIFIED HUGGINGFACE RAG
import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
import requests

# Set HUGGINGFACEHUB_API_TOKEN in your environment or .env before running
if not os.environ.get("HUGGINGFACEHUB_API_TOKEN"):
    raise ValueError("Set HUGGINGFACEHUB_API_TOKEN environment variable with your HuggingFace token")

print("🤖 Loading your RAG system...")

# Load the saved vector database
embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vectorstore = Chroma(persist_directory="./chroma_db", embedding_function=embedding_model)

# Set up the retriever
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

# HuggingFace API setup
API_URL = "https://api-inference.huggingface.co/models/google/flan-t5-large"
headers = {"Authorization": f"Bearer {os.environ['HUGGINGFACEHUB_API_TOKEN']}"}

print("✅ RAG system is ready!")
print("\n" + "="*50)
print("FULL RAG MODE (HuggingFace - FLAN-T5-Large)")
print("="*50)

while True:
    question = input("\n❓ Ask a question (or type 'quit' to exit): ")
    if question.lower() == 'quit':
        break
    
    # 1. Retrieve relevant chunks
    docs = retriever.invoke(question)
    
    # 2. Prepare context from chunks
    context = "\n".join([doc.page_content for doc in docs])
    
    # 3. Prepare prompt for the model
    prompt = f"""Answer the question based on the following context. If you cannot find the answer in the context, say "I don't have that information."

Context:
{context}

Question: {question}

Answer:"""
    
    # 4. Call HuggingFace API
    try:
        print("🔄 Generating answer...")
        response = requests.post(API_URL, headers=headers, json={"inputs": prompt})
        
        if response.status_code == 200:
            result = response.json()
            answer = result[0]['generated_text']
            print(f"\n🤖 ANSWER: {answer}")
            
            print("\n📄 SOURCES USED:")
            for i, doc in enumerate(docs):
                preview = doc.page_content[:100] + "..." if len(doc.page_content) > 100 else doc.page_content
                print(f"\n--- Source {i+1} ---")
                print(preview)
        else:
            print(f"\n❌ API Error: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    print("\n" + "-"*50)