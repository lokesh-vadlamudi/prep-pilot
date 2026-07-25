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

  return (
    <>
      <div className="page-head">
        <Link to="/topics" className="mono" style={{ color: "var(--faint)", fontSize: 12 }}>← syllabus</Link>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10 }}>
          <span className={"chip " + trackClass(topic.track)}>{topic.track}</span>
          <span className="chip">{topic.difficulty}</span>
          {topic.source === "ai" && <span className="chip ai">ai-authored</span>}
        </div>
        <h1>{topic.title}</h1>
      </div>

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
