import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

type Section = { id: number; chapter: string; label: string; citation: string; status: string; concept_id?: number; topic_title?: string; summary?: string; error_message?: string };
type Book = { id: number; title: string; status: string; page_count: number; total_sections: number; completed_sections: number; activated: boolean; error_message?: string; sections?: Section[] };
type Message = { role: string; content: string; citations?: { citation: string }[] };

export default function MakeMeLearn() {
  const [books, setBooks] = useState<Book[]>([]); const [active, setActive] = useState<Book | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [messages, setMessages] = useState<Message[]>([]); const [question, setQuestion] = useState("");
  const [scope, setScope] = useState("book"); const [sectionId, setSectionId] = useState<number | undefined>();
  const [clearing, setClearing] = useState(false); const [confirmingClear, setConfirmingClear] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const confirmBtnRef = useRef<HTMLButtonElement>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);
  const [focusTextarea, setFocusTextarea] = useState(false);

  async function refresh(selectId?: number) {
    const list = await api.books(); setBooks(list);
    const id = selectId || active?.id || list[0]?.id;
    if (id) { const detail = await api.book(id); setActive(detail); setMessages(await api.bookChatHistory(id)); }
  }
  useEffect(() => { refresh().catch(() => setError("Could not load your library.")); }, []);
  useEffect(() => {
    if (!active || !["queued", "processing", "extracting"].includes(active.status)) return;
    const timer = window.setInterval(() => refresh(active.id).catch(() => {}), 4000); return () => clearInterval(timer);
  }, [active?.id, active?.status]);

  useEffect(() => {
    if (confirmingClear) {
      confirmBtnRef.current?.focus();
    } else if (cancelBtnRef.current) {
      cancelBtnRef.current.focus();
    }
  }, [confirmingClear]);

  useEffect(() => {
    if (focusTextarea) {
      if (active && !busy) {
        const texts = document.querySelectorAll(".chat-input textarea");
        (texts[texts.length - 1] as HTMLTextAreaElement)?.focus();
      } else {
        const headings = document.querySelectorAll(".book-chat h2");
        (headings[headings.length - 1] as HTMLElement)?.focus();
      }
      setFocusTextarea(false);
    }
  }, [focusTextarea, active?.id, busy]);

  async function upload(file?: File) {
    if (!file) return; setBusy(true); setError("");
    try { const book = await api.uploadBook(file); await refresh(book.id); }
    catch { setError("Import failed. Use a text-based, unencrypted PDF under 50 MB / 500 pages."); }
    finally { setBusy(false); }
  }
  async function ask() {
    const q = question.trim(); if (!q || !active) return; setQuestion("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    try { const r = await api.bookChat(active.id, q, scope, sectionId); setMessages((m) => [...m, { role: "assistant", content: r.answer, citations: r.citations }]); }
    catch { setMessages((m) => [...m, { role: "assistant", content: "DGX could not answer from the available book excerpts." }]); }
  }

  async function clearChat() {
    if (!active) return; setClearing(true); setConfirmingClear(false);
    try {
      await api.clearBookChat(active.id);
      setMessages([]);
      setFocusTextarea(true);
    } catch {
      setError("Could not clear chat. Please try again.");
    } finally { setClearing(false); }
  }

  return <div className="book-workspace">
    <main className="book-main">
      <header className="page-head book-page-head"><div><span className="eyebrow">PRIVATE LEARNING LAB</span><h1>Make Me Learn</h1><p>Turn a book you own into guided topics, quizzes, and source-backed tutoring.</p></div>
        <label className="btn primary">{busy ? "Importing…" : "Import book"}<input hidden type="file" accept="application/pdf,.pdf" disabled={busy} onChange={(e) => upload(e.target.files?.[0])} /></label>
      </header>
      {error && <div className="notice error">{error}</div>}
      {!books.length && <section className="panel book-empty"><h2>Your private library is empty</h2><p>Choose a digitally readable PDF. Processing stays on the Mac mini and private DGX; OCR is not included yet.</p><p className="muted">Maximum 50 MB and 500 pages. Only upload material you have rights to process.</p></section>}
      {!!books.length && <div className="book-picker">{books.map((b) => <button className={active?.id === b.id ? "active" : ""} key={b.id} onClick={() => refresh(b.id)}>{b.title}<small>{b.status}</small></button>)}</div>}
      {active && <section className="panel book-overview"><div><span className="eyebrow">{active.status}</span><h2>{active.title}</h2><p>{active.page_count} pages · {active.completed_sections}/{active.total_sections} topics generated</p></div>
        <progress max={Math.max(active.total_sections, 1)} value={active.completed_sections} />
        {!active.activated && ["ready", "partial"].includes(active.status) && <button className="btn primary" onClick={async () => { await api.activateBook(active.id); await refresh(active.id); }}>Activate course</button>}
        {active.status === "partial" && <button className="btn" onClick={async () => { await api.retryBook(active.id); await refresh(active.id); }}>Retry failed topics</button>}
      </section>}
      {active && active.activated && <section className="panel continue-card"><span className="eyebrow">RECOMMENDED</span><h2>Continue learning</h2><p>Learn a grounded topic, recall it without notes, then test your understanding.</p><Link className="btn primary" to={active.sections?.find(s => s.concept_id)?.concept_id ? `/topics/${active.sections.find(s => s.concept_id)!.concept_id}` : "/"}>Start a learning session</Link><div className="session-modes"><span>Quick · 5 min</span><span>Learn · 10–15 min</span><span>Deep · 20–30 min</span></div></section>}
    </main>
    <aside className="book-chat"><div><span className="eyebrow">DGX · GROUNDED</span><h2>Ask This Book</h2>
        {confirmingClear ? (
          active ? (
            <div className="clear-confirm">
              <span>Clear all messages for <em>{active.title}</em>?</span>
              <div className="clear-confirm-actions">
                <button className="btn" ref={confirmBtnRef} onClick={clearChat} disabled={clearing || busy} title="Clear chat">Clear</button>
                <button className="btn" ref={cancelBtnRef} onClick={() => setConfirmingClear(false)} disabled={clearing || busy}>Cancel</button>
              </div>
            </div>
          ) : null
        ) : messages.length > 0 ? (
          <button className="btn clear-chat-btn" ref={triggerRef} onClick={() => setConfirmingClear(true)} disabled={busy || clearing} title="Clear chat">Clear chat</button>
        ) : null}
      </div>
      {!active ? <p className="muted">Import or select a book to begin.</p> : <>
        <select value={scope} onChange={(e) => setScope(e.target.value)}><option value="book">Whole book</option><option value="chapter">Selected chapter</option><option value="topic">Selected topic</option></select>
        <div className="chat-scroll">{messages.map((m, i) => <div className={`chat-msg ${m.role}`} key={i}><strong>{m.role === "user" ? "You" : "DGX"}</strong><p>{m.content}</p>{m.citations?.map((c, j) => <small key={j}>{c.citation}</small>)}</div>)}</div>
        <div className="chat-prompts">{["Explain this simply", "Quiz me", "Where does the book support that?"].map(p => <button key={p} onClick={() => setQuestion(p)}>{p}</button>)}</div>
        <div className="chat-input"><textarea value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask a question grounded in this book…"/><button className="btn primary" onClick={ask}>Ask</button></div>
      </>}
    </aside>
    {active && <section className="panel chapter-journey"><h2>Chapter journey</h2><div className="topic-path">{active.sections?.map((s) => <div className={`topic-node ${s.status}`} key={s.id} onClick={() => setSectionId(s.id)}><div><strong>{s.topic_title || s.label}</strong>{s.summary && <p>{s.summary}</p>}<small>{s.citation}</small></div><span>{s.status}</span>{s.concept_id && <Link to={`/topics/${s.concept_id}`}>{active.activated ? "Learn / quiz →" : "Preview →"}</Link>}</div>)}</div></section>}
  </div>;
}
