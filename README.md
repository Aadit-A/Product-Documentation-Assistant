# DocuMind - Product Documentation Assistant

An Azure-backed RAG application that lets users upload product documentation and ask grounded questions about it. The current implementation uses FastAPI, React/Vite, Azure OpenAI, Azure AI Search, Azure AI Document Intelligence, and optional Azure Blob Storage.

## What the application does

```text
PDF upload
   ↓
FastAPI receives and stores the PDF
   ↓
Azure Blob Storage stores the original (when configured)
   ↓
Azure AI Document Intelligence extracts page-aware content
   ↓
Text is chunked
   ↓
Azure OpenAI creates embeddings
   ↓
Azure AI Search stores keyword + vector representations
   ↓
User asks a question
   ↓
Azure OpenAI agent calls the Search tool
   ↓
Azure AI Search retrieves relevant chunks
   ↓
Azure OpenAI generates a grounded answer
   ↓
Sources are returned to the frontend
```

## Authentication model

This version intentionally does **not** use:

- Azure CLI
- `az login`
- `DefaultAzureCredential`
- Microsoft login browser popups
- `AIProjectClient`
- Foundry Agent Service managed-agent authentication

It uses API keys/connection strings for local development:

- Azure OpenAI API key
- Azure AI Search admin/query API key
- Azure AI Document Intelligence API key
- Azure Storage connection string

The agent itself is implemented by the FastAPI application using Azure OpenAI Responses API tool/function calling. It searches Azure AI Search with keyword and vector retrieval before generating an answer and citations.

## Project structure

```text
product-doc-assistant/
├── .env                         # local credentials; never commit
├── .env.example                 # configuration template
├── .gitignore
├── README.md
├── data/
│   ├── sample_product_manual_v1.md
│   └── uploads/
├── backend/
│   ├── __init__.py
│   ├── app.py
│   ├── azure_services.py
│   ├── config.py
│   ├── ingest.py
│   └── requirements.txt
└── frontend/
    ├── .env.example
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.jsx
        ├── main.jsx
        └── styles.css
```

## 1. Configure the environment

Copy `.env.example` to `.env` and fill in the Azure resource values. The required settings are:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_KEY`
- `AZURE_OPENAI_CHAT_DEPLOYMENT`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_API_KEY`
- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`
- `AZURE_DOCUMENT_INTELLIGENCE_KEY`

The embedding deployment must produce **1536 dimensions** for the supplied Search schema. `text-embedding-3-small` does this by default.

`AZURE_STORAGE_CONNECTION_STRING` is required. Uploaded documents are written to Azure Blob Storage and are never persisted in the local project. The FastAPI document endpoint streams source files from Azure for citations. Do not commit `.env` to Git, and rotate any credentials that have been exposed.

## 2. Backend

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start FastAPI from the project root:

```powershell
cd ..
python -m uvicorn backend.app:app --reload --port 8000
```

Health check:

```text
http://localhost:8000/api/health
```

## 3. Frontend

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## 4. Normal workflow

1. Open the frontend.
2. Drop a PDF product manual into the upload area. The UI accepts PDFs up to 25 MB.
3. FastAPI stores the file in Azure Blob Storage; it does not write the upload to local disk.
4. Document Intelligence extracts page-aware PDF text using `prebuilt-layout`.
5. The backend creates chunks and embeddings.
6. Chunks are indexed into Azure AI Search.
7. The UI shows the indexed chunk count.
8. Ask a product question.
9. The AI agent searches the documentation and answers from retrieved evidence.
10. Source links point back to the uploaded document served by FastAPI.

Markdown and plain-text files are also supported by the backend upload endpoint and batch ingestion command, even though the current UI is intentionally limited to PDFs.

## 5. API endpoints

- `GET /api/health` — backend/Search status
- `GET /api/documents` — uploaded documents and indexed chunk count
- `POST /api/documents` — upload and index a PDF, Markdown, or text file; rejects files over 25 MB
- `GET /api/documents/{filename}` — open an uploaded source document
- `POST /api/chat` — ask a grounded question

## 6. Batch ingestion

You normally do **not** need to run a separate ingestion command. Uploading a document through the frontend calls `/api/documents`, which creates the Search index if needed and performs the complete ingestion flow.

The older `backend/ingest.py` command is still available for batch ingestion of source files already placed in `data/`. It reads those source files locally, then sends their contents to Azure; web uploads do not use this local-source path.

```powershell
python -m backend.ingest
```

## 7. Troubleshooting

### Microsoft login page appears

This project should not invoke Azure CLI or `DefaultAzureCredential`. Check that you are running the new `backend/azure_services.py` and `backend/ingest.py` from this package.

### Upload says Document Intelligence authentication failed

Check:

```env
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=...
AZURE_DOCUMENT_INTELLIGENCE_KEY=...
```

### Search returns zero chunks

Check the upload response. A successful upload returns a `chunks` value. Also open `/api/health` and confirm `indexed_chunks` is greater than zero. The Search index name defaults to `product-docs` and can be changed with `AZURE_SEARCH_INDEX_NAME`.

### Frontend cannot connect

Start FastAPI first on port 8000, then Vite on port 5173. `frontend/.env` can override the backend URL:

```env
VITE_API_URL=http://localhost:8000
```

## 8. Notes for production

This is a local-development reference implementation. Before deploying it, add authentication and authorization, validate document ownership, move ingestion to a background job, add request and upload rate limits, and protect uploaded-document URLs. Keep all Azure credentials on the backend.
