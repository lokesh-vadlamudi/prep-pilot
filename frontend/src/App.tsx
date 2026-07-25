import { lazy, Suspense, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "./api";
import Login from "./pages/Login";
import Today from "./pages/Today";
import Topics from "./pages/Topics";
import TopicDetail from "./pages/TopicDetail";
import Problems from "./pages/Problems";
import Mock from "./pages/Mock";
import Ask from "./pages/Ask";
import Progress from "./pages/Progress";
import FlightPlan from "./pages/FlightPlan";

// Heavy (CodeMirror) — only loaded when opening a problem to solve.
const Solve = lazy(() => import("./pages/Solve"));

type Auth = { loading: boolean; authed: boolean; user: string; invite?: string };

export default function App() {
  const [auth, setAuth] = useState<Auth>({ loading: true, authed: false, user: "" });

  useEffect(() => {
    api.me().then((r) => setAuth({
      loading: false, authed: r.authenticated, user: r.username || "", invite: r.invite_code,
    }));
  }, []);

  if (auth.loading) return <div className="auth-wrap"><span className="loading">initializing</span></div>;

  if (!auth.authed)
    return <Login onAuthed={(user) => setAuth({ loading: false, authed: true, user })} />;

  return (
    <div className="shell">
      <Rail user={auth.user} invite={auth.invite}
            onLogout={() => setAuth({ loading: false, authed: false, user: "" })} />
      <div className="main">
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/plan" element={<FlightPlan />} />
          <Route path="/topics" element={<Topics />} />
          <Route path="/topics/:id" element={<TopicDetail />} />
          <Route path="/mock" element={<Mock />} />
          <Route path="/problems" element={<Problems />} />
          <Route path="/problems/:id/solve" element={
            <Suspense fallback={<div className="loading">loading editor</div>}><Solve /></Suspense>
          } />
          <Route path="/ask" element={<Ask />} />
          <Route path="/progress" element={<Progress />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </div>
    </div>
  );
}

function Rail({ user, invite, onLogout }: { user: string; invite?: string; onLogout: () => void }) {
  const nav = useNavigate();
  const [brain, setBrain] = useState<{ online: boolean; model: string }>({ online: false, model: "" });
  const [streak, setStreak] = useState<number>(0);

  useEffect(() => {
    api.brainHealth().then(setBrain).catch(() => {});
    api.today().then((p) => setStreak(p.streak)).catch(() => {});
  }, []);

  const links = [
    { to: "/", label: "Pre-flight", hint: "today" },
    { to: "/plan", label: "Flight plan", hint: "roadmap" },
    { to: "/mock", label: "Mock interview", hint: "simulate" },
    { to: "/problems", label: "NeetCode 150", hint: "coding" },
    { to: "/topics", label: "Syllabus", hint: "topics" },
    { to: "/ask", label: "Ask the tutor", hint: "q&a" },
    { to: "/progress", label: "Flight log", hint: "progress" },
  ];

  async function logout() {
    await api.logout();
    onLogout();
    nav("/");
  }

  return (
    <nav className="rail">
      <div className="brand">
        <span className="logo">Prep<b>Pilot</b></span>
        <span className="tag">v0.1</span>
      </div>
      {links.map((l) => (
        <NavLink key={l.to} to={l.to} end={l.to === "/"} className={({ isActive }) => "navlink" + (isActive ? " active" : "")}>
          <span className="dot" />
          {l.label}
        </NavLink>
      ))}
      <div className="spacer" />
      <div className="status-strip">
        <div className="row">
          <span>streak</span>
          <span className="mono" style={{ color: "var(--amber)" }}>{streak}d</span>
        </div>
        <div className="row">
          <span>brain</span>
          <span className={"led" + (brain.online ? "" : " off")}>{brain.online ? "online" : "offline"}</span>
        </div>
        <div className="row"><span>model</span><span>{brain.model.split(":")[0] || "—"}</span></div>
        <div className="row"><span>pilot</span><span>{user}</span></div>
        {invite && (
          <div className="row" title="Share with a new pilot — they register with this code">
            <span>invite</span><span className="mono">{invite}</span>
          </div>
        )}
        <button className="logout" onClick={logout}>↳ sign out</button>
      </div>
    </nav>
  );
}
