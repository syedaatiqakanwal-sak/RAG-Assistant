# ask.py - FIXED HUGGINGFACE VERSION
import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEndpoint
from langchain_classic.chains import RetrievalQA
import warnings
warnings.filterwarnings('ignore')

# Set HUGGINGFACEHUB_API_TOKEN in your environment or .env before running
if not os.environ.get("HUGGINGFACEHUB_API_TOKEN"):
    raise ValueError("Set HUGGINGFACEHUB_API_TOKEN environment variable with your HuggingFace token")

print("🤖 Loading your RAG system with HuggingFace...")

# Load the saved vector database
print("📚 Loading embeddings...")
embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vectorstore = Chroma(persist_directory="./chroma_db", embedding_function=embedding_model)

# Set up the retriever (gets top 3 relevant chunks)
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

# Use a model that works with HuggingFace Inference API
print("🧠 Connecting to HuggingFace AI model...")

# TRY THESE MODELS - They work with the Inference API:
llm = HuggingFaceEndpoint(
    repo_id="google/flan-t5-large",  # Works well for QA
    task="text2text-generation",     # Correct task for this model
    max_new_tokens=256,
    temperature=0.2,
    repetition_penalty=1.15,
)

# Alternative working models (uncomment to try):
# llm = HuggingFaceEndpoint(
#     repo_id="facebook/bart-large-cnn",   # Good for summarization
#     task="text2text-generation",
#     max_new_tokens=256,
# )
#
# llm = HuggingFaceEndpoint(
#     repo_id="google/flan-t5-base",       # Smaller, faster
#     task="text2text-generation",
#     max_new_tokens=256,
# )

# Create the RAG chain
qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=retriever,
    return_source_documents=True,
)

print("✅ RAG system is ready!")
print("\n" + "="*50)
print("FULL RAG MODE (HuggingFace)")
print("Model: Google FLAN-T5-Large")
print("="*50)

while True:
    question = input("\n❓ Ask a question (or type 'quit' to exit): ")
    if question.lower() == 'quit':
        break
    
    try:
        # Get the answer
        result = qa_chain.invoke({"query": question})
        
        print("\n🤖 ANSWER:")
        if result['result'].strip():
            print(result['result'])
        else:
            print("(No clear answer found in the documents)")
        
        print("\n📄 SOURCES USED:")
        for i, doc in enumerate(result['source_documents']):
            preview = doc.page_content[:150] + "..." if len(doc.page_content) > 150 else doc.page_content
            print(f"\n--- Source {i+1} ---")
            print(preview)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Try asking a different question or check your token.")
    
    print("\n" + "-"*50)