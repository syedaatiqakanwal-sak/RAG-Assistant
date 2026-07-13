# ask_ollama.py - USING OLLAMA (Local LLM)
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaLLM
from langchain_classic.chains import RetrievalQA
import warnings
warnings.filterwarnings('ignore')

print("🤖 Loading your RAG system with Ollama...")

# Load embeddings
print("📚 Loading embeddings...")
embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vectorstore = Chroma(persist_directory="./chroma_db", embedding_function=embedding_model)

# Set up retriever
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

# Connect to Ollama
print("🧠 Connecting to Ollama...")
llm = OllamaLLM(
    model="llama3.2",
    temperature=0.2,
)

# Create RAG chain
qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=retriever,
    return_source_documents=True,
)

print("✅ RAG system is ready!")
print("\n" + "="*50)
print("FULL RAG MODE (Ollama - Llama 3.2)")
print("="*50)

while True:
    question = input("\n❓ Ask a question (or type 'quit' to exit): ")
    if question.lower() == 'quit':
        break
    
    try:
        print("🔄 Generating answer...")
        result = qa_chain.invoke({"query": question})
        
        print("\n🤖 ANSWER:")
        print(result['result'])
        
        print("\n📄 SOURCES USED:")
        for i, doc in enumerate(result['source_documents']):
            preview = doc.page_content[:150] + "..." if len(doc.page_content) > 150 else doc.page_content
            print(f"\n--- Source {i+1} ---")
            print(preview)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Make sure Ollama is running.")
    
    print("\n" + "-"*50)