import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Markdown from "../components/Markdown";
import { api, ProblemItem, catClass, diffClass } from "../api";

type Cheat = { techniques: string[]; corner_cases: string[]; complexity: string };
type ListResp = {
  total: number; solved: number; blind75_total: number; blind75_solved: number;
  category_order: string[]; problems: ProblemItem[];
  cheatsheets: Record<string, Cheat>;
};

function CheatsheetCard({ category, cs }: { category: string; cs: Cheat }) {
  return (
    <div className="panel cheatsheet">
      <div className="eyebrow" style={{ marginBottom: 12 }}>{category} · cheatsheet</div>
      <div className="cheat-grid">
        <div>
          <div className="cheat-h">Techniques</div>
          <ul>{cs.techniques.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </div>
        <div>
          <div className="cheat-h danger">Corner cases to check</div>
          <ul>{cs.corner_cases.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </div>
      </div>
      <div className="cheat-cx"><b>Target complexity:</b> {cs.complexity}</div>
    </div>
  );
}

export default function Problems() {
  const [data, setData] = useState<ListResp | null>(null);
  const [coll, setColl] = useState<"NeetCode 150" | "Blind 75">("NeetCode 150");
  const [cat, setCat] = useState<string>("All");
  const [diff, setDiff] = useState<string>("All");
  const [open, setOpen] = useState<number | null>(null);

  const load = () => api.problems().then(setData);
  useEffect(() => { load(); }, []);

  const inColl = (p: ProblemItem) => coll === "NeetCode 150" || p.in_blind75;
  const shown = useMemo(() => {
    if (!data) return [];
    return data.problems.filter(
      (p) => inColl(p) && (cat === "All" || p.category === cat) && (diff === "All" || p.difficulty === diff)
    );
  }, [data, coll, cat, diff]);

  if (!data) return <div className="loading">loading problems</div>;

  const b75 = coll === "Blind 75";
  const total = b75 ? data.blind75_total : data.total;
  const solved = b75 ? data.blind75_solved : data.solved;
  const pct = Math.round((solved / total) * 100);
  const cats = ["All", ...data.category_order.filter((c) => data.problems.some((p) => p.category === c && inColl(p)))];

  async function cycleStatus(p: ProblemItem) {
    // This control is presented as a completion checkbox. Running code already
    // advances todo -> attempted, so a click here should complete the problem
    // in one step and feed the daily coding target immediately.
    const next = p.status === "solved" ? "todo" : "solved";
    const conf = next === "solved" ? Math.max(1, p.confidence) : p.confidence;
    await api.problemStatus(p.id, { status: next, confidence: conf });
    load();
  }

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">NeetCode 150 · coding patterns</div>
        <h1>Coding problems</h1>
        <p>The NeetCode 150 (Blind 75 included). Solve on LeetCode, then lock in the pattern here — the DGX brain writes the approach and grades your plan.</p>
      </div>

      <div className="panel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 16 }}>
          <div className="progress-ring">
            <span className="big">{solved}</span>
            <span className="of">/ {total} solved · {pct}% · {coll}</span>
          </div>
          <div className="filters" style={{ marginBottom: 4 }}>
            {(["NeetCode 150", "Blind 75"] as const).map((c) => (
              <button key={c} className={"filter-btn" + (coll === c ? " on" : "")}
                onClick={() => { setColl(c); setCat("All"); }}>{c}</button>
            ))}
          </div>
        </div>
        <div className="progress-track" style={{ marginTop: 14, marginBottom: 18 }}>
          <div className="progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="filters" style={{ marginBottom: 12, paddingTop: 16, borderTop: "1px solid var(--hairline-soft)" }}>
          {cats.map((c) => (
            <button key={c} className={"filter-btn" + (cat === c ? " on" : "")} onClick={() => setCat(c)}>{c}</button>
          ))}
        </div>
        <div className="filters" style={{ marginBottom: 0 }}>
          {["All", "Easy", "Medium", "Hard"].map((d) => (
            <button key={d} className={"filter-btn" + (diff === d ? " on" : "")} onClick={() => setDiff(d)}>{d}</button>
          ))}
        </div>
      </div>

      {cat !== "All" && data.cheatsheets?.[cat] && (
        <CheatsheetCard category={cat} cs={data.cheatsheets[cat]} />
      )}

      <div className="panel">
        {shown.map((p) => (
          <div key={p.id}>
            <div className="prob-row">
              <button
                className={"prob-check " + p.status}
                title={p.status === "solved" ? "Solved — click to reset" : "Click to mark solved"}
                onClick={() => cycleStatus(p)}
              >
                {p.status === "solved" ? "✓" : p.status === "attempted" ? "•" : ""}
              </button>
              <span className={"chip " + diffClass(p.difficulty)}>{p.difficulty}</span>
              <span className={"chip " + catClass(p.category)}>{p.category}</span>
              <div className="prob-title">
                <a href={p.url} target="_blank" rel="noreferrer">{p.title}</a> <span className="ext">↗</span>
                <div className="prob-pattern">{p.pattern}</div>
              </div>
              <Link className="filter-btn" to={`/problems/${p.id}/solve`}>solve →</Link>
              <button className="filter-btn" onClick={() => setOpen(open === p.id ? null : p.id)}>
                {open === p.id ? "hide" : "approach"}
              </button>
            </div>
            {open === p.id && <ProblemDetail p={p} onSolvedChange={load} />}
          </div>
        ))}
      </div>
    </>
  );
}

function ProblemDetail({ p, onSolvedChange }: { p: ProblemItem; onSolvedChange: () => void }) {
  const [approach, setApproach] = useState<string>("");
  const [loadingA, setLoadingA] = useState(false);
  const [plan, setPlan] = useState("");
  const [verdict, setVerdict] = useState<{ grade: number; on_track: boolean; feedback: string } | null>(null);
  const [coaching, setCoaching] = useState(false);

  async function reveal() {
    setLoadingA(true);
    const r = await api.problemApproach(p.id);
    setApproach(r.approach_md);
    setLoadingA(false);
  }
  async function coach() {
    setCoaching(true);
    setVerdict(await api.problemCoach(p.id, plan));
    setCoaching(false);
  }
  async function setConfidence(c: number) {
    await api.problemStatus(p.id, { status: "solved", confidence: c });
    onSolvedChange();
  }

  return (
    <div className="panel" style={{ margin: "0 0 12px 32px", background: "var(--surface-2)" }}>
      <div className="eyebrow" style={{ marginBottom: 8 }}>Blurb</div>
      <p className="reference" style={{ marginTop: 0 }}>{p.blurb}</p>

      <div className="coach-box">
        <div className="eyebrow" style={{ marginBottom: 8 }}>Whiteboard your approach — the DGX brain grades it</div>
        <textarea className="answer" style={{ marginTop: 0, minHeight: 90 }}
          placeholder="Describe your plan: pattern, key steps, complexity…"
          value={plan} onChange={(e) => setPlan(e.target.value)} disabled={coaching} />
        <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
          <button className="btn" onClick={coach} disabled={coaching || plan.trim().length < 5}>
            {coaching ? "Grading…" : "Grade my plan"}
          </button>
          <button className="btn ghost" onClick={reveal} disabled={loadingA}>
            {loadingA ? "Authoring…" : approach ? "Regenerate" : "Show worked approach"}
          </button>
        </div>
        {coaching && <p className="loading" style={{ marginTop: 10 }}>the DGX brain is grading your plan</p>}
        {verdict && (
          <div className="verdict">
            <div className="grade-line">
              <span className={"grade-badge " + (verdict.on_track ? "good" : "bad")}>
                {verdict.on_track ? "✓ on track" : "✗ rethink"} · {verdict.grade}/5
              </span>
            </div>
            <div className="feedback">{verdict.feedback}</div>
            <div className="confidence">
              <span className="mono" style={{ alignSelf: "center", color: "var(--faint)", fontSize: 12 }}>Mark solved with recall:</span>
              <button className="sg" onClick={() => setConfidence(1)}>Shaky · 7d</button>
              <button className="sg" onClick={() => setConfidence(2)}>Solid · 21d</button>
              <button className="sg" onClick={() => setConfidence(3)}>Strong · 60d</button>
            </div>
          </div>
        )}
      </div>

      {loadingA && <p className="loading" style={{ marginTop: 14 }}>the DGX brain is authoring the approach</p>}
      {approach && (
        <div className="md" style={{ marginTop: 16, borderTop: "1px solid var(--line)", paddingTop: 16 }}>
          <Markdown>{approach}</Markdown>
        </div>
      )}
    </div>
  );
}
