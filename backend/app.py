"""FastAPI backend for the Product Documentation Assistant."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .azure_services import AzureServices
from .config import settings
from .ingest import ingest_file

app = FastAPI(
    title="Product Documentation Assistant API",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

azure = AzureServices()
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[Message] = Field(default_factory=list)


@app.get("/api/health")
def health() -> dict:
    """Return service and Search index status."""
    try:
        count = azure.search.get_document_count()
        search = "ok"
    except Exception as exc:
        count = 0
        search = f"error: {exc}"
    return {
        "status": "ok",
        "search": search,
        "indexed_chunks": count,
        "storage": "azure-blob" if azure.blob else "local-only",
    }


@app.get("/api/documents")
def list_documents() -> dict:
    """List uploaded source documents stored by the application."""
    files = []
    for path in sorted(UPLOAD_DIR.iterdir()):
        if path.is_file() and path.suffix.lower() in {".pdf", ".md", ".txt"}:
            files.append(
                {
                    "name": path.name,
                    "size": path.stat().st_size,
                    "url": f"{settings.public_app_url.rstrip('/')}/api/documents/{path.name}",
                }
            )
    try:
        indexed_chunks = azure.search.get_document_count()
    except Exception:
        indexed_chunks = 0
    return {"documents": files, "indexed_chunks": indexed_chunks}


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict:
    """Answer a question using the uploaded documentation."""
    history = [message.model_dump() for message in request.history]
    try:
        answer, citations = azure.ask_agent(request.question, history)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "answer": answer,
        "citations": citations,
        "mode": "api-key-agentic-rag",
    }


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...)) -> dict:
    """Upload a PDF/text document, store it, extract it and index its chunks."""
    original_name = Path(file.filename or "document").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".pdf", ".md", ".txt"}:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, Markdown and text files are supported.",
        )

    # Keep the filename safe and reasonably predictable.
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in original_name)
    destination = UPLOAD_DIR / safe_name
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Please upload a file smaller than 25 MB.")

    destination.write_bytes(data)

    try:
        azure.ensure_search_index()
        chunk_count = ingest_file(destination, azure)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Document processing failed: {exc}") from exc

    return {
        "message": "Document uploaded, processed and indexed successfully.",
        "file": safe_name,
        "chunks": chunk_count,
        "url": f"{settings.public_app_url.rstrip('/')}/api/documents/{safe_name}",
        "indexed_chunks": azure.search.get_document_count(),
    }


@app.get("/api/documents/{filename}")
def get_document(filename: str) -> FileResponse:
    """Serve an uploaded source document for local citation links."""
    safe_name = Path(filename).name
    path = UPLOAD_DIR / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document not found.")
    return FileResponse(path)
