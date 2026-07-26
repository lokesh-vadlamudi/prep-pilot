import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, Card, Plan, diffClass } from "../api";
import ReviewCard from "../components/ReviewCard";

function Mission() {
  const [rm, setRm] = useState<any>(null);
  useEffect(() => { api.roadmap().then(setRm).catch(() => {}); }, []);
  if (!rm) return null;
  const cur = rm.phases[rm.current_phase];
  const nowHM = new Date().toTimeString().slice(0, 5);
  let liveIdx = -1;
  rm.mission.slots.forEach((s: any, i: number) => { if (s.time <= nowHM) liveIdx = i; });
  const upcoming = rm.mission.slots.slice(Math.max(liveIdx, 0), Math.max(liveIdx, 0) + 2);
  return (
    <div className="panel">
      <div className="kicker">
        <span className="eyebrow" title={`Week ${rm.week}/${rm.total_weeks} · leg ${cur.callsign}`}>Today's mission · wk {rm.week}</span>
        <span className="chip ai">{rm.mission.track_label}</span>
      </div>
      <ul className="mission-list compact">
        {upcoming.map((s: any, i: number) => (
          <li key={s.time} className={i === 0 && liveIdx >= 0 ? "live" : ""}>
            <span className="mono time">{s.time}</span>
            <span>{s.title}</span>
            {i === 0 && liveIdx >= 0 && <span className="chip ai now-chip">now</span>}
          </li>
        ))}
      </ul>
      <Link to="/plan" className="btn ghost" style={{ display: "inline-block", marginTop: 12 }}>
        Full flight plan →
      </Link>
    </div>
  );
}

function Books() {
  const [books, setBooks] = useState<any[]>([]);
  useEffect(() => { api.books().then(setBooks).catch(() => {}); }, []);
  if (!books.length) return null;
  return (
    <div className="panel s12">
      <div className="eyebrow" style={{ marginBottom: 14 }}>Your books · studied in reading order</div>
      {books.map((b) => {
        const pct = b.total ? Math.round((b.seen / b.total) * 100) : 0;
        return (
          <div className="gauge" key={b.book} style={{ marginBottom: 16 }}>
            <div className="top">
              <span className="name">{b.book}</span>
              <span className="val">{b.seen}/{b.total} sections · {b.current_chapter}</span>
            </div>
            <div className="bar"><span style={{ width: `${pct}%` }} /></div>
          </div>
        );
      })}
      <p style={{ color: "var(--faint)", fontSize: 12.5, marginTop: 4 }}>
        New book sections unlock in order each day; everything you've seen comes back for review.
      </p>
    </div>
  );
}

function CodingTarget() {
  const [t, setT] = useState<any>(null);
  const [editing, setEditing] = useState(false);
  const [target, setTarget] = useState(2);
  const [goalDate, setGoalDate] = useState("");

  const load = () => api.targetStatus().then((r) => {
    setT(r); setTarget(r.daily_problem_target);
    setGoalDate(r.pace?.goal_date || "");
  });
  useEffect(() => { load(); }, []);
  if (!t) return null;

  async function save() {
    await api.setTarget({ daily_problem_target: target, goal_date: goalDate });
    setEditing(false);
    load();
  }

  const done = t.solved_today;
  const goal = t.daily_problem_target;
  const dots = Array.from({ length: Math.max(goal, done) });

  return (
    <div className="panel target-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <span className="eyebrow">Daily coding target</span>
        <button className="filter-btn" onClick={() => setEditing((e) => !e)}>{editing ? "cancel" : "edit"}</button>
      </div>

      {editing ? (
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end", marginTop: 12, flexWrap: "wrap" }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>Problems / day</label>
            <input type="number" min={1} max={20} value={target} onChange={(e) => setTarget(Number(e.target.value))} style={{ width: 90 }} />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>Goal date</label>
            <input type="date" value={goalDate} onChange={(e) => setGoalDate(e.target.value)} />
          </div>
          <button className="btn" onClick={save}>Save</button>
        </div>
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 10, flexWrap: "wrap" }}>
            <span className="mono" style={{ fontSize: 15 }}>
              <b style={{ color: done >= goal ? "var(--teal)" : "var(--amber)" }}>{done}</b>
              <span style={{ color: "var(--faint)" }}> / {goal} today</span>
            </span>
            {t.target_met_today && <span className="pace-tag ok">✓ target met</span>}
            {t.pace && (
              <span className={"pace-tag " + (t.pace.on_track ? "ok" : "behind")}>
                {t.pace.on_track ? "on track" : "behind"} · {t.pace.needed_per_day}/day to hit {t.total_solved + t.pace.remaining} by {t.pace.days_left}d
              </span>
            )}
          </div>
          <div className="bars">
            {dots.map((_, i) => (
              <span key={i} className={"target-dot" + (i < done ? " done" : "")}>{i < done ? "✓" : ""}</span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function ProblemOfDay() {
  const [pod, setPod] = useState<any>(null);
  useEffect(() => { api.problemOfTheDay().then(setPod).catch(() => {}); }, []);
  if (!pod || !pod.problem) return null;
  const p = pod.problem;
  return (
    <div className="panel pod">
      <div className="kicker">
        <span className="eyebrow">Problem of the day</span>
        <span className="chip ai">{pod.reason === "revision" ? "revisit" : pod.reason === "phase" ? "this leg" : "new"}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
        <span className={"chip " + diffClass(p.difficulty)}>{p.difficulty}</span>
        <span className="chip">{p.category}</span>
        <a href={p.url} target="_blank" rel="noreferrer" style={{ fontFamily: "var(--display)", fontWeight: 600, fontSize: 18 }}>
          {p.title} ↗
        </a>
      </div>
      <p style={{ color: "var(--muted)", margin: "10px 0 0" }}>{p.blurb}</p>
      <p className="prob-pattern" style={{ marginTop: 6 }}>{p.pattern}</p>
      <Link to="/problems" className="btn ghost" style={{ display: "inline-block", marginTop: 14 }}>
        Open in Blind 75 →
      </Link>
    </div>
  );
}

export default function Today() {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [started, setStarted] = useState(false);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    api.today().then(setPlan);
  }, []);

  // Reviews first (spaced-repetition due), then new material.
  const queue: Card[] = useMemo(
    () => (plan ? [...plan.reviews, ...plan.new] : []),
    [plan]
  );

  if (!plan) return <div className="loading">loading flight plan</div>;

  const dateStr = new Date(plan.date + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "long", month: "long", day: "numeric",
  });

  if (!started) {
    const total = queue.length;
    return (
      <>
        <div className="page-head">
          <div className="eyebrow">{dateStr}</div>
          <h1>Today's pre-flight</h1>
          <p>Clear your review checks, then take on new territory. Consistency compounds.</p>
        </div>

        <div className="deck">
          <div className="s7 stack">
          <div className="panel">
            <div className="readout">
              <div className="metric">
                <div className="num">{plan.reviews.length}</div>
                <div className="lbl">Due reviews</div>
              </div>
              <div className="metric">
                <div className="num teal">{plan.new.length}</div>
                <div className="lbl">New topics</div>
              </div>
              <div className="metric">
                <div className="num plain">{plan.streak}</div>
                <div className="lbl">Day streak</div>
              </div>
            </div>
            <div style={{ marginTop: 26 }}>
              {total > 0 ? (
                <button className="btn" onClick={() => setStarted(true)}>
                  Begin session · {total} card{total === 1 ? "" : "s"}
                </button>
              ) : (
                <div className="empty">
                  <div className="big">✓</div>
                  <p>All checks cleared for today. New material unlocks tomorrow — or generate more from the syllabus.</p>
                </div>
              )}
            </div>
          </div>
          <ProblemOfDay />
          </div>

          <div className="s5 stack">
            <Mission />
            <CodingTarget />
          </div>

          <Books />
        </div>
      </>
    );
  }

  if (idx >= queue.length) {
    return (
      <>
        <div className="page-head">
          <div className="eyebrow">Session complete</div>
          <h1>Checks cleared ✓</h1>
        </div>
        <div className="panel empty">
          <div className="big">{plan.streak + (plan.reviews.length === 0 ? 1 : 0)}d</div>
          <p>Nice work. Everything you saw is scheduled for its next review automatically.</p>
          <button className="btn" onClick={() => { setStarted(false); setIdx(0); api.today().then(setPlan); }}>
            Back to overview
          </button>
        </div>
      </>
    );
  }

  const card = queue[idx];
  return (
    <div className="review-stage">
      <div className="review-progress">
        <span>CARD {idx + 1} / {queue.length}</span>
        <span>{card.is_new ? "NEW MATERIAL" : "SPACED REVIEW"}</span>
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${(idx / queue.length) * 100}%` }} />
      </div>
      <ReviewCard key={card.card_id} card={card} onDone={() => setIdx((i) => i + 1)} />
    </div>
  );
}
