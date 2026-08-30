import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ArtifactCompletionRule, ArtifactState, CourseArtifact, CourseModule, CourseSource, describeApiError, newRequestId, ReconciliationPreview } from "../api";
import GroundedTutorPanel, { GroundedTutorTurn } from "../components/GroundedTutorPanel";

const sourceGroups: { kinds: string[]; label: string }[] = [
  { kinds: ["topic", "section"], label: "Learn" },
  { kinds: ["resource"], label: "Resources" },
  { kinds: ["hands_on"], label: "Lab checklist" },
  { kinds: ["workplace_project", "workplace_task", "personal_project"], label: "Workplace and portfolio" },
  { kinds: ["paper"], label: "Papers" },
  { kinds: ["hardware"], label: "Hardware" },
  { kinds: ["routine"], label: "Routine" },
];

export default function InferenceModule() {
  const { moduleId = "" } = useParams();
  const [module, setModule] = useState<CourseModule | null>(null);
  const [error, setError] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const focusedModule = useRef("");
  const load = useCallback((signal?: AbortSignal) => {
    setError(""); setModule(null);
    return api.courseModule(moduleId, signal).then(setModule).catch((reason) => {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(describeApiError(reason));
    });
  }, [moduleId]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useLayoutEffect(() => {
    if (!module || focusedModule.current === module.id) return;
    focusedModule.current = module.id; headingRef.current?.focus();
  }, [module]);

  if (error) return <section className="panel course-error" role="alert"><h1>Mission unavailable</h1><p>{error}</p><button className="btn primary" onClick={() => load()}>Try again</button><Link to="/courses/inference-engineering">Return to course</Link></section>;
  if (!module) return <div className="loading" role="status">loading mission</div>;
  const enrollmentRequired = module.next_action === "enroll";
  const setLinkedTopic = (linkedTopic: CourseModule["linked_topic"]) => setModule((current) => current ? { ...current, linked_topic: linkedTopic } : current);

  return <article className="course-module">
    <header className="page-head course-module-head">
      <span className="eyebrow">{module.id} · {module.callsign}</span>
      <h1 ref={headingRef} tabIndex={-1}>{module.title}</h1>
      <p>{module.mission_brief}</p>
      <div className="course-tags"><span>{platformLabel(module.lab.platform)}</span><span>{stateLabel(module.progress.state)}</span></div>
      {!!module.prerequisites.length && <p className="course-prerequisites"><strong>Prerequisite:</strong> {module.prerequisites.join(", ")}</p>}
    </header>

    <nav className="lesson-toolbar" aria-label="Course mission navigation">
      <Link className="lesson-book-link" to="/courses/inference-engineering">← Mission board</Link>
      <MissionNeighbors id={module.id} />
    </nav>

    {enrollmentRequired && <aside className="notice course-enroll-required" role="status"><strong>Enroll before saving mission work</strong><p>This direct link is readable, but checkpoint and interview actions require course enrollment.</p><Link className="btn primary" to="/courses/inference-engineering">Open course enrollment</Link></aside>}

    {module.linked_topic && <section className="panel course-linked-callout"><span className="eyebrow">Existing private material</span><h2>{module.linked_topic.title}</h2><p>Use this source-backed lesson inside the mission without changing its independent practice history.</p><Link className="btn" to={module.linked_topic.course_url}>Open linked lesson →</Link></section>}
    {!enrollmentRequired && <CourseSection title="Reuse existing lessons"><ReconciliationPanel module={module} onLinkChanged={setLinkedTopic} /></CourseSection>}

    <CourseSection title="Learn">
      <ul className="course-checklist">{module.learning_objectives.map((item) => <li key={item}>{item}</li>)}</ul>
      <ol className="course-outline">{module.lesson_outline.map((item) => <li key={item}>{item}</li>)}</ol>
      <SourceItems sources={sourcesFor(module.sources, ["topic", "section"])} />
    </CourseSection>
    <CourseSection title="Resources"><SourceItems sources={sourcesFor(module.sources, ["resource"])} /></CourseSection>
    <CourseSection title="Lab checklist">
      <div className="course-lab-head"><span className="chip">{platformLabel(module.lab.platform)}</span><strong>{module.lab.title}</strong></div>
      <div className="notice"><strong>Safety preflight</strong><ul>{module.lab.safety.map((item) => <li key={item}>{item}</li>)}</ul></div>
      <ol className="course-checklist">{module.lab.steps.map((item) => <li key={item}>{item}</li>)}</ol>
      <p><strong>Verify:</strong> {module.lab.verification}</p>
      <SourceItems sources={sourcesFor(module.sources, ["hands_on"])} />
    </CourseSection>
    {sourceGroups.slice(3).map((group) => {
      const sources = sourcesFor(module.sources, group.kinds);
      return sources.length ? <CourseSection key={group.label} title={group.label}><SourceItems sources={sources} /></CourseSection> : null;
    })}
    <CourseSection title="Checkpoint">{enrollmentRequired ? <p className="muted">Enroll from the course overview to submit checkpoint evidence.</p> : <CheckpointPractice module={module} />}</CourseSection>
    <CourseSection title="Oral interview">{enrollmentRequired ? <><p>{module.oral.opening_prompt}</p><p className="muted">Enroll from the course overview to start interview practice.</p></> : <OralInterview module={module} />}</CourseSection>
    <CourseSection title="Artifacts">{enrollmentRequired ? <p className="muted">Enroll from the course overview to save or export mission artifacts.</p> : <ArtifactForms module={module} />}</CourseSection>
    <CourseSection title="Debrief"><p>{module.debrief_prompt}</p></CourseSection>
  </article>;
}

function ReconciliationPanel({ module, onLinkChanged }: { module: CourseModule; onLinkChanged: (topic: CourseModule["linked_topic"]) => void }) {
  const [preview, setPreview] = useState<ReconciliationPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [requestId, setRequestId] = useState("");
  const [activeFingerprint, setActiveFingerprint] = useState("");
  const [deletedNote, setDeletedNote] = useState("");
  const actionController = useRef<AbortController | null>(null);
  const catalogVersion = module.artifact_state[0]?.catalog_version || "2026.08.29";

  useEffect(() => {
    const controller = new AbortController();
    actionController.current = controller;
    api.courseReconciliationPreview(module.id, false, controller.signal).then(setPreview).catch((reason) => {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(describeApiError(reason));
    });
    return () => { controller.abort(); actionController.current?.abort(); };
  }, [module.id]);

  async function scan() {
    actionController.current?.abort();
    const controller = new AbortController(); actionController.current = controller;
    setBusy(true); setError(""); setDeletedNote(""); setRequestId(""); setActiveFingerprint("");
    try { setPreview(await api.courseReconciliationPreview(module.id, true, controller.signal)); }
    catch (reason) { if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(describeApiError(reason)); }
    finally { setBusy(false); }
  }

  async function confirm(candidate: ReconciliationPreview["candidates"][number]) {
    if (!preview) return;
    const expectedRevision = preview.revision;
    const sameAction = activeFingerprint === candidate.candidate_fingerprint;
    const actionId = sameAction && requestId ? requestId : newRequestId();
    setActiveFingerprint(candidate.candidate_fingerprint); setRequestId(actionId); setBusy(true); setError("");
    try {
      const link = await api.courseReconcile({ module_id: module.id, candidate_fingerprint: candidate.candidate_fingerprint, expected_revision: expectedRevision, request_id: actionId, catalog_version: catalogVersion });
      setPreview({ module_id: module.id, state: "linked", revision: link.revision, candidates: [], link }); setRequestId("");
      onLinkChanged({ concept_id: candidate.concept_id, title: candidate.title, course_url: `/courses/inference-engineering/${module.id}/linked-topics/${candidate.concept_id}`, revision: link.revision });
    } catch (reason) { setError(describeApiError(reason)); }
    finally { setBusy(false); }
  }

  async function removeLink() {
    if (!preview?.link) return;
    const savedLink = preview.link;
    const actionId = requestId || newRequestId();
    if (!requestId) setRequestId(actionId);
    setBusy(true); setError("");
    try {
      await api.courseDeleteLink(savedLink.link_id, { candidate_fingerprint: savedLink.candidate_fingerprint, expected_revision: savedLink.revision, request_id: actionId, catalog_version: catalogVersion });
      setPreview({ module_id: module.id, state: "not_scanned", revision: savedLink.revision + 1, candidates: [] }); setRequestId(""); setDeletedNote("The course link was removed. The independent lesson was not deleted."); onLinkChanged(null);
    } catch (reason) { setError(describeApiError(reason)); }
    finally { setBusy(false); }
  }

  if (!preview) return error
    ? <div><p className="notice error" role="alert">{error}</p><button className="btn" onClick={scan} disabled={busy}>Retry checking lesson links</button></div>
    : <p className="loading" role="status">checking existing lesson links</p>;
  return <div className="course-reconcile"><p className="muted">Reuse an existing private lesson by linking it to this mission. This does not create another lesson or change its independent history.</p>
    {error && <p className="notice error" role="alert">{error}</p>}{deletedNote && <p className="notice" role="status">{deletedNote}</p>}
    {(preview.state === "linked" || preview.state === "stale") && preview.link ? <>{preview.state === "stale" && <p className="notice">This saved link is stale. Remove only the course link, then scan again before confirming another lesson.</p>}<button className="btn ghost" disabled={busy} onClick={removeLink}>{error ? "Retry removing course link" : "Remove course link"}</button></> : <button className="btn" disabled={busy} onClick={scan}>Scan existing lessons</button>}
    {preview.state === "none_found" && <p className="notice">No matching private lesson was found. Continue with the catalog material in this mission.</p>}
    {!!preview.candidates?.length && <div className="course-reconcile-candidates">{preview.candidates.map((candidate) => <article key={candidate.candidate_fingerprint}><h3>{candidate.title}</h3><p>{candidate.partial ? "This candidate needs your confirmation because the match is partial or ambiguous." : "The title and catalog identity match; confirm before creating the course link."}</p><button className="btn" disabled={busy} onClick={() => confirm(candidate)}>{error && activeFingerprint === candidate.candidate_fingerprint ? `Retry link ${candidate.title}` : `Link ${candidate.title}`}</button></article>)}</div>}
  </div>;
}

function CheckpointPractice({ module }: { module: CourseModule }) {
  const [answers, setAnswers] = useState<Record<string, string>>(() => Object.fromEntries(module.checkpoint.prompts.map((_prompt, index) => [`q${index + 1}`, ""])));
  const [requestId, setRequestId] = useState("");
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const catalogVersion = module.artifact_state[0]?.catalog_version || "2026.08.29";
  const complete = module.checkpoint.prompts.every((_prompt, index) => answers[`q${index + 1}`]?.trim());

  function change(prompt: string, value: string) {
    if (error) { setError(""); setRequestId(""); }
    setAnswers((current) => ({ ...current, [prompt]: value }));
  }

  async function submit() {
    if (!complete || busy) return;
    const actionId = requestId || newRequestId();
    if (!requestId) setRequestId(actionId);
    setBusy(true); setError("");
    try {
      const result = await api.courseCheckpoint(module.checkpoint.id, { request_id: actionId, catalog_version: catalogVersion, answers });
      setFeedback(result.feedback); setRequestId("");
    } catch (reason) { setError(describeApiError(reason)); }
    finally { setBusy(false); }
  }

  return <form className="course-checkpoint-form" onSubmit={(event) => { event.preventDefault(); submit(); }}>
    <p className="muted">Respond to every prompt, then request qualitative feedback grounded in this mission and your saved evidence.</p>
    {module.checkpoint.prompts.map((prompt, index) => <label key={prompt}><span>{prompt}</span><textarea value={answers[`q${index + 1}`]} onChange={(event) => change(`q${index + 1}`, event.target.value)} required /></label>)}
    {error && <p role="alert" className="notice error">{error} Your answers remain available for an exact retry.</p>}
    {feedback && <div className="notice" role="status"><strong>Qualitative feedback</strong><p>{feedback}</p></div>}
    <button className="btn primary" type="submit" disabled={!complete || busy}>{error ? "Retry checkpoint" : "Submit checkpoint"}</button>
  </form>;
}

function OralInterview({ module }: { module: CourseModule }) {
  const [revision, setRevision] = useState(module.oral_state.revision);
  const [oralState, setOralState] = useState(module.oral_state.state);
  const catalogVersion = module.artifact_state[0]?.catalog_version || "2026.08.29";
  const turns: GroundedTutorTurn[] = module.oral_state.turns.map((turn) => ({
    id: turn.turn_id, prompt: turn.prompt, response: turn.response,
    feedback: turn.feedback, nextQuestion: turn.next_question,
  }));
  const prompt = turns[turns.length - 1]?.nextQuestion || module.oral.opening_prompt;

  async function submit(response: string, requestId: string) {
    const result = await api.courseOralTurn(module.id, { request_id: requestId, catalog_version: catalogVersion, response });
    setRevision(result.revision); setOralState(result.state);
    return { id: result.turn_id, prompt: result.prompt, response: result.user_response, feedback: result.feedback, nextQuestion: result.next_question };
  }

  return <div className="course-oral-grid">
    <div><h3>Review guide</h3><ul className="course-checklist">{module.oral.rubric.map((item) => <li key={item}>{item}</li>)}</ul></div>
    <GroundedTutorPanel identityKey={`${module.id}:${module.oral_state.revision}`} eyebrow="DGX · MISSION GROUNDED" title="Practice with the online interviewer" prompt={prompt} turns={turns} helperText="One prompt at a time. Feedback stays qualitative and tied to this mission." onSubmit={submit} />
    <OnlineDebrief module={module} revision={revision} oralState={oralState} catalogVersion={catalogVersion} />
    <OfflineOralPractice module={module} revision={revision} catalogVersion={catalogVersion} />
  </div>;
}

function OnlineDebrief({ module, revision: initialRevision, oralState: initialState, catalogVersion }: { module: CourseModule; revision: number; oralState: string; catalogVersion: string }) {
  const [revision, setRevision] = useState(initialRevision);
  const [state, setState] = useState(initialState);
  const [feedback, setFeedback] = useState(module.oral_state.review_feedback);
  const [requestId, setRequestId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const evidenceRevision = useRef(initialRevision);
  useEffect(() => {
    const evidenceChanged = initialRevision > evidenceRevision.current;
    evidenceRevision.current = Math.max(evidenceRevision.current, initialRevision);
    setRevision((current) => Math.max(current, initialRevision)); setState(initialState);
    if (evidenceChanged) { setRequestId(""); setError(""); }
  }, [initialRevision, initialState]);

  async function complete() {
    if (busy) return;
    const actionId = requestId || newRequestId();
    if (!requestId) setRequestId(actionId);
    setBusy(true); setError("");
    try {
      const result = await api.courseOralComplete(module.id, { request_id: actionId, catalog_version: catalogVersion, expected_revision: revision });
      setRevision(result.revision); setState(result.review_state); setFeedback("The DGX qualitative debrief was saved. Reload this mission to view the persisted review detail."); setRequestId("");
    } catch (reason) { setError(describeApiError(reason)); }
    finally { setBusy(false); }
  }

  if (state === "reviewed") return <div className="notice course-reviewed" role="status"><strong>Qualitative debrief</strong><p>{feedback || "This oral practice is reviewed and remains available on reload."}</p></div>;
  if (state !== "practicing" && state !== "awaiting_review") return null;
  return <div className="course-online-debrief"><p className="muted">When your evidence is ready, ask the DGX interviewer for a final qualitative debrief.</p>{error && <p className="notice error" role="alert">{error}</p>}<button className="btn" disabled={busy} onClick={complete}>{error ? "Retry qualitative debrief" : "Request qualitative debrief"}</button></div>;
}

function OfflineOralPractice({ module, revision: initialRevision, catalogVersion }: { module: CourseModule; revision: number; catalogVersion: string }) {
  const [note, setNote] = useState(module.oral_state.self_record_note);
  const [reflection, setReflection] = useState("");
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const [revision, setRevision] = useState(initialRevision);
  const [state, setState] = useState(module.oral_state.state);
  const [requestId, setRequestId] = useState(() => newRequestId());
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { setRevision((current) => Math.max(current, initialRevision)); }, [initialRevision]);

  async function saveOffline() {
    if (!note.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const result = await api.courseOralSelfRecord(module.id, { request_id: requestId, catalog_version: catalogVersion, expected_revision: revision, note: note.trim() });
      setRevision(result.revision); setState(result.review_state as typeof state); setRequestId(newRequestId());
    } catch (reason) { setError(describeApiError(reason)); }
    finally { setBusy(false); }
  }

  async function saveReview() {
    if (!reflection.trim() || !acknowledged.length || busy) return;
    setBusy(true); setError("");
    try {
      const result = await api.courseOralReview(module.id, { request_id: requestId, catalog_version: catalogVersion, expected_revision: revision, method: "self", acknowledgements: acknowledged, reflection: reflection.trim() });
      setRevision(result.revision); setState(result.review_state as typeof state); setRequestId(newRequestId());
    } catch (reason) { setError(describeApiError(reason)); }
    finally { setBusy(false); }
  }

  function toggle(item: string) {
    changeFailedAction();
    setAcknowledged((items) => items.includes(item) ? items.filter((value) => value !== item) : [...items, item]);
  }

  function changeFailedAction() {
    if (!error) return;
    setError(""); setRequestId(newRequestId());
  }

  return <section className="course-offline" aria-labelledby={`offline-${module.id}`}>
    <h3 id={`offline-${module.id}`}>Offline practice and self-review</h3>
    <p className="muted">Record aloud without the DGX connection, then leave a bounded note and review it against the mission guide.</p>
    <label><span>Offline practice note</span><textarea value={note} onChange={(event) => { changeFailedAction(); setNote(event.target.value); }} /></label>
    {error && <p role="alert" className="notice error">{error}</p>}
    <button className="btn" disabled={busy || !note.trim()} onClick={saveOffline}>{error ? "Retry offline practice" : "Save offline practice"}</button>
    {(state === "awaiting_review" || state === "practicing") && <div className="course-self-review">
      <fieldset><legend>Self-review guide</legend>{module.oral.rubric.map((item) => <label key={item}><input type="checkbox" checked={acknowledged.includes(item)} onChange={() => toggle(item)} /> {item}</label>)}</fieldset>
      <label><span>Reflection</span><textarea value={reflection} onChange={(event) => { changeFailedAction(); setReflection(event.target.value); }} /></label>
      <button className="btn" disabled={busy || !reflection.trim() || !acknowledged.length} onClick={saveReview}>Complete self-review</button>
    </div>}
    {state === "reviewed" && <p className="notice" role="status">Practice reviewed. You can keep practicing and revise your evidence.</p>}
  </section>;
}

function ArtifactForms({ module }: { module: CourseModule }) {
  return <div className="course-artifact-grid">{module.artifacts.map((artifact) => {
    const state = module.artifact_state.find((item) => item.artifact_id === artifact.id);
    return state ? <ArtifactForm key={artifact.id} module={module} artifact={artifact} initial={state} /> : <p className="notice error" role="alert" key={artifact.id}>Artifact state is unavailable. Reload before editing {artifact.title}.</p>;
  })}</div>;
}

function ArtifactForm({ module, artifact, initial }: { module: CourseModule; artifact: CourseArtifact; initial: ArtifactState }) {
  const [draft, setDraft] = useState<Record<string, any>>(() => cloneDraft(initial.draft_fields));
  const [note, setNote] = useState(initial.note);
  const [uri, setUri] = useState(initial.artifact_uri);
  const [revision, setRevision] = useState(initial.revision);
  const [requestId, setRequestId] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const valid = artifactDraftValid(module, artifact, draft) && Boolean(note.trim()) && artifactUriValid(uri);
  const uriHelpId = `artifact-uri-help-${artifact.id}`;

  function changed(next: () => void) {
    if (error) { setError(""); setRequestId(""); }
    setSaved(false); next();
  }

  async function save() {
    if (!valid || busy) return;
    const actionId = requestId || newRequestId();
    if (!requestId) setRequestId(actionId);
    setBusy(true); setError("");
    try {
      const result = await api.courseSaveArtifact(module.id, artifact.id, { request_id: actionId, catalog_version: initial.catalog_version, expected_revision: revision, note: note.trim(), artifact_uri: uri.trim(), draft_fields: draft });
      setRevision(result.revision); setRequestId(""); setSaved(true);
    } catch (reason) { setError(describeApiError(reason)); }
    finally { setBusy(false); }
  }

  return <article className="course-artifact" aria-labelledby={`artifact-${artifact.id}`}>
    <span className="mono">{artifact.output_format}</span><h3 id={`artifact-${artifact.id}`}>{artifact.title}</h3>
    {initial.completed && <p className="notice">Completed evidence remains editable; saving creates the next owner revision.</p>}
    <ArtifactDraftFields module={module} artifact={artifact} draft={draft} change={(next) => changed(() => setDraft(next))} />
    <label><span>Owner note</span><textarea value={note} onChange={(event) => changed(() => setNote(event.target.value))} required /></label>
    <label><span>Artifact URI</span><input aria-label="Artifact URI" value={uri} onChange={(event) => changed(() => setUri(event.target.value))} placeholder="HTTPS URL or repository-relative path" aria-describedby={uriHelpId} required /><small id={uriHelpId}>HTTPS URL or repository-relative path</small></label>
    <ul>{artifact.verification_rubric.map((item) => <li key={item}>{item}</li>)}</ul>
    {error && <p role="alert" className="notice error">{error} Your draft and owner metadata remain available.</p>}
    {saved && <p role="status" className="notice">Artifact revision saved.</p>}
    <div className="course-artifact-actions"><button className="btn primary" disabled={!valid || busy} onClick={save}>{error ? `Retry artifact: ${artifact.title}` : `Save artifact: ${artifact.title}`}</button><button className="btn ghost" type="button" onClick={() => exportArtifact(artifact, note, uri, draft)}>Export draft</button></div>
  </article>;
}

function ArtifactDraftFields({ module, artifact, draft, change }: { module: CourseModule; artifact: CourseArtifact; draft: Record<string, any>; change: (next: Record<string, any>) => void }) {
  const controlled = new Set<string>();
  if (module.selection_rule) controlled.add("selected_experiments");
  if (artifact.completion_rule) [artifact.completion_rule.collection_field, artifact.completion_rule.chosen_id_field, artifact.completion_rule.evidence_field].forEach((field) => { if (field) controlled.add(field); });
  return <div className="course-artifact-fields">
    {module.selection_rule && <ExperimentSelection rule={module.selection_rule} selected={Array.isArray(draft.selected_experiments) ? draft.selected_experiments : []} change={(selected) => change({ ...draft, selected_experiments: selected })} />}
    {artifact.completion_rule && <CompletionFields rule={artifact.completion_rule} draft={draft} change={change} />}
    {artifact.template_fields.filter((field) => !controlled.has(field)).map((field) => <label key={field}><span>{fieldLabel(field)}</span><textarea value={typeof draft[field] === "string" ? draft[field] : ""} onChange={(event) => change({ ...draft, [field]: event.target.value })} required /></label>)}
  </div>;
}

function ExperimentSelection({ rule, selected, change }: { rule: NonNullable<CourseModule["selection_rule"]>; selected: string[]; change: (value: string[]) => void }) {
  function toggle(id: string) {
    if (selected.includes(id)) return change(selected.filter((value) => value !== id));
    if (selected.length < rule.maximum) change([...selected, id]);
  }
  return <fieldset><legend>Select {rule.minimum}–{rule.maximum} experiments</legend>{rule.options.map((option) => <label key={option.id}><input type="checkbox" checked={selected.includes(option.id)} onChange={() => toggle(option.id)} /> {option.label}<small>{option.id}</small></label>)}</fieldset>;
}

function CompletionFields({ rule, draft, change }: { rule: ArtifactCompletionRule; draft: Record<string, any>; change: (next: Record<string, any>) => void }) {
  const rows = completionRows(rule, draft);
  function updateRow(index: number, value: string) {
    const next = rows.map((row, rowIndex) => rowIndex === index ? { ...row, [rule.entry_value_field]: value } : row);
    change({ ...draft, [rule.collection_field]: next });
  }
  const chosen = rule.chosen_id_field ? String(draft[rule.chosen_id_field] || "") : "";
  const evidence = rule.evidence_field ? (draft[rule.evidence_field] || {}) : {};
  return <>
    {rows.map((row, index) => <label key={row[rule.entry_id_field]}><span>{rule.collection_field === "paper_notes" ? "Paper note" : "Scope"}: {rule.entries[index].label}</span><textarea value={row[rule.entry_value_field]} maxLength={rule.maximum_value_length} onChange={(event) => updateRow(index, event.target.value)} required /></label>)}
    {rule.chosen_id_field && <label><span>Chosen project</span><select value={chosen} onChange={(event) => change({ ...draft, [rule.chosen_id_field!]: event.target.value, [rule.evidence_field!]: { ...evidence, [rule.evidence_id_field!]: event.target.value } })} required><option value="">Choose a project</option>{rule.entries.map((entry) => <option value={entry.source_id} key={entry.source_id}>{entry.label}</option>)}</select></label>}
    {rule.evidence_field && <label><span>Proposal evidence</span><textarea value={evidence[rule.evidence_value_field! as string] || ""} maxLength={rule.maximum_value_length} onChange={(event) => change({ ...draft, [rule.evidence_field!]: { ...evidence, [rule.evidence_id_field!]: chosen, [rule.evidence_value_field!]: event.target.value } })} required /></label>}
  </>;
}

function completionRows(rule: ArtifactCompletionRule, draft: Record<string, any>) {
  const saved = Array.isArray(draft[rule.collection_field]) ? draft[rule.collection_field] : [];
  return rule.entries.map((entry) => saved.find((row: any) => row?.[rule.entry_id_field] === entry.source_id) || { [rule.entry_id_field]: entry.source_id, [rule.entry_value_field]: "" });
}

function artifactDraftValid(module: CourseModule, artifact: CourseArtifact, draft: Record<string, any>) {
  if (module.selection_rule) {
    const selected = draft.selected_experiments;
    if (!Array.isArray(selected) || selected.length < module.selection_rule.minimum || selected.length > module.selection_rule.maximum) return false;
  }
  if (artifact.completion_rule) {
    const rule = artifact.completion_rule, rows = completionRows(rule, draft);
    if (rows.some((row) => !String(row[rule.entry_value_field] || "").trim())) return false;
    if (rule.chosen_id_field && !draft[rule.chosen_id_field]) return false;
    if (rule.evidence_field && !String(draft[rule.evidence_field]?.[rule.evidence_value_field!] || "").trim()) return false;
  }
  return artifact.template_fields.every((field) => [artifact.completion_rule?.collection_field, artifact.completion_rule?.chosen_id_field, artifact.completion_rule?.evidence_field, module.selection_rule ? "selected_experiments" : ""].includes(field) || Boolean(String(draft[field] || "").trim()));
}

function exportArtifact(artifact: CourseArtifact, note: string, uri: string, draft: Record<string, any>) {
  const url = URL.createObjectURL(new Blob([JSON.stringify({ title: artifact.title, note, artifact_uri: uri, draft_fields: draft }, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${artifact.id}.json`; anchor.click(); URL.revokeObjectURL(url);
}

function cloneDraft(value: Record<string, unknown>) { return JSON.parse(JSON.stringify(value || {})); }
function fieldLabel(value: string) { return value.replace(/_/g, " ").replace(/^./, (letter) => letter.toUpperCase()); }
function artifactUriValid(value: string) {
  const location = value.trim();
  if (/^https:/i.test(location)) {
    if (!/^https:\/\/[^/]/i.test(location)) return false;
    try {
      const url = new URL(location);
      return Boolean(url.hostname) && !url.username && !url.password;
    } catch { return false; }
  }
  return Boolean(location) && !location.startsWith("/") && !location.split("/").includes("..") && !/^[a-z][a-z0-9+.-]*:/i.test(location);
}

function CourseSection({ title, children }: { title: string; children: React.ReactNode }) {
  const id = `course-${title.toLowerCase().replace(/\W+/g, "-")}`;
  return <section className="panel course-stage" aria-labelledby={id}><h2 id={id}>{title}</h2>{children}</section>;
}

function SourceItems({ sources }: { sources: CourseSource[] }) {
  if (!sources.length) return <p className="muted">No additional catalog entries for this stage.</p>;
  return <ul className="course-source-list">{sources.map((source) => <li key={source.id}><span>{source.label}</span><small>{source.id}</small></li>)}</ul>;
}

function sourcesFor(sources: CourseSource[], kinds: string[]) {
  return sources.filter((source) => kinds.includes(source.kind));
}

function MissionNeighbors({ id }: { id: string }) {
  const index = Number(id.slice(3));
  const path = (value: number) => `/courses/inference-engineering/IC-${String(value).padStart(2, "0")}`;
  return <div className="lesson-nav-actions">{index > 0 && <Link className="lesson-nav-link previous" to={path(index - 1)}>← Previous mission</Link>}{index < 16 && <Link className="lesson-nav-link next" to={path(index + 1)}>Next mission →</Link>}</div>;
}

function stateLabel(state: string) {
  return ({ not_started: "Not started", in_progress: "In progress", ready_for_checkpoint: "Ready for checkpoint", complete: "Complete" } as Record<string, string>)[state] || state;
}

function platformLabel(platform: string) {
  return ({ dgx: "DGX Spark", mac: "Mac mini", both: "DGX + Mac", optional_cloud: "Optional cloud lab" } as Record<string, string>)[platform] || platform;
}
