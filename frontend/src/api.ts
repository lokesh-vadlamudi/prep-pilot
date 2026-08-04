const json = { "Content-Type": "application/json" };

async function req(path: string, opts: RequestInit = {}) {
  const r = await fetch(path, { credentials: "same-origin", ...opts });
  if (r.status === 401) throw new Error("unauthorized");
  if (!r.ok) throw new Error(`${r.status}`);
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.text();
}

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

export type SubmitResult = {
  grade: number;
  correct: boolean;
  ai_feedback: string;
  answer: string;
  explanation: string;
  next_review_days: number;
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
  health: (): Promise<{ ok: boolean; environment: string; release: string; scheduler_enabled: boolean }> =>
    req("/api/health"),

  today: (): Promise<Plan> => req("/api/today"),
  learnNext: (): Promise<LearnNext> => req("/api/learn-next"),
  diagnoseLearnNext: (): Promise<LearningDiagnosis> =>
    req("/api/learn-next/diagnose", { method: "POST" }),
  roadmap: () => req("/api/roadmap"),
  books: () => req("/api/books"),
  book: (id: number) => req(`/api/books/${id}`),
  uploadBook: (file: File) => {
    const body = new FormData(); body.append("file", file);
    return req("/api/books", { method: "POST", body });
  },
  activateBook: (id: number) => req(`/api/books/${id}/activate`, { method: "POST" }),
  retryBook: (id: number) => req(`/api/books/${id}/retry`, { method: "POST" }),
  bookChat: (id: number, question: string, scope = "book", section_id?: number) =>
    req(`/api/books/${id}/chat`, { method: "POST", headers: json, body: JSON.stringify({ question, scope, section_id }) }),
  bookChatHistory: (id: number) => req(`/api/books/${id}/chat`),
  card: (id: number) => req(`/api/card/${id}`),
  submit: (body: { card_id: number; user_answer?: string; self_grade?: number }): Promise<SubmitResult> =>
    req("/api/submit", { method: "POST", headers: json, body: JSON.stringify(body) }),
  progress: () => req("/api/progress"),
  topics: () => req("/api/topics"),
  topic: (id: number) => req(`/api/topic/${id}`),
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

  // Mock interviews
  mockStart: (body: { kind: string; topic?: string; duration_min?: number }) =>
    req("/api/mock/start", { method: "POST", headers: json, body: JSON.stringify(body) }),
  mockReply: (id: number, message: string) =>
    req(`/api/mock/${id}/reply`, { method: "POST", headers: json, body: JSON.stringify({ message }) }),
  mockFinish: (id: number) => req(`/api/mock/${id}/finish`, { method: "POST" }),
  mockHistory: () => req("/api/mock/history"),
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
