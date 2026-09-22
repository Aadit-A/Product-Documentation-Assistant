"""Environment-backed application configuration."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """All runtime settings for the Product Documentation Assistant."""

    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_key: str = os.getenv("AZURE_OPENAI_KEY", "")
    azure_openai_chat_deployment: str = os.getenv(
        "AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4.1-mini"
    )
    azure_openai_embedding_deployment: str = os.getenv(
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"
    )

    search_endpoint: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    search_api_key: str = os.getenv("AZURE_SEARCH_API_KEY", "")
    search_index_name: str = os.getenv("AZURE_SEARCH_INDEX_NAME", "product-docs")

    document_intelligence_endpoint: str = os.getenv(
    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", ""
    )

    document_intelligence_key: str = os.getenv(
        "AZURE_DOCUMENT_INTELLIGENCE_KEY", ""
    )

    storage_connection_string: str = os.getenv(
        "AZURE_STORAGE_CONNECTION_STRING", ""
    )
    storage_container: str = os.getenv(
        "AZURE_STORAGE_CONTAINER", "product-documents"
    )

    public_app_url: str = os.getenv("PUBLIC_APP_URL", "http://localhost:8000")
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

    search_top_k: int = int(os.getenv("SEARCH_TOP_K", "5"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "1400"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "180"))


settings = Settings()
