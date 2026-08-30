import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Markdown from "../components/Markdown";
import { api, describeApiError, LinkedCourseTopic } from "../api";

export default function InferenceLinkedTopic() {
  const { moduleId = "", conceptId = "" } = useParams();
  const [topic, setTopic] = useState<LinkedCourseTopic | null>(null);
  const [error, setError] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const load = useCallback((signal?: AbortSignal) => {
    setError(""); setTopic(null);
    return api.courseLinkedTopic(moduleId, Number(conceptId), signal).then(setTopic).catch((reason) => {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(describeApiError(reason));
    });
  }, [moduleId, conceptId]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);
  useEffect(() => { if (topic) headingRef.current?.focus(); }, [topic?.id]);

  if (error) return <section className="panel course-error" role="alert"><h1>Linked lesson unavailable</h1><p>{error}</p><button className="btn" onClick={() => load()}>Try again</button><Link to={`/courses/inference-engineering/${moduleId}`}>Return to mission</Link></section>;
  if (!topic) return <div className="loading" role="status">loading linked lesson</div>;
  return <article className="lesson-page course-linked-topic">
    <header className="page-head"><span className="eyebrow">Course-linked private lesson</span><h1 ref={headingRef} tabIndex={-1}>{topic.title}</h1><p>{topic.summary}</p></header>
    <nav className="lesson-toolbar" aria-label="Course lesson navigation"><Link className="lesson-book-link" to={`/courses/inference-engineering/${moduleId}`}>← Return to mission</Link></nav>
    <div className="panel md lesson-content"><Markdown>{topic.lesson_md}</Markdown></div>
    <p className="muted">This lesson is read-only here. Its independent practice history remains outside the course.</p>
  </article>;
}
