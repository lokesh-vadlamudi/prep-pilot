import { useEffect, useMemo, useState } from "react";

import { api } from "../api";

type UserRow = {
  username: string;
  level: string;
  created_at: string;
  last_login_at: string | null;
  last_active_at: string | null;
  login_days: number;
  active_days: number;
  recent_active_dates: string[];
  progress: {
    last_progress_at: string | null;
    study_days: number;
    current_streak: number;
    reviews: number;
    accuracy: number | null;
    problems_solved: number;
    problems_attempted: number;
    topics_completed: number;
    mocks_completed: number;
    cards_reviewed: number;
    cards_total: number;
  };
};

function when(value: string | null) {
  if (!value) return "Never";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value + (value.endsWith("Z") ? "" : "Z")));
}

function daysAgo(value: string | null) {
  if (!value) return Infinity;
  return Math.floor((Date.now() - new Date(value + (value.endsWith("Z") ? "" : "Z")).getTime()) / 86400000);
}

export default function AdminDashboard() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<{ window_days: number; users: UserRow[] } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api.adminAudit(days).then(setData).catch(() => setError("Unable to load the admin report."));
  }, [days]);

  const summary = useMemo(() => {
    const users = data?.users || [];
    return {
      users: users.length,
      active: users.filter((u) => u.active_days > 0).length,
      progressing: users.filter((u) => u.progress.last_progress_at && daysAgo(u.progress.last_progress_at) < days).length,
      solved: users.reduce((total, u) => total + u.progress.problems_solved, 0),
    };
  }, [data, days]);

  return (
    <>
      <div className="page-head admin-head">
        <div>
          <div className="eyebrow">Admin monitor</div>
          <h1>User activity</h1>
          <p>Account-level engagement and learning progress. No answers, transcripts, IP addresses, or browser data.</p>
        </div>
        <label className="admin-window">Window
          <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
        </label>
      </div>

      {error && <div className="panel error">{error}</div>}
      {!data && !error && <div className="loading">loading user monitor</div>}
      {data && <div className="deck admin-deck">
        <div className="panel s12">
          <div className="readout admin-readout">
            <div className="metric"><div className="num plain">{summary.users}</div><div className="lbl">Accounts</div></div>
            <div className="metric"><div className="num teal">{summary.active}</div><div className="lbl">Active in window</div></div>
            <div className="metric"><div className="num">{summary.progressing}</div><div className="lbl">Progressing</div></div>
            <div className="metric"><div className="num plain">{summary.solved}</div><div className="lbl">Problems solved</div></div>
          </div>
        </div>

        <div className="panel s12 admin-table-panel">
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead><tr>
                <th>Pilot</th><th>Activity</th><th>Study</th><th>Coding</th><th>Reviews</th><th>Other progress</th>
              </tr></thead>
              <tbody>{data.users.map((user) => {
                const freshness = daysAgo(user.last_active_at);
                return <tr key={user.username}>
                  <td data-label="Pilot"><strong>{user.username}</strong><span>{user.level} · joined {when(user.created_at).split(",")[0]}</span></td>
                  <td data-label="Activity">
                    <span className={`admin-status ${freshness <= 1 ? "current" : freshness < days ? "recent" : "quiet"}`}>
                      {freshness <= 1 ? "Active" : freshness < days ? "Recent" : "Quiet"}
                    </span>
                    <span>{user.active_days} active · {user.login_days} login days</span>
                    <span>Last active: {when(user.last_active_at)}</span>
                  </td>
                  <td data-label="Study"><strong>{user.progress.study_days} {user.progress.study_days === 1 ? "day" : "days"}</strong><span>{user.progress.current_streak}d current streak</span><span>Last progress: {when(user.progress.last_progress_at)}</span></td>
                  <td data-label="Coding"><strong>{user.progress.problems_solved} solved</strong><span>{user.progress.problems_attempted} attempted</span></td>
                  <td data-label="Reviews"><strong>{user.progress.reviews} answers</strong><span>{user.progress.accuracy == null ? "No accuracy yet" : `${Math.round(user.progress.accuracy * 100)}% accurate`}</span><span>{user.progress.cards_reviewed}/{user.progress.cards_total} cards reviewed</span></td>
                  <td data-label="Other progress"><strong>{user.progress.topics_completed} topics</strong><span>{user.progress.mocks_completed} mocks completed</span></td>
                </tr>;
              })}</tbody>
            </table>
          </div>
        </div>
      </div>}
    </>
  );
}
