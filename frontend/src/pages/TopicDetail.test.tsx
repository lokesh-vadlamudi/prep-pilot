import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TopicDetail from "./TopicDetail";
import { api } from "../api";

vi.mock("../components/ReviewCard", () => ({
  default: ({ card, onDone }: any) => <div data-testid={`review-${card.card_id}`}>
    <button onClick={() => onDone({ correct: card.card_id % 2 === 1, feedback: "reviewed" })}>Finish card</button>
    <button onClick={() => onDone()}>Skip card</button>
  </div>,
}));

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return { ...actual, api: { ...actual.api, topic: vi.fn(), topicStatus: vi.fn(), ask: vi.fn() } };
});

const topic = {
  id: 7, title: "Continuous batching", track: "system-design", difficulty: "advanced",
  source: "curated", completed: false, summary: "Batch active requests together.",
  lesson_md: "# Scheduler\nServe work continuously.", tags: "inference", cards: [], book_navigation: null,
};

describe("TopicDetail grounded tutor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("scrollTo", vi.fn());
    vi.mocked(api.topic).mockResolvedValue(topic);
    vi.mocked(api.ask).mockResolvedValue({ answer: "Paged batching reuses available compute while requests advance." });
  });
  afterEach(cleanup);

  it("keeps the standard lesson and uses the shared accessible grounded response flow", async () => {
    render(<MemoryRouter initialEntries={["/topics/7"]}><Routes><Route path="/topics/:id" element={<TopicDetail />} /></Routes></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Continuous batching" })).toBeTruthy();
    expect(screen.getByText("Serve work continuously.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Your response"), { target: { value: "Explain why batches can change while decoding." } });
    fireEvent.click(screen.getByRole("button", { name: "Send response" }));

    expect(await screen.findByText(/Paged batching reuses/)).toBeTruthy();
    expect(screen.getByText("What would you like to examine next?")).toBeTruthy();
    await waitFor(() => expect(api.ask).toHaveBeenCalledTimes(1));
    expect(api.ask).toHaveBeenCalledWith(expect.stringContaining("batches can change"), expect.stringContaining("Continuous batching"), expect.any(Array));
    fireEvent.change(screen.getByLabelText("Your response"), { target: { value: "Show a trace example." } });
    fireEvent.click(screen.getByRole("button", { name: "Send response" }));
    await waitFor(() => expect(api.ask).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.ask).mock.calls[1][2]).toHaveLength(3);
  });

  it("does not let a late quiz opening overwrite a return to tutor mode", async () => {
    let resolveQuiz!: (value: { answer: string }) => void;
    const quizResponse = new Promise<{ answer: string }>((resolve) => { resolveQuiz = resolve; });
    vi.mocked(api.ask).mockImplementationOnce(() => quizResponse);
    render(<MemoryRouter initialEntries={["/topics/7"]}><Routes><Route path="/topics/:id" element={<TopicDetail />} /></Routes></MemoryRouter>);
    await screen.findByRole("heading", { name: "Continuous batching" });
    fireEvent.click(screen.getByRole("button", { name: "Quiz me" }));
    fireEvent.click(screen.getByRole("button", { name: "Tutor" }));
    await act(async () => { resolveQuiz({ answer: "Stale quiz opening" }); await quizResponse; });
    expect(screen.getByText("What would you like to explore about Continuous batching?")).toBeTruthy();
    expect(screen.queryByText("Stale quiz opening")).toBeNull();
  });

  it("preserves the complete book journey, quiz, and lesson completion controls", async () => {
    const withCards = {
      ...topic, source: "ai", tags: "", cards: [
        { card_id: 11, introduced: false, question: "q1" },
        { card_id: 12, introduced: true, question: "q2" },
      ],
      book_navigation: {
        book_title: "Inference handbook", position: 2, total: 3,
        previous: { id: 6, title: "Previous lesson" }, next: { id: 8, title: "Next lesson" },
      },
    };
    vi.mocked(api.topic).mockResolvedValue(withCards);
    vi.mocked(api.topicStatus).mockResolvedValue({ ok: true });
    render(<MemoryRouter initialEntries={["/topics/7"]}><Routes><Route path="/topics/:id" element={<TopicDetail />} /></Routes></MemoryRouter>);
    await screen.findByRole("heading", { name: topic.title });
    expect(screen.getByText("ai-authored")).toBeTruthy();
    expect(screen.getByText("Inference handbook")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Previous lesson/ })).toHaveAttribute("href", "/topics/6");
    expect(screen.getByRole("link", { name: /Next lesson/ })).toHaveAttribute("href", "/topics/8");
    fireEvent.click(screen.getByRole("button", { name: /mark complete/i }));
    await waitFor(() => expect(api.topicStatus).toHaveBeenCalledWith(7, true));
    expect(screen.getByRole("button", { name: /completed/i })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: /start quiz/i }));
    expect(screen.getByText(/QUESTION 1 \/ 2/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /back to lesson/i }));
    fireEvent.click(screen.getByRole("button", { name: /start quiz/i }));
    fireEvent.click(screen.getByRole("button", { name: "Finish card" }));
    expect(await screen.findByText(/QUESTION 2 \/ 2/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Skip card" }));
    expect(await screen.findByRole("heading", { name: "1 of 1 correct" })).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /next lesson/i }).every((link) => link.getAttribute("href") === "/topics/8")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /retry quiz/i }));
    expect(screen.getByText(/QUESTION 1 \/ 2/)).toBeTruthy();
  });

  it("marks an unfinished lesson complete after its last card and supports reviewing it", async () => {
    vi.mocked(api.topic).mockResolvedValue({ ...topic, cards: [{ card_id: 21, introduced: false }], book_navigation: { book_title: "Book", position: 1, total: 1, previous: null, next: null } });
    vi.mocked(api.topicStatus).mockResolvedValue({ ok: true });
    render(<MemoryRouter initialEntries={["/topics/7"]}><Routes><Route path="/topics/:id" element={<TopicDetail />} /></Routes></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /start quiz/i }));
    fireEvent.click(screen.getByRole("button", { name: "Finish card" }));
    await waitFor(() => expect(api.topicStatus).toHaveBeenCalledWith(7, true));
    expect((await screen.findAllByRole("link", { name: /finish/i })).every((link) => link.getAttribute("href") === "/read")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /review lesson/i }));
    expect(await screen.findByText("Serve work continuously.")).toBeTruthy();
  });

  it("starts an honest oral quiz, submits grounded history, and explains a failed opening", async () => {
    vi.mocked(api.ask)
      .mockResolvedValueOnce({ answer: "Why can queue time rise?" })
      .mockResolvedValueOnce({ answer: "Correct trade-off. Now justify a bound." })
      .mockRejectedValueOnce(new Error("offline"));
    render(<MemoryRouter initialEntries={["/topics/7"]}><Routes><Route path="/topics/:id" element={<TopicDetail />} /></Routes></MemoryRouter>);
    await screen.findByRole("heading", { name: topic.title });
    fireEvent.click(screen.getByRole("button", { name: "Quiz me" }));
    expect(await screen.findByText("Why can queue time rise?")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Your response"), { target: { value: "Because admission can wait." } });
    fireEvent.keyDown(screen.getByLabelText("Your response"), { key: "Enter" });
    expect(await screen.findByText(/Correct trade-off/)).toBeTruthy();
    expect(screen.getByText(/deeper question/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Tutor" }));
    fireEvent.click(screen.getByRole("button", { name: "Quiz me" }));
    expect(await screen.findByText(/DGX tutor is unavailable/)).toBeTruthy();
  });

  it("leaves a route without an id in loading state", () => {
    render(<MemoryRouter><TopicDetail /></MemoryRouter>);
    expect(screen.getByText("loading")).toBeTruthy();
    expect(api.topic).not.toHaveBeenCalled();
  });

  it("finishes a standalone already-complete quiz without changing lesson status", async () => {
    vi.mocked(api.topic).mockResolvedValue({ ...topic, completed: true, cards: [{ card_id: 31, introduced: true }] });
    render(<MemoryRouter initialEntries={["/topics/7"]}><Routes><Route path="/topics/:id" element={<TopicDetail />} /></Routes></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /start quiz/i }));
    fireEvent.click(screen.getByRole("button", { name: "Skip card" }));
    expect(await screen.findByRole("heading", { name: "0 of 0 correct" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /finish/i })).toHaveAttribute("href", "/topics");
    expect(api.topicStatus).not.toHaveBeenCalled();
  });

  it("invalidates a late quiz opening when the topic unmounts", async () => {
    let resolveQuiz!: (value: { answer: string }) => void;
    vi.mocked(api.ask).mockImplementationOnce(() => new Promise((resolve) => { resolveQuiz = resolve; }));
    const view = render(<MemoryRouter initialEntries={["/topics/7"]}><Routes><Route path="/topics/:id" element={<TopicDetail />} /></Routes></MemoryRouter>);
    await screen.findByRole("heading", { name: topic.title });
    fireEvent.click(screen.getByRole("button", { name: "Quiz me" }));
    view.unmount();
    await act(async () => resolveQuiz({ answer: "Late opening" }));
    expect(api.ask).toHaveBeenCalledTimes(1);
  });
});
