import { useEffect, useRef, useState } from "react";

const API = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

function App() {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState({ backend: "checking", indexed: 0, documents: [] });
  const [notice, setNotice] = useState(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef(null);

  async function refreshStatus() {
    try {
      const [healthResponse, documentsResponse] = await Promise.all([
        fetch(`${API}/api/health`),
        fetch(`${API}/api/documents`),
      ]);
      if (!healthResponse.ok || !documentsResponse.ok) throw new Error("Backend unavailable");
      const health = await healthResponse.json();
      const docs = await documentsResponse.json();
      setStatus({ backend: "online", indexed: health.indexed_chunks || 0, documents: docs.documents || [] });
    } catch {
      setStatus({ backend: "offline", indexed: 0, documents: [] });
    }
  }

  useEffect(() => {
    refreshStatus();
  }, []);

  async function uploadFile(file) {
    if (!file) return;
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      setNotice({ type: "error", text: "Please upload a PDF product manual." });
      return;
    }
    if (file.size > 25 * 1024 * 1024) {
      setNotice({ type: "error", text: "The PDF must be smaller than 25 MB." });
      return;
    }

    setUploading(true);
    setNotice({ type: "info", text: "Uploading PDF, extracting pages, creating embeddings and indexing…" });

    const form = new FormData();
    form.append("file", file);

    try {
      const response = await fetch(`${API}/api/documents`, { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Upload failed");
      setNotice({ type: "success", text: `${data.file} is ready. ${data.chunks} chunks were indexed.` });
      await refreshStatus();
      setMessages([]);
    } catch (error) {
      setNotice({ type: "error", text: error.message });
    } finally {
      setUploading(false);
    }
  }

  function handleFileInput(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    uploadFile(file);
  }

  async function sendMessage(text = question) {
    const value = text.trim();
    if (!value || loading || uploading) return;

    const nextMessages = [...messages, { role: "user", content: value }];
    setMessages(nextMessages);
    setQuestion("");
    setLoading(true);
    setNotice(null);

    try {
      const response = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: value, history: messages.slice(-8) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "The assistant could not answer.");
      setMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: data.answer,
          citations: data.citations || [],
        },
      ]);
    } catch (error) {
      setNotice({ type: "error", text: error.message });
      setMessages(nextMessages);
    } finally {
      setLoading(false);
    }
  }

  const hasDocuments = status.indexed > 0;

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="brand-wrap">
            <div className="brand-mark">D</div>
            <div>
              <div className="brand">DocuMind</div>
              <div className="brand-subtitle">Product Documentation Assistant</div>
            </div>
          </div>
          <div className={`connection ${status.backend}`}>
            <span /> {status.backend === "online" ? "Backend online" : status.backend === "offline" ? "Backend offline" : "Connecting"}
          </div>
        </div>
      </header>

      <main className="container">
        <section className="intro">
          <div className="badge">AZURE AI · RAG · DOCUMENT SEARCH</div>
          <h1>Ask questions about your product manual.</h1>
          <p>Upload a PDF and DocuMind will extract its content, create searchable embeddings, and answer questions using evidence from the document.</p>
        </section>

        <section className="upload-card">
          <div
            className={`dropzone ${dragging ? "dragging" : ""}`}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              uploadFile(event.dataTransfer.files?.[0]);
            }}
            onClick={() => !uploading && fileInput.current?.click()}
          >
            <input ref={fileInput} type="file" accept="application/pdf,.pdf" hidden onChange={handleFileInput} />
            <div className="upload-icon">↑</div>
            <div className="drop-title">{uploading ? "Processing your PDF…" : "Drop your product PDF here"}</div>
            <div className="drop-subtitle">or click to choose a file · PDF up to 25 MB</div>
            <button className="choose-button" type="button" disabled={uploading}>Choose PDF</button>
          </div>

          <div className="pipeline">
            <div className="pipeline-step"><b>01</b><span>Upload PDF</span></div>
            <div className="pipeline-line" />
            <div className="pipeline-step"><b>02</b><span>Extract & chunk</span></div>
            <div className="pipeline-line" />
            <div className="pipeline-step"><b>03</b><span>Embed & index</span></div>
            <div className="pipeline-line" />
            <div className="pipeline-step"><b>04</b><span>Ask questions</span></div>
          </div>
        </section>

        {notice && <div className={`notice ${notice.type}`}>{notice.text}</div>}

        <section className="dashboard-grid">
          <aside className="sidebar">
            <div className="side-card">
              <div className="side-heading">Knowledge base</div>
              <div className="stat-number">{status.indexed}</div>
              <div className="stat-label">indexed chunks</div>
              <div className="status-bar"><span style={{ width: status.indexed ? "100%" : "8%" }} /></div>
            </div>

            <div className="side-card">
              <div className="side-heading">Uploaded documents</div>
              {status.documents.length === 0 ? (
                <div className="empty-docs">No documents yet. Upload a PDF to create your knowledge base.</div>
              ) : (
                <div className="doc-list">
                  {status.documents.map((doc) => (
                    <a key={doc.name} href={doc.url} target="_blank" rel="noreferrer" className="doc-item">
                      <span className="pdf-label">PDF</span>
                      <span className="doc-name">{doc.name}</span>
                    </a>
                  ))}
                </div>
              )}
            </div>
          </aside>

          <section className="chat-card">
            <div className="chat-header">
              <div>
                <div className="chat-title">Documentation chat</div>
                <div className="chat-subtitle">{hasDocuments ? "Answers are grounded in your indexed documents." : "Upload a PDF before asking a product question."}</div>
              </div>
              <div className="grounded-pill"><span /> Grounded RAG</div>
            </div>

            <div className="messages">
              {messages.length === 0 ? (
                <div className="empty-chat">
                  <div className="empty-chat-icon">?</div>
                  <h2>{hasDocuments ? "Your documentation is ready." : "Your knowledge base is empty."}</h2>
                  <p>{hasDocuments ? "Ask something specific about the uploaded product manual." : "Upload a PDF above. The assistant will search it before answering."}</p>
                  {hasDocuments && (
                    <div className="suggestions">
                      {[
                        "What are the main features?",
                        "What are the key specifications?",
                        "How do I set up the product?",
                        "How do I troubleshoot common errors?",
                      ].map((item) => <button key={item} onClick={() => sendMessage(item)}>{item}</button>)}
                    </div>
                  )}
                </div>
              ) : (
                messages.map((message, index) => (
                  <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                    <div className="avatar">{message.role === "user" ? "Y" : "D"}</div>
                    <div className="message-content">
                      <div className="message-label">{message.role === "user" ? "You" : "DocuMind"}</div>
                      <div className="message-body">{message.content}</div>
                      {message.citations?.length > 0 && (
                        <div className="sources">
                          <div className="sources-title">Sources</div>
                          {message.citations.map((citation, i) => (
                            <a href={citation.url} target="_blank" rel="noreferrer" key={`${citation.url}-${i}`}>
                              <span>[{i + 1}]</span> {citation.title || "Documentation"}
                            </a>
                          ))}
                        </div>
                      )}
                    </div>
                  </article>
                ))
              )}
              {loading && <div className="loading"><span /><span /><span /> Searching your documentation…</div>}
            </div>

            <form className="composer" onSubmit={(event) => { event.preventDefault(); sendMessage(); }}>
              <input value={question} onChange={(event) => setQuestion(event.target.value)} disabled={!hasDocuments || loading || uploading} placeholder={hasDocuments ? "Ask about setup, features, specifications, troubleshooting…" : "Upload a PDF to enable questions"} maxLength={4000} />
              <button type="submit" disabled={!hasDocuments || loading || uploading || !question.trim()}>{loading ? "…" : "Ask"}</button>
            </form>
          </section>
        </section>
      </main>
    </div>
  );
}

export default App;
