import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Markdown from "../components/Markdown";
import ReviewCard from "../components/ReviewCard";
import { api, Card, SubmitResult, trackClass } from "../api";

type ChatMode = "tutor" | "quiz";
type ChatMessage = { role: "user" | "assistant"; content: string };

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
  const [quizIndex, setQuizIndex] = useState<number | null>(null);
  const [quizResults, setQuizResults] = useState<SubmitResult[]>([]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    setTopic(null);
    setQuizIndex(null);
    setQuizResults([]);
    if (id) api.topic(Number(id)).then(setTopic);
  }, [id]);

  if (!topic) return <div className="loading">loading</div>;

  async function toggleComplete() {
    await api.topicStatus(topic.id, !topic.completed);
    setTopic({ ...topic, completed: !topic.completed });
  }

  const nav = topic.book_navigation;
  const quizCards: Card[] = topic.cards.map((card: any) => ({
    ...card,
    concept_id: topic.id,
    concept_title: topic.title,
    track: topic.track,
    tags: topic.tags || "",
    is_new: !card.introduced,
  }));
  const quizComplete = quizIndex !== null && quizIndex >= quizCards.length;

  async function finishQuestion(result?: SubmitResult) {
    const results = result ? [...quizResults, result] : quizResults;
    setQuizResults(results);
    const nextIndex = (quizIndex ?? 0) + 1;
    setQuizIndex(nextIndex);
    if (nextIndex >= quizCards.length && !topic.completed) {
      await api.topicStatus(topic.id, true);
      setTopic({ ...topic, completed: true });
    }
    window.scrollTo({ top: 0, left: 0, behavior: "smooth" });
  }

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

      {quizIndex === null && <>
        <div className="panel md lesson-content">
          <Markdown>{topic.lesson_md}</Markdown>
        </div>
        <section className="panel topic-quiz-cta">
          <div>
            <span className="eyebrow">CHECK YOUR UNDERSTANDING</span>
            <h2>{quizCards.length ? `${quizCards.length}-question topic quiz` : "Practice coming soon"}</h2>
            <p>{quizCards.length ? "Answer the generated questions for this lesson. Results update your spaced-repetition schedule." : "This lesson does not have generated practice cards yet."}</p>
          </div>
          {quizCards.length > 0 && <button className="btn primary" onClick={() => { setQuizIndex(0); setQuizResults([]); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
            Start quiz ({quizCards.length}) →
          </button>}
        </section>
      </>}

      {quizIndex !== null && !quizComplete && <section className="topic-quiz-stage">
        <div className="review-progress">
          <span>TOPIC QUIZ · QUESTION {quizIndex + 1} / {quizCards.length}</span>
          <button className="filter-btn" onClick={() => setQuizIndex(null)}>Back to lesson</button>
        </div>
        <div className="progress-track"><div className="progress-fill" style={{ width: `${(quizIndex / quizCards.length) * 100}%` }} /></div>
        <ReviewCard key={quizCards[quizIndex].card_id} card={quizCards[quizIndex]} onDone={finishQuestion} />
      </section>}

      {quizComplete && <section className="panel topic-quiz-result">
        <span className="eyebrow">TOPIC QUIZ COMPLETE</span>
        <h2>{quizResults.filter((r) => r.correct).length} of {quizResults.length} correct</h2>
        <p>This lesson is marked complete and every question has been scheduled for its next review.</p>
        <div className="topic-result-actions">
          <button className="btn ghost" onClick={() => { setQuizIndex(0); setQuizResults([]); }}>Retry quiz</button>
          <button className="btn ghost" onClick={() => { setQuizIndex(null); window.scrollTo({ top: 0, left: 0, behavior: "smooth" }); }}>Review lesson</button>
          {nav?.next ? <Link className="btn primary" to={`/topics/${nav.next.id}`}>Next lesson →</Link> : <Link className="btn primary" to={nav ? "/make-me-learn" : "/topics"}>Finish →</Link>}
        </div>
      </section>}

      <TopicChat key={topic.id} topic={topic} />
    </div>
  );
}

function TopicChat({ topic }: { topic: any }) {
  const [mode, setMode] = useState<ChatMode>("tutor");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMode("tutor");
    setMessages([]);
    setInput("");
    setBusy(false);
  }, [topic.id]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, busy]);

  const lessonContext = `Topic: ${topic.title}\nTrack: ${topic.track}\nSummary: ${topic.summary || ""}\nLesson:\n${topic.lesson_md}`;
  const quizInstructions = `${lessonContext}\n\nYou are conducting a rigorous oral quiz on only this topic. Ask exactly one question at a time. After each learner answer, briefly state what was correct or missing, then ask one harder follow-up. Do not reveal an answer before the learner attempts it. Keep each turn concise.`;

  async function switchMode(next: ChatMode) {
    setMode(next);
    setMessages([]);
    setInput("");
    if (next === "quiz") {
      setBusy(true);
      try {
        const response = await api.ask("Begin the oral quiz with the first question.", quizInstructions);
        setMessages([{ role: "assistant", content: response.answer }]);
      } catch {
        setMessages([{ role: "assistant", content: "The DGX tutor is unavailable right now." }]);
      } finally {
        setBusy(false);
      }
    }
  }

  async function send() {
    const value = input.trim();
    if (!value || busy) return;
    const userMessage: ChatMessage = { role: "user", content: value };
    const history = messages.slice(-8);
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setBusy(true);
    try {
      const context = mode === "quiz" ? quizInstructions : lessonContext;
      const response = await api.ask(value, context, history);
      setMessages((current) => [...current, { role: "assistant", content: response.answer }]);
    } catch {
      setMessages((current) => [...current, { role: "assistant", content: "The DGX tutor is unavailable right now." }]);
    } finally {
      setBusy(false);
    }
  }

  return <section className="panel topic-chat" aria-labelledby="topic-chat-title">
    <div className="topic-chat-head">
      <div><span className="eyebrow">DGX · TOPIC GROUNDED</span><h2 id="topic-chat-title">Tutor this topic</h2></div>
      <div className="topic-chat-modes" role="group" aria-label="Topic chat mode">
        <button className={`filter-btn${mode === "tutor" ? " on" : ""}`} onClick={() => switchMode("tutor")} disabled={busy}>Tutor</button>
        <button className={`filter-btn${mode === "quiz" ? " on" : ""}`} onClick={() => switchMode("quiz")} disabled={busy}>Quiz me</button>
      </div>
    </div>
    <p className="muted">{mode === "quiz" ? "Answer aloud or in writing. The tutor will evaluate and keep increasing the difficulty." : "Ask for an explanation, example, analogy, or deeper technical detail from this lesson."}</p>
    <div className="topic-chat-log" aria-live="polite">
      {!messages.length && !busy && <div className="topic-chat-empty">Ask anything about {topic.title}.</div>}
      {messages.map((message, index) => <div className={`bubble ${message.role === "user" ? "user" : "assistant"}`} key={index}>
        {message.role === "assistant" ? <div className="md"><Markdown>{message.content}</Markdown></div> : message.content}
      </div>)}
      {busy && <div className="bubble assistant"><span className="loading">the DGX tutor is thinking</span></div>}
      <div ref={endRef} />
    </div>
    <div className="topic-chat-input">
      <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } }} placeholder={mode === "quiz" ? "Answer the tutor's question…" : "Ask about this topic…"} disabled={busy} />
      <button className="btn primary" onClick={send} disabled={busy || !input.trim()}>Send</button>
    </div>
  </section>;
}
