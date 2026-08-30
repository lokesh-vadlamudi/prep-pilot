import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, CourseOverview, describeApiError, newRequestId } from "../api";

const stateLabel: Record<string, string> = {
  not_started: "Not started", in_progress: "In progress", ready_for_checkpoint: "Ready for checkpoint", complete: "Complete",
};

export default function InferenceCourse() {
  const [course, setCourse] = useState<CourseOverview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const enrollmentRequest = useRef(newRequestId());
  const headingRef = useRef<HTMLHeadingElement>(null);

  const load = useCallback((signal?: AbortSignal) => {
    setError("");
    return api.courseOverview(signal).then(setCourse).catch((reason) => {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(describeApiError(reason));
    });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useLayoutEffect(() => { if (course) headingRef.current?.focus(); }, [course?.key]);


  async function enroll() {
    if (!course || busy) return;
    setBusy(true); setError("");
    try {
      await api.courseEnroll({ request_id: enrollmentRequest.current, catalog_version: course.version });
      enrollmentRequest.current = newRequestId();
      await load();
    } catch (reason) {
      setError(describeApiError(reason));
    } finally { setBusy(false); }
  }

  if (error && !course) return <CourseLoadError message={error} retry={() => load()} />;
  if (!course) return <div className="loading" role="status">loading inference course</div>;
  const completed = course.modules.filter((module) => module.state === "complete").length;
  const current = course.modules.find((module) => module.state === "in_progress") || course.modules.find((module) => module.state !== "complete");

  return <div className="course-page">
    <header className="page-head course-hero">
      <span className="eyebrow">Inference engineering · mission course</span>
      <h1 ref={headingRef} tabIndex={-1}>{course.title}</h1>
      <p>{course.audience}. Learn the system, run real DGX and Mac labs, defend decisions, and leave with useful artifacts.</p>
      <div className="course-facts" aria-label="Course completion facts">
        <strong>{completed} complete · {course.modules.length} total</strong>
        <span>DGX Spark + Mac mini</span>
      </div>
      {!course.enrolled && <button className="btn primary" onClick={enroll} disabled={busy}>{busy ? "Enrolling…" : "Enroll in course"}</button>}
      {course.enrolled && current && <Link className="btn primary" to={current.url}>Resume {current.title} →</Link>}
    </header>
    {error && <div className="notice error" role="alert">{error}<button className="btn ghost" onClick={() => load()}>Try again</button></div>}
    <section aria-labelledby="mission-sequence-title">
      <div className="course-section-head"><span className="eyebrow">Flight board</span><h2 id="mission-sequence-title">Mission sequence</h2></div>
      <ol className="course-mission-grid">
        {course.modules.map((module) => <li className={`panel course-mission ${module.state}`} key={module.id}>
          <div className="kicker"><span className="mono">{module.id} · {module.callsign}</span><span className="chip">{stateLabel[module.state]}</span></div>
          <h3><Link to={module.url}>{module.title}</Link></h3>
          <div className="course-tags"><span>{platformLabel(module.platform)}</span><span>{module.artifacts.length} artifact{module.artifacts.length === 1 ? "" : "s"}</span></div>
          {!!module.prerequisites.length && module.state === "not_started" && <p className="course-blocked">Requires {module.prerequisites.join(", ")}.</p>}
          {module.artifacts.map((artifact) => <div className="course-artifact-summary" key={artifact.id}><strong>{artifact.title}</strong><small>{artifact.expectations[0]}</small></div>)}
        </li>)}
      </ol>
    </section>
  </div>;
}

function CourseLoadError({ message, retry }: { message: string; retry: () => void }) {
  return <section className="panel course-error" role="alert"><h1>Inference course unavailable</h1><p>{message}</p><button className="btn primary" onClick={retry}>Try again</button></section>;
}

function platformLabel(platform: string) {
  return ({ dgx: "DGX Spark", mac: "Mac mini", both: "DGX + Mac", optional_cloud: "Optional cloud lab" } as Record<string, string>)[platform] || platform;
}
