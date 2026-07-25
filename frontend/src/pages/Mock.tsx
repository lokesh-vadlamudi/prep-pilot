import { useEffect, useRef, useState } from "react";
import Markdown from "../components/Markdown";
import { api } from "../api";

type Turn = { role: "interviewer" | "candidate"; content: string };
type Kind = "coding" | "system_design" | "behavioral";
const KINDS: { id: Kind; label: string; blurb: string }[] = [
  { id: "coding", label: "Coding", blurb: "Algorithms round — think aloud, complexity, edge cases." },
  { id: "system_design", label: "System Design", blurb: "Design a system; defend scale & trade-offs." },
  { id: "behavioral", label: "Behavioral", blurb: "STAR stories — scope, impact, ownership." },
];

export default function Mock() {
  const [phase, setPhase] = useState<"setup" | "live" | "done">("setup");
  const [kind, setKind] = useState<Kind>("coding");
  const [topic, setTopic] = useState("");
  const [duration, setDuration] = useState(40);

  const [sid, setSid] = useState<number | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [rubric, setRubric] = useState<any>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [turns, busy]);

  // countdown
  useEffect(() => {
    if (phase !== "live") return;
    const t = setInterval(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [phase]);

  async function start() {
    setBusy(true);
    try {
      const r = await api.mockStart({ kind, topic, duration_min: duration });
      setSid(r.id);
      setTurns([{ role: "interviewer", content: r.message }]);
      setSecondsLeft(duration * 60);
      setPhase("live");
    } finally { setBusy(false); }
  }

  async function send() {
    if (!msg.trim() || !sid) return;
    const mine = msg;
    setTurns((t) => [...t, { role: "candidate", content: mine }]);
    setMsg("");
    setBusy(true);
    try {
      const r = await api.mockReply(sid, mine);
      setTurns((t) => [...t, { role: "interviewer", content: r.message }]);
    } finally { setBusy(false); }
  }

  async function finish() {
    if (!sid) return;
    setBusy(true);
    try {
      setRubric(await api.mockFinish(sid));
      setPhase("done");
    } finally { setBusy(false); }
  }

  const mmss = `${String(Math.floor(secondsLeft / 60)).padStart(2, "0")}:${String(secondsLeft % 60).padStart(2, "0")}`;

  // ---------- setup ----------
  if (phase === "setup") {
    return (
      <>
        <div className="page-head">
          <div className="eyebrow">Mock interview · DGX interviewer</div>
          <h1>Sit a mock interview</h1>
          <p>A timed round with the DGX as your interviewer — it probes with follow-ups, then scores you on a real rubric.</p>
        </div>
        <div className="panel">
          <div className="eyebrow" style={{ marginBottom: 10 }}>Round type</div>
          <div className="grid three" style={{ marginBottom: 20 }}>
            {KINDS.map((k) => (
              <button key={k.id} className={"mock-kind" + (kind === k.id ? " on" : "")} onClick={() => setKind(k.id)}>
                <div className="mk-label">{k.label}</div>
                <div className="mk-blurb">{k.blurb}</div>
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: 220 }}>
              <label>Focus (optional)</label>
              <input value={topic} onChange={(e) => setTopic(e.target.value)}
                placeholder={kind === "system_design" ? "e.g. design a rate limiter" : kind === "behavioral" ? "e.g. conflict, leadership" : "e.g. graphs, DP"} />
            </div>
            <div className="field" style={{ marginBottom: 0 }}>
              <label>Duration</label>
              <select value={duration} onChange={(e) => setDuration(Number(e.target.value))}
                style={{ background: "var(--surface-2)", border: "1px solid var(--line)", borderRadius: 8, color: "var(--text)", padding: "12px 14px" }}>
                <option value={20}>20 min</option><option value={30}>30 min</option>
                <option value={40}>40 min</option><option value={60}>60 min</option>
              </select>
            </div>
            <button className="btn" onClick={start} disabled={busy}>{busy ? "Starting…" : "Start interview"}</button>
          </div>
        </div>
      </>
    );
  }

  // ---------- done: scorecard ----------
  if (phase === "done" && rubric) {
    const v = (rubric.verdict || "").toLowerCase();
    const good = v.includes("hire") && !v.includes("no hire");
    return (
      <>
        <div className="page-head">
          <div className="eyebrow">Scorecard · {KINDS.find((k) => k.id === kind)?.label}</div>
          <h1>How you did</h1>
        </div>
        <div className="panel">
          <div className="score-top">
            <div className="metric"><div className={"num" + (good ? " teal" : "")}>{rubric.overall}/5</div><div className="lbl">Overall</div></div>
            <span className={"verdict-badge " + (good ? "good" : "bad")}>{rubric.verdict}</span>
          </div>
          <div style={{ marginTop: 18 }}>
            {(rubric.dimensions || []).map((d: any) => (
              <div className="gauge" key={d.name} style={{ marginBottom: 14 }}>
                <div className="top"><span className="name">{d.name.replace(/_/g, " ")}</span><span className="val">{d.score}/5</span></div>
                <div className="bar"><span style={{ width: `${(d.score / 5) * 100}%` }} /></div>
                <p className="dim-note">{d.note}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="grid two">
          <div className="panel"><div className="eyebrow" style={{ marginBottom: 10, color: "var(--teal)" }}>Strengths</div>
            <ul className="fb-list">{(rubric.strengths || []).map((s: string, i: number) => <li key={i}>{s}</li>)}</ul></div>
          <div className="panel"><div className="eyebrow" style={{ marginBottom: 10, color: "var(--amber)" }}>Work on next</div>
            <ul className="fb-list">{(rubric.improvements || []).map((s: string, i: number) => <li key={i}>{s}</li>)}</ul></div>
        </div>
        <button className="btn" style={{ marginTop: 16 }} onClick={() => { setPhase("setup"); setTurns([]); setRubric(null); setSid(null); }}>New interview</button>
      </>
    );
  }

  // ---------- live ----------
  return (
    <div className="mock-live">
      <div className="mock-bar">
        <span className="eyebrow">{KINDS.find((k) => k.id === kind)?.label} interview</span>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span className={"timer" + (secondsLeft <= 60 ? " low" : "")}>{mmss}</span>
          <button className="btn ghost" onClick={finish} disabled={busy}>End & get feedback</button>
        </div>
      </div>
      <div className="mock-log">
        {turns.map((t, i) => (
          <div key={i} className={"bubble " + (t.role === "interviewer" ? "assistant" : "user")}>
            {t.role === "interviewer" ? <div className="md"><Markdown>{t.content}</Markdown></div> : t.content}
          </div>
        ))}
        {busy && <div className="bubble assistant"><span className="loading">interviewer is thinking</span></div>}
        <div ref={endRef} />
      </div>
      <div className="mock-input">
        <textarea
          placeholder="Think out loud — type your answer, ⌘/Ctrl+Enter to send"
          value={msg}
          onChange={(e) => setMsg(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send(); }}
          disabled={busy}
        />
        <button className="btn" onClick={send} disabled={busy || !msg.trim()}>Send</button>
      </div>
    </div>
  );
}
