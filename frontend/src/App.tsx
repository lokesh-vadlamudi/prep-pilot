import { lazy, Suspense, useEffect, useRef, useState } from "react";
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
import MakeMeLearn from "./pages/MakeMeLearn";

// Heavy (CodeMirror) — only loaded when opening a problem to solve.
const Solve = lazy(() => import("./pages/Solve"));

const THEME_KEY = "pp-theme";

function initialTheme(): string {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "dark" || stored === "light") return stored;
  } catch { /* ignore */ }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

// ── Theme provider (centralized state) ────────────────────────────

export function useTheme() {
  const [theme, setTheme] = useState<string>(initialTheme);
  const themeRef = useRef(theme);
  themeRef.current = theme;

  useEffect(() => {
    // Apply theme attribute and browser chrome colors on mount and every change.
    const t = themeRef.current;
    document.documentElement.setAttribute("data-theme", t);
    document.documentElement.setAttribute("color-scheme", t);
    const meta = document.querySelector('meta[name="theme-color"]') as HTMLMetaElement | null;
    if (meta) {
      meta.content = t === "dark" ? "#0c1626" : "#F2F6FA";
    }
  }, [theme]);

  // Persist user preference and listen for OS preference changes.
  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e: MediaQueryListEvent | MediaQueryList) => {
      if (localStorage.getItem(THEME_KEY) === null) {
        setTheme(e.matches ? "dark" : "light");
      }
    };
    try {
      mql.addEventListener("change", handler);
    } catch {
      // Safari fallback
      mql.addListener(handler as any);
    }
    return () => {
      try { mql.removeEventListener("change", handler); } catch {}
      try { mql.removeListener(handler as any); } catch {}
    };
  }, []);

  const toggle = () => {
    const next = themeRef.current === "dark" ? "light" : "dark";
    try { localStorage.setItem(THEME_KEY, next); } catch { /* ignore */ }
    setTheme(next);
  };

  return { theme, toggle };
}

// ── App ───────────────────────────────────────────────────────────

type Auth = { loading: boolean; authed: boolean; user: string; invite?: string };
type Runtime = { environment: string; release: string };

export default function App() {
  const [auth, setAuth] = useState<Auth>({ loading: true, authed: false, user: "" });
  const [runtime, setRuntime] = useState<Runtime>({ environment: "production", release: "" });
  const { toggle } = useTheme();

  useEffect(() => {
    api.me().then((r) => setAuth({
      loading: false, authed: r.authenticated, user: r.username || "", invite: r.invite_code,
    }));
    api.health().then((r) => setRuntime({ environment: r.environment, release: r.release })).catch(() => {});
  }, []);

  if (auth.loading) return <div className="auth-wrap"><span className="loading">initializing</span></div>;

  const isDev = runtime.environment === "development";

  if (!auth.authed)
    return (
      <div className={isDev ? "environment-dev" : ""}>
        {isDev && <DevBanner release={runtime.release} />}
        <Login onAuthed={(user) => setAuth({ loading: false, authed: true, user })} />
      </div>
    );

  return (
    <div className={isDev ? "environment-dev" : ""}>
      {isDev && <DevBanner release={runtime.release} />}
      <div className="shell">
        <Rail user={auth.user} invite={auth.invite} runtime={runtime} themeToggle={toggle}
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
            <Route path="/make-me-learn" element={<MakeMeLearn />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}

function DevBanner({ release }: { release: string }) {
  return <div className="dev-banner">Development preview · {release || "local"} · isolated test data</div>;
}

function Rail({ user, invite, runtime, themeToggle, onLogout }: {
  user: string; invite?: string; runtime: Runtime; themeToggle: () => void; onLogout: () => void;
}) {
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
    { to: "/make-me-learn", label: "Make me learn", hint: "books" },
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
        <span className="tag">{runtime.environment === "development" ? "DEV" : runtime.release || "v0.1"}</span>
        <button
          className="theme-toggle"
          onClick={themeToggle}
          aria-pressed={false}
          title="Toggle dark mode"
        >
          <span className="theme-icon-light" aria-hidden>☀</span>
          <span className="theme-icon-dark" aria-hidden>☾</span>
        </button>
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
