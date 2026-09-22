"""Document ingestion pipeline using Azure AI Document Intelligence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential

from .azure_services import AzureServices
from .config import settings


SUPPORTED_TEXT = {".txt", ".md"}
SUPPORTED_DOCUMENTS = {".pdf"}


def analyze_pdf(path: Path) -> list[tuple[int, str]]:
    """
    Analyze a PDF using Azure AI Document Intelligence
    and return page-numbered text.
    """

    if not settings.document_intelligence_endpoint:
        raise ValueError(
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT is not configured."
        )

    if not settings.document_intelligence_key:
        raise ValueError(
            "AZURE_DOCUMENT_INTELLIGENCE_KEY is not configured."
        )

    client = DocumentIntelligenceClient(
        endpoint=settings.document_intelligence_endpoint,
        credential=AzureKeyCredential(
            settings.document_intelligence_key
        ),
    )

    with path.open("rb") as file:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            body=file,
        )

    result = poller.result()

    pages: list[tuple[int, str]] = []

    for page in result.pages:
        page_number = page.page_number

        lines = []

        if page.lines:
            for line in page.lines:
                if line.content:
                    lines.append(line.content)

        page_text = "\n".join(lines).strip()

        if page_text:
            pages.append((page_number, page_text))

    return pages


def read_document(path: Path) -> list[tuple[int, str]]:
    """
    Read a supported document.

    Returns:
        List of (page_number, text).
    """

    suffix = path.suffix.lower()

    if suffix in SUPPORTED_TEXT:
        text = path.read_text(encoding="utf-8")
        return [(1, text)]

    if suffix in SUPPORTED_DOCUMENTS:
        return analyze_pdf(path)

    raise ValueError(f"Unsupported file type: {path.suffix}")


def page_chunks(
    pages: list[tuple[int, str]],
    chunk_size: int,
    overlap: int,
) -> Iterable[tuple[int, str]]:
    """
    Split each page into overlapping chunks while preserving
    the original page number.
    """

    for page_number, body in pages:

        body = re.sub(r"\n{3,}", "\n\n", body).strip()

        if not body:
            continue

        start = 0

        while start < len(body):

            end = min(
                start + chunk_size,
                len(body)
            )

            piece = body[start:end].strip()

            if piece:
                yield page_number, piece

            if end >= len(body):
                break

            start = max(
                end - overlap,
                start + 1
            )


def ingest_file(path: Path, azure: AzureServices) -> int:
    """
    Process one document:

    PDF
      ↓
    Document Intelligence
      ↓
    page-aware chunks
      ↓
    embeddings
      ↓
    Azure AI Search
    """

    pages = read_document(path)

    version_match = re.search(
        r"(?:v|version[ _-]*)(\d+(?:\.\d+)*)",
        path.stem,
        re.I,
    )

    version = (
        version_match.group(1)
        if version_match
        else "unknown"
    )

    category = (
        path.parent.name
        if path.parent.name != "data"
        else "general"
    )

    # Store original document in Azure Blob Storage
    source_url = azure.upload_blob(
        path.name,
        path.read_bytes(),
    )

    chunks = []

    for number, (page, content) in enumerate(
        page_chunks(
            pages,
            settings.chunk_size,
            settings.chunk_overlap,
        )
    ):

        chunk_id = (
            f"{path.stem.lower().replace(' ', '-')}"
            f"-{page}-{number}"
        )

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

    if not chunks:
        raise ValueError(
            "No text could be extracted from the document."
        )

    azure.upsert_chunks(chunks)

    return len(chunks)


def ingest_directory(directory: Path) -> int:
    """
    Create the Azure AI Search index and ingest
    every supported document.
    """

    azure = AzureServices()

    azure.ensure_search_index()

    total = 0

    for path in sorted(directory.rglob("*")):

        if (
            path.is_file()
            and path.suffix.lower()
            in SUPPORTED_TEXT | SUPPORTED_DOCUMENTS
        ):
            total += ingest_file(
                path,
                azure,
            )

    return total


if __name__ == "__main__":

    root = (
        Path(__file__).resolve().parents[1]
        / "data"
    )

    print(
        f"Indexed {ingest_directory(root)} "
        "document chunks."
    )