import { useMemo, useRef, useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

/** Render the chat application, document uploader, and source citations. */
export default function App() {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [notice, setNotice] = useState("");
  const fileInput = useRef(null);

  const suggestions = useMemo(
    () => [
      "What does this product do?",
      "How do I reset the device?",
      "What are the main specifications?",
      "What should I do if I see an error?",
    ],
    [],
  );

  /** Send the current question to the FastAPI backend and append the grounded response. */
  async function sendMessage(text = question) {
    const value = text.trim();
    if (!value || loading) return;
    const nextMessages = [...messages, { role: "user", content: value }];
    setMessages(nextMessages);
    setQuestion("");
    setLoading(true);
    setNotice("");
    try {
      const response = await fetch(`${API}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: value, history: messages.slice(-8) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Request failed");
      setMessages([
        ...nextMessages,
        { role: "assistant", content: data.answer, citations: data.citations || [], mode: data.mode },
      ]);
    } catch (error) {
      setNotice(error.message);
      setMessages(nextMessages);
    } finally {
      setLoading(false);
    }
  }

  /** Upload a product document to the backend ingestion pipeline. */
  async function uploadDocument(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setNotice("");
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await fetch(`${API}/api/documents`, { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Upload failed");
      setNotice(`${data.file} indexed successfully (${data.chunks} chunks).`);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <div className="brand">DocuMind</div>
          <div className="subtitle">AI Product Documentation Assistant</div>
        </div>
        <label className="upload-button">
          {uploading ? "Indexing…" : "Upload documentation"}
          <input ref={fileInput} type="file" accept=".pdf,.md,.txt" onChange={uploadDocument} disabled={uploading} />
        </label>
      </header>

      <main className="workspace">
        <section className="hero">
          <span className="eyebrow">Azure AI • RAG • Foundry Agent</span>
          <h1>Ask your product documentation.</h1>
          <p>
            Get grounded answers from your manuals, specifications, FAQs, and troubleshooting guides with source references.
          </p>
        </section>

        <section className="chat-card">
          <div className="messages">
            {messages.length === 0 && (
              <div className="empty-state">
                <div className="empty-icon">⌁</div>
                <h2>What do you want to know?</h2>
                <div className="suggestions">
                  {suggestions.map((item) => (
                    <button key={item} onClick={() => sendMessage(item)}>{item}</button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((message, index) => (
              <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                <div className="message-label">{message.role === "user" ? "You" : "Assistant"}</div>
                <div className="message-body">{message.content}</div>
                {message.citations?.length > 0 && (
                  <div className="sources">
                    <strong>Sources</strong>
                    {message.citations.map((citation, citationIndex) => (
                      <a key={`${citation.url}-${citationIndex}`} href={citation.url} target="_blank" rel="noreferrer">
                        {citationIndex + 1}. {citation.title || "Documentation"}
                      </a>
                    ))}
                  </div>
                )}
              </article>
            ))}
            {loading && <div className="typing">Searching documentation and preparing an answer…</div>}
          </div>

          {notice && <div className="notice">{notice}</div>}

          <form
            className="composer"
            onSubmit={(event) => {
              event.preventDefault();
              sendMessage();
            }}
          >
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask about setup, specifications, troubleshooting, or configuration…"
              maxLength={4000}
            />
            <button type="submit" disabled={loading || !question.trim()}>Ask</button>
          </form>
        </section>
      </main>
    </div>
  );
}
