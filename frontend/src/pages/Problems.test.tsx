import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Problems from "./Problems";
import { api } from "../api";

vi.mock("../api", () => ({
  api: {
    problems: vi.fn(),
    problemStatus: vi.fn(),
  },
  catClass: vi.fn(() => ""),
  diffClass: vi.fn(() => ""),
}));

const response = {
  total: 1,
  solved: 0,
  blind75_total: 1,
  blind75_solved: 0,
  category_order: ["Arrays & Hashing"],
  cheatsheets: {},
  problems: [{
    id: 1,
    slug: "two-sum",
    title: "Two Sum",
    category: "Arrays & Hashing",
    difficulty: "Easy",
    url: "https://leetcode.com/problems/two-sum/",
    blurb: "Find two values.",
    pattern: "Hash map",
    status: "todo",
    confidence: 0,
    has_approach: false,
    in_blind75: true,
  }],
};

describe("NeetCode completion control", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.problems).mockResolvedValue(response);
    vi.mocked(api.problemStatus).mockResolvedValue({ ok: true });
  });

  it("marks a todo problem solved on the first click", async () => {
    render(<MemoryRouter><Problems /></MemoryRouter>);

    fireEvent.click(await screen.findByTitle("Click to mark solved"));

    await waitFor(() => {
      expect(api.problemStatus).toHaveBeenCalledWith(1, { status: "solved", confidence: 1 });
    });
  });

  it("resets a solved problem on the next click", async () => {
    vi.mocked(api.problems).mockResolvedValue({
      ...response,
      solved: 1,
      blind75_solved: 1,
      problems: [{ ...response.problems[0], status: "solved", confidence: 2 }],
    });
    render(<MemoryRouter><Problems /></MemoryRouter>);

    fireEvent.click(await screen.findByTitle("Solved — click to reset"));

    await waitFor(() => {
      expect(api.problemStatus).toHaveBeenCalledWith(1, { status: "todo", confidence: 2 });
    });
  });
});
