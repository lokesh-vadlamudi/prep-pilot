import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InferenceModule from "./InferenceModule";
import { api, type CourseModule } from "../api";

const requestIds = vi.hoisted(() => ({ value: 0 }));

vi.mock("../api", () => ({
  api: {
    courseModule: vi.fn(), courseReconciliationPreview: vi.fn(), courseReconcile: vi.fn(), courseDeleteLink: vi.fn(),
    courseSaveArtifact: vi.fn(), courseCheckpoint: vi.fn(), courseOralTurn: vi.fn(), courseOralSelfRecord: vi.fn(),
    courseOralComplete: vi.fn(), courseOralReview: vi.fn(),
  },
  newRequestId: vi.fn(() => `request-${++requestIds.value}`),
  describeApiError: vi.fn(() => "Mission service is unavailable. Try again."),
}));

export const moduleDetail: CourseModule = {
  id: "IC-03", title: "Tower Control: vLLM", callsign: "TOWER",
  mission_brief: "Operate vLLM as a measured serving system.", prerequisites: ["IC-02"],
  learning_objectives: ["Explain PagedAttention", "Tune capacity"],
  lesson_outline: ["PagedAttention", "Scheduler and batching"],
  lab: { title: "Benchmark vLLM on DGX", platform: "dgx", steps: ["Serve an 8B model", "Sweep concurrency"], verification: "Capture TTFT and TPOT", safety: ["Display commands only", "Sanitize host output"] },
  checkpoint: { id: "IC-03-CHECKPOINT", prompts: ["Defend the scheduler choice"] },
  oral: { id: "IC-03-ORAL", opening_prompt: "Explain the serving bottleneck.", rubric: ["Uses measured evidence", "Names trade-offs"] },
  artifacts: [{ id: "IC-03-ARTIFACT", title: "vLLM benchmark report", template_key: "benchmark", output_format: "csv", template_fields: ["model", "ttft"], verification_rubric: ["Reports model and workload"], source_ids: ["SRC-P2-1-HANDS-BENCHMARK"] }],
  sources: [
    { id: "S1", kind: "topic", label: "Continuous batching" }, { id: "S2", kind: "resource", label: "vLLM docs" },
    { id: "S3", kind: "hands_on", label: "Concurrency benchmark" }, { id: "S4", kind: "workplace_project", label: "Observable gateway" },
    { id: "S5", kind: "paper", label: "PagedAttention paper" }, { id: "S6", kind: "hardware", label: "DGX Spark" },
    { id: "S7", kind: "routine", label: "Saturday lab" },
  ],
  oral_state: { state: "not_started", mode: "", revision: 0, self_record_note: "", review_method: "", review_feedback: "", turns: [] },
  artifact_state: [{ artifact_id: "IC-03-ARTIFACT", title: "vLLM benchmark report", completed: false, revision: 0, note: "", artifact_uri: "", draft_fields: {}, catalog_version: "2026.08.29" }],
  debrief_prompt: "What changed in your mental model?", progress: { mission_id: "IC-03", state: "in_progress", completed_at: null },
  next_action: "continue_mission", linked_topic: { concept_id: 42, title: "PagedAttention deep dive", course_url: "/courses/inference-engineering/IC-03/linked-topics/42", revision: 1 },
};

function mount() {
  return render(<MemoryRouter initialEntries={["/courses/inference-engineering/IC-03"]}>
    <Routes><Route path="/courses/inference-engineering/:moduleId" element={<InferenceModule />} /></Routes>
  </MemoryRouter>);
}

describe("InferenceModule journey", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
  beforeEach(() => {
    requestIds.value = 0;
    vi.clearAllMocks();
    vi.mocked(api.courseModule).mockResolvedValue(moduleDetail);
    vi.mocked(api.courseReconciliationPreview).mockResolvedValue({ module_id: "IC-03", state: "not_scanned", revision: 0, candidates: [] });
  });

  it("renders every mission stage and every source group in order", async () => {
    mount();
    const heading = await screen.findByRole("heading", { name: "Tower Control: vLLM" });
    expect(document.activeElement).toBe(heading);
    ["Learn", "Resources", "Lab checklist", "Checkpoint", "Oral interview", "Artifacts", "Debrief"].forEach((name) => {
      expect(screen.getByRole("heading", { name })).toBeTruthy();
    });
    ["Continuous batching", "vLLM docs", "Concurrency benchmark", "Observable gateway", "PagedAttention paper", "S6", "Saturday lab"].forEach((label) => expect(screen.getByText(label)).toBeTruthy());
    expect(screen.getByRole("link", { name: /open linked lesson/i }).getAttribute("href")).toBe("/courses/inference-engineering/IC-03/linked-topics/42");
    expect(document.body.textContent).not.toMatch(/\b(?:xp|points?|streaks?|scores?|grades?|badges?|leaderboards?|percentages?)\b/i);
  });

  it("resumes grounded oral turns and offers explicit online and offline practice", async () => {
    vi.mocked(api.courseModule).mockResolvedValue({
      ...moduleDetail,
      oral_state: { ...moduleDetail.oral_state, state: "practicing", revision: 1, turns: [{
        turn_id: "saved-turn", prompt: "Explain the scheduler.", response: "It batches active requests.",
        feedback: "Good foundation; connect this to queueing.", next_question: "What changes under burst load?", created_at: "2026-08-29T18:00:00Z",
      }] },
    });
    vi.mocked(api.courseOralTurn).mockResolvedValue({
      mission_id: "IC-03", recorded: true, turn_id: "request-1", prompt: "What changes under burst load?", user_response: "Queue delay grows.",
      feedback: "Useful operational framing.", next_question: "Which trace would verify it?", state: "practicing", revision: 2,
    });
    vi.mocked(api.courseOralSelfRecord).mockResolvedValue({ mission_id: "IC-03", review_state: "awaiting_review", review_method: "offline", revision: 2 });
    mount();
    expect(await screen.findByText("Good foundation; connect this to queueing.")).toBeTruthy();
    expect(screen.getByText("What changes under burst load?")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Your response"), { target: { value: "Queue delay grows." } });
    fireEvent.click(screen.getByRole("button", { name: "Send response" }));
    await waitFor(() => expect(api.courseOralTurn).toHaveBeenCalledWith("IC-03", {
      request_id: "request-1", catalog_version: "2026.08.29", response: "Queue delay grows.",
    }));
    expect(await screen.findByText("Which trace would verify it?")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Offline practice note"), { target: { value: "Recorded locally, then self-reviewed against the rubric." } });
    fireEvent.click(screen.getByRole("button", { name: "Save offline practice" }));
    await waitFor(() => expect(api.courseOralSelfRecord).toHaveBeenCalledWith("IC-03", {
      request_id: "request-2", catalog_version: "2026.08.29", expected_revision: 2,
      note: "Recorded locally, then self-reviewed against the rubric.",
    }));
    expect(document.body.textContent).not.toMatch(/\b(?:xp|points?|streaks?|scores?|grades?|percentages?)\b/i);
  });

  it("rotates the self-review action identity when failed content changes", async () => {
    vi.mocked(api.courseModule).mockResolvedValue({
      ...moduleDetail,
      oral_state: { ...moduleDetail.oral_state, state: "awaiting_review", revision: 2, self_record_note: "Recorded offline." },
    });
    vi.mocked(api.courseOralReview).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ mission_id: "IC-03", review_state: "reviewed", review_method: "self_rubric", revision: 3 });
    mount();
    await screen.findByRole("heading", { name: "Tower Control: vLLM" });
    fireEvent.click(screen.getByRole("checkbox", { name: "Uses measured evidence" }));
    fireEvent.change(screen.getByLabelText("Reflection"), { target: { value: "First reflection." } });
    fireEvent.click(screen.getByRole("button", { name: "Complete self-review" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Reflection"), { target: { value: "Revised reflection with trace evidence." } });
    fireEvent.click(screen.getByRole("button", { name: "Complete self-review" }));

    await waitFor(() => expect(api.courseOralReview).toHaveBeenCalledTimes(2));
    const [first, second] = vi.mocked(api.courseOralReview).mock.calls.map((call) => (call[1] as any).request_id);
    expect(second).not.toBe(first);
  });

  it("retains checkpoint answers and action identity for an exact retry, then shows qualitative feedback", async () => {
    vi.mocked(api.courseCheckpoint).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({
      checkpoint_id: moduleDetail.checkpoint.id, attempt_id: 1, passed: true,
      mission_state: "ready_for_checkpoint", feedback: "Your trade-off is grounded in measured scheduler behavior.",
    });
    mount();
    await screen.findByRole("heading", { name: "Tower Control: vLLM" });
    const answer = screen.getByLabelText("Defend the scheduler choice");
    fireEvent.change(answer, { target: { value: "I would compare queue delay and token throughput under the same workload." } });
    fireEvent.click(screen.getByRole("button", { name: "Submit checkpoint" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect((answer as HTMLTextAreaElement).value).toContain("queue delay");
    fireEvent.click(screen.getByRole("button", { name: "Retry checkpoint" }));

    await waitFor(() => expect(api.courseCheckpoint).toHaveBeenCalledTimes(2));
    const calls = vi.mocked(api.courseCheckpoint).mock.calls;
    expect((calls[0][1] as any).request_id).toBe((calls[1][1] as any).request_id);
    expect((calls[0][1] as any).answers).toEqual({ q1: "I would compare queue delay and token throughput under the same workload." });
    expect(await screen.findByText("Your trade-off is grounded in measured scheduler behavior.")).toBeTruthy();
  });

  it("gates mutation controls when a direct mission link requires enrollment", async () => {
    vi.mocked(api.courseModule).mockResolvedValue({ ...moduleDetail, next_action: "enroll" });
    mount();
    expect(await screen.findByText("Enroll before saving mission work")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open course enrollment" }).getAttribute("href")).toBe("/courses/inference-engineering");
    expect(screen.queryByRole("button", { name: "Submit checkpoint" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Send response" })).toBeNull();
  });

  it("retries the same oral debrief action and renders reload-visible reviewed feedback", async () => {
    vi.mocked(api.courseModule).mockResolvedValue({
      ...moduleDetail,
      oral_state: { ...moduleDetail.oral_state, state: "practicing", revision: 1 },
    });
    vi.mocked(api.courseOralComplete).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ mission_id: "IC-03", review_state: "reviewed", review_method: "dgx", revision: 2 });
    mount();
    await screen.findByRole("heading", { name: "Tower Control: vLLM" });
    fireEvent.click(screen.getByRole("button", { name: "Request qualitative debrief" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry qualitative debrief" }));
    await waitFor(() => expect(api.courseOralComplete).toHaveBeenCalledTimes(2));
    const ids = vi.mocked(api.courseOralComplete).mock.calls.map((call) => (call[1] as any).request_id);
    expect(ids[1]).toBe(ids[0]);
    expect(await screen.findByText(/DGX qualitative debrief was saved/)).toBeTruthy();
  });

  it("rotates a failed semantic debrief receipt after a new oral turn changes evidence revision", async () => {
    vi.mocked(api.courseModule).mockResolvedValue({
      ...moduleDetail,
      oral_state: { ...moduleDetail.oral_state, state: "practicing", revision: 1 },
    });
    vi.mocked(api.courseOralComplete)
      .mockRejectedValueOnce(new Error("oral_evidence_incomplete"))
      .mockResolvedValueOnce({ mission_id: "IC-03", review_state: "reviewed", review_method: "dgx", revision: 3 });
    vi.mocked(api.courseOralTurn).mockResolvedValue({
      mission_id: "IC-03", recorded: true, turn_id: "new-evidence-turn", prompt: "Explain the serving bottleneck.",
      user_response: "The trace shows queue delay under burst load.", feedback: "Evidence recorded.",
      next_question: "Which bound would you defend?", state: "practicing", revision: 2,
    });
    mount();
    await screen.findByRole("heading", { name: moduleDetail.title });
    fireEvent.click(screen.getByRole("button", { name: "Request qualitative debrief" }));
    expect(await screen.findByRole("button", { name: "Retry qualitative debrief" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Your response"), { target: { value: "The trace shows queue delay under burst load." } });
    fireEvent.click(screen.getByRole("button", { name: "Send response" }));
    await waitFor(() => expect(api.courseOralTurn).toHaveBeenCalledTimes(1));
    fireEvent.click(await screen.findByRole("button", { name: "Request qualitative debrief" }));
    await waitFor(() => expect(api.courseOralComplete).toHaveBeenCalledTimes(2));
    const calls = vi.mocked(api.courseOralComplete).mock.calls.map((call) => call[1] as any);
    expect(calls[1].request_id).not.toBe(calls[0].request_id);
    expect(calls[1].expected_revision).toBe(2);
  });

  it("renders the typed IC-12 selection and saves two to three stable source ids", async () => {
    const options = Array.from({ length: 8 }, (_, index) => ({ id: `SRC-EXP-${index + 1}`, label: `Experiment ${index + 1}` }));
    const artifact = { ...moduleDetail.artifacts[0], id: "IC-12-ARTIFACT", title: "Frontier experiment portfolio", template_fields: ["option_map", "selected_experiments", "measurements", "deferred_rationale", "next_probe"] };
    const state = { artifact_id: artifact.id, title: artifact.title, completed: false, revision: 2, note: "Owner note", artifact_uri: "artifacts/frontier.json", draft_fields: { option_map: "Mapped", selected_experiments: [options[0].id, options[1].id], measurements: "Captured", deferred_rationale: "Bounded", next_probe: "Probe" }, catalog_version: "2026.08.29" };
    vi.mocked(api.courseModule).mockResolvedValue({ ...moduleDetail, id: "IC-12", artifacts: [artifact], artifact_state: [state], selection_rule: { minimum: 2, maximum: 3, options } } as any);
    vi.mocked(api.courseSaveArtifact).mockResolvedValue({ ...state, revision: 3 });
    mount();
    await screen.findByRole("heading", { name: "Tower Control: vLLM" });
    const choices = screen.getAllByRole("checkbox", { name: /Experiment/ });
    expect(choices).toHaveLength(8);
    expect(choices.filter((choice) => (choice as HTMLInputElement).checked)).toHaveLength(2);
    fireEvent.click(choices[2]);
    fireEvent.click(screen.getByRole("button", { name: "Save artifact: Frontier experiment portfolio" }));
    await waitFor(() => expect(api.courseSaveArtifact).toHaveBeenCalledWith("IC-12", artifact.id, expect.objectContaining({
      expected_revision: 2,
      draft_fields: expect.objectContaining({ selected_experiments: [options[0].id, options[1].id, options[2].id] }),
    })));
  });

  it("renders exact IC-14 project scopes/proposal and nine ordered IC-16 paper notes", async () => {
    const workplaceEntries = Array.from({ length: 4 }, (_, index) => ({ source_id: `SRC-WP-0${index + 1}`, label: `Project ${index + 1}` }));
    const workplaceRule = { id: "workplace", collection_field: "project_scopes", entry_id_field: "project_id", entry_value_field: "scope", entries: workplaceEntries, chosen_id_field: "chosen_project_id", evidence_field: "selected_proposal", evidence_id_field: "project_id", evidence_value_field: "evidence", maximum_value_length: 2000 };
    const workplaceArtifact = { ...moduleDetail.artifacts[0], id: "IC-14-ARTIFACT", title: "Workplace proposal", template_fields: ["project_scopes", "chosen_project_id", "selected_proposal"], completion_rule: workplaceRule };
    vi.mocked(api.courseModule).mockResolvedValue({ ...moduleDetail, id: "IC-14", artifacts: [workplaceArtifact], artifact_state: [{ ...moduleDetail.artifact_state[0], artifact_id: workplaceArtifact.id, title: workplaceArtifact.title, draft_fields: { project_scopes: workplaceEntries.map((entry) => ({ project_id: entry.source_id, scope: `${entry.label} scope` })), chosen_project_id: workplaceEntries[0].source_id, selected_proposal: { project_id: workplaceEntries[0].source_id, evidence: "Proposal evidence" } } }] } as any);
    const view = mount();
    await screen.findByRole("heading", { name: "Tower Control: vLLM" });
    expect(screen.getAllByLabelText(/Scope: Project/)).toHaveLength(4);
    expect(screen.getByLabelText("Chosen project")).toBeTruthy();
    expect(screen.getByLabelText("Proposal evidence")).toBeTruthy();
    view.unmount();

    const paperEntries = Array.from({ length: 9 }, (_, index) => ({ source_id: `SRC-PAPER-${String(index + 1).padStart(2, "0")}`, label: `Paper ${index + 1}` }));
    const paperRule = { id: "papers", collection_field: "paper_notes", entry_id_field: "paper_id", entry_value_field: "note", entries: paperEntries, chosen_id_field: null, evidence_field: null, evidence_id_field: null, evidence_value_field: null, maximum_value_length: 2000 };
    const paperArtifact = { ...moduleDetail.artifacts[0], id: "IC-16-ARTIFACT", title: "Paper notes", template_fields: ["paper_notes"], completion_rule: paperRule };
    vi.mocked(api.courseModule).mockResolvedValue({ ...moduleDetail, id: "IC-16", artifacts: [paperArtifact], artifact_state: [{ ...moduleDetail.artifact_state[0], artifact_id: paperArtifact.id, title: paperArtifact.title, draft_fields: { paper_notes: paperEntries.map((entry) => ({ paper_id: entry.source_id, note: `${entry.label} note` })) } }] } as any);
    mount();
    await screen.findByRole("heading", { name: "Tower Control: vLLM" });
    expect(screen.getAllByLabelText(/Paper note: Paper/)).toHaveLength(9);
  });

  it("previews existing lessons before explicit retry-safe link confirmation", async () => {
    vi.mocked(api.courseModule).mockResolvedValue({ ...moduleDetail, linked_topic: null });
    const preview = { module_id: "IC-03", state: "needs_confirmation" as const, revision: 4, candidates: [
      { concept_id: 42, title: "PagedAttention deep dive", match_kind: "exact_title", candidate_fingerprint: "fingerprint-42", partial: false },
      { concept_id: 43, title: "Ambiguous scheduler notes", match_kind: "partial", candidate_fingerprint: "fingerprint-43", partial: true },
    ] };
    vi.mocked(api.courseReconciliationPreview).mockResolvedValueOnce({ module_id: "IC-03", state: "not_scanned", revision: 0, candidates: [] }).mockResolvedValueOnce(preview);
    vi.mocked(api.courseReconcile).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ link_id: 9, module_id: "IC-03", concept_id: 42, match_kind: "exact_title", candidate_fingerprint: "fingerprint-42", revision: 5, deleted: false });
    mount();
    await screen.findByRole("heading", { name: "Tower Control: vLLM" });
    fireEvent.click(screen.getByRole("button", { name: "Scan existing lessons" }));
    expect(await screen.findByText("Ambiguous scheduler notes")).toBeTruthy();
    expect(screen.getByText(/needs your confirmation because the match is partial/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Link PagedAttention deep dive" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry link PagedAttention deep dive" }));
    await waitFor(() => expect(api.courseReconcile).toHaveBeenCalledTimes(2));
    const ids = vi.mocked(api.courseReconcile).mock.calls.map((call) => (call[0] as any).request_id);
    expect(ids[1]).toBe(ids[0]);
    expect(await screen.findByRole("link", { name: "Open linked lesson →" })).toBeTruthy();
  });

  it("explains unmatched scans and deletes only the course link", async () => {
    vi.mocked(api.courseReconciliationPreview).mockResolvedValueOnce({ module_id: "IC-03", state: "linked", revision: 3, candidates: [], link: { link_id: 9, module_id: "IC-03", concept_id: 42, match_kind: "exact_title", candidate_fingerprint: "fingerprint-42", revision: 3 } });
    vi.mocked(api.courseDeleteLink).mockResolvedValue({ link_id: 9, module_id: "IC-03", concept_id: 42, match_kind: "exact_title", candidate_fingerprint: "fingerprint-42", revision: 4, deleted: true });
    mount();
    await screen.findByRole("heading", { name: "Tower Control: vLLM" });
    fireEvent.click(await screen.findByRole("button", { name: "Remove course link" }));
    await waitFor(() => expect(api.courseDeleteLink).toHaveBeenCalledWith(9, expect.objectContaining({ candidate_fingerprint: "fingerprint-42", expected_revision: 3 })));
    expect(api.courseReconcile).not.toHaveBeenCalled();
    expect(await screen.findByText(/independent lesson was not deleted/i)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Open linked lesson →" })).toBeNull();
  });

  it("rotates a failed confirm identity after a fresh scan revision", async () => {
    const candidate = { concept_id: 42, title: "PagedAttention deep dive", match_kind: "exact_title", candidate_fingerprint: "fingerprint-42", partial: false };
    vi.mocked(api.courseReconciliationPreview)
      .mockResolvedValueOnce({ module_id: "IC-03", state: "not_scanned", revision: 0, candidates: [] })
      .mockResolvedValueOnce({ module_id: "IC-03", state: "needs_confirmation", revision: 4, candidates: [candidate] })
      .mockResolvedValueOnce({ module_id: "IC-03", state: "needs_confirmation", revision: 5, candidates: [candidate] });
    vi.mocked(api.courseReconcile).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ link_id: 9, module_id: "IC-03", concept_id: 42, match_kind: "exact_title", candidate_fingerprint: "fingerprint-42", revision: 6, deleted: false });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Scan existing lessons" }));
    fireEvent.click(await screen.findByRole("button", { name: "Link PagedAttention deep dive" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Scan existing lessons" }));
    fireEvent.click(await screen.findByRole("button", { name: "Link PagedAttention deep dive" }));
    await waitFor(() => expect(api.courseReconcile).toHaveBeenCalledTimes(2));
    const ids = vi.mocked(api.courseReconcile).mock.calls.map((call) => (call[0] as any).request_id);
    expect(ids[1]).not.toBe(ids[0]);
    expect((vi.mocked(api.courseReconcile).mock.calls[1][0] as any).expected_revision).toBe(5);
  });

  it("explains a stale saved link and aborts a scan when the module unmounts", async () => {
    vi.mocked(api.courseReconciliationPreview).mockResolvedValueOnce({ module_id: "IC-03", state: "stale", revision: 3, candidates: [], link: { link_id: 9, module_id: "IC-03", concept_id: 42, match_kind: "exact_title", candidate_fingerprint: "fingerprint-42", revision: 3 } });
    const view = mount();
    expect(await screen.findByText(/saved link is stale/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Remove course link" })).toBeTruthy();
    view.unmount();

    let scanSignal: AbortSignal | undefined;
    vi.mocked(api.courseReconciliationPreview).mockResolvedValueOnce({ module_id: "IC-03", state: "not_scanned", revision: 0, candidates: [] }).mockImplementationOnce((_id, _scan, signal) => { scanSignal = signal; return new Promise(() => {}); });
    const pending = mount();
    fireEvent.click(await screen.findByRole("button", { name: "Scan existing lessons" }));
    pending.unmount();
    expect(scanSignal?.aborted).toBe(true);
  });

  it("recovers from mission and reconciliation loading failures without hiding the error", async () => {
    vi.mocked(api.courseModule).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(moduleDetail);
    vi.mocked(api.courseReconciliationPreview).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ module_id: "IC-03", state: "none_found", revision: 1, candidates: [] });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    await screen.findByRole("heading", { name: moduleDetail.title });
    expect(await screen.findByText(/Mission service is unavailable/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry checking lesson links" }));
    expect(await screen.findByText(/No matching private lesson was found/)).toBeTruthy();
  });

  it("retries link removal with one request id and preserves the lesson after failure", async () => {
    vi.mocked(api.courseReconciliationPreview).mockResolvedValue({ module_id: "IC-03", state: "linked", revision: 3, candidates: [], link: { link_id: 9, module_id: "IC-03", concept_id: 42, match_kind: "exact_title", candidate_fingerprint: "fingerprint-42", revision: 3 } });
    vi.mocked(api.courseDeleteLink).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ link_id: 9, module_id: "IC-03", concept_id: 42, match_kind: "exact_title", candidate_fingerprint: "fingerprint-42", revision: 4, deleted: true });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Remove course link" }));
    expect(await screen.findByRole("button", { name: "Retry removing course link" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open linked lesson/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry removing course link" }));
    await waitFor(() => expect(api.courseDeleteLink).toHaveBeenCalledTimes(2));
    const calls = vi.mocked(api.courseDeleteLink).mock.calls;
    expect((calls[0][1] as any).request_id).toBe((calls[1][1] as any).request_id);
  });

  it("preserves artifact drafts for exact retry, rotates after editing, and exports owner data", async () => {
    const state = { ...moduleDetail.artifact_state[0], completed: true, note: "Owner", artifact_uri: "artifacts/report.csv", draft_fields: { model: "llama", ttft: "30ms" } };
    vi.mocked(api.courseModule).mockResolvedValue({ ...moduleDetail, artifact_state: [state] });
    vi.mocked(api.courseSaveArtifact).mockRejectedValueOnce(new Error("offline")).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ ...state, revision: 1 });
    const createUrl = vi.fn(() => "blob:artifact");
    const revokeUrl = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL: createUrl, revokeObjectURL: revokeUrl });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    mount();
    await screen.findByText(/Completed evidence remains editable/);
    fireEvent.click(screen.getByRole("button", { name: /Save artifact/ }));
    expect(await screen.findByRole("button", { name: /Retry artifact/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Retry artifact/ }));
    await waitFor(() => expect(api.courseSaveArtifact).toHaveBeenCalledTimes(2));
    const firstIds = vi.mocked(api.courseSaveArtifact).mock.calls.map((call) => (call[2] as any).request_id);
    expect(firstIds[1]).toBe(firstIds[0]);
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "mixtral" } });
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Save artifact/ }));
    await screen.findByText("Artifact revision saved.");
    const finalId = (vi.mocked(api.courseSaveArtifact).mock.calls[2][2] as any).request_id;
    expect(finalId).not.toBe(firstIds[0]);
    fireEvent.click(screen.getByRole("button", { name: "Export draft" }));
    expect(createUrl).toHaveBeenCalled(); expect(click).toHaveBeenCalled(); expect(revokeUrl).toHaveBeenCalledWith("blob:artifact");
    click.mockRestore();
  });

  it("edits typed completion fields and enforces the experiment maximum", async () => {
    const options = Array.from({ length: 8 }, (_, index) => ({ id: `SRC-EXP-${index + 1}`, label: `Experiment ${index + 1}` }));
    const artifact = { ...moduleDetail.artifacts[0], id: "IC-12-ARTIFACT", template_fields: ["selected_experiments", "model"] };
    const state = { ...moduleDetail.artifact_state[0], artifact_id: artifact.id, draft_fields: { selected_experiments: options.slice(0, 3).map((option) => option.id), model: "llama" }, note: "Owner", artifact_uri: "artifacts/frontier.json" };
    vi.mocked(api.courseModule).mockResolvedValue({ ...moduleDetail, id: "IC-12", artifacts: [artifact], artifact_state: [state], selection_rule: { minimum: 2, maximum: 3, options } } as any);
    mount();
    const choices = await screen.findAllByRole("checkbox", { name: /Experiment/ });
    fireEvent.click(choices[3]);
    expect((choices[3] as HTMLInputElement).checked).toBe(false);
    fireEvent.click(choices[0]);
    expect((choices[0] as HTMLInputElement).checked).toBe(false);
  });

  it("keeps scan failures actionable and ignores an intentionally aborted rescan", async () => {
    vi.mocked(api.courseReconciliationPreview)
      .mockResolvedValueOnce({ module_id: "IC-03", state: "not_scanned", revision: 0, candidates: [] })
      .mockRejectedValueOnce(new Error("offline"))
      .mockRejectedValueOnce(new DOMException("superseded", "AbortError"));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "Scan existing lessons" }));
    expect(await screen.findByText(/Mission service is unavailable/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Scan existing lessons" }));
    await waitFor(() => expect(api.courseReconciliationPreview).toHaveBeenCalledTimes(3));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("rotates changed offline practice and completes a qualitative self-review", async () => {
    vi.mocked(api.courseModule).mockResolvedValue({ ...moduleDetail, oral_state: { ...moduleDetail.oral_state, state: "practicing", revision: 1 } });
    vi.mocked(api.courseOralSelfRecord)
      .mockRejectedValueOnce(new Error("offline")).mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ mission_id: "IC-03", review_state: "awaiting_review", review_method: "offline", revision: 2 });
    vi.mocked(api.courseOralReview).mockResolvedValue({ mission_id: "IC-03", review_state: "reviewed", review_method: "self", revision: 3 });
    mount();
    await screen.findByRole("heading", { name: moduleDetail.title });
    const note = screen.getByLabelText("Offline practice note");
    fireEvent.change(note, { target: { value: "First recording" } });
    fireEvent.click(screen.getByRole("button", { name: "Save offline practice" }));
    fireEvent.click(await screen.findByRole("button", { name: "Retry offline practice" }));
    await waitFor(() => expect(api.courseOralSelfRecord).toHaveBeenCalledTimes(2));
    const retryIds = vi.mocked(api.courseOralSelfRecord).mock.calls.map((call) => (call[1] as any).request_id);
    expect(retryIds[1]).toBe(retryIds[0]);
    fireEvent.change(note, { target: { value: "Revised recording" } });
    fireEvent.click(screen.getByRole("button", { name: "Save offline practice" }));
    await waitFor(() => expect(api.courseOralSelfRecord).toHaveBeenCalledTimes(3));
    expect((vi.mocked(api.courseOralSelfRecord).mock.calls[2][1] as any).request_id).not.toBe(retryIds[0]);
    const rubric = screen.getByRole("checkbox", { name: "Uses measured evidence" });
    fireEvent.click(rubric); fireEvent.click(rubric); fireEvent.click(rubric);
    fireEvent.change(screen.getByLabelText("Reflection"), { target: { value: "The trace supports the trade-off." } });
    fireEvent.click(screen.getByRole("button", { name: "Complete self-review" }));
    expect(await screen.findByText(/Practice reviewed/)).toBeTruthy();
  });

  it("updates exact completion-rule rows, chosen proposal evidence, and owner metadata", async () => {
    const entries = Array.from({ length: 4 }, (_, index) => ({ source_id: `SRC-WP-0${index + 1}`, label: `Project ${index + 1}` }));
    const rule = { id: "workplace", collection_field: "project_scopes", entry_id_field: "project_id", entry_value_field: "scope", entries, chosen_id_field: "chosen_project_id", evidence_field: "selected_proposal", evidence_id_field: "project_id", evidence_value_field: "evidence", maximum_value_length: 2000 };
    const artifact = { ...moduleDetail.artifacts[0], id: "IC-14-ARTIFACT", title: "Workplace proposal", template_fields: ["project_scopes", "chosen_project_id", "selected_proposal"], completion_rule: rule };
    const state = { ...moduleDetail.artifact_state[0], artifact_id: artifact.id, title: artifact.title, note: "", artifact_uri: "", draft_fields: {} };
    vi.mocked(api.courseModule).mockResolvedValue({ ...moduleDetail, id: "IC-14", artifacts: [artifact], artifact_state: [state] } as any);
    vi.mocked(api.courseSaveArtifact).mockResolvedValue({ ...state, revision: 1 });
    mount();
    const scopes = await screen.findAllByLabelText(/Scope: Project/);
    scopes.forEach((field, index) => fireEvent.change(field, { target: { value: `Bounded scope ${index + 1}` } }));
    fireEvent.change(screen.getByLabelText("Chosen project"), { target: { value: "SRC-WP-02" } });
    fireEvent.change(screen.getByLabelText("Proposal evidence"), { target: { value: "Trace and rollback evidence" } });
    fireEvent.change(screen.getByLabelText("Owner note"), { target: { value: "Owned by pilot" } });
    fireEvent.change(screen.getByLabelText("Artifact URI"), { target: { value: "https://artifacts.example/proposal.json" } });
    fireEvent.click(screen.getByRole("button", { name: /Save artifact/ }));
    await waitFor(() => expect(api.courseSaveArtifact).toHaveBeenCalledWith("IC-14", artifact.id, expect.objectContaining({
      draft_fields: expect.objectContaining({ chosen_project_id: "SRC-WP-02", selected_proposal: { project_id: "SRC-WP-02", evidence: "Trace and rollback evidence" } }),
    })));
  });

  it("renders boundary navigation, fallback labels, empty sources, and missing artifact state", async () => {
    vi.mocked(api.courseModule).mockResolvedValue({
      ...moduleDetail, id: "IC-00", prerequisites: [], sources: [],
      lab: { ...moduleDetail.lab, platform: "optional_cloud" }, progress: { ...moduleDetail.progress, state: "complete" },
      artifacts: [{ ...moduleDetail.artifacts[0], id: "missing" }], artifact_state: [], linked_topic: null,
    });
    mount();
    await screen.findByRole("heading", { name: moduleDetail.title });
    expect(screen.queryByRole("link", { name: /Previous mission/ })).toBeNull();
    expect(screen.getByRole("link", { name: /Next mission/ })).toHaveAttribute("href", "/courses/inference-engineering/IC-01");
    expect(screen.getAllByText("Optional cloud lab").length).toBeGreaterThan(0);
    expect(screen.getByText("Complete")).toBeTruthy();
    expect(screen.getAllByText(/No additional catalog entries/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Artifact state is unavailable/)).toBeTruthy();
  });

  it("ignores an aborted mission load", async () => {
    vi.mocked(api.courseModule).mockRejectedValue(new DOMException("departed", "AbortError"));
    const view = mount();
    expect(await screen.findByRole("status")).toHaveTextContent("loading mission");
    view.unmount();
  });

  it("guides portable artifact locations and rejects a local-machine file URI", async () => {
    vi.mocked(api.courseModule).mockResolvedValue({
      ...moduleDetail,
      artifact_state: [{ ...moduleDetail.artifact_state[0], note: "Owner", artifact_uri: "artifacts/report.csv", draft_fields: { model: "llama", ttft: "30ms" } }],
    });
    mount();
    const uri = await screen.findByLabelText("Artifact URI");
    expect(uri).toHaveAttribute("placeholder", "HTTPS URL or repository-relative path");
    expect(screen.getByText("HTTPS URL or repository-relative path")).toBeTruthy();
    for (const rejected of ["file:///Users/pilot/report.csv", "/tmp/report.csv", "../private/report.csv", "http://insecure.example/report.csv", "https://", "https:///report.csv", "https://pilot@artifacts.example/report.csv", "https://pilot:secret@artifacts.example/report.csv", ""]) {
      fireEvent.change(uri, { target: { value: rejected } });
      expect(screen.getByRole("button", { name: /Save artifact/ })).toBeDisabled();
    }
    for (const accepted of ["https://artifacts.example/report.csv", "artifacts/report.csv"]) {
      fireEvent.change(uri, { target: { value: accepted } });
      expect(screen.getByRole("button", { name: /Save artifact/ })).toBeEnabled();
    }
  });

  it("keeps aborted reconciliation neutral and renders the persisted reviewed fallback", async () => {
    vi.mocked(api.courseModule).mockResolvedValue({ ...moduleDetail, oral_state: { ...moduleDetail.oral_state, state: "reviewed", revision: 4, review_feedback: "" } });
    vi.mocked(api.courseReconciliationPreview).mockRejectedValue(new DOMException("departed", "AbortError"));
    mount();
    expect(await screen.findByText(/oral practice is reviewed and remains available/)).toBeTruthy();
    expect(screen.getByText("checking existing lesson links")).toBeTruthy();
    expect(screen.queryByText(/Mission service is unavailable/)).toBeNull();
  });

  it("rotates checkpoint identity when failed answers change", async () => {
    vi.mocked(api.courseCheckpoint).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({
      checkpoint_id: moduleDetail.checkpoint.id, attempt_id: 2, passed: false,
      mission_state: "in_progress", feedback: "Clarify the workload evidence.",
    });
    mount();
    const answer = await screen.findByLabelText("Defend the scheduler choice");
    fireEvent.change(answer, { target: { value: "First answer" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit checkpoint" }));
    await screen.findByRole("alert");
    fireEvent.change(answer, { target: { value: "Revised answer" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit checkpoint" }));
    await waitFor(() => expect(api.courseCheckpoint).toHaveBeenCalledTimes(2));
    const calls = vi.mocked(api.courseCheckpoint).mock.calls;
    expect((calls[0][1] as any).request_id).not.toBe((calls[1][1] as any).request_id);
  });

  it("treats non-string generic drafts and absent experiment selections as incomplete", async () => {
    const options = Array.from({ length: 8 }, (_, index) => ({ id: `SRC-EXP-${index + 1}`, label: `Experiment ${index + 1}` }));
    const state = { ...moduleDetail.artifact_state[0], note: "Owner", artifact_uri: "artifacts/report.csv", draft_fields: { model: 42, ttft: "30ms" } };
    vi.mocked(api.courseModule).mockResolvedValue({ ...moduleDetail, id: "IC-12", artifact_state: [state], selection_rule: { minimum: 2, maximum: 3, options } } as any);
    mount();
    expect(await screen.findByLabelText("Model")).toHaveValue("");
    expect(screen.getAllByRole("checkbox", { name: /Experiment/ }).every((choice) => !(choice as HTMLInputElement).checked)).toBe(true);
    expect(screen.getByRole("button", { name: /Save artifact/ })).toBeDisabled();
  });
});
