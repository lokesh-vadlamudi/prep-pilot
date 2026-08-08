import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Markdown from "../components/Markdown";
import { api, trackClass } from "../api";

export default function TopicDetail() {
  const { id } = useParams();
  const [topic, setTopic] = useState<any>(null);

  useEffect(() => {
    if (id) api.topic(Number(id)).then(setTopic);
  }, [id]);

  if (!topic) return <div className="loading">loading</div>;

  async function toggleComplete() {
    await api.topicStatus(topic.id, !topic.completed);
    setTopic({ ...topic, completed: !topic.completed });
  }

  const nav = topic.book_navigation;

  return (
    <>
      <div className="page-head">
        <Link to={nav ? "/make-me-learn" : "/topics"} className="mono" style={{ color: "var(--faint)", fontSize: 12 }}>
          ← {nav ? nav.book_title : "syllabus"}
        </Link>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10 }}>
          <span className={"chip " + trackClass(topic.track)}>{topic.track}</span>
          <span className="chip">{topic.difficulty}</span>
          {topic.source === "ai" && <span className="chip ai">ai-authored</span>}
        </div>
        <h1>{topic.title}</h1>
        {nav && <p className="muted">Lesson {nav.position} of {nav.total} · {nav.book_title}</p>}
        <button className={"btn " + (topic.completed ? "primary" : "ghost")} onClick={toggleComplete}>
          {topic.completed ? "✓ Completed" : "Mark complete"}
        </button>
      </div>

      {nav && <div className="panel" style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        {nav.previous ? <Link className="btn ghost" to={`/topics/${nav.previous.id}`}>← {nav.previous.title}</Link> : <span />}
        {nav.next ? <Link className="btn primary" to={`/topics/${nav.next.id}`}>{nav.next.title} →</Link> : <Link className="btn primary" to="/make-me-learn">Back to book →</Link>}
      </div>}

      <div className="panel md">
        <Markdown>{topic.lesson_md}</Markdown>
      </div>

      <div className="panel">
        <div className="eyebrow" style={{ marginBottom: 12 }}>Practice cards ({topic.cards.length})</div>
        {topic.cards.map((c: any) => (
          <div key={c.card_id} className="topic-row">
            <span className="chip">{c.kind}</span>
            <div style={{ flex: 1 }}>
              <div className="t-title" style={{ fontWeight: 400, fontSize: 14 }}>{c.prompt}</div>
              <div className="t-summary">
                {c.introduced ? `next review in ${c.interval_days}d` : "not yet introduced"}
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
