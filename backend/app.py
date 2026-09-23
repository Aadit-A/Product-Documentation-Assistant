"""FastAPI backend for the Product Documentation Assistant."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .azure_services import AzureServices
from .config import settings
from .ingest import ingest_document

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
        "storage": "azure-blob" if azure.blob else "not-configured",
    }


@app.get("/api/documents")
def list_documents() -> dict:
    """List uploaded source documents stored by the application."""
    try:
        files = azure.list_blobs()
        indexed_chunks = azure.search.get_document_count()
    except Exception:
        files = []
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
async def upload_document(
    file: bytes = File(...),
    x_file_name: str = Header(default="document.pdf"),
) -> dict:
    """Upload a PDF/text document, store it, extract it and index its chunks."""
    original_name = Path(x_file_name or "document.pdf").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".pdf", ".md", ".txt"}:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, Markdown and text files are supported.",
        )

    # Keep the filename safe and reasonably predictable.
    safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in original_name)
    data = file
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Please upload a file smaller than 25 MB.")

    try:
        azure.ensure_search_index()
        chunk_count = ingest_document(safe_name, data, azure)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document processing failed: {exc}") from exc

    return {
        "message": "Document uploaded, processed and indexed successfully.",
        "file": safe_name,
        "chunks": chunk_count,
        "url": f"{settings.public_app_url.rstrip('/')}/api/documents/{safe_name}",
        "indexed_chunks": azure.search.get_document_count(),
    }


@app.get("/api/documents/{filename}")
def get_document(filename: str) -> Response:
    """Stream an uploaded source document from Azure Blob Storage."""
    safe_name = Path(filename).name
    try:
        data, content_type = azure.download_blob(safe_name)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    return Response(content=data, media_type=content_type)


@app.delete("/api/documents/{filename}")
def delete_document(filename: str) -> dict:
    """Delete one Azure Blob document and its indexed Search chunks."""
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid document name.")

    try:
        deleted_chunks = azure.delete_document(safe_name)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Azure temporarily closed the delete connection. "
                "Please retry the deletion. Details: " + str(exc)
            ),
        ) from exc

    return {
        "message": "Document and indexed chunks deleted successfully.",
        "file": safe_name,
        "deleted_chunks": deleted_chunks,
    }
