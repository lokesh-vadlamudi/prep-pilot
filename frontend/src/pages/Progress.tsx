import { useEffect, useState } from "react";

import { api } from "../api";

export default function Progress() {
  const [s, setS] = useState<any>(null);
  const [ps, setPs] = useState<any>(null);
  useEffect(() => {
    api.progress().then(setS);
    api.problemStats().then(setPs).catch(() => {});
  }, []);
  if (!s) return <div className="loading">loading flight log</div>;

  const maxRev = Math.max(1, ...s.activity.map((a: any) => a.total ?? a.reviews));
  const tracks = Object.entries(s.per_track) as [string, any][];

  return (
    <>
      <div className="page-head">
        <div className="eyebrow">Flight log</div>
        <h1>Your progress</h1>
        <p>Retention, mastery altitude per track, and your recent activity.</p>
      </div>

      <div className="panel">
        <div className="readout">
          <div className="metric"><div className="num">{s.streak}</div><div className="lbl">Day streak</div></div>
          <div className="metric"><div className="num plain">{s.introduced}</div><div className="lbl">Cards in rotation</div></div>
          <div className="metric"><div className="num plain">{s.attempts}</div><div className="lbl">Total reviews</div></div>
          <div className="metric"><div className="num teal">{Math.round(s.accuracy * 100)}%</div><div className="lbl">Accuracy</div></div>
        </div>
      </div>

      {ps && (
        <div className="panel">
          <div className="eyebrow" style={{ marginBottom: 12 }}>NeetCode 150 · coding</div>
          <div className="progress-ring">
            <span className="big">{ps.solved}</span>
            <span className="of">/ {ps.total} solved</span>
          </div>
          <div className="progress-track" style={{ marginTop: 12, marginBottom: 14 }}>
            <div className="progress-fill" style={{ width: `${Math.round((ps.solved / ps.total) * 100)}%` }} />
          </div>
          <div className="pill-row">
            {(["Easy", "Medium", "Hard"] as const).map((d) => (
              <span className="pill" key={d}>{d}: <b>{ps.by_difficulty[d].solved}</b>/{ps.by_difficulty[d].total}</span>
            ))}
          </div>
        </div>
      )}

      <div className="grid two">
        <div className="panel">
          <div className="eyebrow" style={{ marginBottom: 16 }}>Mastery altitude by track</div>
          {tracks.map(([name, v]) => {
            const pct = v.total ? Math.round((v.mastered / v.total) * 100) : 0;
            return (
              <div className="gauge" key={name} style={{ marginBottom: 16 }}>
                <div className="top">
                  <span className="name">{name}</span>
                  <span className="val">{v.mastered}/{v.total} mastered · {v.seen} seen</span>
                </div>
                <div className="bar"><span style={{ width: `${pct}%` }} /></div>
              </div>
            );
          })}
        </div>

        <div className="panel">
          <div className="eyebrow" style={{ marginBottom: 16 }}>Last 14 days</div>
          <div className="spark">
            {s.activity.map((a: any) => {
              const total = a.total ?? a.reviews;
              return (
                <div
                  key={a.day}
                  className={"b" + (total > 0 ? " on" : "")}
                  style={{ height: `${(total / maxRev) * 100}%` }}
                  title={`${a.day}: ${a.reviews} reviews · ${a.coding ?? 0} coding`}
                />
              );
            })}
          </div>
          <div className="mono" style={{ color: "var(--faint)", fontSize: 11, marginTop: 10, display: "flex", justifyContent: "space-between" }}>
            <span>14d ago</span><span>today</span>
          </div>
          <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 18 }}>
            A card counts as <b style={{ color: "var(--teal)" }}>mastered</b> once its review interval reaches a week —
            proof it's sticking in long-term memory, not just crammed.
          </p>
        </div>
      </div>
    </>
  );
}
