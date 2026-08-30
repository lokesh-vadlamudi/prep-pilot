import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InferenceLinkedTopic from "./InferenceLinkedTopic";
import { api } from "../api";

vi.mock("../api", () => ({
  api: { courseLinkedTopic: vi.fn() },
  describeApiError: vi.fn(() => "Linked lesson is unavailable."),
}));

describe("InferenceLinkedTopic", () => {
  afterEach(cleanup);
  beforeEach(() => vi.clearAllMocks());

  it("uses only the nested read-only lesson contract", async () => {
    vi.mocked(api.courseLinkedTopic).mockResolvedValue({
      id: 42, module_id: "IC-03", title: "PagedAttention", track: "Inference Engineering",
      summary: "Private source-backed lesson", lesson_md: "## Reused lesson\nBounded content.",
      source: "book", audience: "senior",
      course_url: "/courses/inference-engineering/IC-03/linked-topics/42",
    });
    render(<MemoryRouter initialEntries={["/courses/inference-engineering/IC-03/linked-topics/42"]}>
      <Routes><Route path="/courses/inference-engineering/:moduleId/linked-topics/:conceptId" element={<InferenceLinkedTopic />} /></Routes>
    </MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "PagedAttention" })).toBeTruthy();
    expect(api.courseLinkedTopic).toHaveBeenCalledWith("IC-03", 42, expect.any(AbortSignal));
    expect(screen.getByRole("link", { name: /return to mission/i }).getAttribute("href")).toBe("/courses/inference-engineering/IC-03");
    expect(document.body.textContent).not.toMatch(/quiz|sm-?2|grade|percentage|score/i);
  });

  it("shows a typed failure, retries, and aborts when the route departs", async () => {
    vi.mocked(api.courseLinkedTopic)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({
        id: 7, module_id: "IC-09", title: "Retry lesson", track: "Inference Engineering",
        summary: "Recovered", lesson_md: "Safe content", source: "book", audience: "senior",
        course_url: "/courses/inference-engineering/IC-09/linked-topics/7",
      });
    const view = render(<MemoryRouter initialEntries={["/courses/inference-engineering/IC-09/linked-topics/7"]}>
      <Routes><Route path="/courses/inference-engineering/:moduleId/linked-topics/:conceptId" element={<InferenceLinkedTopic />} /></Routes>
    </MemoryRouter>);
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    const heading = await screen.findByRole("heading", { name: "Retry lesson" });
    expect(document.activeElement).toBe(heading);
    const initialSignal = vi.mocked(api.courseLinkedTopic).mock.calls[0][2] as AbortSignal;
    view.unmount();
    expect(initialSignal.aborted).toBe(true);
  });

  it("ignores an abort without replacing the loading state", async () => {
    vi.mocked(api.courseLinkedTopic).mockRejectedValue(new DOMException("left", "AbortError"));
    render(<MemoryRouter initialEntries={["/courses/inference-engineering/IC-01/linked-topics/not-a-number"]}>
      <Routes><Route path="/courses/inference-engineering/:moduleId/linked-topics/:conceptId" element={<InferenceLinkedTopic />} /></Routes>
    </MemoryRouter>);
    expect(await screen.findByRole("status")).toHaveTextContent("loading linked lesson");
    expect(api.courseLinkedTopic).toHaveBeenCalledWith("IC-01", Number.NaN, expect.any(AbortSignal));
  });
});
