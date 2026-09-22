"""FastAPI application for the Product Documentation Assistant."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .azure_services import AzureServices
from .config import settings
from .ingest import ingest_file

app = FastAPI(title="Product Documentation Assistant", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

azure = AzureServices()
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class Message(BaseModel):
    """Represent one chat message sent between the browser and backend."""

    role: str
    content: str


class ChatRequest(BaseModel):
    """Represent a chat request with recent conversation history."""

    question: str = Field(min_length=1, max_length=4000)
    history: list[Message] = Field(default_factory=list)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Return a simple health response for the frontend and deployment probes."""
    return {"status": "ok"}


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict:
    """Answer a product question through the Foundry agent, with direct RAG as a safe fallback."""
    history = [message.model_dump() for message in request.history]
    try:
        azure.ensure_search_index()
        answer, citations = azure.ask_agent(request.question, history)
        mode = "foundry-agent"
    except Exception as agent_error:
        try:
            answer, citations = azure.direct_rag(request.question, history)
            mode = "direct-rag-fallback"
        except Exception as rag_error:
            raise HTTPException(
                status_code=503,
                detail=f"Azure AI is not configured or reachable. Agent: {agent_error}; RAG: {rag_error}",
            ) from rag_error
    return {"answer": answer, "citations": citations, "mode": mode}


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...)) -> dict:
    """Save an uploaded document, process it through the ingestion pipeline, and index its chunks."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".txt", ".md"}:
        raise HTTPException(status_code=400, detail="Only PDF, Markdown and text files are supported.")
    destination = UPLOAD_DIR / Path(file.filename).name
    with destination.open("wb") as output:
        shutil.copyfileobj(file.file, output)
    try:
        azure.ensure_search_index()
        count = ingest_file(destination, azure)
    except Exception as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {"message": "Document indexed successfully.", "chunks": count, "file": destination.name}


@app.get("/api/documents/{filename}")
def get_document(filename: str) -> FileResponse:
    """Serve an uploaded document so citation URLs can open the source file locally."""
    safe_name = Path(filename).name
    path = UPLOAD_DIR / safe_name
    if not path.exists():
        path = Path(__file__).resolve().parents[1] / "data" / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document not found.")
    return FileResponse(path)
