"""API-key based Azure services and the application-managed RAG agent."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
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
from azure.search.documents.models import VectorizedQuery
from azure.storage.blob import BlobServiceClient, ContentSettings

from .config import settings


class AzureServices:
    """Create Azure clients using API keys/connection strings only."""

    def __init__(self) -> None:
        if not settings.azure_openai_endpoint or not settings.azure_openai_key:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY must be configured in .env."
            )
        if not settings.search_endpoint or not settings.search_api_key:
            raise ValueError(
                "AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY must be configured in .env."
            )

        # Azure OpenAI v1 endpoint. No Azure CLI or DefaultAzureCredential is used.
        self.openai = OpenAI(
            api_key=settings.azure_openai_key,
            base_url=f"{settings.azure_openai_endpoint.rstrip('/')}/openai/v1/",
        )

        search_credential = AzureKeyCredential(settings.search_api_key)
        self.search_index = SearchIndexClient(
            endpoint=settings.search_endpoint,
            credential=search_credential,
        )
        self.search = SearchClient(
            endpoint=settings.search_endpoint,
            index_name=settings.search_index_name,
            credential=search_credential,
        )

        self.blob = (
            BlobServiceClient.from_connection_string(settings.storage_connection_string)
            if settings.storage_connection_string
            else None
        )

    def ensure_search_index(self) -> None:
        """Create/update the vector-enabled Azure AI Search index."""
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(
                name="content",
                type=SearchFieldDataType.String,
                analyzer_name="en.microsoft",
            ),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SearchableField(
                name="section",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SimpleField(
                name="page",
                type=SearchFieldDataType.Int32,
                filterable=True,
                sortable=True,
            ),
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
            profiles=[
                VectorSearchProfile(
                    name="product-vector-profile",
                    algorithm_configuration_name="product-hnsw",
                )
            ],
        )

        index = SearchIndex(
            name=settings.search_index_name,
            fields=fields,
            vector_search=vector_search,
        )
        self.search_index.create_or_update_index(index)

    def embed(self, text: str) -> list[float]:
        """Create a 1536-dimensional embedding using the configured deployment."""
        response = self.openai.embeddings.create(
            model=settings.azure_openai_embedding_deployment,
            input=text,
        )
        return response.data[0].embedding

    def upload_blob(self, file_name: str, data: bytes) -> str:
        """Persist an uploaded document in Azure Blob Storage when configured."""
        if not self.blob:
            return f"{settings.public_app_url.rstrip('/')}/api/documents/{file_name}"

        container = self.blob.get_container_client(settings.storage_container)
        try:
            container.create_container()
        except Exception:
            pass

        blob = container.get_blob_client(file_name)
        content_type = "application/pdf" if file_name.lower().endswith(".pdf") else "text/plain"
        blob.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        # Keep citations on the FastAPI URL so they work even when the Blob container is private.
        return f"{settings.public_app_url.rstrip('/')}/api/documents/{file_name}"

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Embed document chunks and upload them to Azure AI Search."""
        if not chunks:
            raise ValueError("No readable content was extracted from the document.")

        payload = []
        for chunk in chunks:
            payload.append({**chunk, "content_vector": self.embed(chunk["content"])})

        for start in range(0, len(payload), 500):
            self.search.upload_documents(documents=payload[start : start + 500])

    def search_product_documentation(self, query: str) -> dict[str, Any]:
        """Run keyword + vector hybrid retrieval against the product documentation."""
        vector = self.embed(query)
        results = self.search.search(
            search_text=query,
            vector_queries=[
                VectorizedQuery(
                    vector=vector,
                    k_nearest_neighbors=settings.search_top_k,
                    fields="content_vector",
                )
            ],
            top=settings.search_top_k,
            select=[
                "content",
                "title",
                "page",
                "section",
                "version",
                "category",
                "source_url",
            ],
        )

        documents = []
        for number, result in enumerate(results, start=1):
            documents.append(
                {
                    "id": number,
                    "title": result.get("title", "Documentation"),
                    "page": result.get("page", 0),
                    "section": result.get("section", ""),
                    "version": result.get("version", ""),
                    "category": result.get("category", ""),
                    "source_url": result.get("source_url", ""),
                    "content": result.get("content", ""),
                }
            )

        return {"query": query, "results": documents}

    def _tools(self) -> list[dict[str, Any]]:
        """Define the documentation search function available to the model."""
        return [
            {
                "type": "function",
                "name": "search_product_documentation",
                "description": (
                    "Search the uploaded product documentation. Use this for product-specific "
                    "questions about features, specifications, setup, configuration, compatibility, "
                    "troubleshooting, limits, or procedures."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "A focused search query for the documentation.",
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        ]

    @staticmethod
    def _instructions() -> str:
        """Return the grounding and citation rules for the agent."""
        return """
You are a Product Documentation Assistant.

Your source of truth is the uploaded product documentation available through the
search_product_documentation tool.

Rules:
- For every product-specific question, use the search tool before answering.
- Never invent product specifications, procedures, compatibility, limits, or features.
- If the retrieved evidence is insufficient, say that the uploaded documentation does not
  provide enough evidence.
- If the user has uploaded multiple documents/versions, use the evidence relevant to the question.
- For procedures, use numbered steps.
- Cite retrieved evidence using [1], [2], etc.
- End with a short Sources section containing only sources actually returned by the search tool.
- If the user asks a follow-up, use conversation context but verify product facts against the documents.
"""

    def ask_agent(
        self,
        question: str,
        history: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]]]:
        """Run an application-managed tool-calling RAG agent."""
        if self.search.get_document_count() == 0:
            return (
                "Please upload a product PDF first. I don't have any indexed documentation to use yet.",
                [],
            )

        input_items: list[dict[str, Any]] = [
            {"role": m["role"], "content": m["content"]}
            for m in history[-8:]
        ]
        input_items.append({"role": "user", "content": question})

        citations: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        response = self.openai.responses.create(
            model=settings.azure_openai_chat_deployment,
            instructions=self._instructions(),
            input=input_items,
            tools=self._tools(),
        )

        for _ in range(4):
            calls = [item for item in response.output if getattr(item, "type", None) == "function_call"]
            if not calls:
                return response.output_text, citations

            outputs = []
            for call in calls:
                if call.name != "search_product_documentation":
                    continue
                try:
                    args = json.loads(call.arguments)
                    result = self.search_product_documentation(args["query"])
                    for doc in result["results"]:
                        url = doc.get("source_url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            citations.append(
                                {
                                    "title": f"{doc['title']} — p.{doc['page']}",
                                    "url": url,
                                }
                            )
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(result, ensure_ascii=False),
                        }
                    )
                except Exception as exc:
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps({"error": str(exc)}),
                        }
                    )

            input_items = input_items + list(response.output) + outputs
            response = self.openai.responses.create(
                model=settings.azure_openai_chat_deployment,
                instructions=self._instructions(),
                input=input_items,
                tools=self._tools(),
            )

        return (
            "I couldn't complete the documentation lookup. Please try the question again.",
            citations,
        )
