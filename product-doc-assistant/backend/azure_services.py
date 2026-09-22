"""Azure service clients and the shared RAG/agent orchestration layer."""

from __future__ import annotations

from typing import Any

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AISearchIndexResource,
    AzureAISearchQueryType,
    AzureAISearchTool,
    AzureAISearchToolResource,
    PromptAgentDefinition,
)
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.storage.blob import BlobServiceClient

from .config import settings


class AzureServices:
    """Create and expose the Azure clients used by the application."""

    def __init__(self) -> None:
        """Initialize credential-backed Azure clients and the Foundry OpenAI client."""
        self.credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
        self.project = AIProjectClient(
            endpoint=settings.foundry_project_endpoint,
            credential=self.credential,
        )
        self.openai = self.project.get_openai_client()
        search_credential = AzureKeyCredential(settings.search_api_key) if settings.search_api_key else self.credential
        self.search_index = SearchIndexClient(settings.search_endpoint, search_credential)
        self.search = SearchClient(
            settings.search_endpoint,
            settings.search_index_name,
            search_credential,
        )
        self.blob = (
            BlobServiceClient.from_connection_string(settings.storage_connection_string)
            if settings.storage_connection_string
            else None
        )
        self._agent_version: str | None = None

    def ensure_search_index(self) -> None:
        """Create or replace the vector-enabled Azure AI Search index used by the assistant."""
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SearchableField(name="section", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="page", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
            SimpleField(name="version", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="category", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="source_url", type=SearchFieldDataType.String, retrievable=True),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=1536,
                vector_search_profile_name="product-vector-profile",
            ),
        ]
        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="product-hnsw")],
            profiles=[VectorSearchProfile(name="product-vector-profile", algorithm_configuration_name="product-hnsw")],
        )
        index = SearchIndex(
            name=settings.search_index_name,
            fields=fields,
            vector_search=vector_search,
        )
        self.search_index.create_or_update_index(index)

    def embed(self, text: str) -> list[float]:
        """Generate an embedding vector with the configured Foundry embedding deployment."""
        response = self.openai.embeddings.create(
            model=settings.embedding_model_deployment,
            input=text,
        )
        return response.data[0].embedding

    def upload_blob(self, file_name: str, data: bytes) -> str:
        """Upload a document to Blob Storage and return its application citation URL."""
        if not self.blob:
            return f"{settings.public_app_url.rstrip('/')}/api/documents/{file_name}"
        container = self.blob.get_container_client(settings.storage_container)
        try:
            container.create_container()
        except Exception:
            pass
        blob = container.get_blob_client(file_name)
        blob.upload_blob(data, overwrite=True)
        return f"{settings.public_app_url.rstrip('/')}/api/documents/{file_name}"

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Embed and upload document chunks into Azure AI Search in one batch."""
        payload = []
        for chunk in chunks:
            payload.append({**chunk, "content_vector": self.embed(chunk["content"])})
        for start in range(0, len(payload), 500):
            self.search.upload_documents(documents=payload[start : start + 500])

    def create_agent(self) -> str:
        """Create a Foundry prompt agent connected to the configured Azure AI Search index."""
        connection = self.project.connections.get(settings.search_connection_name)
        definition = PromptAgentDefinition(
            model=settings.foundry_model_deployment,
            instructions=(
                "You are a Product Documentation Assistant. "
                "Use the Azure AI Search tool as the source of truth. "
                "Never invent specifications, procedures, compatibility, or limits. "
                "If the documentation does not provide enough evidence, say so clearly. "
                "Always cite retrieved sources. Explain technical procedures as numbered steps when appropriate."
            ),
            tools=[
                AzureAISearchTool(
                    azure_ai_search=AzureAISearchToolResource(
                        indexes=[
                            AISearchIndexResource(
                                project_connection_id=connection.id,
                                index_name=settings.search_index_name,
                                query_type=AzureAISearchQueryType.VECTOR_SIMPLE_HYBRID,
                                top_k=settings.top_k,
                            )
                        ]
                    )
                )
            ],
        )
        agent = self.project.agents.create_version(
            agent_name=settings.agent_name,
            definition=definition,
            description="Grounded product documentation assistant",
        )
        self._agent_version = agent.version
        return agent.version

    def ask_agent(self, question: str, history: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
        """Ask the Foundry agent a question and extract inline URL citations from its response."""
        if not self._agent_version:
            self.create_agent()
        context = "\n".join(f"{m['role'].title()}: {m['content']}" for m in history[-6:])
        prompt = f"Conversation context:\n{context}\n\nCurrent user question:\n{question}" if context else question
        response = self.openai.responses.create(
            input=prompt,
            extra_body={
                "agent_reference": {
                    "name": settings.agent_name,
                    "type": "agent_reference",
                }
            },
        )
        citations: list[dict[str, str]] = []
        for item in getattr(response, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                for annotation in getattr(content, "annotations", []) or []:
                    url = getattr(annotation, "url", None)
                    title = getattr(annotation, "title", None)
                    if url:
                        citations.append({"title": title or "Source", "url": url})
        return response.output_text, citations

    def direct_rag(self, question: str, history: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
        """Fallback to direct hybrid/vector retrieval plus the Foundry model when agent setup is unavailable."""
        vector = self.embed(question)
        results = self.search.search(
            search_text=question,
            vector_queries=[
                VectorizedQuery(
                    vector=vector,
                    k_nearest_neighbors=settings.top_k,
                    fields="content_vector",
                )
            ],
            top=settings.top_k,
            select=["content", "title", "page", "section", "version", "category", "source_url"],
        )
        sources = []
        context_parts = []
        for result in results:
            context_parts.append(
                f"SOURCE: {result.get('title')} | page={result.get('page')} | "
                f"section={result.get('section')} | version={result.get('version')}\n{result.get('content')}"
            )
            sources.append({
                "title": f"{result.get('title')} — p.{result.get('page')}",
                "url": result.get("source_url", ""),
            })
        context = "\n\n---\n\n".join(context_parts)
        if not context:
            return "I couldn't find relevant information in the indexed product documentation.", []
        history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-6:])
        prompt = f"""
You are a product documentation assistant.
Answer ONLY from the supplied documentation context.
If the context does not contain enough evidence, say that the documentation does not provide the answer.
Never invent specifications or procedures.
Be concise and helpful. Cite sources in a Sources section using [n] markers.

Conversation:
{history_text}

Question:
{question}

Documentation context:
{context}
"""
        response = self.openai.responses.create(
            model=settings.foundry_model_deployment,
            input=prompt,
        )
        return response.output_text, sources
