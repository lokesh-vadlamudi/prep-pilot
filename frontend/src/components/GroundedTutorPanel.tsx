import { useEffect, useRef, useState } from "react";
import { describeApiError, newRequestId } from "../api";
import Markdown from "./Markdown";

export type GroundedTutorTurn = {
  id: string;
  prompt: string;
  response: string;
  feedback: string;
  nextQuestion?: string;
};

export type GroundedTutorResult = GroundedTutorTurn & { nextQuestion: string };

type Props = {
  identityKey: string;
  title: string;
  prompt: string;
  turns: GroundedTutorTurn[];
  eyebrow?: string;
  helperText?: string;
  placeholder?: string;
  onSubmit: (response: string, requestId: string, turns: GroundedTutorTurn[]) => Promise<GroundedTutorResult>;
};

function useGroundedAction(identityKey: string, persistedTurns: GroundedTutorTurn[], onSubmit: Props["onSubmit"]) {
  const [draft, setDraftState] = useState("");
  const [requestId, setRequestId] = useState(() => newRequestId());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [localTurns, setLocalTurns] = useState<GroundedTutorTurn[]>([]);
  const attempted = useRef<string | null>(null);
  const generation = useRef(0);
  const identity = useRef(identityKey);

  useEffect(() => {
    if (identity.current === identityKey) return;
    identity.current = identityKey; generation.current += 1; attempted.current = null;
    setDraftState(""); setBusy(false); setError(""); setLocalTurns([]); setRequestId(newRequestId());
  }, [identityKey]);

  useEffect(() => () => { generation.current += 1; }, []);

  function setDraft(value: string) {
    if (attempted.current !== null && value !== attempted.current) {
      generation.current += 1; attempted.current = null; setRequestId(newRequestId()); setBusy(false); setError("");
    }
    setDraftState(value);
  }

  async function submit() {
    const value = draft.trim();
    if (!value || busy) return;
    attempted.current = value; setBusy(true); setError("");
    const action = ++generation.current;
    try {
      const result = await onSubmit(value, requestId, [...persistedTurns, ...localTurns]);
      if (action !== generation.current) return;
      setLocalTurns((current) => [...current, result]); setDraftState(""); attempted.current = null; setRequestId(newRequestId());
    } catch (reason) {
      if (action === generation.current) setError(describeApiError(reason));
    } finally {
      if (action === generation.current) setBusy(false);
    }
  }

  return { draft, setDraft, busy, error, localTurns, submit };
}

function TutorHistory({ turns }: { turns: GroundedTutorTurn[] }) {
  if (!turns.length) return null;
  return <div className="grounded-turns" aria-label="Saved interview turns">{turns.map((turn) => <article className="grounded-turn" key={turn.id}>
    <p className="grounded-prompt"><strong>Prompt:</strong> {turn.prompt}</p>
    <p><strong>Your response:</strong> {turn.response}</p>
    <div className="md grounded-feedback"><strong>Qualitative feedback</strong><Markdown>{turn.feedback}</Markdown></div>
  </article>)}</div>;
}

export default function GroundedTutorPanel(props: Props) {
  const action = useGroundedAction(props.identityKey, props.turns, props.onSubmit);
  const turns = [...props.turns, ...action.localTurns];
  const currentPrompt = turns[turns.length - 1]?.nextQuestion || props.prompt;
  return <section className="panel topic-chat grounded-tutor" aria-labelledby={`grounded-${props.identityKey.replace(/\W/g, "-")}`}>
    <div className="topic-chat-head"><div><span className="eyebrow">{props.eyebrow || "DGX · SOURCE GROUNDED"}</span><h2 id={`grounded-${props.identityKey.replace(/\W/g, "-")}`}>{props.title}</h2></div></div>
    {props.helperText && <p className="muted">{props.helperText}</p>}
    <TutorHistory turns={turns} />
    <div className="grounded-current" aria-live="polite"><span className="eyebrow">CURRENT PROMPT</span><p>{currentPrompt}</p></div>
    {action.error && <p className="notice error" role="alert">{action.error}</p>}
    {action.busy && <p className="loading" role="status">the DGX tutor is reviewing this response</p>}
    <div className="topic-chat-input">
      <label className="grounded-response"><span>Your response</span><textarea value={action.draft} onChange={(event) => action.setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); action.submit(); } }} placeholder={props.placeholder || "Respond with your reasoning and evidence…"} aria-describedby={action.error ? "grounded-draft-help" : undefined} /></label>
      {action.error && <small id="grounded-draft-help">Your draft remains here for the retry.</small>}
      <button className="btn primary" onClick={action.submit} disabled={action.busy || !action.draft.trim()}>{action.error ? "Retry response" : "Send response"}</button>
    </div>
  </section>;
}
