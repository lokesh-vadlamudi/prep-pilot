import { useEffect, useRef, useState } from "react";
import Markdown from "../components/Markdown";
import { api } from "../api";

const SUGGESTIONS = [
  "Design a URL shortener that handles 10k writes/sec.",
  "Explain the difference between optimistic and pessimistic locking with a Go example.",
  "How would you roll out a schema migration with zero downtime?",
  "Walk me through debugging a memory leak in a Node service in production.",
];

type Msg = { role: "user" | "assistant"; content: string };
const STORE_KEY = "preppilot_ask_thread";

function loadThread(): Msg[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export default function Ask() {
  const [q, setQ] = useState("");
  const [thread, setThread] = useState<Msg[]>(loadThread);
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  // Persist the conversation so it survives leaving/returning to the tab and refreshes.
  useEffect(() => {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(thread)); } catch { /* ignore quota */ }
  }, [thread]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [thread, busy]);

  async function ask(question: string) {
    const question_ = question.trim();
    if (!question_ || busy) return;
    const history = thread.slice(-8); // send recent turns for follow-up context
    setThread((t) => [...t, { role: "user", content: question_ }]);
    setQ("");
    setBusy(true);
    try {
      const r = await api.ask(question_, "", history);
      setThread((t) => [...t, { role: "assistant", content: r.answer }]);
    } catch {
      setThread((t) => [...t, { role: "assistant", content: "_The DGX brain is unreachable right now._" }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">Q&A · powered by the DGX brain</div>
        <h1>Ask the tutor</h1>
        <p>A running conversation — ask anything, then keep drilling with follow-ups. Tuned for a senior Go/Python/TS engineer.</p>
      </div>

      {thread.length > 0 && (
        <div className="panel">
          <div className="mentor-log" style={{ padding: 0, maxHeight: "none" }}>
            {thread.map((m, i) => (
              <div key={i} className={"bubble " + m.role}>
                {m.role === "assistant" ? <div className="md"><Markdown>{m.content}</Markdown></div> : m.content}
              </div>
            ))}
            {busy && <div className="bubble assistant"><span className="loading">the DGX brain is composing an answer</span></div>}
            <div ref={endRef} />
          </div>
          {thread.length > 0 && (
            <button className="filter-btn" style={{ marginTop: 12 }} onClick={() => setThread([])}>
              ↺ new conversation
            </button>
          )}
        </div>
      )}

      <div className="panel">
        <textarea
          className="answer"
          style={{ marginTop: 0, minHeight: 80 }}
          placeholder={thread.length ? "Ask a follow-up…" : "Ask anything…"}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask(q); }}
        />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}>
          <span className="mono" style={{ color: "var(--faint)", fontSize: 11 }}>⌘/Ctrl + Enter</span>
          <button className="btn" onClick={() => ask(q)} disabled={busy || q.trim().length < 3}>
            {busy ? "Thinking…" : thread.length ? "Send" : "Ask"}
          </button>
        </div>
      </div>

      {thread.length === 0 && !busy && (
        <div className="panel">
          <div className="eyebrow" style={{ marginBottom: 12 }}>Try one</div>
          {SUGGESTIONS.map((s) => (
            <button key={s} className="topic-row" style={{ width: "100%", background: "none", border: "none", borderBottom: "1px solid var(--line)", textAlign: "left", color: "var(--text)" }} onClick={() => ask(s)}>
              <span className="t-title" style={{ fontWeight: 400 }}>{s}</span>
            </button>
          ))}
        </div>
      )}
    </>
  );
}
