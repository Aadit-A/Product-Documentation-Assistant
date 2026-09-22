"""Document ingestion pipeline for Blob Storage, Content Understanding and Azure AI Search."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from azure.ai.contentunderstanding import ContentUnderstandingClient, to_llm_input
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential

from .azure_services import AzureServices
from .config import settings


SUPPORTED_TEXT = {".txt", ".md"}
SUPPORTED_DOCUMENTS = {".pdf"}


def analyze_pdf(path: Path) -> str:
    """Analyze a PDF with Azure Content Understanding and return RAG-ready markdown."""
    credential = (
        AzureKeyCredential(settings.content_understanding_api_key)
        if settings.content_understanding_api_key
        else DefaultAzureCredential(exclude_interactive_browser_credential=False)
    )
    client = ContentUnderstandingClient(
        endpoint=settings.content_understanding_endpoint,
        credential=credential,
        api_version="2025-11-01",
    )
    with path.open("rb") as file:
        poller = client.begin_analyze_binary(
            analyzer_id="prebuilt-documentSearch",
            binary_input=file.read(),
        )
    result = poller.result()
    return to_llm_input(result)


def read_document(path: Path) -> str:
    """Read a supported document and return normalized text suitable for chunking."""
    if path.suffix.lower() in SUPPORTED_TEXT:
        return path.read_text(encoding="utf-8")
    if path.suffix.lower() in SUPPORTED_DOCUMENTS:
        return analyze_pdf(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def page_chunks(text: str, chunk_size: int, overlap: int) -> Iterable[tuple[int, str]]:
    """Yield size-limited chunks while preserving Content Understanding page markers when available."""
    pages = re.split(r"<!--\s*InputPageNumber:\s*(\d+)\s*-->", text)
    if len(pages) == 1:
        pages = ["1", text]
    for index in range(1, len(pages), 2):
        page = int(pages[index])
        body = re.sub(r"\n{3,}", "\n\n", pages[index + 1]).strip()
        if not body:
            continue
        start = 0
        while start < len(body):
            end = min(start + chunk_size, len(body))
            piece = body[start:end].strip()
            if piece:
                yield page, piece
            if end >= len(body):
                break
            start = max(end - overlap, start + 1)


def ingest_file(path: Path, azure: AzureServices) -> int:
    """Process one document, create embeddings, and upload all chunks to Azure AI Search."""
    text = read_document(path)
    version_match = re.search(r"(?:v|version[ _-]*)(\d+(?:\.\d+)*)", path.stem, re.I)
    version = version_match.group(1) if version_match else "unknown"
    category = path.parent.name if path.parent.name != "data" else "general"
    source_url = azure.upload_blob(path.name, path.read_bytes())
    chunks = []
    for number, (page, content) in enumerate(
        page_chunks(text, settings.chunk_size, settings.chunk_overlap)
    ):
        chunk_id = f"{path.stem.lower().replace(' ', '-')}-{page}-{number}"
        chunks.append(
            {
                "id": chunk_id[:128],
                "content": content,
                "title": path.name,
                "section": "Product Documentation",
                "page": page,
                "version": version,
                "category": category,
                "source_url": source_url,
            }
        )
    azure.upsert_chunks(chunks)
    return len(chunks)


def ingest_directory(directory: Path) -> int:
    """Create the index and ingest every supported document under a directory."""
    azure = AzureServices()
    azure.ensure_search_index()
    total = 0
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_TEXT | SUPPORTED_DOCUMENTS:
            total += ingest_file(path, azure)
    return total


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "data"
    print(f"Indexed {ingest_directory(root)} document chunks.")
