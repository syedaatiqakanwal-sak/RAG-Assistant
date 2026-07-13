@echo off
cd /d "%~dp0backend"
..\rag_env\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001
