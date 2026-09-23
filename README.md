# DocuMind - Product Documentation Assistant

DocuMind is an Azure-backed retrieval-augmented generation (RAG) application for asking questions about product documentation. Users upload a product manual in the React web application, the FastAPI backend extracts and indexes it in Azure, and Azure OpenAI answers questions using retrieved documentation as evidence.

The project is designed for local development with Azure API keys and connection strings. It does not use Azure CLI login, `DefaultAzureCredential`, Microsoft login popups, Foundry Agent Service, or local persistence of web-uploaded documents.

## What the application provides

- Upload a PDF product manual from the browser.
- Store uploaded source documents in Azure Blob Storage.
- Extract page-aware PDF text with Azure AI Document Intelligence.
- Split extracted content into overlapping chunks.
- Generate vector embeddings with Azure OpenAI.
- Store keyword fields and vectors in Azure AI Search.
- Ask questions through an application-managed Azure OpenAI tool-calling agent.
- Return grounded answers with links to source documents and page metadata.
- Show backend status, document names, and indexed chunk counts in the UI.

The web interface accepts PDF files up to 25 MB. The backend API and batch ingestion command also support `.md` and `.txt` files.

## Architecture

```text
Browser (React + Vite)
        |
        | POST /api/documents with PDF bytes
        v
FastAPI backend
        |
        | validate file and keep upload in memory
        | ensure Azure AI Search index exists
        |
        +--> Azure AI Document Intelligence
        |        prebuilt-layout PDF extraction
        |
        +--> Azure Blob Storage
        |        original source document
        |
        +--> Azure OpenAI embeddings
        |        batched chunk embeddings
        |
        +--> Azure AI Search
                 keyword fields + 1536-dimensional vectors

Browser question
        |
        v
FastAPI /api/chat
        |
        v
Azure OpenAI Responses API agent
        |
        | calls search_product_documentation(query)
        v
Azure AI Search hybrid retrieval
        |
        | relevant chunks and source metadata
        v
Azure OpenAI grounded answer
        |
        v
React chat with citations
```

### Document ingestion flow

1. The browser validates that the selected file is a PDF smaller than 25 MB.
2. The frontend sends the file as multipart form data to `POST /api/documents` and passes its filename in the `X-File-Name` header.
3. FastAPI validates the extension and size. It does not write the web upload to the project directory.
4. The backend creates the Search index if it does not already exist.
5. PDF bytes are sent to Azure AI Document Intelligence using `prebuilt-layout`. Extracted text keeps page numbers for citations.
6. The original bytes are uploaded to the configured Azure Blob Storage container.
7. Each page is split into chunks using `CHUNK_SIZE` and `CHUNK_OVERLAP`.
8. Azure OpenAI creates embeddings in batches of 64 chunks.
9. Chunks and embeddings are uploaded to Azure AI Search in batches of up to 500 documents.
10. The API returns the indexed chunk count. Source links use FastAPI, which streams the document from Blob Storage.

### Question-answering flow

1. The browser sends the question and up to the last eight chat messages to `POST /api/chat`.
2. The backend sends the question to Azure OpenAI through the Responses API.
3. The model can call `search_product_documentation`.
4. The function creates a question embedding and performs hybrid Azure AI Search retrieval using keyword and vector search.
5. Retrieved chunks are returned to the model as tool output.
6. The model answers from the retrieved evidence and includes source references.
7. The backend returns the answer and deduplicated citation URLs to React.

## Repository layout

```text
product-doc-assistant/
├── .env.example                 # local configuration template
├── .gitignore
├── README.md
├── data/
│   ├── sample_product_manual_v1.md
│   └── uploads/                  # ignored; not used by browser uploads
├── backend/
│   ├── __init__.py
│   ├── app.py                   # FastAPI routes and application startup
│   ├── azure_services.py        # Azure clients, Search, Blob, embeddings, agent
│   ├── config.py                # environment-backed settings
│   ├── ingest.py                # extraction, chunking, and ingestion pipeline
│   └── requirements.txt
└── frontend/
    ├── .env.example
    ├── index.html
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.jsx              # upload, status, chat, and citation UI
        ├── main.jsx
        └── styles.css
```

## Azure prerequisites

Create or obtain these Azure resources before starting:

1. **Azure OpenAI** with a chat deployment such as `gpt-4.1-mini` and an embedding deployment such as `text-embedding-3-small`. The embedding deployment must return 1536 dimensions to match the Search schema.
2. **Azure AI Search** with a service endpoint and admin/indexing API key. The application creates the vector-enabled index automatically when it does not exist.
3. **Azure AI Document Intelligence** with an endpoint and API key. It extracts PDFs with `prebuilt-layout`.
4. **Azure Blob Storage** with a connection string and container name. This is required because web-uploaded documents are stored in Azure and not in the local project.

The application uses API keys and a storage connection string for local development. For production, use managed identity/RBAC and a secret manager where possible.

## Configuration

From the repository root, copy the template:

```powershell
Copy-Item .env.example .env
```

Fill in the required values:

```env
AZURE_OPENAI_ENDPOINT=https://your-openai-resource.openai.azure.com
AZURE_OPENAI_KEY=your-openai-key
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4.1-mini
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small

AZURE_SEARCH_ENDPOINT=https://your-search-service.search.windows.net
AZURE_SEARCH_API_KEY=your-search-admin-key
AZURE_SEARCH_INDEX_NAME=product-docs

AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://your-document-intelligence.cognitiveservices.azure.com
AZURE_DOCUMENT_INTELLIGENCE_KEY=your-document-intelligence-key

AZURE_STORAGE_CONNECTION_STRING=your-storage-connection-string
AZURE_STORAGE_CONTAINER=product-documents
```

Other settings control local URLs and RAG behavior:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PUBLIC_APP_URL` | `http://localhost:8000` | Base URL used in citation links |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Allowed browser origin for CORS |
| `SEARCH_TOP_K` | `5` | Number of Search results per query |
| `CHUNK_SIZE` | `1400` | Approximate characters per chunk |
| `CHUNK_OVERLAP` | `180` | Overlap between chunks on a page |

Never commit `.env`. The repository ignores it, and credentials must remain server-side.

## Run locally

### Backend

From the repository root in PowerShell:

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app:app --reload --port 8000
```

The backend is available at `http://localhost:8000`. Interactive API documentation is available at `http://localhost:8000/docs`.

If PowerShell blocks activation for the current session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
backend\.venv\Scripts\Activate.ps1
```

### Frontend

Open a second terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The frontend uses `http://localhost:8000` by default. To use another backend, create `frontend/.env`:

```env
VITE_API_URL=http://localhost:8000
```

Start the backend before the frontend so the status indicator can connect.

### Production frontend build

```powershell
Set-Location frontend
npm run build
npm run preview
```

The output is written to `frontend/dist/`, which is ignored by Git.

## Use the application

1. Start the backend and frontend.
2. Open `http://localhost:5173`.
3. Drop a PDF into the upload area or choose a PDF file.
4. Wait for extraction, embedding, and Search indexing to finish.
5. Confirm that the knowledge base shows an indexed chunk count.
6. Ask a specific question about setup, features, specifications, limits, or troubleshooting.
7. Open returned citation links to inspect the source document.

Example questions:

- What are the main product features?
- What are the key specifications?
- How do I set up the product?
- What does error E104 mean?
- Does the documentation say the device supports Wi-Fi 7?

The assistant is instructed to say when the indexed documentation does not provide enough evidence. It should not be treated as a general-purpose assistant for facts outside the uploaded documentation.

## API reference

### `GET /api/health`

Returns backend status, Search connectivity, indexed chunk count, and storage mode.

```json
{
  "status": "ok",
  "search": "ok",
  "indexed_chunks": 12,
  "storage": "azure-blob"
}
```

### `GET /api/documents`

Lists PDF, Markdown, and text documents in the configured Blob Storage container and returns the current Search document count.

### `POST /api/documents`

Uploads and indexes a document. The request is multipart form data with a `file` field and should include the original filename in `X-File-Name`.

Supported extensions are `.pdf`, `.md`, and `.txt`. The maximum size is 25 MB.

```powershell
curl.exe -X POST http://localhost:8000/api/documents `
  -H "X-File-Name: sample_product_manual_v1.md" `
  -F "file=@data/sample_product_manual_v1.md"
```

### `GET /api/documents/{filename}`

Streams a source document from Azure Blob Storage through FastAPI. The backend reduces the requested name to its filename component before accessing Blob Storage.

### `POST /api/chat`

Accepts a question and optional conversation history:

```json
{
  "question": "How do I reset the device?",
  "history": [
    {"role": "user", "content": "What is the device?"},
    {"role": "assistant", "content": "..."}
  ]
}
```

The response includes `answer`, `citations`, and the active `mode`.

## Batch ingestion

Browser uploads use the Azure-backed web path. For local development or repeatable seed data, `backend/ingest.py` can read supported files from `data/` and send their contents to Azure:

```powershell
python -m backend.ingest
```

The command creates the Search index if necessary and ingests every `.pdf`, `.md`, and `.txt` file under `data/`. Local files are batch inputs only; the source document is uploaded to Blob Storage and indexed content is stored in Azure.

## Performance notes

PDF ingestion is synchronous from the browser's perspective: the upload request completes only after extraction, embedding, and indexing finish. The implementation reduces processing time by:

- Sending PDF bytes directly to Azure services without writing a web upload to local disk.
- Creating the Search index only when it is missing.
- Generating embeddings in batches of 64 chunks.
- Uploading Search documents in batches of up to 500.

For larger production workloads, move ingestion to a background queue and return a job ID immediately. Azure Functions, Azure Container Apps jobs, or a queue-backed worker are suitable next steps.

## Troubleshooting

### Backend exits during startup

`AzureServices` validates required credentials at startup. Check that all required variables in `.env` are populated, especially `AZURE_STORAGE_CONNECTION_STRING`.

### Upload fails with a Document Intelligence error

Check the endpoint and key:

```env
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=...
AZURE_DOCUMENT_INTELLIGENCE_KEY=...
```

Also confirm that the resource is available and that the uploaded file is a readable PDF.

### Upload succeeds but no chunks are indexed

Inspect the upload response and call `/api/health`. Confirm that:

- `indexed_chunks` is greater than zero.
- The embedding deployment returns 1536-dimensional vectors.
- The Search key can create indexes and upload documents.
- The Search endpoint and index name are correct.

### Frontend reports that the backend is offline

Start FastAPI on port 8000, check `http://localhost:8000/api/health`, and verify `VITE_API_URL` if the backend is elsewhere. Confirm that `FRONTEND_ORIGIN` matches the browser origin.

### Azure Blob Storage documents are not visible

Confirm that the connection string is valid, the container name matches `AZURE_STORAGE_CONTAINER`, and the storage account allows the application to create containers and upload/read blobs.

## Security and production considerations

This repository is a local-development reference implementation. Before exposing it publicly:

- Add user authentication and authorization.
- Restrict documents and citations to the owning user or tenant.
- Replace API keys and connection strings with managed identity/RBAC and a secret manager.
- Move ingestion to an asynchronous worker with job status tracking.
- Add upload, chat, and Search rate limits.
- Add file validation, malware scanning, and stricter filename/document metadata validation.
- Protect the document download endpoint and avoid unrestricted source URLs.
- Add structured logging, monitoring, retries, and retrieval-quality evaluation.
- Review prompt-injection risks in uploaded documents and treat retrieved text as untrusted input.

## License

No license has been declared for this repository. Add a license file before distributing the project.
