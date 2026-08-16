import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Solve from "./Solve";
import { api } from "../api";

vi.mock("@uiw/react-codemirror", () => ({
  default: ({ value }: { value: string }) => <textarea aria-label="code editor" readOnly value={value} />,
}));

vi.mock("../api", () => ({
  api: {
    problem: vi.fn(),
    starter: vi.fn(),
    runCode: vi.fn(),
    mentor: vi.fn(),
    problemStatus: vi.fn(),
    problemHints: vi.fn(),
  },
  diffClass: vi.fn(() => ""),
}));

const problem = {
  id: 88,
  difficulty: "Medium",
  category: "Binary Search",
  title: "Search a 2D Matrix",
  url: "https://leetcode.com/problems/search-a-2d-matrix/",
  blurb: "Find the target.",
  pattern: "Binary search",
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function renderSolve() {
  return render(
    <MemoryRouter initialEntries={["/problems/88/solve"]}>
      <Routes>
        <Route path="/problems/:id/solve" element={<Solve theme="light" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Solve starter loading", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.problem).mockResolvedValue(problem);
  });

  it("shows a retryable error instead of a blank editor", async () => {
    vi.mocked(api.starter)
      .mockRejectedValueOnce(new Error("503"))
      .mockResolvedValueOnce({ starter_code: "def searchMatrix(matrix, target):\n    pass" });

    renderSolve();

    expect((await screen.findByRole("alert")).textContent).toContain("HTTP 503");
    expect(screen.queryByLabelText("code editor")).toBeNull();
    expect((screen.getByRole("button", { name: "▶ Run tests" }) as HTMLButtonElement).disabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "↻ Retry starter load" }));

    expect((await screen.findByLabelText("code editor") as HTMLTextAreaElement).value).toBe("def searchMatrix(matrix, target):\n    pass");
    expect(api.starter).toHaveBeenNthCalledWith(2, 88, "python");
    expect((screen.getByRole("button", { name: "▶ Run tests" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("ignores a stale starter response after the language changes", async () => {
    const python = deferred<{ starter_code: string }>();
    const javascript = deferred<{ starter_code: string }>();
    vi.mocked(api.starter)
      .mockImplementationOnce(() => python.promise)
      .mockImplementationOnce(() => javascript.promise);

    renderSolve();
    await screen.findByText("Search a 2D Matrix");
    fireEvent.click(screen.getByRole("button", { name: "JavaScript" }));

    javascript.resolve({ starter_code: "function searchMatrix(matrix, target) {}" });
    expect((await screen.findByLabelText("code editor") as HTMLTextAreaElement).value).toBe("function searchMatrix(matrix, target) {}");

    python.resolve({ starter_code: "def stale(): pass" });
    await waitFor(() => {
      expect((screen.getByLabelText("code editor") as HTMLTextAreaElement).value).toBe("function searchMatrix(matrix, target) {}");
    });
  });
});
