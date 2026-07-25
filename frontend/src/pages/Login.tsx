import { useEffect, useState } from "react";
import { api } from "../api";

export default function Login({ onAuthed }: { onAuthed: (user: string) => void }) {
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.needsSetup().then((r) => {
      setNeedsSetup(r.needs_setup);
      setUsername(r.username);
    });
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      if (needsSetup) {
        const r = await api.setup(password);
        if (!r.ok) throw new Error(password.length < 6 ? "Choose at least 6 characters." : "Setup failed.");
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

  if (needsSetup === null) return <div className="auth-wrap"><span className="loading">connecting</span></div>;

  return (
    <div className="auth-wrap">
      <form className="auth-card panel" onSubmit={submit}>
        <div className="brand">
          <span className="logo">Prep<b>Pilot</b></span>
        </div>
        <h2>{needsSetup ? "Set your passcode" : "Pre-flight sign in"}</h2>
        <p className="sub">
          {needsSetup
            ? "First run — pick a passcode to lock down this trainer."
            : "Your daily senior-engineering interview trainer."}
        </p>
        {!needsSetup && (
          <div className="field">
            <label>Pilot</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </div>
        )}
        <div className="field">
          <label>{needsSetup ? "New passcode" : "Passcode"}</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={needsSetup ? "new-password" : "current-password"}
            autoFocus
          />
        </div>
        {err && <div className="err">{err}</div>}
        <button className="btn wide" disabled={busy}>
          {busy ? "…" : needsSetup ? "Create & enter" : "Enter cockpit"}
        </button>
      </form>
    </div>
  );
}
