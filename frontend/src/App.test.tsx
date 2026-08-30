import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { api } from "./api";

vi.mock("./pages/Login", () => ({ default: ({ onAuthed }: any) => <button onClick={() => onAuthed({ username: "captain", invite_code: "INVITE", is_admin: true })}>Complete login</button> }));
vi.mock("./pages/Today", () => ({ default: () => <h1>Today page</h1> }));
vi.mock("./pages/FlightPlan", () => ({ default: () => <h1>Flight plan page</h1> }));
vi.mock("./pages/Topics", () => ({ default: () => <h1>Topics page</h1> }));
vi.mock("./pages/TopicDetail", () => ({ default: () => <h1>Topic detail page</h1> }));
vi.mock("./pages/Mock", () => ({ default: () => <h1>Mock page</h1> }));
vi.mock("./pages/Problems", () => ({ default: () => <h1>Problems page</h1> }));
vi.mock("./pages/Ask", () => ({ default: () => <h1>Ask page</h1> }));
vi.mock("./pages/Progress", () => ({ default: () => <h1>Progress page</h1> }));
vi.mock("./pages/MakeMeLearn", () => ({ default: () => <h1>Learn page</h1> }));
vi.mock("./pages/AdminDashboard", () => ({ default: () => <h1>Admin page</h1> }));
vi.mock("./pages/InferenceModule", () => ({ default: () => <h1>Module page</h1> }));
vi.mock("./pages/InferenceLinkedTopic", () => ({ default: () => <h1>Linked page</h1> }));
vi.mock("./pages/Solve", () => ({ default: ({ theme }: { theme: string }) => <h1>Solve page · {theme}</h1> }));

vi.mock("./api", () => ({
  api: {
    me: vi.fn(), health: vi.fn(), brainHealth: vi.fn(), today: vi.fn(), logout: vi.fn(), courseOverview: vi.fn(),
  },
  newRequestId: vi.fn(() => "request-fixed"),
  describeApiError: vi.fn(() => "Unavailable"),
}));

describe("course app shell", () => {
  afterEach(cleanup);
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
    vi.mocked(api.me).mockResolvedValue({ authenticated: true, username: "pilot" });
    vi.mocked(api.health).mockResolvedValue({ ok: true, environment: "development", release: "test", scheduler_enabled: false });
    vi.mocked(api.brainHealth).mockResolvedValue({ online: true, model: "local" });
    vi.mocked(api.today).mockResolvedValue({ streak: 4 } as any);
    vi.mocked(api.logout).mockResolvedValue({ ok: true });
    vi.mocked(api.courseOverview).mockResolvedValue({ key: "inference-engineering", version: "v1", title: "Inference Flight School: Token to Traffic", audience: "builder", enrolled: true, modules: [] });
  });

  it("adds the course route and omits the shared streak fetch and row on descendants", async () => {
    render(<MemoryRouter initialEntries={["/courses/inference-engineering"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Inference Flight School: Token to Traffic" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Inference course" })).toBeTruthy();
    expect(api.today).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toMatch(/streak/i);
    expect(document.querySelector("main#main-content")).toBeTruthy();
  });

  it.each([
    ["/courses/inference-engineering/IC-03", "Module page"],
    ["/courses/inference-engineering/IC-03/linked-topics/17", "Linked page"],
  ])("suppresses streak state throughout course descendant %s", async (path, heading) => {
    render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: heading })).toBeTruthy();
    expect(api.today).not.toHaveBeenCalled();
    expect(screen.queryByText(/streak/i)).toBeNull();
  });

  it("keeps standard topic and lazy solve navigation behavior", async () => {
    const topic = render(<MemoryRouter initialEntries={["/topics/17"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Topic detail page" })).toBeTruthy();
    await waitFor(() => expect(api.today).toHaveBeenCalledTimes(1));
    expect(screen.getByText("4d")).toBeTruthy();
    topic.unmount();

    render(<MemoryRouter initialEntries={["/problems/17/solve"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Solve page · light" })).toBeTruthy();
  });

  it("renders loading, signs in, shows standard status, toggles theme, and signs out", async () => {
    let resolveMe!: (value: any) => void;
    vi.mocked(api.me).mockImplementationOnce(() => new Promise((resolve) => { resolveMe = resolve; }));
    const view = render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    expect(screen.getByText("initializing")).toBeTruthy();
    await act(async () => resolveMe({ authenticated: false }));
    fireEvent.click(await screen.findByRole("button", { name: "Complete login" }));
    expect(await screen.findByRole("heading", { name: "Today page" })).toBeTruthy();
    expect(screen.getByText("4d")).toBeTruthy();
    expect(screen.getByText("online")).toBeTruthy();
    expect(screen.getByText("INVITE")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Admin monitor" })).toBeTruthy();
    const theme = screen.getByRole("button", { name: "Switch to dark mode" });
    fireEvent.click(theme);
    expect(await screen.findByRole("button", { name: "Switch to light mode" })).toBeTruthy();
    expect(localStorage.getItem("pp-theme")).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));
    await waitFor(() => expect(api.logout).toHaveBeenCalled());
    expect(await screen.findByRole("button", { name: "Complete login" })).toBeTruthy();
    view.unmount();
  });

  it("uses stored and system theme preferences with the Safari listener fallback", async () => {
    localStorage.setItem("pp-theme", "dark");
    let legacyHandler!: (event: { matches: boolean }) => void;
    const addListener = vi.fn((handler) => { legacyHandler = handler; });
    const removeListener = vi.fn();
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(() => { throw new Error("legacy Safari"); }),
      removeEventListener: vi.fn(() => { throw new Error("legacy Safari"); }),
      addListener, removeListener,
    })));
    const view = render(<MemoryRouter initialEntries={["/unknown"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Today page" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeTruthy();
    expect(addListener).toHaveBeenCalled();
    await act(async () => legacyHandler({ matches: false }));
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeTruthy();
    view.unmount();
    expect(removeListener).toHaveBeenCalled();
  });

  it("reacts to an unstored OS preference and handles unavailable runtime services", async () => {
    let themeHandler!: (event: { matches: boolean }) => void;
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn((_name, handler) => { themeHandler = handler; }),
      removeEventListener: vi.fn(),
    })));
    vi.mocked(api.health).mockRejectedValue(new Error("offline"));
    vi.mocked(api.brainHealth).mockRejectedValue(new Error("offline"));
    vi.mocked(api.today).mockRejectedValue(new Error("offline"));
    render(<MemoryRouter initialEntries={["/admin"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Today page" })).toBeTruthy();
    expect(screen.getByText("offline")).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
    await act(async () => themeHandler({ matches: true }));
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeTruthy();
    await act(async () => themeHandler({ matches: false }));
    expect(screen.getByRole("button", { name: "Switch to dark mode" })).toBeTruthy();
  });

  it("applies system-dark browser chrome and toggles back to light", async () => {
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.append(meta);
    vi.stubGlobal("matchMedia", vi.fn(() => ({
      matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    })));
    render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Today page" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeTruthy();
    expect(meta.content).toBe("#0c1626");
    fireEvent.click(screen.getByRole("button", { name: "Switch to light mode" }));
    expect(await screen.findByRole("button", { name: "Switch to dark mode" })).toBeTruthy();
    expect(meta.content).toBe("#F2F6FA");
    meta.remove();
  });

  it("renders production login without a banner and development fallback release text", async () => {
    vi.mocked(api.me).mockResolvedValueOnce({ authenticated: false });
    vi.mocked(api.health).mockResolvedValueOnce({
      ok: true, environment: "production", release: "v1", scheduler_enabled: false,
    });
    const production = render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    expect(await screen.findByRole("button", { name: "Complete login" })).toBeTruthy();
    expect(screen.queryByText(/Development preview/)).toBeNull();
    production.unmount();

    vi.mocked(api.me).mockResolvedValueOnce({ authenticated: false });
    vi.mocked(api.health).mockResolvedValueOnce({
      ok: true, environment: "development", release: "", scheduler_enabled: false,
    });
    render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    expect(await screen.findByText(/Development preview · local/)).toBeTruthy();
  });

});
