import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Markdown from "../components/Markdown";
import { api, trackClass } from "../api";

function LessonToolbar({ nav, completed, onToggle }: any) {
  return (
    <nav className="lesson-toolbar" aria-label="Lesson navigation">
      <div className="lesson-toolbar-meta">
        <button className="lesson-complete" onClick={onToggle} aria-pressed={completed}>
          <span className={`prob-check${completed ? " solved" : ""}`} aria-hidden="true">✓</span>
          <span>{completed ? "Completed" : "Mark complete"}</span>
        </button>
        <Link className="lesson-book-link" to={nav ? "/make-me-learn" : "/topics"}>
          ← {nav ? "Book journey" : "Syllabus"}
        </Link>
      </div>

      {nav && <span className="lesson-position">Lesson {nav.position} of {nav.total}</span>}

      {nav && <div className="lesson-nav-actions">
        {nav.previous && <Link className="lesson-nav-link previous" to={`/topics/${nav.previous.id}`}>
          <span className="lesson-nav-direction">← Previous</span>
          <span className="lesson-nav-title">{nav.previous.title}</span>
        </Link>}
        {nav.next ? <Link className="lesson-nav-link next" to={`/topics/${nav.next.id}`}>
          <span className="lesson-nav-direction">Next →</span>
          <span className="lesson-nav-title">{nav.next.title}</span>
        </Link> : <Link className="lesson-nav-link next" to="/make-me-learn">
          <span className="lesson-nav-direction">Finish →</span>
          <span className="lesson-nav-title">Return to book journey</span>
        </Link>}
      </div>}
    </nav>
  );
}

export default function TopicDetail() {
  const { id } = useParams();
  const [topic, setTopic] = useState<any>(null);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    setTopic(null);
    if (id) api.topic(Number(id)).then(setTopic);
  }, [id]);

  if (!topic) return <div className="loading">loading</div>;

  async function toggleComplete() {
    await api.topicStatus(topic.id, !topic.completed);
    setTopic({ ...topic, completed: !topic.completed });
  }

  const nav = topic.book_navigation;

  return (
    <div className="lesson-page">
      <div className="page-head">
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className={"chip " + trackClass(topic.track)}>{topic.track}</span>
          <span className="chip">{topic.difficulty}</span>
          {topic.source === "ai" && <span className="chip ai">ai-authored</span>}
        </div>
        <h1>{topic.title}</h1>
        {nav && <p className="muted">{nav.book_title}</p>}
      </div>

      <LessonToolbar nav={nav} completed={topic.completed} onToggle={toggleComplete} />

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
    </div>
  );
}
