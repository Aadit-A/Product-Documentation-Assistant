# DocuMind — Product Documentation Assistant

An Azure-based RAG application that lets a user upload a product PDF and ask grounded questions about it.

## What the application does

```text
PDF upload
   ↓
FastAPI receives and stores the PDF
   ↓
Azure Blob Storage stores the original (when configured)
   ↓
Azure Content Understanding extracts page-aware content
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
- Azure Content Understanding API key
- Azure Storage connection string

The agent itself is implemented by the FastAPI application using Azure OpenAI tool/function calling.

## Project structure

```text
product-doc-assistant/
├── .env
├── .env.example
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

## 1. Configure `.env`

Copy `.env.example` to `.env` and fill in your own credentials.

Do not commit `.env` to Git. Rotate any Azure keys that have previously been exposed.

The embedding deployment must produce **1536 dimensions** if you keep the supplied Search schema. `text-embedding-3-small` does this by default.

## 2. Backend

From the project root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If your Content Understanding package needs the preview release:

```powershell
python -m pip install --pre azure-ai-contentunderstanding
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
2. Drop a PDF product manual into the upload area.
3. FastAPI stores the PDF locally and in Blob Storage when configured.
4. Content Understanding extracts the PDF.
5. The backend creates chunks and embeddings.
6. Chunks are indexed into Azure AI Search.
7. The UI shows the indexed chunk count.
8. Ask a product question.
9. The AI agent searches the documentation and answers from retrieved evidence.
10. Source links point back to the uploaded document served by FastAPI.

## 5. API endpoints

- `GET /api/health` — backend/Search status
- `GET /api/documents` — uploaded documents and indexed chunk count
- `POST /api/documents` — upload and index a PDF/MD/TXT file
- `GET /api/documents/{filename}` — open an uploaded source document
- `POST /api/chat` — ask a grounded question

## 6. If the Search index is empty

You normally do **not** need to run a separate ingestion command. Uploading a PDF through the frontend calls `/api/documents`, which performs the complete ingestion flow.

The older `backend/ingest.py` command is still available for batch ingestion of files already placed in `data/`:

```powershell
python -m backend.ingest
```

## 7. Troubleshooting

### Microsoft login page appears

This project should not invoke Azure CLI or `DefaultAzureCredential`. Check that you are running the new `backend/azure_services.py` and `backend/ingest.py` from this package.

### Upload says Content Understanding authentication failed

Check:

```env
CONTENT_UNDERSTANDING_ENDPOINT=...
CONTENT_UNDERSTANDING_API_KEY=...
```

### Search returns zero chunks

Check the upload response. A successful upload returns a `chunks` value. Also open `/api/health` and confirm `indexed_chunks` is greater than zero.

### Frontend cannot connect

Start FastAPI first on port 8000, then Vite on port 5173. `frontend/.env` can override the backend URL:

```env
VITE_API_URL=http://localhost:8000
```
