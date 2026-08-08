import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, trackClass } from "../api";

type Topic = { id: number; track: string; title: string; difficulty: string; tags: string; summary: string; source: string; completed: boolean };

export default function Topics() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = () => api.topics().then(setTopics);
  useEffect(() => { load(); }, []);

  async function generate() {
    setBusy(true);
    setMsg("The DGX brain is authoring new material…");
    try {
      const r = await api.generateNow(1);
      await load();
      setMsg(`Added ${r.added} fresh topic${r.added === 1 ? "" : "s"}.`);
    } catch {
      setMsg("Generation failed — is the DGX brain online?");
    } finally {
      setBusy(false);
    }
  }

  const standardTracks = ["DSA", "System Design", "CS Fundamentals", "Behavioral"];
  const tracks = [...new Set(topics.map((topic) => topic.track))].sort((a, b) => {
    const ai = standardTracks.indexOf(a); const bi = standardTracks.indexOf(b);
    if (ai >= 0 || bi >= 0) return (ai >= 0 ? ai : standardTracks.length) - (bi >= 0 ? bi : standardTracks.length);
    return a.localeCompare(b);
  });

  async function toggleComplete(topic: Topic) {
    await api.topicStatus(topic.id, !topic.completed);
    setTopics((rows) => rows.map((row) => row.id === topic.id ? { ...row, completed: !row.completed } : row));
  }

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">Syllabus · {topics.length} concepts</div>
        <h1>The training syllabus</h1>
        <p>Every concept you've unlocked. New material is authored nightly — or on demand.</p>
      </div>

      <div className="panel" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <span className="mono" style={{ color: "var(--muted)", fontSize: 13 }}>
          {msg || "Grow the bank with senior-level topics tuned to your stack."}
        </span>
        <button className="btn ghost" onClick={generate} disabled={busy}>
          {busy ? "Authoring…" : "+ Generate new topics"}
        </button>
      </div>

      {tracks.map((t) => {
        const rows = topics.filter((x) => x.track === t);
        if (!rows.length) return null;
        return (
          <div className="panel" key={t}>
            <div className="eyebrow" style={{ marginBottom: 10 }}>{t} · {rows.filter((x) => x.completed).length}/{rows.length} complete</div>
            {rows.map((x) => (
              <div className="topic-row" key={x.id}>
                <button className={"prob-check " + (x.completed ? "solved" : "todo")}
                  title={x.completed ? "Completed — click to reset" : "Mark topic complete"}
                  aria-label={`${x.completed ? "Reset" : "Complete"} ${x.title}`}
                  onClick={() => toggleComplete(x)}>{x.completed ? "✓" : ""}</button>
                <span className={"chip " + trackClass(x.track)}>{x.difficulty}</span>
                <Link to={`/topics/${x.id}`} style={{ flex: 1, color: "inherit", textDecoration: "none" }}>
                  <div className="t-title">{x.title}</div>
                  <div className="t-summary">{x.summary}</div>
                </Link>
                {x.source === "ai" && <span className="chip ai">ai</span>}
                {x.source === "book" && <span className="chip">book</span>}
              </div>
            ))}
          </div>
        );
      })}
    </>
  );
}
