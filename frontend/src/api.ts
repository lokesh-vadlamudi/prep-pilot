const json = { "Content-Type": "application/json" };

export class ApiError extends Error {
  status: number;
  code: string;
  detail: string;
  retryable: boolean;

  constructor(status: number, code: string, detail: string, retryable = status === 0 || status >= 500) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.retryable = retryable;
  }
}

async function req(path: string, opts: RequestInit = {}) {
  let r: Response;
  try {
    r = await fetch(path, { credentials: "same-origin", ...opts });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "offline", "PrepPilot could not reach the course service.", true);
  }
  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await r.json() : await r.text();
  if (!r.ok) {
    const payload = typeof body === "object" && body ? body as Record<string, any> : {};
    const failure = payload.error && typeof payload.error === "object" ? payload.error : payload;
    const fallback = r.status === 401 ? "Your session expired." : `Request failed (${r.status}).`;
    const detail = normalizeDetail(failure.detail ?? payload.detail, fallback);
    const retryable = typeof failure.retryable === "boolean" ? failure.retryable : undefined;
    throw new ApiError(r.status, failure.code || (r.status === 401 ? "unauthorized" : `http_${r.status}`), detail, retryable);
  }
  return body;
}

async function reqBlob(path: string, opts: RequestInit = {}): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: "same-origin", ...opts });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "offline", "PrepPilot could not reach the course service.", true);
  }
  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    const body = contentType.includes("application/json") ? await response.json() : await response.text();
    const payload = typeof body === "object" && body ? body as Record<string, any> : {};
    const failure = payload.error && typeof payload.error === "object" ? payload.error : payload;
    const fallback = response.status === 401 ? "Your session expired." : `Request failed (${response.status}).`;
    const detail = normalizeDetail(failure.detail ?? payload.detail, fallback);
    const retryable = typeof failure.retryable === "boolean" ? failure.retryable : undefined;
    throw new ApiError(
      response.status,
      failure.code || (response.status === 401 ? "unauthorized" : `http_${response.status}`),
      detail,
      retryable,
    );
  }
  return response.blob();
}

function normalizeDetail(value: unknown, fallback: string): string {
  if (typeof value === "string" && value.trim()) return value;
  if (Array.isArray(value)) {
    const messages = value.map((item) => {
      if (!item || typeof item !== "object") return String(item);
      const detail = item as { loc?: unknown; msg?: unknown };
      const location = Array.isArray(detail.loc) ? detail.loc.map(String).join(".") : "";
      const message = typeof detail.msg === "string" ? detail.msg : JSON.stringify(item);
      return location ? `${location}: ${message}` : message;
    }).filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  return fallback;
}

export function describeApiError(error: unknown): string {
  if (!(error instanceof ApiError)) return "Something went wrong. Try again.";
  if (error.status === 401) return "Your session expired. Sign in again, then return to this mission.";
  if (error.status === 404) return "This course item is no longer available.";
  if (error.status === 409) return error.detail || "This mission changed. Refresh it before continuing.";
  if (error.status === 422) return error.detail || "Check the required evidence and try again.";
  if (error.status === 429) return "The course service is busy. Wait a moment, then retry this same action.";
  return error.detail || "PrepPilot could not reach the course service. Try again.";
}

export function newRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `course-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export type CourseState = "not_started" | "in_progress" | "ready_for_checkpoint" | "complete";
export type CourseModuleSummary = {
  id: string; order: number; callsign: string; title: string; prerequisites: string[]; platform: string;
  artifacts: { id: string; title: string; expectations: string[] }[];
  state: CourseState; next_action: string; url: string;
};
export type CourseOverview = {
  key: string; version: string; title: string; audience: string; enrolled: boolean; modules: CourseModuleSummary[];
};
export type CourseSource = { id: string; kind: string; label: string };
export type CourseArtifact = {
  id: string; title: string; template_key: string; output_format: string; template_fields: string[];
  verification_rubric: string[]; source_ids: string[]; completion_rule?: ArtifactCompletionRule | null;
};
export type ArtifactCompletionRule = {
  id: string; collection_field: string; entry_id_field: string; entry_value_field: string;
  entries: { source_id: string; label: string }[]; chosen_id_field: string | null;
  evidence_field: string | null; evidence_id_field: string | null; evidence_value_field: string | null;
  maximum_value_length: number;
};
export type ArtifactState = {
  artifact_id: string; title: string; completed: boolean; revision: number; note: string;
  artifact_uri: string; draft_fields: Record<string, unknown>; catalog_version: string;
};
export type OralTurnState = {
  turn_id: string; prompt: string; response: string; feedback: string; next_question: string; created_at: string;
};
export type OralState = {
  state: "not_started" | "practicing" | "awaiting_review" | "reviewed"; mode: string; revision: number;
  self_record_note: string; review_method: string; review_feedback: string; turns: OralTurnState[];
};
export type CourseModule = {
  id: string; title: string; callsign: string; mission_brief: string; prerequisites: string[];
  learning_objectives: string[]; lesson_outline: string[];
  lab: { title: string; platform: string; steps: string[]; verification: string; safety: string[] };
  checkpoint: { id: string; prompts: string[] };
  oral: { id: string; opening_prompt: string; rubric: string[] };
  artifacts: CourseArtifact[]; sources: CourseSource[]; oral_state: OralState; artifact_state: ArtifactState[];
  selection_rule?: { minimum: number; maximum: number; options: { id: string; label: string }[] } | null;
  debrief_prompt: string; progress: { mission_id: string; state: CourseState; completed_at: string | null };
  next_action: string; linked_topic: { concept_id: number; title: string; course_url: string; revision: number } | null;
};
export type LinkedCourseTopic = {
  id: number; module_id: string; title: string; track: string; summary: string; lesson_md: string;
  source: string; audience: string; course_url: string;
};
export type ReconciliationPreview = {
  module_id: string; state: "not_scanned" | "linked" | "partial" | "needs_confirmation" | "none_found" | "stale";
  revision: number; candidates: { concept_id: number; title: string; match_kind: string; candidate_fingerprint: string; partial: boolean }[];
  link?: { link_id: number; module_id: string; concept_id: number; match_kind: string; candidate_fingerprint: string; revision: number } | null;
};
export type OralTurnResult = {
  mission_id: string; turn_id: string; recorded: boolean; prompt: string; user_response: string;
  feedback: string; next_question: string; state: "practicing"; revision: number;
};
export type OralMutationResult = { mission_id: string; review_state: string; review_method: string; revision: number };
export type CheckpointResult = { checkpoint_id: string; attempt_id: number; passed: boolean; mission_state: string; feedback: string };

const coursePath = "/api/courses/inference-engineering";
const mutation = (path: string, method: "POST" | "PUT" | "DELETE", body: object) =>
  req(path, { method, headers: json, body: JSON.stringify(body) });

export type Card = {
  card_id: number;
  concept_id: number;
  concept_title: string;
  track: string;
  tags: string;
  kind: "mcq" | "free" | "code";
  prompt: string;
  choices: string[];
  is_new: boolean;
};

export type Plan = {
  date: string;
  reviews: Card[];
  new: Card[];
  streak: number;
  adaptive?: { new_topic_limit: number; reason: string; recent_accuracy: number | null };
};

export type LearnNext = {
  date: string;
  mode: "recover" | "review" | "learn" | "practice";
  title: string;
  reason: string;
  objective: string;
  estimated_minutes: number;
  action: { kind: "review_session" | "topic" | "coding_problem"; href: string; label: string };
  signals: {
    due_reviews: number;
    recent_accuracy: number | null;
    attempts_considered: number;
    weak_track: string | null;
    new_topic_limit: number;
  };
  concept: LearnNextConcept | null;
  up_next: LearnNextConcept | null;
};

export type LearnNextConcept = {
  id: number;
  title: string;
  track: string;
  difficulty: string;
  summary: string;
  mastery_state: "Unseen" | "Learning" | "Practiced" | "Retained";
};

export type LearningDiagnosis = {
  available: boolean;
  diagnosis: string;
  teaching_focus: string;
  check_question: string;
};

export type BookCitation = {
  section_id: number | null;
  citation: string;
  page_start: number;
  page_end: number;
};
export type BookChatResponse = { answer: string; citations: BookCitation[] };
export type BookChatMessage = { role: string; content: string; citations: BookCitation[] };

export type BookBookmark = {
  page: number;
  note: string | null;
  created_at: string;
  updated_at: string;
};

export type BookReaderState = {
  book_id: number;
  page: number;
  progress_updated_at: string | null;
  bookmarks: BookBookmark[];
};

export type BookSearchResult = { page: number; snippet: string; match_count: number };
export type BookSearchResponse = { query: string; results: BookSearchResult[]; truncated: boolean };

export type BookSection = {
  id: number; chapter: string; label: string; citation: string;
  page_start: number; page_end: number; status?: string; concept_id?: number;
  topic_title?: string; summary?: string; error_message?: string;
};
export type OwnerBook = {
  id: number; title: string; page_count: number; access: "owner"; is_owner: true;
  shared_with_all: boolean; status: string; total_sections: number; completed_sections: number;
  generated_lessons: number; failed_sections: number; remaining_sections: number;
  activated: boolean; error_code?: string; error_message?: string; sections?: BookSection[];
};
export type SharedBook = {
  id: number; title: string; page_count: number; access: "shared"; is_owner: false;
  shared_with_all: true; sections?: BookSection[];
};
export type Book = OwnerBook | SharedBook;
export type BookSharingResult = {
  book_id: number; access: "owner"; is_owner: true; shared_with_all: boolean;
  updated_at: string; changed: boolean;
};

const SHARED_SUMMARY_KEYS = new Set([
  "id", "title", "page_count", "access", "is_owner", "shared_with_all",
]);
const SHARED_DETAIL_KEYS = new Set([...SHARED_SUMMARY_KEYS, "sections"]);
const SHARED_SECTION_KEYS = new Set([
  "id", "chapter", "label", "page_start", "page_end", "citation",
]);

function integer(value: unknown, minimum = 0): value is number {
  return Number.isInteger(value) && (value as number) >= minimum;
}

function decodeSharedSection(value: unknown): BookSection | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  if (Object.keys(item).some((key) => !SHARED_SECTION_KEYS.has(key))) return null;
  if (!integer(item.id, 1) || typeof item.chapter !== "string" || typeof item.label !== "string"
      || typeof item.citation !== "string" || !integer(item.page_start, 1)
      || !integer(item.page_end, item.page_start as number)) return null;
  return item as BookSection;
}

function decodeBook(value: unknown, detail: boolean): Book | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  if (!integer(item.id, 1) || typeof item.title !== "string" || !integer(item.page_count)) return null;
  if (item.access === "shared") {
    const allowed = detail ? SHARED_DETAIL_KEYS : SHARED_SUMMARY_KEYS;
    if (item.is_owner !== false || item.shared_with_all !== true
        || Object.keys(item).some((key) => !allowed.has(key))) return null;
    if (detail) {
      if (!Array.isArray(item.sections)) return null;
      const sections = item.sections.map(decodeSharedSection);
      if (sections.some((section) => section === null)) return null;
      return { ...item, sections } as SharedBook;
    }
    return item as SharedBook;
  }
  if (item.access !== "owner" || item.is_owner !== true || typeof item.shared_with_all !== "boolean"
      || typeof item.status !== "string" || !integer(item.total_sections)
      || !integer(item.completed_sections) || !integer(item.generated_lessons)
      || !integer(item.failed_sections) || !integer(item.remaining_sections)
      || typeof item.activated !== "boolean") return null;
  if (detail && item.sections !== undefined && !Array.isArray(item.sections)) return null;
  return item as OwnerBook;
}

function decodeBookList(value: unknown): Book[] {
  return Array.isArray(value)
    ? value.map((item) => decodeBook(item, false)).filter((item): item is Book => item !== null)
    : [];
}

function decodeBookDetail(value: unknown): Book {
  const book = decodeBook(value, true);
  if (!book) throw new ApiError(0, "invalid_book_response", "PrepPilot received an invalid book response.", false);
  return book;
}

function decodeBookCitation(value: unknown): BookCitation | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  if (typeof item.citation !== "string" || !Number.isInteger(item.page_start) || !Number.isInteger(item.page_end)) return null;
  const start = item.page_start as number;
  const end = item.page_end as number;
  if (start < 1 || start > end) return null;
  if (item.section_id !== null && item.section_id !== undefined && !Number.isInteger(item.section_id)) return null;
  return {
    section_id: item.section_id == null ? null : item.section_id as number,
    citation: item.citation,
    page_start: start,
    page_end: end,
  };
}

function decodeBookCitations(value: unknown): BookCitation[] {
  return Array.isArray(value) ? value.map(decodeBookCitation).filter((item): item is BookCitation => item !== null) : [];
}

function decodeBookChatResponse(value: unknown): BookChatResponse {
  const item = value && typeof value === "object" ? value as Record<string, unknown> : {};
  return { answer: typeof item.answer === "string" ? item.answer : "", citations: decodeBookCitations(item.citations) };
}

function decodeBookChatHistory(value: unknown): BookChatMessage[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((row) => {
    if (!row || typeof row !== "object") return [];
    const item = row as Record<string, unknown>;
    if (typeof item.role !== "string" || typeof item.content !== "string") return [];
    return [{ role: item.role, content: item.content, citations: decodeBookCitations(item.citations) }];
  });
}

export type SubmitResult = {
  grade: number;
  correct: boolean;
  ai_feedback: string;
  answer: string;
  explanation: string;
  next_review_days: number;
};

export type JobStatus = "saved" | "applied" | "interview" | "offer" | "rejected" | "withdrawn";
export type JobApplication = {
  id: number;
  company: string;
  role: string;
  job_url: string;
  location: string;
  status: JobStatus;
  applied_date: string | null;
  follow_up_date: string | null;
  notes: string;
  created_at: string;
  updated_at: string;
};
export type JobsDashboard = {
  date: string;
  daily_target: number;
  applied_today: number;
  remaining_today: number;
  target_met: boolean;
  follow_ups_due: JobApplication[];
  counts: Record<JobStatus, number>;
  jobs: JobApplication[];
};

export const api = {
  needsSetup: () => req("/api/needs-setup"),
  setup: (password: string, username = "") =>
    fetch("/api/setup", { method: "POST", headers: json, body: JSON.stringify({ password, username }) }),
  me: () => req("/api/auth/me"),
  login: (username: string, password: string) =>
    fetch("/api/auth/login", { method: "POST", headers: json, body: JSON.stringify({ username, password }) }),
  register: (username: string, password: string, invite_code: string, level = "newgrad", lang = "python") =>
    fetch("/api/auth/register", { method: "POST", headers: json, body: JSON.stringify({ username, password, invite_code, level, lang }) }),
  logout: () => req("/api/auth/logout", { method: "POST" }),
  adminAudit: (days = 30) => req(`/api/auth/audit?days=${days}`),
  health: (): Promise<{ ok: boolean; environment: string; release: string; scheduler_enabled: boolean }> =>
    req("/api/health"),

  today: (): Promise<Plan> => req("/api/today"),
  learnNext: (): Promise<LearnNext> => req("/api/learn-next"),
  diagnoseLearnNext: (): Promise<LearningDiagnosis> =>
    req("/api/learn-next/diagnose", { method: "POST" }),
  roadmap: () => req("/api/roadmap"),
  books: (): Promise<Book[]> => req("/api/books").then(decodeBookList),
  book: (id: number): Promise<Book> => req(`/api/books/${id}`).then(decodeBookDetail),
  uploadBook: (file: File) => {
    const body = new FormData(); body.append("file", file);
    return req("/api/books", { method: "POST", body });
  },
  activateBook: (id: number) => req(`/api/books/${id}/activate`, { method: "POST" }),
  retryBook: (id: number) => req(`/api/books/${id}/retry`, { method: "POST" }),
  shareBook: (id: number, shared_with_all: boolean): Promise<BookSharingResult> =>
    req(`/api/books/${id}/sharing`, {
      method: "PUT", headers: json, body: JSON.stringify({ shared_with_all }),
    }),
  bookPageUrl: (id: number, page: number) => `/api/books/${id}/pages/${page}`,
  bookPage: (id: number, page: number, signal?: AbortSignal): Promise<Blob> =>
    reqBlob(`/api/books/${id}/pages/${page}`, { signal }),
  bookChat: (id: number, question: string, scope = "book", section_id?: number, page?: number): Promise<BookChatResponse> =>
    req(`/api/books/${id}/chat`, { method: "POST", headers: json, body: JSON.stringify({ question, scope, section_id, page }) }).then(decodeBookChatResponse),
  bookChatHistory: (id: number): Promise<BookChatMessage[]> => req(`/api/books/${id}/chat`).then(decodeBookChatHistory),
  clearBookChat: (id: number) => req(`/api/books/${id}/chat`, { method: "DELETE" }),
  bookReaderState: (id: number, signal?: AbortSignal): Promise<BookReaderState> =>
    req(`/api/books/${id}/reader-state`, { signal }),
  saveBookProgress: (id: number, page: number) =>
    req(`/api/books/${id}/progress`, { method: "PUT", headers: json, body: JSON.stringify({ page }) }),
  saveBookBookmark: (id: number, page: number, note: string) =>
    req(`/api/books/${id}/bookmarks/${page}`, { method: "PUT", headers: json, body: JSON.stringify({ note }) }),
  deleteBookBookmark: (id: number, page: number) =>
    req(`/api/books/${id}/bookmarks/${page}`, { method: "DELETE" }),
  searchBook: (id: number, query: string, signal?: AbortSignal): Promise<BookSearchResponse> =>
    req(`/api/books/${id}/search?q=${encodeURIComponent(query)}`, { signal }),
  card: (id: number) => req(`/api/card/${id}`),
  submit: (body: { card_id: number; user_answer?: string; self_grade?: number }): Promise<SubmitResult> =>
    req("/api/submit", { method: "POST", headers: json, body: JSON.stringify(body) }),
  progress: () => req("/api/progress"),
  topics: () => req("/api/topics"),
  topic: (id: number) => req(`/api/topic/${id}`),
  topicStatus: (id: number, completed: boolean) =>
    req(`/api/topic/${id}/status`, { method: "POST", headers: json, body: JSON.stringify({ completed }) }),
  ask: (question: string, context = "", history: { role: string; content: string }[] = []) =>
    req("/api/ask", { method: "POST", headers: json, body: JSON.stringify({ question, context, history }) }),
  brainHealth: () => req("/api/brain-health"),
  generateNow: (perTrack = 1) => req(`/api/generate-now?per_track=${perTrack}`, { method: "POST" }),

  // Blind 75 coding problems
  problems: () => req("/api/problems"),
  problem: (id: number) => req(`/api/problems/${id}`),
  problemStats: () => req("/api/problems/stats/summary"),
  problemOfTheDay: () => req("/api/problems/of-the-day"),
  problemApproach: (id: number) => req(`/api/problems/${id}/approach`, { method: "POST" }),
  problemStatus: (id: number, body: { status?: string; confidence?: number; notes?: string }) =>
    req(`/api/problems/${id}/status`, { method: "POST", headers: json, body: JSON.stringify(body) }),
  problemCoach: (id: number, plan: string) =>
    req(`/api/problems/${id}/coach`, { method: "POST", headers: json, body: JSON.stringify({ plan }) }),
  problemHints: (id: number) => req(`/api/problems/${id}/hints`),

  // Code execution + mentor + daily target
  starter: (id: number, language: string) => req(`/api/problems/${id}/starter?language=${language}`),
  runCode: (id: number, language: string, code: string) =>
    req(`/api/problems/${id}/run`, { method: "POST", headers: json, body: JSON.stringify({ language, code }) }),
  mentor: (id: number, body: { language: string; code: string; mode: string; message?: string; test_summary?: string; history?: any[] }) =>
    req(`/api/problems/${id}/mentor`, { method: "POST", headers: json, body: JSON.stringify(body) }),
  targetStatus: () => req("/api/problems/target/status"),
  setTarget: (body: { daily_problem_target?: number; goal_total?: number; goal_date?: string }) =>
    req("/api/problems/target", { method: "POST", headers: json, body: JSON.stringify(body) }),

  // Manual job search tracker
  jobs: (): Promise<JobsDashboard> => req("/api/jobs"),
  addJob: (body: Partial<JobApplication> & { company: string; role: string }) =>
    req("/api/jobs", { method: "POST", headers: json, body: JSON.stringify(body) }),
  updateJob: (id: number, body: Partial<JobApplication>) =>
    req(`/api/jobs/${id}`, { method: "PATCH", headers: json, body: JSON.stringify(body) }),
  deleteJob: (id: number) => req(`/api/jobs/${id}`, { method: "DELETE" }),
  setJobTarget: (daily_target: number) =>
    req("/api/jobs/target/daily", { method: "PUT", headers: json, body: JSON.stringify({ daily_target }) }),

  // Mock interviews
  mockStart: (body: { kind: string; topic?: string; duration_min?: number }) =>
    req("/api/mock/start", { method: "POST", headers: json, body: JSON.stringify(body) }),
  mockReply: (id: number, message: string) =>
    req(`/api/mock/${id}/reply`, { method: "POST", headers: json, body: JSON.stringify({ message }) }),
  mockFinish: (id: number) => req(`/api/mock/${id}/finish`, { method: "POST" }),
  mockHistory: () => req("/api/mock/history"),

  // Inference Flight School
  courseOverview: (signal?: AbortSignal): Promise<CourseOverview> => req(coursePath, { signal }),
  courseModule: (moduleId: string, signal?: AbortSignal): Promise<CourseModule> =>
    req(`${coursePath}/modules/${encodeURIComponent(moduleId)}`, { signal }),
  courseLinkedTopic: (moduleId: string, conceptId: number, signal?: AbortSignal): Promise<LinkedCourseTopic> =>
    req(`${coursePath}/modules/${encodeURIComponent(moduleId)}/linked-topics/${conceptId}`, { signal }),
  courseEnroll: (body: { request_id: string; catalog_version: string }) => mutation(`${coursePath}/enroll`, "POST", body),
  courseReconciliationPreview: (moduleId: string, scan = false, signal?: AbortSignal): Promise<ReconciliationPreview> =>
    req(`${coursePath}/reconcile/${encodeURIComponent(moduleId)}?scan=${scan}`, { signal }),
  courseReconcile: (body: object) => mutation(`${coursePath}/reconcile`, "POST", body),
  courseDeleteLink: (linkId: number, body: object) => mutation(`${coursePath}/links/${linkId}`, "DELETE", body),
  courseSaveArtifact: (missionId: string, artifactId: string, body: object) =>
    mutation(`${coursePath}/missions/${encodeURIComponent(missionId)}/artifacts/${encodeURIComponent(artifactId)}`, "PUT", body),
  courseCheckpoint: (checkpointId: string, body: object): Promise<CheckpointResult> =>
    mutation(`${coursePath}/checkpoints/${encodeURIComponent(checkpointId)}/submit`, "POST", body),
  courseOralTurn: (missionId: string, body: object): Promise<OralTurnResult> => mutation(`${coursePath}/oral/${encodeURIComponent(missionId)}/turn`, "POST", body),
  courseOralSelfRecord: (missionId: string, body: object): Promise<OralMutationResult> => mutation(`${coursePath}/oral/${encodeURIComponent(missionId)}/self-record`, "POST", body),
  courseOralComplete: (missionId: string, body: object): Promise<OralMutationResult> => mutation(`${coursePath}/oral/${encodeURIComponent(missionId)}/complete`, "POST", body),
  courseOralReview: (missionId: string, body: object): Promise<OralMutationResult> => mutation(`${coursePath}/oral/${encodeURIComponent(missionId)}/review`, "POST", body),
};

export type TestCase = { name: string; ok: boolean; expected: string; got: string };
export type RunResult = {
  ok: boolean; timed_out: boolean; exit_code: number; stdout: string; stderr: string;
  duration_ms: number; harness_validated: boolean;
  tests: { passed: number; total: number; cases: TestCase[] } | null;
};

export type ProblemItem = {
  id: number; slug: string; title: string; category: string;
  difficulty: "Easy" | "Medium" | "Hard"; url: string; blurb: string; pattern: string;
  status: "todo" | "attempted" | "solved"; confidence: number; has_approach: boolean;
  in_blind75: boolean;
};

export const catClass = (c: string) =>
  ({
    "Arrays & Hashing": "dsa", "Two Pointers": "dsa", "Sliding Window": "dsa",
    "1-D DP": "sd", "2-D DP": "sd", Greedy: "sd",
    Graphs: "cs", "Advanced Graphs": "cs", Trees: "bhv", Tries: "bhv",
  } as Record<string, string>)[c] || "";
export const diffClass = (d: string) =>
  ({ Easy: "diff-e", Medium: "diff-m", Hard: "diff-h" } as Record<string, string>)[d] || "";

export const trackClass = (t: string) =>
  ({ DSA: "dsa", "System Design": "sd", "CS Fundamentals": "cs", Behavioral: "bhv" } as Record<string, string>)[t] || "";
