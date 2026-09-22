# DocuMind — Product Documentation Assistant

A compact, Azure-native RAG application that answers product questions from indexed documentation. It uses Microsoft Foundry, Foundry Agent Service, Azure AI Search, Azure Content Understanding, optional Blob Storage, FastAPI, and React.

## Architecture

```text
Documents → Blob Storage → Azure Content Understanding → chunking + embeddings
                                                        ↓
                                                   Azure AI Search
                                                        ↓
User → React → FastAPI → Foundry Agent → Azure AI Search → grounded answer + citations
                                  ↘ direct RAG fallback if Agent Service setup is unavailable
```

Microsoft's current Foundry documentation supports connecting a prompt agent directly to an Azure AI Search index and returning source citations. Azure AI Search supports vector/hybrid retrieval, and Content Understanding provides a prebuilt `prebuilt-documentSearch` analyzer for RAG-oriented document extraction. See the official links below.

- https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/ai-search
- https://learn.microsoft.com/en-us/azure/search/search-get-started-vector
- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/

## Project structure

```text
product-doc-assistant/
├── .env                         # local credentials/config; never commit
├── .env.example                 # safe configuration template
├── .gitignore
├── README.md
├── data/
│   └── sample_product_manual_v1.md
├── backend/
│   ├── __init__.py
│   ├── app.py
│   ├── azure_services.py
│   ├── config.py
│   ├── ingest.py
│   └── requirements.txt
├── frontend/
│   ├── package.json
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       └── styles.css
└── scripts/
```

## Azure setup

Create/configure:

1. A Microsoft Foundry project.
2. A chat model deployment; put its deployment name in `FOUNDRY_MODEL_DEPLOYMENT`.
3. An embedding deployment compatible with 1536-dimensional vectors; `text-embedding-3-small` is the default in `.env`.
4. An Azure AI Search service.
5. An Azure AI Search connection in the Foundry project. Put its **connection name** in `AZURE_SEARCH_CONNECTION_NAME`.
6. A Content Understanding-enabled Foundry/Azure AI resource. Put its endpoint and key in the corresponding variables, or use `DefaultAzureCredential` and leave the key empty.
7. Optional: an Azure Storage account and container if you want documents stored in Blob Storage.

For keyless local development, install Azure CLI and run:

```bash
az login
```

The application uses `DefaultAzureCredential` where possible. For Azure AI Search, you can use either an API key or Entra ID. For production, prefer Entra ID/RBAC and managed identity over hard-coded keys.

## Install and run

### Backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..
python -m backend.ingest
uvicorn backend.app:app --reload --port 8000
```

The first ingestion creates the `product-docs` index and indexes the sample manual.

### Frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal, normally `http://localhost:5173`.

## Uploading documents

Use **Upload documentation** in the UI. PDFs go through Azure Content Understanding's `prebuilt-documentSearch` analyzer, which produces RAG-ready structured markdown. Markdown/text files are ingested directly.

Supported formats in this compact implementation:

- PDF
- Markdown
- TXT

## Important Foundry Search connection requirement

The Foundry Agent Service path requires an Azure AI Search project connection. The current Microsoft documentation describes configuring an Azure AI Search tool with a project connection ID and an index name. The application reads `AZURE_SEARCH_CONNECTION_NAME` and resolves the connection through the Foundry project SDK.

If that agent configuration is temporarily unavailable, `/api/chat` automatically falls back to direct vector/hybrid retrieval plus the configured Foundry model. This keeps local development usable while preserving the same RAG data path.

## Demo questions

After indexing the sample manual, try:

1. `What is the maximum supported storage?`
2. `How do I reset the device?`
3. `What does error E104 mean?`
4. `My Internet light is red. What should I do?`
5. `Does the documentation say the device supports Wi-Fi 7?`

The final question is intentionally designed to test grounded behavior.

## Security

- `.env` is ignored by Git.
- Do not place Azure keys in React code.
- The frontend talks only to FastAPI.
- Use Entra ID/managed identity and RBAC for deployed environments.
- Keep search credentials server-side.
- Treat uploaded documentation as untrusted input and keep the agent instructed to use retrieved documentation as evidence rather than as executable instructions.

## AI-103 concepts demonstrated

- Generative AI
- Prompt engineering
- RAG
- Embeddings
- Vector search
- Hybrid search
- AI agents
- Tool use
- Document understanding
- OCR/layout extraction for PDFs
- Grounding and citations
- Responsible AI / hallucination control
- Evaluation-ready retrieval pipeline

## Notes

The application intentionally keeps the repository small. Production hardening can add authentication, persistent conversation storage, background ingestion jobs, richer evaluation, telemetry, and role-based document access without changing the core RAG architecture.
