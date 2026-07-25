import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

type Phase = {
  index: number; key: string; callsign: string; name: string; motto: string;
  start: string; end: string; status: "cleared" | "current" | "upcoming";
  focus: { code: string; design: string; dgx: string; read: string; story: string };
  categories: string[];
  coding: { total: number; solved: number };
};

type Roadmap = {
  today: string; start: string; end: string;
  week: number; total_weeks: number; pct: number; current_phase: number;
  phases: Phase[];
  mission: { track: string; track_label: string; slots: { time: string; title: string }[] };
  rhythm: { day: string; track: string }[];
};

const FOCUS_ROWS: { key: keyof Phase["focus"]; icon: string; label: string }[] = [
  { key: "code", icon: "🧩", label: "Coding" },
  { key: "design", icon: "📐", label: "Design" },
  { key: "dgx", icon: "⚡", label: "DGX lab" },
  { key: "read", icon: "📖", label: "Reading" },
  { key: "story", icon: "🗣️", label: "Behavioral" },
];

const fmt = (iso: string) =>
  new Date(iso + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" });

export default function FlightPlan() {
  const [rm, setRm] = useState<Roadmap | null>(null);
  useEffect(() => { api.roadmap().then(setRm).catch(() => {}); }, []);
  if (!rm) return <div className="loading">loading flight plan</div>;

  const cur = rm.phases[rm.current_phase];
  const nowHM = new Date().toTimeString().slice(0, 5);
  // Current slot = last slot whose time has passed.
  let liveIdx = -1;
  rm.mission.slots.forEach((s, i) => { if (s.time <= nowHM) liveIdx = i; });

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">
          Week {rm.week} of {rm.total_weeks} · leg {rm.current_phase + 1}/6 · {fmt(rm.start)} → {fmt(rm.end)}
        </div>
        <h1>Flight plan</h1>
        <p>{cur.motto}</p>
      </div>

      {/* Flight path: six legs, plane at today's position */}
      <div className="panel">
        <div className="flightpath">
          {rm.phases.map((p) => (
            <div key={p.key} className={"leg-seg " + p.status} title={`${p.callsign} · ${fmt(p.start)}–${fmt(p.end)}`}>
              <span className="leg-tick">{p.callsign}</span>
            </div>
          ))}
          <span className="plane" style={{ left: `${rm.pct}%` }}>✈</span>
        </div>
        <div className="flightpath-meta">
          <span>{fmt(rm.start)} · wheels up</span>
          <span className="mono" style={{ color: "var(--amber)" }}>{rm.pct}% of the route flown</span>
          <span>{fmt(rm.end)} · interviews</span>
        </div>
      </div>

      {/* Today's mission */}
      <div className="panel">
        <div className="kicker">
          <span className="eyebrow">Today's mission</span>
          <span className="chip ai">{rm.mission.track_label}</span>
        </div>
        <ul className="mission-list">
          {rm.mission.slots.map((s, i) => (
            <li key={s.time} className={i === liveIdx ? "live" : i < liveIdx ? "past" : ""}>
              <span className="mono time">{s.time}</span>
              <span>{s.title}</span>
              {i === liveIdx && <span className="chip ai now-chip">now</span>}
            </li>
          ))}
        </ul>
      </div>

      {/* Weekly rhythm */}
      <div className="panel">
        <div className="eyebrow" style={{ marginBottom: 12 }}>Weekly rhythm</div>
        <div className="rhythm">
          {rm.rhythm.map((r, i) => (
            <div key={r.day} className={"rhythm-day" + (i === (new Date().getDay() + 6) % 7 ? " today" : "")}>
              <span className="mono d">{r.day}</span>
              <span className="t">{r.track}</span>
            </div>
          ))}
        </div>
      </div>

      {/* The six legs */}
      <div className="legs">
        {rm.phases.map((p) => {
          const pct = p.coding.total ? Math.round((p.coding.solved / p.coding.total) * 100) : 0;
          return (
            <div key={p.key} className={"panel leg-card " + p.status}>
              <div className="kicker">
                <span className="mono callsign">{p.callsign}</span>
                <span className={"chip " + (p.status === "current" ? "ai" : "")}>
                  {p.status === "cleared" ? "✓ cleared" : p.status === "current" ? "▶ flying" : "upcoming"}
                </span>
              </div>
              <div className="leg-title">
                M{p.index + 1} · {p.name}
                <span className="dates">{fmt(p.start)} – {fmt(p.end)}</span>
              </div>
              <p className="leg-motto">{p.motto}</p>
              <div className="leg-focus">
                {FOCUS_ROWS.map((f) => (
                  <div className="row" key={f.key}>
                    <span className="ic">{f.icon}</span>
                    <span>{p.focus[f.key]}</span>
                  </div>
                ))}
              </div>
              <div className="gauge" style={{ marginTop: 14 }}>
                <div className="top">
                  <span className="name">{p.categories.length ? "leg problems" : "all problems"}</span>
                  <span className="val">{p.coding.solved}/{p.coding.total} solved</span>
                </div>
                <div className="bar"><span style={{ width: `${pct}%` }} /></div>
              </div>
            </div>
          );
        })}
      </div>

      <p style={{ color: "var(--faint)", fontSize: 12.5, marginTop: 16 }}>
        Problem-of-the-day follows the current leg's categories automatically, and Alfred's
        Telegram pings pull live numbers from this plan. Land the last leg with the writeup
        published and applications out. <Link to="/problems">Fly today's problems →</Link>
      </p>
    </>
  );
}
