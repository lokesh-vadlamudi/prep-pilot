import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, trackClass } from "../api";

type Topic = { id: number; track: string; title: string; difficulty: string; tags: string; summary: string; source: string };

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

  const tracks = ["DSA", "System Design", "CS Fundamentals", "Behavioral"];

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
            <div className="eyebrow" style={{ marginBottom: 10 }}>{t}</div>
            {rows.map((x) => (
              <Link to={`/topics/${x.id}`} className="topic-row" key={x.id}>
                <span className={"chip " + trackClass(x.track)}>{x.difficulty}</span>
                <div style={{ flex: 1 }}>
                  <div className="t-title">{x.title}</div>
                  <div className="t-summary">{x.summary}</div>
                </div>
                {x.source === "ai" && <span className="chip ai">ai</span>}
              </Link>
            ))}
          </div>
        );
      })}
    </>
  );
}
