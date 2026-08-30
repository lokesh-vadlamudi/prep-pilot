import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InferenceCourse from "./InferenceCourse";
import { api, type CourseOverview } from "../api";

vi.mock("../api", () => ({
  api: { courseOverview: vi.fn(), courseEnroll: vi.fn() },
  newRequestId: vi.fn(() => "request-fixed"),
  describeApiError: vi.fn(() => "Course service is unavailable. Try again."),
}));

const modules: CourseOverview["modules"] = Array.from({ length: 17 }, (_, index) => ({
  id: `IC-${String(index).padStart(2, "0")}`,
  order: index,
  callsign: `CALL ${index}`,
  title: index === 0 ? "Hangar Check" : `Mission ${index}`,
  prerequisites: index ? [`IC-${String(index - 1).padStart(2, "0")}`] : [],
  platform: index % 2 ? "dgx" : "both",
  artifacts: [{ id: `A-${index}`, title: "Lab record", expectations: ["Capture observed behavior"] }],
  state: index === 0 ? "in_progress" : "not_started",
  next_action: index === 0 ? "continue_mission" : "save_evidence",
  url: `/courses/inference-engineering/IC-${String(index).padStart(2, "0")}`,
}));

const overview: CourseOverview = {
  key: "inference-engineering",
  version: "2026.08.29",
  title: "Inference Flight School: Token to Traffic",
  audience: "Experienced full-stack developer",
  enrolled: true,
  modules,
};

function mount() {
  return render(<MemoryRouter><InferenceCourse /></MemoryRouter>);
}

describe("InferenceCourse", () => {
  afterEach(cleanup);
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.courseOverview).mockResolvedValue(overview);
  });

  it("renders the complete evidence-led mission journey and focuses its heading", async () => {
    mount();
    const heading = await screen.findByRole("heading", { name: overview.title });
    expect(document.activeElement).toBe(heading);
    expect(screen.getAllByRole("link", { name: /mission/i })).toHaveLength(16);
    expect(screen.getByRole("link", { name: "Hangar Check" }).getAttribute("href")).toBe("/courses/inference-engineering/IC-00");
    expect(screen.getByText("0 complete · 17 total")).toBeTruthy();
    expect(screen.getByText("DGX Spark + Mac mini")).toBeTruthy();
    expect(screen.getAllByText("Lab record")).toHaveLength(17);
    expect(document.body.textContent).not.toMatch(/\b(?:xp|points?|streaks?|scores?|grades?|badges?|leaderboards?|percentages?)\b/i);
  });

  it("enrolls with one retained request id and recovers from a failed load", async () => {
    vi.mocked(api.courseOverview)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ ...overview, enrolled: false })
      .mockResolvedValueOnce(overview);
    vi.mocked(api.courseEnroll).mockResolvedValue({ created: true });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /try again/i }));
    const enrollButton = await screen.findByRole("button", { name: /enroll/i });
    enrollButton.focus();
    fireEvent.click(enrollButton);
    await waitFor(() => expect(api.courseEnroll).toHaveBeenCalledWith({
      request_id: "request-fixed", catalog_version: overview.version,
    }));
    expect(await screen.findByText("0 complete · 17 total")).toBeTruthy();
    expect(document.activeElement?.textContent).not.toBe(overview.title);
  });

  it("retains enrollment identity across failure and exposes every honest board state", async () => {
    const varied = {
      ...overview,
      enrolled: false,
      modules: modules.map((module, index) => ({
        ...module,
        platform: ["dgx", "mac", "both", "optional_cloud", "custom"][index % 5],
        state: index === 0 ? "ready_for_checkpoint" as const : "not_started" as const,
        artifacts: index === 0 ? [] : index === 1 ? [module.artifacts[0], { ...module.artifacts[0], id: "extra" }] : module.artifacts,
      })),
    };
    vi.mocked(api.courseOverview).mockResolvedValue(varied);
    vi.mocked(api.courseEnroll).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({ created: true });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /enroll/i }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: /enroll/i }));
    await waitFor(() => expect(api.courseEnroll).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.courseEnroll).mock.calls[0][0].request_id).toBe(vi.mocked(api.courseEnroll).mock.calls[1][0].request_id);
    expect(screen.getAllByText("Mac mini").length).toBeGreaterThan(0);
    expect(screen.getAllByText("DGX + Mac").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Optional cloud lab").length).toBeGreaterThan(0);
    expect(screen.getAllByText("custom").length).toBeGreaterThan(0);
    expect(screen.getByText("0 artifacts")).toBeTruthy();
    expect(screen.getByText("2 artifacts")).toBeTruthy();
  });

  it("does not offer a resume action after every mission is complete and aborts a departed load", async () => {
    vi.mocked(api.courseOverview).mockResolvedValue({ ...overview, modules: modules.map((module) => ({ ...module, state: "complete" })) });
    const view = mount();
    expect(await screen.findByText("17 complete · 17 total")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /resume/i })).toBeNull();
    const signal = vi.mocked(api.courseOverview).mock.calls[0][0] as AbortSignal;
    view.unmount();
    expect(signal.aborted).toBe(true);
  });

  it("keeps an aborted initial request in a neutral loading state", async () => {
    vi.mocked(api.courseOverview).mockRejectedValue(new DOMException("departed", "AbortError"));
    const view = mount();
    expect(await screen.findByRole("status")).toHaveTextContent("loading inference course");
    view.unmount();
  });
});
