import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, JobApplication, JobsDashboard, JobStatus } from "../api";

const STATUSES: { value: JobStatus; label: string }[] = [
  { value: "saved", label: "Saved" },
  { value: "applied", label: "Applied" },
  { value: "interview", label: "Interview" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
  { value: "withdrawn", label: "Withdrawn" },
];

const emptyForm = {
  company: "", role: "", job_url: "", location: "", status: "applied" as JobStatus,
  applied_date: new Date().toLocaleDateString("en-CA"), follow_up_date: "", notes: "",
};

export default function Jobs() {
  const [data, setData] = useState<JobsDashboard | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [target, setTarget] = useState(5);
  const [showForm, setShowForm] = useState(false);
  const [filter, setFilter] = useState<"all" | JobStatus>("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    try {
      const next = await api.jobs();
      setData(next);
      setTarget(next.daily_target);
      setError("");
    } catch {
      setError("Could not load your job tracker.");
    }
  }

  useEffect(() => { load(); }, []);

  const visibleJobs = useMemo(
    () => (data?.jobs || []).filter((job) => filter === "all" || job.status === filter),
    [data, filter],
  );

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.addJob({
        ...form,
        applied_date: form.status === "saved" ? null : (form.applied_date || null),
        follow_up_date: form.follow_up_date || null,
      });
      setForm({ ...emptyForm, applied_date: new Date().toLocaleDateString("en-CA") });
      setShowForm(false);
      await load();
    } catch {
      setError("Could not save this application. Company and role are required.");
    } finally {
      setBusy(false);
    }
  }

  async function saveTarget() {
    if (target < 1 || target > 50) return;
    setBusy(true);
    try { await api.setJobTarget(target); await load(); }
    catch { setError("Could not update the daily target."); }
    finally { setBusy(false); }
  }

  async function patchJob(id: number, body: Partial<JobApplication>) {
    try { await api.updateJob(id, body); await load(); }
    catch { setError("Could not update that application."); }
  }

  async function removeJob(job: JobApplication) {
    if (!window.confirm(`Remove ${job.role} at ${job.company}?`)) return;
    try { await api.deleteJob(job.id); await load(); }
    catch { setError("Could not remove that application."); }
  }

  if (!data) return <div className="loading">loading job search</div>;
  const progress = Math.min(100, Math.round((data.applied_today / data.daily_target) * 100));

  return (
    <>
      <div className="page-head jobs-head">
        <div>
          <div className="eyebrow">Application control</div>
          <h1>Job search</h1>
          <p>Manually track applications, stay on pace, and remember every follow-up.</p>
        </div>
        <button className="btn" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Close" : "+ Log application"}
        </button>
      </div>

      {error && <div className="jobs-error">{error}</div>}

      {showForm && (
        <form className="panel job-form" onSubmit={submit}>
          <div className="panel-title"><div><span className="eyebrow">Manual entry</span><h2>Log a job</h2></div></div>
          <div className="job-form-grid">
            <label><span>Company *</span><input required value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} placeholder="Acme" /></label>
            <label><span>Role *</span><input required value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} placeholder="Software Engineer" /></label>
            <label><span>Status</span><select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as JobStatus })}>{STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select></label>
            <label><span>Applied on</span><input type="date" disabled={form.status === "saved"} value={form.applied_date} onChange={(e) => setForm({ ...form, applied_date: e.target.value })} /></label>
            <label><span>Follow up on</span><input type="date" value={form.follow_up_date} onChange={(e) => setForm({ ...form, follow_up_date: e.target.value })} /></label>
            <label><span>Location</span><input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="Remote / Seattle" /></label>
            <label className="job-wide"><span>Job link</span><input type="url" value={form.job_url} onChange={(e) => setForm({ ...form, job_url: e.target.value })} placeholder="https://…" /></label>
            <label className="job-wide"><span>Notes</span><textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Referral, recruiter, next step…" /></label>
          </div>
          <div className="job-form-actions"><button className="btn" disabled={busy}>Save application</button></div>
        </form>
      )}

      <div className="deck jobs-summary">
        <section className={`panel s7 daily-target ${data.target_met ? "met" : ""}`}>
          <div className="target-copy">
            <div className="eyebrow">Today's target</div>
            <h2>{data.target_met ? "Target cleared" : `${data.remaining_today} application${data.remaining_today === 1 ? "" : "s"} to go`}</h2>
            <p>{data.applied_today} of {data.daily_target} applications logged today.</p>
          </div>
          <div className="target-ring" style={{ "--target-progress": `${progress * 3.6}deg` } as React.CSSProperties}><span>{data.applied_today}</span><small>/{data.daily_target}</small></div>
          <div className="target-settings">
            <label>Daily target <input type="number" min="1" max="50" value={target} onChange={(e) => setTarget(Number(e.target.value))} /></label>
            <button className="btn ghost" disabled={busy || target === data.daily_target} onClick={saveTarget}>Update</button>
          </div>
        </section>

        <section className={`panel s5 reminder-panel ${data.follow_ups_due.length ? "due" : ""}`}>
          <div className="eyebrow">Reminders</div>
          <h2>{data.follow_ups_due.length ? `${data.follow_ups_due.length} follow-up${data.follow_ups_due.length === 1 ? "" : "s"} due` : "You're caught up"}</h2>
          {data.follow_ups_due.length ? (
            <div className="reminder-list">{data.follow_ups_due.slice(0, 3).map((job) => (
              <button key={job.id} onClick={() => patchJob(job.id, { follow_up_date: null })} title="Dismiss this reminder">
                <span><b>{job.company}</b> · {job.role}</span><small>{job.follow_up_date} · dismiss ×</small>
              </button>
            ))}</div>
          ) : <p>No follow-ups are overdue. Add a date to any application to get an in-app reminder here.</p>}
        </section>
      </div>

      <section className="panel jobs-board">
        <div className="jobs-toolbar">
          <div><div className="eyebrow">Pipeline</div><h2>{data.jobs.length} tracked jobs</h2></div>
          <div className="job-filters">
            <button className={filter === "all" ? "on" : ""} onClick={() => setFilter("all")}>All <b>{data.jobs.length}</b></button>
            {STATUSES.slice(0, 5).map((s) => <button key={s.value} className={filter === s.value ? "on" : ""} onClick={() => setFilter(s.value)}>{s.label} <b>{data.counts[s.value]}</b></button>)}
          </div>
        </div>

        {visibleJobs.length === 0 ? (
          <div className="jobs-empty"><span>◎</span><h3>{data.jobs.length ? "No jobs in this status" : "Your pipeline is clear"}</h3><p>Log an application or save a lead when you're ready.</p></div>
        ) : (
          <div className="job-list">{visibleJobs.map((job) => (
            <article className="job-row" key={job.id}>
              <div className="job-main">
                <div className="job-company">{job.company}</div>
                <h3>{job.role}</h3>
                <div className="job-meta">
                  {job.location && <span>{job.location}</span>}
                  {job.applied_date && <span>Applied {job.applied_date}</span>}
                  {job.follow_up_date && <span className={job.follow_up_date <= data.date ? "late" : ""}>Follow up {job.follow_up_date}</span>}
                </div>
                {job.notes && <p>{job.notes}</p>}
              </div>
              <div className="job-controls">
                <select className={`job-status status-${job.status}`} value={job.status} onChange={(e) => patchJob(job.id, { status: e.target.value as JobStatus })}>{STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select>
                <label>Follow-up <input type="date" value={job.follow_up_date || ""} onChange={(e) => patchJob(job.id, { follow_up_date: e.target.value || null })} /></label>
                <div className="job-actions">{job.job_url && <a className="btn ghost" href={job.job_url} target="_blank" rel="noreferrer">Open job ↗</a>}<button className="job-delete" onClick={() => removeJob(job)} title="Remove application">×</button></div>
              </div>
            </article>
          ))}</div>
        )}
      </section>
    </>
  );
}
