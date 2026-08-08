import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import CodeMirror from "@uiw/react-codemirror";
import { oneDark } from "@codemirror/theme-one-dark";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { StreamLanguage } from "@codemirror/language";
import { go } from "@codemirror/legacy-modes/mode/go";
import Markdown from "../components/Markdown";
import { api, RunResult, diffClass } from "../api";

type Msg = { role: "user" | "assistant"; content: string };
type Lang = "python" | "javascript" | "go";
const LANGS: { id: Lang; label: string }[] = [
  { id: "python", label: "Python" },
  { id: "javascript", label: "JavaScript" },
  { id: "go", label: "Go" },
];
const langExt = (l: Lang) =>
  l === "python" ? python() : l === "javascript" ? javascript() : StreamLanguage.define(go);

export default function Solve({ theme }: { theme: "light" | "dark" }) {
  const { id } = useParams();
  const pid = Number(id);
  const [problem, setProblem] = useState<any>(null);
  const [lang, setLang] = useState<Lang>("python");
  const [code, setCode] = useState("");
  const [starterLoading, setStarterLoading] = useState(true);
  const [result, setResult] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);

  // hint ladder
  const [hints, setHints] = useState<string[]>([]);
  const [revealed, setRevealed] = useState(0);
  const [hintsLoading, setHintsLoading] = useState(false);

  // mentor chat
  const [chat, setChat] = useState<Msg[]>([]);
  const [msg, setMsg] = useState("");
  const [mentorBusy, setMentorBusy] = useState(false);
  const [reviewedCode, setReviewedCode] = useState<string | null>(null);
  const chatEnd = useRef<HTMLDivElement>(null);
  const stale = reviewedCode !== null && reviewedCode !== code;

  useEffect(() => { api.problem(pid).then(setProblem); }, [pid]);

  useEffect(() => {
    setStarterLoading(true);
    setResult(null);
    api.starter(pid, lang).then((r) => {
      setCode(r.starter_code);
      setStarterLoading(false);
    }).catch(() => setStarterLoading(false));
  }, [pid, lang]);

  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [chat, mentorBusy]);

  const testSummary = (r: RunResult | null) =>
    r?.tests ? `${r.tests.passed}/${r.tests.total} tests passing` : (r ? "run errored" : "not run yet");

  async function run() {
    setRunning(true);
    setResult(null);
    try {
      const r: RunResult = await api.runCode(pid, lang, code);
      setResult(r);
      // Continuous mentoring: auto-review when something is wrong.
      const failing = !r.ok;
      if (failing) autoMentor(r);
    } finally {
      setRunning(false);
    }
  }

  async function autoMentor(r: RunResult) {
    setMentorBusy(true);
    try {
      const res = await api.mentor(pid, {
        language: lang, code, mode: "review", test_summary: testSummary(r),
        message: "My run just failed — what should I fix?", history: [],
      });
      setChat((c) => [...c, { role: "assistant", content: res.answer }]);
      setReviewedCode(code);
    } finally { setMentorBusy(false); }
  }

  async function ask(mode: "chat" | "review" | "explain", text?: string) {
    const userMsg = text ?? msg;
    if (mode === "chat" && !userMsg.trim()) return;
    const codeAtAsk = code;
    setMentorBusy(true);
    if (mode === "chat") setChat((c) => [...c, { role: "user", content: userMsg }]);
    if (mode === "explain") setChat((c) => [...c, { role: "user", content: "Explain my code line by line." }]);
    if (mode === "review") setChat((c) => [...c, { role: "user", content: "Review my current code." }]);
    setMsg("");
    try {
      const res = await api.mentor(pid, {
        language: lang, code: codeAtAsk, mode, message: mode === "chat" ? userMsg : "",
        // Only free-form chat needs prior turns; Review/Explain look at the current
        // code fresh so they don't rehash earlier (identical) feedback.
        test_summary: testSummary(result), history: mode === "chat" ? chat : [],
      });
      setChat((c) => [...c, { role: "assistant", content: res.answer }]);
      setReviewedCode(codeAtAsk);
    } finally { setMentorBusy(false); }
  }

  function clearMentor() {
    setChat([]);
    setReviewedCode(null);
  }

  async function markSolved(confidence: number) {
    await api.problemStatus(pid, { status: "solved", confidence });
    setProblem((p: any) => ({ ...p, status: "solved" }));
  }

  async function revealHint() {
    if (hints.length === 0) {
      setHintsLoading(true);
      try {
        const r = await api.problemHints(pid);
        setHints(r.hints);
        setRevealed(1);
      } finally { setHintsLoading(false); }
    } else {
      setRevealed((n) => Math.min(n + 1, hints.length));
    }
  }

  if (!problem) return <div className="loading">loading problem</div>;

  return (
    <div className="solve">
      <div className="solve-head">
        <Link to="/problems" className="mono" style={{ color: "var(--faint)", fontSize: 12 }}>← problems</Link>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8, flexWrap: "wrap" }}>
          <span className={"chip " + diffClass(problem.difficulty)}>{problem.difficulty}</span>
          <span className="chip">{problem.category}</span>
          <h1 style={{ margin: 0, fontSize: 22 }}>{problem.title}</h1>
          <a href={problem.url} target="_blank" rel="noreferrer" className="ext">open on LeetCode ↗</a>
        </div>
        <p style={{ color: "var(--muted)", margin: "8px 0 0" }}>{problem.blurb} · <span className="prob-pattern">{problem.pattern}</span></p>
      </div>

      <div className="solve-grid">
        {/* Left: editor + run + results */}
        <div className="solve-main">
          <div className="editor-bar">
            <div className="lang-tabs">
              {LANGS.map((l) => (
                <button key={l.id} className={"filter-btn" + (lang === l.id ? " on" : "")} onClick={() => setLang(l.id)}>
                  {l.label}
                </button>
              ))}
            </div>
            <button className="btn" onClick={run} disabled={running || starterLoading}>
              {running ? "Running…" : "▶ Run tests"}
            </button>
          </div>

          <div className="editor-wrap">
            {starterLoading ? (
              <div className="loading" style={{ padding: 20 }}>the DGX brain is preparing tests & starter code</div>
            ) : (
              <CodeMirror
                value={code}
                height="380px"
                theme={theme === "dark" ? oneDark : "light"}
                extensions={theme === "dark" ? [langExt(lang), oneDark] : [langExt(lang)]}
                onChange={setCode}
              />
            )}
          </div>

          <div className="hint-ladder">
            <div className="hint-bar">
              <span className="eyebrow">Hint ladder</span>
              <button className="filter-btn" onClick={revealHint}
                disabled={hintsLoading || (hints.length > 0 && revealed >= hints.length)}>
                {hintsLoading ? "…" : hints.length === 0 ? "Show a hint" : revealed >= hints.length ? "all shown" : `Next hint (${revealed}/${hints.length})`}
              </button>
            </div>
            {hints.slice(0, revealed).map((h, i) => (
              <div key={i} className="hint-rung">
                <span className="rung-num">{i + 1}</span>
                <div className="md"><Markdown>{h}</Markdown></div>
              </div>
            ))}
            {revealed > 0 && revealed >= hints.length && (
              <p className="hint-foot">Still stuck? Ask the mentor to <b>Explain</b>, or open the full worked approach from the problem list.</p>
            )}
          </div>

          {result && <Results result={result} testSummary={testSummary(result)} onSolved={markSolved} />}
        </div>

        {/* Right: mentor chat */}
        <div className="mentor">
          <div className="mentor-head">
            <span className="eyebrow">Mentor · DGX</span>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="filter-btn" onClick={() => ask("review")} disabled={mentorBusy}>Review</button>
              <button className="filter-btn" onClick={() => ask("explain")} disabled={mentorBusy}>Explain</button>
              {chat.length > 0 && (
                <button className="filter-btn" onClick={clearMentor} disabled={mentorBusy} title="Clear the mentor conversation">↺ clear</button>
              )}
            </div>
          </div>
          {stale && !mentorBusy && chat.length > 0 && (
            <button className="mentor-stale" onClick={() => ask("review")}>
              ⚠ You've edited the code since this feedback — click to re-review the latest.
            </button>
          )}
          <div className="mentor-log">
            {chat.length === 0 && !mentorBusy && (
              <p className="mentor-hint">Write code and hit Run — I'll jump in when a test fails. Or ask me to
                <b> Review</b> your approach, <b>Explain</b> it line by line, or answer any question below.</p>
            )}
            {chat.map((m, i) => (
              <div key={i} className={"bubble " + m.role}>
                {m.role === "assistant" ? <div className="md"><Markdown>{m.content}</Markdown></div> : m.content}
              </div>
            ))}
            {mentorBusy && <div className="bubble assistant"><span className="loading">thinking</span></div>}
            <div ref={chatEnd} />
          </div>
          <div className="mentor-input">
            <textarea
              placeholder="Ask the mentor… (⌘/Ctrl+Enter)"
              value={msg}
              onChange={(e) => setMsg(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask("chat"); }}
            />
            <button className="btn" onClick={() => ask("chat")} disabled={mentorBusy || !msg.trim()}>Send</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Results({ result, testSummary, onSolved }: { result: RunResult; testSummary: string; onSolved: (c: number) => void }) {
  return (
    <div className="panel" style={{ marginTop: 14 }}>
      <div className="grade-line">
        <span className={"grade-badge " + (result.ok ? "good" : "bad")}>
          {result.ok ? "✓ all tests passing" : result.timed_out ? "✗ timed out" : "✗ " + testSummary}
        </span>
        <span className="next">{result.duration_ms}ms{result.harness_validated ? "" : " · unverified harness"}</span>
      </div>

      {result.tests && (
        <div className="cases">
          {result.tests.cases.map((c, i) => (
            <div key={i} className={"case " + (c.ok ? "ok" : "bad")}>
              <span className="case-name">{c.ok ? "✓" : "✗"} {c.name}</span>
              {!c.ok && <span className="case-diff">expected <code>{c.expected}</code> · got <code>{c.got}</code></span>}
            </div>
          ))}
        </div>
      )}

      {result.stderr && (
        <pre className="stderr">{result.stderr}</pre>
      )}
      {result.stdout && (
        <details className="stdout-details"><summary>stdout</summary><pre>{result.stdout}</pre></details>
      )}

      {result.ok && (
        <div className="confidence">
          <span className="mono" style={{ alignSelf: "center", color: "var(--faint)", fontSize: 12 }}>Solved! Lock it in:</span>
          <button className="sg" onClick={() => onSolved(1)}>Shaky · 7d</button>
          <button className="sg" onClick={() => onSolved(2)}>Solid · 21d</button>
          <button className="sg" onClick={() => onSolved(3)}>Strong · 60d</button>
        </div>
      )}
    </div>
  );
}
