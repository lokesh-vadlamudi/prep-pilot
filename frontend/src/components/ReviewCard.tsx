import { useState } from "react";
import Markdown from "./Markdown";
import { api, Card, SubmitResult, trackClass } from "../api";

export default function ReviewCard({ card, onDone }: { card: Card; onDone: (result?: SubmitResult) => void }) {
  const [selected, setSelected] = useState<string>("");
  const [text, setText] = useState("");
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [reveal, setReveal] = useState<{ answer: string; explanation: string } | null>(null);

  const isMcq = card.kind === "mcq";
  const isFree = card.kind === "free" || card.kind === "code";

  async function gradeMcq(choice: string) {
    if (result) return;
    setSelected(choice);
    setBusy(true);
    setResult(await api.submit({ card_id: card.card_id, user_answer: choice }));
    setBusy(false);
  }

  async function gradeFree() {
    setBusy(true);
    setResult(await api.submit({ card_id: card.card_id, user_answer: text }));
    setBusy(false);
  }

  async function showAnswer() {
    setBusy(true);
    const d = await api.card(card.card_id);
    setReveal({ answer: d.answer, explanation: d.explanation });
    setBusy(false);
  }

  async function selfGrade(g: number) {
    setBusy(true);
    setResult(await api.submit({ card_id: card.card_id, user_answer: text, self_grade: g }));
    setBusy(false);
  }

  return (
    <div className="qcard">
      <div className="meta">
        <span className={"chip " + trackClass(card.track)}>{card.track}</span>
        <span className="mono" style={{ color: "var(--faint)", fontSize: 12 }}>{card.concept_title}</span>
        {card.is_new && <span className="new-badge">NEW</span>}
      </div>

      <div className="prompt">{card.prompt}</div>

      {isMcq && (
        <div className="choices">
          {card.choices.map((c) => {
            let cls = "choice";
            if (result) {
              if (c === result.answer) cls += " correct";
              else if (c === selected) cls += " wrong";
            } else if (c === selected) cls += " selected";
            return (
              <button key={c} className={cls} onClick={() => gradeMcq(c)} disabled={!!result || busy}>
                {c}
              </button>
            );
          })}
        </div>
      )}

      {isFree && !result && (
        <>
          <textarea
            className="answer"
            placeholder="Answer as if whiteboarding in the interview — the DGX tutor will grade it."
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={busy}
          />
          <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
            <button className="btn" onClick={gradeFree} disabled={busy || text.trim().length < 3}>
              {busy ? "Grading…" : "Grade my answer"}
            </button>
            {!reveal && (
              <button className="btn ghost" onClick={showAnswer} disabled={busy}>
                Skip / show answer
              </button>
            )}
          </div>
          {busy && <p className="loading" style={{ marginTop: 12 }}>DGX brain is working</p>}
          {reveal && (
            <div className="verdict">
              <div className="reference md"><b>Reference answer</b><Markdown>{"\n\n" + reveal.answer}</Markdown></div>
              {reveal.explanation && <p className="reference" style={{ marginTop: 8 }}>{reveal.explanation}</p>}
              <div className="self-grade">
                <span className="mono" style={{ alignSelf: "center", color: "var(--faint)", fontSize: 12 }}>How did you do?</span>
                <button className="sg" onClick={() => selfGrade(2)}>Missed it</button>
                <button className="sg" onClick={() => selfGrade(3)}>Shaky</button>
                <button className="sg" onClick={() => selfGrade(4)}>Solid</button>
                <button className="sg" onClick={() => selfGrade(5)}>Nailed it</button>
              </div>
            </div>
          )}
        </>
      )}

      {result && (
        <div className="verdict">
          <div className="grade-line">
            <span className={"grade-badge " + (result.correct ? "good" : "bad")}>
              {result.correct ? "✓ correct" : "✗ review"} · grade {result.grade}/5
            </span>
            <span className="next">next check in {result.next_review_days}d</span>
          </div>
          {result.ai_feedback && <div className="feedback">{result.ai_feedback}</div>}
          {!isMcq && <div className="reference"><b>Reference:</b> {result.answer}</div>}
          {result.explanation && <p className="reference" style={{ marginTop: 10 }}>{result.explanation}</p>}
        </div>
      )}

      {(result || reveal) && (
        <FollowUp
          card={card}
          userAnswer={isMcq ? selected : text}
          answer={result?.answer ?? reveal?.answer ?? ""}
          explanation={result?.explanation ?? reveal?.explanation ?? ""}
          feedback={result?.ai_feedback ?? ""}
        />
      )}

      {result && <button className="btn" style={{ marginTop: 20 }} onClick={() => onDone(result)}>Next →</button>}
    </div>
  );
}

function FollowUp({
  card, userAnswer, answer, explanation, feedback,
}: {
  card: Card; userAnswer: string; answer: string; explanation: string; feedback: string;
}) {
  const [q, setQ] = useState("");
  const [thread, setThread] = useState<{ q: string; a: string }[]>([]);
  const [asking, setAsking] = useState(false);

  async function ask() {
    const question = q.trim();
    if (!question) return;
    setAsking(true);
    setQ("");
    const context =
      `The learner just reviewed this flashcard and wants to go deeper.\n` +
      `Concept: ${card.concept_title} (${card.track})\n` +
      `Question on the card: ${card.prompt}\n` +
      (answer ? `Reference answer: ${answer}\n` : "") +
      (explanation ? `Explanation shown: ${explanation}\n` : "") +
      (userAnswer ? `The learner's own answer was: ${userAnswer}\n` : "") +
      (feedback ? `Feedback they got: ${feedback}\n` : "") +
      `Answer their follow-up in that context; be concise and concrete.`;
    try {
      const r = await api.ask(question, context);
      setThread((t) => [...t, { q: question, a: r.answer }]);
    } catch {
      setThread((t) => [...t, { q: question, a: "_The DGX brain is unreachable right now._" }]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="followup">
      <div className="eyebrow" style={{ marginBottom: 8 }}>Ask a follow-up · DGX</div>
      {thread.map((t, i) => (
        <div key={i} className="fu-turn">
          <div className="fu-q">{t.q}</div>
          <div className="md fu-a"><Markdown>{t.a}</Markdown></div>
        </div>
      ))}
      {asking && <p className="loading" style={{ margin: "6px 0" }}>the DGX brain is answering</p>}
      <div className="fu-input">
        <input
          placeholder="e.g. why not use a different approach here? (Enter to send)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") ask(); }}
          disabled={asking}
        />
        <button className="btn ghost" onClick={ask} disabled={asking || !q.trim()}>Ask</button>
      </div>
    </div>
  );
}
