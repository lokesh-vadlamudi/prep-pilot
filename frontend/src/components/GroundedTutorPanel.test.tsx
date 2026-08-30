import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import GroundedTutorPanel, { type GroundedTutorResult, type GroundedTutorTurn } from "./GroundedTutorPanel";
import { newRequestId } from "../api";

vi.mock("../api", () => ({
  newRequestId: vi.fn()
    .mockReturnValueOnce("request-one")
    .mockReturnValueOnce("request-two")
    .mockReturnValue("request-later"),
  describeApiError: vi.fn(() => "The DGX tutor is unavailable. Your draft is safe; retry when ready."),
}));

const persisted = [{
  id: "turn-1",
  prompt: "Why does batching improve throughput?",
  response: "It shares model work across requests.",
  feedback: "Good start. Name the latency trade-off.",
}];

describe("GroundedTutorPanel", () => {
  afterEach(cleanup);

  it("restores qualitative turns and retries the same action without losing the draft", async () => {
    const submit = vi.fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({
        id: "turn-2",
        prompt: "What happens to latency?",
        response: "Queue time can rise.",
        feedback: "Grounded in the scheduler behavior.",
        nextQuestion: "How would you verify that on DGX?",
      });
    render(<GroundedTutorPanel
      identityKey="IC-03:0"
      eyebrow="DGX · MISSION GROUNDED"
      title="Practice the oral interview"
      prompt="What happens to latency?"
      turns={persisted}
      onSubmit={submit}
    />);

    expect(screen.getByText(persisted[0].prompt)).toBeTruthy();
    expect(screen.getByText(persisted[0].response)).toBeTruthy();
    expect(screen.getByText(persisted[0].feedback)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Your response"), { target: { value: "Queue time can rise." } });
    fireEvent.click(screen.getByRole("button", { name: "Send response" }));
    expect((await screen.findByRole("alert")).textContent).toContain("draft is safe");
    expect((screen.getByLabelText("Your response") as HTMLTextAreaElement).value).toBe("Queue time can rise.");
    fireEvent.click(screen.getByRole("button", { name: "Retry response" }));

    await waitFor(() => expect(submit).toHaveBeenCalledTimes(2));
    expect(submit.mock.calls.map((call) => call[1])).toEqual(["request-one", "request-one"]);
    expect(await screen.findByText("Grounded in the scheduler behavior.")).toBeTruthy();
    expect(screen.getByText("How would you verify that on DGX?")).toBeTruthy();
    expect((screen.getByLabelText("Your response") as HTMLTextAreaElement).value).toBe("");
    expect(document.body.textContent).not.toMatch(/\b(?:xp|points?|streaks?|scores?|grades?|percentages?)\b/i);
  });

  it("ignores an old response after the grounded identity changes", async () => {
    let resolve!: (value: any) => void;
    const submit = vi.fn(() => new Promise<GroundedTutorResult>((done) => { resolve = done; }));
    const { rerender } = render(<GroundedTutorPanel identityKey="topic:1" title="Tutor this topic" prompt="First prompt" turns={[]} onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText("Your response"), { target: { value: "Old draft" } });
    fireEvent.click(screen.getByRole("button", { name: "Send response" }));
    rerender(<GroundedTutorPanel identityKey="topic:2" title="Tutor this topic" prompt="New prompt" turns={[]} onSubmit={submit} />);
    resolve({ id: "old", prompt: "First prompt", response: "Old draft", feedback: "Old feedback", nextQuestion: "Old follow-up" });

    await waitFor(() => expect(screen.getByText("New prompt")).toBeTruthy());
    expect(screen.queryByText("Old feedback")).toBeNull();
    expect((screen.getByLabelText("Your response") as HTMLTextAreaElement).value).toBe("");
  });

  it("invalidates a late response when the panel unmounts", async () => {
    let resolve!: (value: any) => void;
    const submit = vi.fn(() => new Promise<GroundedTutorResult>((done) => { resolve = done; }));
    const { unmount } = render(<GroundedTutorPanel identityKey="course:one" title="Practice" prompt="Prompt" turns={[]} onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText("Your response"), { target: { value: "Pending response" } });
    fireEvent.click(screen.getByRole("button", { name: "Send response" }));
    const idsBeforeUnmount = vi.mocked(newRequestId).mock.calls.length;
    unmount();
    resolve({ id: "late", prompt: "Prompt", response: "Pending response", feedback: "Late feedback", nextQuestion: "Late question" });
    await Promise.resolve();
    expect(vi.mocked(newRequestId).mock.calls.length).toBe(idsBeforeUnmount);
  });

  it("sends on Enter while preserving Shift+Enter for a new line", async () => {
    const submit = vi.fn().mockResolvedValue({ id: "keyboard", prompt: "Prompt", response: "Keyboard response", feedback: "Feedback", nextQuestion: "Next" });
    render(<GroundedTutorPanel identityKey="keyboard" title="Practice" prompt="Prompt" turns={[]} onSubmit={submit} />);
    const input = screen.getByLabelText("Your response");
    fireEvent.change(input, { target: { value: "Keyboard response" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
  });

  it("rotates identity when changed content invalidates an in-flight action", async () => {
    vi.mocked(newRequestId).mockReturnValueOnce("action-before-change").mockReturnValueOnce("action-after-change").mockReturnValue("action-after-success");
    let resolve!: (value: GroundedTutorResult) => void;
    const submit = vi.fn(() => new Promise<GroundedTutorResult>((done) => { resolve = done; }));
    render(<GroundedTutorPanel identityKey="change" eyebrow="Mac · SELF REVIEW" helperText="Use local evidence." placeholder="Write a reflection" title="Practice" prompt="Prompt" turns={[]} onSubmit={submit} />);
    const input = screen.getByLabelText("Your response");
    expect(input.getAttribute("placeholder")).toBe("Write a reflection");
    expect(screen.getByText("Use local evidence.")).toBeTruthy();
    fireEvent.change(input, { target: { value: "First payload" } });
    fireEvent.click(screen.getByRole("button", { name: "Send response" }));
    expect(await screen.findByRole("status")).toBeTruthy();
    fireEvent.change(input, { target: { value: "Different payload" } });
    expect(screen.queryByRole("status")).toBeNull();
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(submit).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(2));
    const actions = submit.mock.calls as unknown as [string, string, GroundedTutorTurn[]][];
    expect(actions.map((call) => call[1])).toEqual(["action-before-change", "action-after-change"]);
    resolve({ id: "latest", prompt: "Prompt", response: "Different payload", feedback: "Saved", nextQuestion: "Next" });
    await screen.findByText("Saved");
  });
});
