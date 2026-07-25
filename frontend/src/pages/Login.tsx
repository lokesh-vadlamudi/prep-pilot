import { useEffect, useState } from "react";
import { api } from "../api";

type Mode = "signin" | "register" | "setup";

export default function Login({ onAuthed }: { onAuthed: (user: string) => void }) {
  const [mode, setMode] = useState<Mode | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [invite, setInvite] = useState("");
  const [level, setLevel] = useState("newgrad");
  const [lang, setLang] = useState("python");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.needsSetup().then((r) => {
      setMode(r.needs_setup ? "setup" : "signin");
      setUsername(r.needs_setup ? r.username : "");
    });
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      if (mode === "setup") {
        const r = await api.setup(password, username);
        if (!r.ok) throw new Error(password.length < 6 ? "Choose at least 6 characters." : "Setup failed.");
      } else if (mode === "register") {
        const r = await api.register(username, password, invite, level, lang);
        if (!r.ok) {
          const detail = (await r.json().catch(() => null))?.detail;
          throw new Error(detail || "Couldn't create the account.");
        }
      } else {
        const r = await api.login(username, password);
        if (!r.ok) throw new Error("Wrong username or password.");
      }
      const me = await api.me();
      onAuthed(me.username);
    } catch (e: any) {
      setErr(e.message || "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  if (mode === null) return <div className="auth-wrap"><span className="loading">connecting</span></div>;

  const title = mode === "setup" ? "Set up the cockpit" : mode === "register" ? "New pilot" : "Pre-flight sign in";
  const sub =
    mode === "setup"
      ? "First run — choose your pilot name and passcode."
      : mode === "register"
      ? "Create your own account — progress, streaks, and reviews are yours alone."
      : "Your daily senior-engineering interview trainer.";

  return (
    <div className="auth-wrap">
      <form className="auth-card panel" onSubmit={submit}>
        <div className="brand">
          <span className="logo">Prep<b>Pilot</b></span>
        </div>
        <h2>{title}</h2>
        <p className="sub">{sub}</p>
        <div className="field">
          <label>Pilot</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </div>
        <div className="field">
          <label>{mode === "signin" ? "Passcode" : "New passcode"}</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "signin" ? "current-password" : "new-password"}
          />
        </div>
        {mode === "register" && (
          <>
            <div className="field">
              <label>Invite code</label>
              <input value={invite} onChange={(e) => setInvite(e.target.value)} placeholder="ask the admin" />
            </div>
            <div className="field">
              <label>Experience</label>
              <select value={level} onChange={(e) => setLevel(e.target.value)}>
                <option value="newgrad">New grad / early career (SDE-1)</option>
                <option value="senior">Experienced (senior+)</option>
              </select>
            </div>
            <div className="field">
              <label>Preferred language</label>
              <select value={lang} onChange={(e) => setLang(e.target.value)}>
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
                <option value="go">Go</option>
              </select>
            </div>
          </>
        )}
        {err && <div className="err">{err}</div>}
        <button className="btn wide" disabled={busy}>
          {busy ? "…" : mode === "signin" ? "Enter cockpit" : "Create & enter"}
        </button>
        {mode !== "setup" && (
          <p className="sub" style={{ marginTop: 12, textAlign: "center" }}>
            {mode === "signin" ? (
              <a href="#" onClick={(e) => { e.preventDefault(); setErr(""); setMode("register"); }}>
                Have an invite code? Create an account →
              </a>
            ) : (
              <a href="#" onClick={(e) => { e.preventDefault(); setErr(""); setMode("signin"); }}>
                ← Back to sign in
              </a>
            )}
          </p>
        )}
      </form>
    </div>
  );
}
