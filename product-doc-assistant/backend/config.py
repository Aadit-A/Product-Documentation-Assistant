"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Store Azure and application configuration in one immutable object."""

    foundry_project_endpoint: str = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
    foundry_model_deployment: str = os.getenv("FOUNDRY_MODEL_DEPLOYMENT", "")
    embedding_model_deployment: str = os.getenv("EMBEDDING_MODEL_DEPLOYMENT", "text-embedding-3-small")
    search_endpoint: str = os.getenv("AZURE_SEARCH_ENDPOINT", "")
    search_api_key: str = os.getenv("AZURE_SEARCH_API_KEY", "")
    search_index_name: str = os.getenv("AZURE_SEARCH_INDEX_NAME", "product-docs")
    search_connection_name: str = os.getenv("AZURE_SEARCH_CONNECTION_NAME", "")
    content_understanding_endpoint: str = os.getenv("CONTENT_UNDERSTANDING_ENDPOINT", "")
    content_understanding_api_key: str = os.getenv("CONTENT_UNDERSTANDING_API_KEY", "")
    storage_connection_string: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    storage_container: str = os.getenv("AZURE_STORAGE_CONTAINER", "product-documents")
    public_app_url: str = os.getenv("PUBLIC_APP_URL", "http://localhost:8000")
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    agent_name: str = os.getenv("FOUNDRY_AGENT_NAME", "product-documentation-agent")
    top_k: int = int(os.getenv("SEARCH_TOP_K", "5"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "1400"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "180"))


settings = Settings()
