# Lumora RAG Web Application

Production-ready Retrieval-Augmented Generation web app powered by:

- FastAPI async backend
- ChromaDB persistent vector store
- Ollama with `llama3.2`
- HuggingFace `all-MiniLM-L6-v2` embeddings
- Vanilla HTML/CSS/JS frontend with streaming chat and an admin panel

## Features

- Streaming RAG chat with source attribution
- Multiple local chat sessions persisted in `localStorage`
- Copy answers and export chats as text or PDF via print
- Admin JWT login
- Drag-and-drop batch upload for PDF, DOCX, TXT, CSV, and Markdown
- Document list, search, preview, bulk delete, and manual re-index
- Stats dashboard and user activity log
- ChromaDB semantic retrieval with adjustable temperature and `top_k`
- WebSocket status updates and chat rate limiting

## Quick Start

1. Start Ollama:

```powershell
ollama run llama3.2
```

2. Install backend dependencies, or use the included `rag_env` if it already works:

```powershell
cd backend
python -m venv ..\rag_env
..\rag_env\Scripts\pip install -r requirements.txt
```

3. Configure environment:

```powershell
Copy-Item .env.example .env
```

Change `SECRET_KEY`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD` before production use.

4. Run the API and frontend:

```powershell
..\rag_env\Scripts\python run.py
```

Open `http://localhost:8000`.

## Admin Login

Default development credentials:

- Username: `admin`
- Password: `admin123`

Change these in `backend/.env` for production.

## API Endpoints

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/status`
- `POST /api/chat`
- `POST /api/chat/stream`
- `GET /api/documents`
- `POST /api/documents/upload`
- `DELETE /api/documents/{id}`
- `POST /api/documents/delete`
- `POST /api/documents/reindex`
- `GET /api/documents/{id}/preview`
- `GET /api/stats`
- `GET /api/activity`
- `WS /api/ws/status`

Interactive docs are available at `http://localhost:8000/docs`.

## Document Storage

Uploaded files are persisted under:

- `data/txt`
- `data/pdf`
- `data/docx`
- `data/csv`
- `data/markdown`

The vector index is persisted in `chroma_db`.

## Re-indexing

Use the admin panel's **Re-index all** button, or call:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/documents/reindex -Headers @{ Authorization = "Bearer <token>" }
```

## Docker

Build and run the web app:

```powershell
docker build -t lumora-rag .
docker run --rm -p 8000:8000 -v ${PWD}\data:/app/data -v ${PWD}\chroma_db:/app/chroma_db lumora-rag
```

If Ollama runs on the host, configure `OLLAMA_BASE_URL` appropriately for your Docker environment.

## Production Notes

- Set a long random `SECRET_KEY`.
- Replace `CORS_ORIGINS=*` with the deployed frontend domain.
- Put the app behind HTTPS.
- Run Ollama on a reachable server and set `OLLAMA_BASE_URL`.
- Persist `data/` and `chroma_db/` volumes.
- Keep upload limits conservative and review documents before ingestion.
