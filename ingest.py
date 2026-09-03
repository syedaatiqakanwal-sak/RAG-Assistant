# ingest.py - Updated with PDF, DOCX, CSV, Markdown support
import os
from pathlib import Path
from langchain_community.document_loaders import (
    DirectoryLoader,
    TextLoader,
    PyPDFLoader,
    UnstructuredWordDocumentLoader,
    CSVLoader,
    UnstructuredMarkdownLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
import warnings
warnings.filterwarnings('ignore')

print("🚀 Starting RAG ingestion process with multi-format support...")
print("="*60)

# Define file type loaders
loaders = {
    '.txt': TextLoader,
    '.pdf': PyPDFLoader,
    '.docx': UnstructuredWordDocumentLoader,
    '.csv': CSVLoader,
    '.md': UnstructuredMarkdownLoader,
}

# Define folder structure
folders = {
    '.txt': './data/txt/',
    '.pdf': './data/pdf/',
    '.docx': './data/docx/',
    '.csv': './data/csv/',
    '.md': './data/markdown/',
}

# Create folders if they don't exist
print("📁 Creating folder structure...")
for folder in folders.values():
    os.makedirs(folder, exist_ok=True)

# Load all documents from all folders
all_documents = []
print("\n📚 Loading documents...")

for ext, folder_path in folders.items():
    # Check if folder exists and has files
    if not os.path.exists(folder_path):
        continue
    
    # Get all files with this extension
    files = list(Path(folder_path).glob(f'*{ext}'))
    if not files:
        continue
    
    print(f"  📂 Found {len(files)} {ext} file(s) in {folder_path}")
    
    try:
        # Use the appropriate loader
        loader_class = loaders[ext]
        loader = DirectoryLoader(
            folder_path,
            glob=f"**/*{ext}",
            loader_cls=loader_class,
            show_progress=True,
            silent_errors=True,
            use_multithreading=True
        )
        
        documents = loader.load()
        
        # Add metadata to each document
        for doc in documents:
            doc.metadata['file_type'] = ext
            doc.metadata['source'] = doc.metadata.get('source', 'Unknown')
        
        all_documents.extend(documents)
        print(f"  ✅ Loaded {len(documents)} documents from {ext} files")
        
    except Exception as e:
        print(f"  ⚠️ Error loading {ext} files: {e}")

if not all_documents:
    print("\n❌ No documents found!")
    print("Please add files to the following folders:")
    print("  - data/txt/     (for .txt files)")
    print("  - data/pdf/     (for .pdf files)")
    print("  - data/docx/    (for .docx files)")
    print("  - data/csv/     (for .csv files)")
    print("  - data/markdown/ (for .md files)")
    exit()

print(f"\n✅ Total documents loaded: {len(all_documents)}")

# Split documents into chunks
print("\n✂️ Splitting documents into chunks...")
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,        # Increased for better context
    chunk_overlap=100,     # More overlap for continuity
    length_function=len,
    separators=["\n\n", "\n", ".", " ", ""],
)
chunks = text_splitter.split_documents(all_documents)
print(f"✅ Split into {len(chunks)} chunks")

# Create embeddings
print("\n🔄 Creating embeddings... This may take a moment.")
embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# Store in Chroma vector database
print("💾 Storing in vector database...")
vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embedding_model,
    persist_directory="./chroma_db"
)

print("\n" + "="*60)
print("✅ Indexing complete!")
print(f"📊 Total chunks stored: {len(chunks)}")
print(f"📁 Documents processed: {len(all_documents)}")

# Show file type summary
print("\n📋 File type summary:")
for ext, folder in folders.items():
    if os.path.exists(folder):
        count = len(list(Path(folder).glob(f'*{ext}')))
        if count > 0:
            print(f"  {ext}: {count} file(s)")

print("\n🚀 Ready to query!")
print("Run: streamlit run app_pro.py")
print("  or: python ask_ollama.py")