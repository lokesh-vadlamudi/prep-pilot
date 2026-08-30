import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import MakeMeLearn from "./MakeMeLearn";

vi.mock("../api", () => ({
  api: {
    books: vi.fn(), book: vi.fn(), bookChatHistory: vi.fn(), bookChat: vi.fn(),
    bookPageUrl: vi.fn((id: number, page: number) => `/api/books/${id}/pages/${page}`),
    bookPage: vi.fn(),
    uploadBook: vi.fn(), activateBook: vi.fn(), retryBook: vi.fn(), clearBookChat: vi.fn(),
    bookReaderState: vi.fn(), saveBookProgress: vi.fn(), saveBookBookmark: vi.fn(),
    deleteBookBookmark: vi.fn(), searchBook: vi.fn(), shareBook: vi.fn(),
  },
}));

const summary = {
  id: 7, title: "Inference Engineering", status: "partial", page_count: 3,
  total_sections: 1, completed_sections: 1, generated_lessons: 1, failed_sections: 0,
  remaining_sections: 0, activated: true, access: "owner", is_owner: true,
  shared_with_all: false,
};
const detail = {
  ...summary,
  sections: [{
    id: 11, chapter: "Hardware", label: "GPU hardware", citation: "pages 2-3",
    status: "complete", page_start: 2, page_end: 3, concept_id: 41,
    topic_title: "GPU Hardware", summary: "How accelerators execute inference.",
  }],
};

describe("Read a book", () => {
  afterEach(() => { cleanup(); vi.useRealTimers(); });
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("scrollTo", vi.fn());
    Element.prototype.scrollIntoView = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true, value: vi.fn(() => "blob:book-page"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true, value: vi.fn(),
    });
    vi.mocked(api.books).mockResolvedValue([summary] as any);
    vi.mocked(api.book).mockResolvedValue(detail as any);
    vi.mocked(api.bookChatHistory).mockResolvedValue([] as any);
    vi.mocked(api.bookPage).mockResolvedValue(new Blob(["page"], { type: "image/png" }));
    vi.mocked(api.bookReaderState).mockResolvedValue({ book_id: 7, page: 1, progress_updated_at: null, bookmarks: [] } as any);
    vi.mocked(api.saveBookProgress).mockResolvedValue({ book_id: 7, page: 2, updated_at: "now" } as any);
    vi.mocked(api.saveBookBookmark).mockImplementation(async (_id, page, note) => ({ page, note, created_at: "now", updated_at: "now" } as any));
    vi.mocked(api.deleteBookBookmark).mockResolvedValue(undefined as any);
    vi.mocked(api.searchBook).mockResolvedValue({ query: "GPU + cache", results: [{ page: 3, snippet: "GPU + cache", match_count: 2 }], truncated: false } as any);
    vi.mocked(api.bookChat).mockResolvedValue({
      answer: "Page two explains GPU execution.",
      citations: [{ section_id: 11, citation: "Inference Engineering, page 3", page_start: 3, page_end: 3 }],
    } as any);
    vi.mocked(api.uploadBook).mockResolvedValue(summary as any);
    vi.mocked(api.activateBook).mockResolvedValue({ activated: true } as any);
    vi.mocked(api.retryBook).mockResolvedValue({ queued: true } as any);
    vi.mocked(api.clearBookChat).mockResolvedValue({ deleted: 1 } as any);
    vi.mocked(api.shareBook).mockImplementation(async (_id, shared) => ({
      book_id: 7, access: "owner", is_owner: true, shared_with_all: shared,
      updated_at: "now", changed: true,
    } as any));
  });

  it("keeps the current page visible and sends that page with chat questions", async () => {
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "Read a book" })).toBeTruthy();
    expect(await screen.findByAltText("Page 1 of Inference Engineering")).toHaveAttribute(
      "src", "blob:book-page",
    );
    expect(screen.getByRole("heading", { name: "Ask page 1" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByAltText("Page 2 of Inference Engineering")).toHaveAttribute(
      "src", "blob:book-page",
    );
    expect(screen.getByRole("heading", { name: "Ask page 2" })).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText("Ask about page 2…"), {
      target: { value: "What does this page explain?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(api.bookChat).toHaveBeenCalledWith(
      7, "What does this page explain?", "page", undefined, 2,
    ));

    expect(await screen.findByText("Page two explains GPU execution.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Go to cited page 3" }));
    expect(await screen.findByAltText("Page 3 of Inference Engineering")).toBeTruthy();
    await waitFor(() => expect(api.saveBookProgress).toHaveBeenLastCalledWith(7, 3));
  });

  it("resumes per-book state and supports private bookmark notes and jumps", async () => {
    vi.mocked(api.bookReaderState).mockResolvedValueOnce({
      book_id: 7, page: 2, progress_updated_at: "now",
      bookmarks: [{ page: 3, note: "Existing note", created_at: "then", updated_at: "now" }],
    } as any);
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);

    expect(await screen.findByAltText("Page 2 of Inference Engineering")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Go to bookmarked page 3" }));
    expect(await screen.findByAltText("Page 3 of Inference Engineering")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Bookmark note for page 3"), { target: { value: "Key proof" } });
    expect(screen.getByLabelText("Bookmark note for page 3")).toHaveAttribute("maxlength", "2000");
    fireEvent.click(screen.getByRole("button", { name: "Save bookmark for page 3" }));
    await waitFor(() => expect(api.saveBookBookmark).toHaveBeenCalledWith(7, 3, "Key proof"));
    fireEvent.click(screen.getByRole("button", { name: "Remove bookmark from page 3" }));
    await waitFor(() => expect(api.deleteBookBookmark).toHaveBeenCalledWith(7, 3));
  });

  it("runs literal search and sends result jumps through the shared progress path", async () => {
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByRole("heading", { name: "Read a book" });

    fireEvent.change(screen.getByLabelText("Search this book"), { target: { value: "GPU + cache" } });
    fireEvent.click(screen.getByRole("button", { name: "Search book" }));
    await waitFor(() => expect(api.searchBook).toHaveBeenCalledWith(7, "GPU + cache", expect.any(AbortSignal)));
    fireEvent.click(await screen.findByRole("button", { name: "Go to search result on page 3" }));
    expect(await screen.findByAltText("Page 3 of Inference Engineering")).toBeTruthy();
    await waitFor(() => expect(api.saveBookProgress).toHaveBeenLastCalledWith(7, 3));
  });

  it("renders malformed or out-of-range citations inert and has no nested main landmark", async () => {
    vi.mocked(api.bookChatHistory).mockResolvedValueOnce([
      { role: "assistant", content: "Legacy", citations: [
        { citation: "bad", page_start: 99, page_end: 99 },
        { citation: "boolean", page_start: true, page_end: true },
      ] },
    ] as any);
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    expect(await screen.findByText("Legacy")).toBeTruthy();
    expect(screen.getByText("bad")).toBeTruthy();
    expect(screen.getByText("boolean")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /cited page 99/i })).toBeNull();
    expect(document.querySelector("main")).toBeNull();
    expect(document.querySelector(".book-main")).toBeTruthy();
  });

  it("jumps to a section page while keeping generated lessons optional", async () => {
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByRole("heading", { name: "Read a book" });

    fireEvent.click(screen.getByRole("button", { name: "Read page 2" }));

    expect(await screen.findByAltText("Page 2 of Inference Engineering")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open lesson →" })).toHaveAttribute("href", "/topics/41");

    fireEvent.change(screen.getByPlaceholderText("Ask about page 2…"), {
      target: { value: "What does this page explain?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(api.bookChat).toHaveBeenCalledWith(
      7, "What does this page explain?", "page", undefined, 2,
    ));

    fireEvent.change(screen.getByLabelText("Chat context"), { target: { value: "chapter" } });
    fireEvent.change(screen.getByPlaceholderText("Ask a question grounded in this book…"), {
      target: { value: "Summarize this chapter" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(api.bookChat).toHaveBeenLastCalledWith(
      7, "Summarize this chapter", "chapter", 11, undefined,
    ));
  });

  it("handles an empty library plus successful and failed imports", async () => {
    vi.mocked(api.books).mockResolvedValueOnce([] as any).mockResolvedValue([summary] as any);
    const view = render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Your private library is empty" })).toBeTruthy();
    const input = view.container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [] } });
    expect(api.uploadBook).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { files: [new File(["pdf"], "reader.pdf", { type: "application/pdf" })] } });
    await waitFor(() => expect(api.uploadBook).toHaveBeenCalled());
    expect(await screen.findByAltText("Page 1 of Inference Engineering")).toBeTruthy();

    vi.mocked(api.uploadBook).mockRejectedValueOnce(new Error("bad"));
    fireEvent.change(input, { target: { files: [new File(["bad"], "bad.pdf", { type: "application/pdf" })] } });
    expect(await screen.findByText(/Import failed/)).toBeTruthy();
  });

  it("lets only the owner share and unshare with an explicit confirmation", async () => {
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");

    fireEvent.click(screen.getByRole("button", { name: "Share with all users" }));
    expect(screen.getByText(/Every signed-in user can read, search, and chat with this book/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm sharing" }));
    await waitFor(() => expect(api.shareBook).toHaveBeenCalledWith(7, true));
    expect(await screen.findByText("Shared with everyone")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Stop sharing" }));
    await waitFor(() => expect(api.shareBook).toHaveBeenLastCalledWith(7, false));
    expect(await screen.findByText("Private")).toBeTruthy();
  });

  it("keeps the confirmed server state when sharing fails", async () => {
    vi.mocked(api.shareBook).mockRejectedValueOnce({ detail: "Sharing is temporarily unavailable." });
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");

    fireEvent.click(screen.getByRole("button", { name: "Share with all users" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm sharing" }));

    expect(await screen.findByText("Sharing is temporarily unavailable.")).toBeTruthy();
    expect(screen.getByText("Private")).toBeTruthy();
    expect(screen.queryByText("Shared with everyone")).toBeNull();
  });

  it("ignores duplicate and stale sharing completions", async () => {
    const second = { ...summary, id: 8, title: "Second Book", status: "ready" };
    vi.mocked(api.books).mockResolvedValue([summary, second] as any);
    vi.mocked(api.book).mockImplementation(async (id) => ({
      ...detail, ...(id === 8 ? second : summary), sections: [],
    }) as any);
    vi.mocked(api.bookReaderState).mockImplementation(async (id) => ({
      book_id: id, page: 1, progress_updated_at: null, bookmarks: [],
    }) as any);
    let resolveShare: ((value: any) => void) | undefined;
    vi.mocked(api.shareBook).mockImplementationOnce(() => new Promise((resolve) => { resolveShare = resolve; }));
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");

    fireEvent.click(screen.getByRole("button", { name: "Share with all users" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Confirm sharing" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Share with all users" }));
    const confirm = screen.getByRole("button", { name: "Confirm sharing" });
    act(() => { confirm.click(); confirm.click(); });
    expect(api.shareBook).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /Second Book/ }));
    await screen.findByAltText("Page 1 of Second Book");
    await act(async () => { resolveShare?.({
      book_id: 7, access: "owner", is_owner: true, shared_with_all: true,
      updated_at: "now", changed: true,
    }); });
    expect(screen.getByText("Private")).toBeTruthy();
    expect(screen.queryByText("Shared with everyone")).toBeNull();

    let rejectShare: ((reason: unknown) => void) | undefined;
    vi.mocked(api.shareBook).mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectShare = reject; }));
    fireEvent.click(screen.getByRole("button", { name: "Share with all users" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm sharing" }));
    fireEvent.click(screen.getByRole("button", { name: /Inference Engineering/ }));
    await screen.findByAltText("Page 1 of Inference Engineering");
    await act(async () => { rejectShare?.({ detail: "stale failure" }); });
    expect(screen.queryByText("stale failure")).toBeNull();
  });

  it("shows a shared book as reader-only and hides owner lesson controls", async () => {
    const shared = {
      id: 8, title: "Shared Systems", page_count: 2, access: "shared",
      is_owner: false, shared_with_all: true,
    };
    const sharedDetail = {
      ...shared,
      sections: [{ id: 21, chapter: "Serving", label: "Batching", citation: "page 2", page_start: 2, page_end: 2 }],
    };
    vi.mocked(api.books).mockResolvedValue([shared] as any);
    vi.mocked(api.book).mockResolvedValue(sharedDetail as any);
    vi.mocked(api.bookReaderState).mockResolvedValue({ book_id: 8, page: 1, progress_updated_at: null, bookmarks: [] } as any);

    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    expect(await screen.findByAltText("Page 1 of Shared Systems")).toBeTruthy();
    expect(screen.getAllByText("Shared with you").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Share with all users" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add lessons to syllabus" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry failed section" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Read page 2" }));
    expect(screen.queryByRole("link", { name: "Open lesson →" })).toBeNull();
    expect(screen.getByRole("option", { name: "Selected section" })).toBeTruthy();
  });

  it("exits a shared book immediately when page access is revoked", async () => {
    const shared = {
      id: 8, title: "Shared Systems", page_count: 2, access: "shared",
      is_owner: false, shared_with_all: true,
    };
    const ownerBook = { ...summary, id: 9, title: "My Private Book", status: "ready" };
    vi.mocked(api.books)
      .mockResolvedValueOnce([shared, ownerBook] as any)
      .mockResolvedValue([ownerBook] as any);
    vi.mocked(api.book).mockImplementation(async (id) => (
      id === 8 ? { ...shared, sections: [] } : { ...detail, ...ownerBook, sections: [] }
    ) as any);
    vi.mocked(api.bookReaderState).mockImplementation(async (id) => ({
      book_id: id, page: 1, progress_updated_at: null, bookmarks: [],
    }) as any);
    vi.mocked(api.bookPage)
      .mockResolvedValueOnce(new Blob(["shared"], { type: "image/png" }))
      .mockRejectedValueOnce({ status: 404, detail: "Book not found" });

    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Shared Systems");
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));

    expect(await screen.findByText("This book is no longer shared with you.")).toBeTruthy();
    expect(await screen.findByAltText("Page 1 of My Private Book")).toBeTruthy();
    expect(screen.queryByText("Shared Systems")).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:book-page");
  });

  it("drops a book revoked between listing and private-state loading", async () => {
    const shared = {
      id: 8, title: "Shared Systems", page_count: 2, access: "shared",
      is_owner: false, shared_with_all: true,
    };
    const ownerBook = { ...summary, id: 9, title: "My Private Book", status: "ready" };
    vi.mocked(api.books)
      .mockResolvedValueOnce([shared, ownerBook] as any)
      .mockResolvedValue([ownerBook] as any);
    vi.mocked(api.book).mockImplementation(async (id) => (
      id === 8 ? { ...shared, sections: [] } : { ...detail, ...ownerBook, sections: [] }
    ) as any);
    vi.mocked(api.bookReaderState)
      .mockRejectedValueOnce({ status: 404, detail: "Book not found" })
      .mockResolvedValue({ book_id: 9, page: 1, progress_updated_at: null, bookmarks: [] } as any);

    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    expect(await screen.findByAltText("Page 1 of My Private Book")).toBeTruthy();
    expect(screen.queryByText("Shared Systems")).toBeNull();
  });

  it("handles page transport failure and aborts an obsolete page request", async () => {
    const second = { ...summary, id: 8, title: "Second Book", status: "ready" };
    vi.mocked(api.books).mockResolvedValue([summary, second] as any);
    vi.mocked(api.book).mockImplementation(async (id) => ({
      ...detail, ...(id === 8 ? second : summary), sections: [],
    }) as any);
    vi.mocked(api.bookReaderState).mockImplementation(async (id) => ({
      book_id: id, page: 1, progress_updated_at: null, bookmarks: [],
    }) as any);
    vi.mocked(api.bookPage).mockRejectedValueOnce(new Error("render offline"));
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);

    expect(await screen.findByText("This page could not be rendered.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry page render" }));
    await screen.findByAltText("Page 1 of Inference Engineering");

    vi.mocked(api.bookPage).mockRejectedValueOnce({ status: 404, detail: "Page file missing" });
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("This page could not be rendered.")).toBeTruthy();
    expect(screen.getAllByText("Inference Engineering").length).toBeGreaterThan(0);
    expect(screen.queryByText("This book is no longer shared with you.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry page render" }));
    await screen.findByAltText("Page 2 of Inference Engineering");

    vi.mocked(api.bookPage).mockImplementationOnce((_id, _page, signal) => new Promise((_resolve, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("stop", "AbortError")));
    }));
    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    await waitFor(() => expect(api.bookPage).toHaveBeenLastCalledWith(7, 1, expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole("button", { name: /Second Book/ }));
    expect(await screen.findByAltText("Page 1 of Second Book")).toBeTruthy();
    expect(screen.queryByText("This page could not be rendered.")).toBeNull();
  });

  it("recovers when progress discovers that a shared book was revoked", async () => {
    const shared = {
      id: 8, title: "Shared Systems", page_count: 2, access: "shared",
      is_owner: false, shared_with_all: true,
    };
    const ownerBook = { ...summary, id: 9, title: "My Private Book", status: "ready" };
    vi.mocked(api.books)
      .mockResolvedValueOnce([shared, ownerBook] as any)
      .mockResolvedValue([ownerBook] as any);
    vi.mocked(api.book).mockImplementation(async (id) => (
      id === 8 ? { ...shared, sections: [] } : { ...detail, ...ownerBook, sections: [] }
    ) as any);
    vi.mocked(api.bookReaderState).mockImplementation(async (id) => ({
      book_id: id, page: 1, progress_updated_at: null, bookmarks: [],
    }) as any);
    vi.mocked(api.saveBookProgress).mockRejectedValueOnce({ status: 404, detail: "Book not found" });

    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Shared Systems");
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByAltText("Page 1 of My Private Book")).toBeTruthy();
    expect(screen.getByText("This book is no longer shared with you.")).toBeTruthy();
  });

  it("preserves the current book when a chat 404 cannot be confirmed as revocation", async () => {
    const shared = {
      id: 8, title: "Shared Systems", page_count: 2, access: "shared",
      is_owner: false, shared_with_all: true,
    };
    vi.mocked(api.books)
      .mockResolvedValueOnce([shared] as any)
      .mockRejectedValueOnce(new Error("library offline"));
    vi.mocked(api.book).mockResolvedValue({ ...shared, sections: [] } as any);
    vi.mocked(api.bookReaderState).mockResolvedValue({
      book_id: 8, page: 1, progress_updated_at: null, bookmarks: [],
    } as any);
    vi.mocked(api.bookChat).mockRejectedValueOnce({ status: 404, detail: "Book not found" });

    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Shared Systems");
    fireEvent.click(screen.getByRole("button", { name: "What are the key ideas?" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(/retry when DGX is available/i)).toBeTruthy();
    expect(screen.getByAltText("Page 1 of Shared Systems")).toBeTruthy();
    expect(screen.queryByText("This book is no longer shared with you.")).toBeNull();
  });

  it("finishes revocation even when loading the fallback book fails", async () => {
    const shared = {
      id: 8, title: "Shared Systems", page_count: 2, access: "shared",
      is_owner: false, shared_with_all: true,
    };
    const ownerBook = { ...summary, id: 9, title: "Fallback Book", status: "ready" };
    vi.mocked(api.books)
      .mockResolvedValueOnce([shared, ownerBook] as any)
      .mockResolvedValueOnce([ownerBook] as any)
      .mockRejectedValueOnce(new Error("fallback offline"));
    vi.mocked(api.book).mockResolvedValue({ ...shared, sections: [] } as any);
    vi.mocked(api.bookReaderState).mockResolvedValue({
      book_id: 8, page: 1, progress_updated_at: null, bookmarks: [],
    } as any);
    vi.mocked(api.bookChat).mockRejectedValueOnce({ status: 404, detail: "Book not found" });

    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Shared Systems");
    fireEvent.click(screen.getByRole("button", { name: "What are the key ideas?" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("This book is no longer shared with you.")).toBeTruthy();
    expect(screen.queryByText("Shared Systems")).toBeNull();
  });

  it("uses search 404s to exit a confirmed-revoked shared book", async () => {
    const shared = {
      id: 8, title: "Shared Systems", page_count: 2, access: "shared",
      is_owner: false, shared_with_all: true,
    };
    const ownerBook = { ...summary, id: 9, title: "Search Fallback", status: "ready" };
    vi.mocked(api.books)
      .mockResolvedValueOnce([shared, ownerBook] as any)
      .mockResolvedValue([ownerBook] as any);
    vi.mocked(api.book).mockImplementation(async (id) => (
      id === 8 ? { ...shared, sections: [] } : { ...detail, ...ownerBook, sections: [] }
    ) as any);
    vi.mocked(api.bookReaderState).mockImplementation(async (id) => ({
      book_id: id, page: 1, progress_updated_at: null, bookmarks: [],
    }) as any);
    vi.mocked(api.searchBook).mockRejectedValueOnce({ status: 404, detail: "Book not found" });

    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Shared Systems");
    fireEvent.change(screen.getByLabelText("Search this book"), { target: { value: "revoked" } });
    fireEvent.click(screen.getByRole("button", { name: "Search book" }));
    expect(await screen.findByAltText("Page 1 of Search Fallback")).toBeTruthy();
    expect(screen.getByText("This book is no longer shared with you.")).toBeTruthy();
  });

  it("exits a revoked shared book when a private bookmark update fails", async () => {
    const shared = {
      id: 8, title: "Shared Systems", page_count: 2, access: "shared",
      is_owner: false, shared_with_all: true,
    };
    vi.mocked(api.books)
      .mockResolvedValueOnce([shared] as any)
      .mockResolvedValueOnce([] as any);
    vi.mocked(api.book).mockResolvedValue({ ...shared, sections: [] } as any);
    vi.mocked(api.bookReaderState).mockResolvedValue({
      book_id: 8, page: 1, progress_updated_at: null, bookmarks: [],
    } as any);
    vi.mocked(api.saveBookBookmark).mockRejectedValueOnce({ status: 404, detail: "Book not found" });

    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Shared Systems");
    fireEvent.click(screen.getByRole("button", { name: "Save bookmark for page 1" }));

    expect(await screen.findByText("This book is no longer shared with you.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Your private library is empty" })).toBeTruthy();
  });

  it("keeps the selected book readable when resume state cannot be loaded", async () => {
    vi.mocked(api.bookReaderState).mockRejectedValueOnce(new Error("state unavailable"));
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);

    expect(await screen.findByAltText("Page 1 of Inference Engineering")).toBeTruthy();
    expect(screen.getByText("Resume state could not be loaded. Starting at page 1.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Ask page 1" })).toBeTruthy();
  });

  it("switches books, clears transient state, resumes the selected book, and reports load failure", async () => {
    const second = { ...summary, id: 8, title: "Second Book", status: "ready" };
    const secondDetail = { ...detail, ...second, sections: [] };
    vi.mocked(api.books).mockResolvedValue([summary, second] as any);
    vi.mocked(api.book).mockImplementation(async (id) => (id === 8 ? secondDetail : detail) as any);
    vi.mocked(api.bookReaderState).mockImplementation(async (id) => ({ book_id: id, page: id === 8 ? 3 : 1, progress_updated_at: null, bookmarks: [] }) as any);
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");
    fireEvent.change(screen.getByPlaceholderText("Ask about page 1…"), { target: { value: "draft" } });
    fireEvent.click(screen.getByRole("button", { name: /Second Book/ }));
    expect(await screen.findByAltText("Page 3 of Second Book")).toBeTruthy();
    expect(screen.getByPlaceholderText("Ask about page 3…")).toHaveValue("");

    vi.mocked(api.book).mockRejectedValueOnce(new Error("load"));
    fireEvent.click(screen.getByRole("button", { name: /Inference Engineering/ }));
    expect(await screen.findByText("Could not load that book.")).toBeTruthy();
  });

  it("runs activation, retry, page error/retry, zoom, bounds, and progress failure controls", async () => {
    const ready = { ...summary, status: "ready", activated: false, failed_sections: 1 };
    vi.mocked(api.books).mockResolvedValue([ready] as any);
    vi.mocked(api.book).mockResolvedValue({ ...detail, ...ready } as any);
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    const image = await screen.findByAltText("Page 1 of Inference Engineering");

    fireEvent.click(screen.getByRole("button", { name: "Add lessons to syllabus" }));
    await waitFor(() => expect(api.activateBook).toHaveBeenCalledWith(7));
    vi.mocked(api.saveBookProgress).mockRejectedValueOnce(new Error("offline"));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByText(/resume progress could not be saved/)).toBeTruthy();

    const pageInput = screen.getByLabelText("Page number");
    fireEvent.change(pageInput, { target: { value: "99" } });
    expect(await screen.findByAltText("Page 3 of Inference Engineering")).toBeTruthy();
    fireEvent.change(pageInput, { target: { value: "0" } });
    expect(await screen.findByAltText("Page 1 of Inference Engineering")).toBeTruthy();
    for (let index = 0; index < 5; index += 1) fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    expect(screen.getByText("70%")).toBeTruthy();
    for (let index = 0; index < 12; index += 1) fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(screen.getByText("180%")).toBeTruthy();
    fireEvent.error(screen.getByAltText("Page 1 of Inference Engineering"));
    fireEvent.click(await screen.findByRole("button", { name: "Retry page render" }));
    fireEvent.load(await screen.findByAltText("Page 1 of Inference Engineering"));
    expect(screen.queryByText("rendering page")).toBeNull();
  });

  it("prioritizes the page with focus, fit, and keyboard-resizable chat controls", async () => {
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    const image = await screen.findByAltText("Page 1 of Inference Engineering");
    const workspace = image.closest(".book-workspace") as HTMLElement;
    const reader = image.closest(".book-reader") as HTMLElement;
    const surface = image.closest(".book-reader-surface") as HTMLElement;

    expect(screen.getByRole("link", { name: "Back to PrepPilot" })).toHaveAttribute("href", "/");
    expect(workspace.style.getPropertyValue("--book-chat-width")).toBe("420px");
    const separator = screen.getByRole("separator", { name: "Resize DGX chat" });
    Object.assign(separator, { setPointerCapture: vi.fn(), releasePointerCapture: vi.fn() });
    fireEvent.keyDown(separator, { key: "Home" });
    fireEvent.keyDown(separator, { key: "ArrowLeft" });
    expect(workspace.style.getPropertyValue("--book-chat-width")).toBe("444px");
    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(workspace.style.getPropertyValue("--book-chat-width")).toBe("420px");
    fireEvent.pointerMove(separator, { clientX: 0, pointerId: 1 });
    expect(workspace.style.getPropertyValue("--book-chat-width")).toBe("420px");
    fireEvent.pointerDown(separator, { pointerId: 1 });
    fireEvent.pointerMove(separator, { clientX: 0, pointerId: 1 });
    expect(workspace.style.getPropertyValue("--book-chat-width")).toBe("512px");
    fireEvent.pointerMove(separator, { clientX: 1000, pointerId: 1 });
    expect(workspace.style.getPropertyValue("--book-chat-width")).toBe("340px");
    fireEvent.pointerUp(separator, { pointerId: 1 });
    fireEvent.pointerDown(separator, { pointerId: 2 });
    fireEvent.pointerCancel(separator, { pointerId: 2 });

    fireEvent.click(screen.getByRole("button", { name: "Fit page" }));
    expect(image).toHaveClass("fit-page");
    fireEvent.click(screen.getByRole("button", { name: "Fit width" }));
    expect(image).toHaveClass("fit-width");

    const focus = screen.getByRole("button", { name: "Enter reading focus" });
    fireEvent.click(focus);
    expect(workspace).toHaveClass("is-reading-focus");
    const exitFocus = screen.getByRole("button", { name: "Exit reading focus" });
    expect(exitFocus).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(exitFocus);
    expect(workspace).not.toHaveClass("is-reading-focus");

    expect(surface.nextElementSibling).toHaveClass("book-companion-tools");
    expect(reader.compareDocumentPosition(document.querySelector(".book-overview") as Node) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows bookmark, search, DGX, and clear-chat unhappy paths without losing the page", async () => {
    vi.mocked(api.bookReaderState).mockResolvedValueOnce({
      book_id: 7, page: 1, progress_updated_at: null,
      bookmarks: [{ page: 1, note: null, created_at: "then", updated_at: "now" }],
    } as any);
    vi.mocked(api.bookChatHistory).mockResolvedValueOnce([{ role: "assistant", content: "Prior answer", citations: [null, {}, { citation: 4 }] }] as any);
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");
    expect(screen.getAllByText("Citation unavailable")).toHaveLength(3);

    vi.mocked(api.saveBookBookmark).mockRejectedValueOnce({ detail: "Private note failed" });
    fireEvent.click(screen.getByRole("button", { name: "Save bookmark for page 1" }));
    expect(await screen.findByText("Private note failed")).toBeTruthy();
    vi.mocked(api.deleteBookBookmark).mockRejectedValueOnce(new Error("offline"));
    fireEvent.click(screen.getByRole("button", { name: "Remove bookmark from page 1" }));
    expect(await screen.findByText("Could not remove this bookmark.")).toBeTruthy();

    vi.mocked(api.searchBook).mockResolvedValueOnce({ query: "none", results: [], truncated: false } as any);
    fireEvent.change(screen.getByLabelText("Search this book"), { target: { value: "none" } });
    fireEvent.click(screen.getByRole("button", { name: "Search book" }));
    expect(await screen.findByText("No exact matches found.")).toBeTruthy();
    vi.mocked(api.searchBook).mockRejectedValueOnce({ detail: "Private search failed" });
    fireEvent.change(screen.getByLabelText("Search this book"), { target: { value: "error" } });
    fireEvent.click(screen.getByRole("button", { name: "Search book" }));
    expect(await screen.findByText("Private search failed")).toBeTruthy();

    vi.mocked(api.bookChat).mockRejectedValueOnce(new Error("DGX down"));
    fireEvent.click(screen.getByRole("button", { name: "What are the key ideas?" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(/retry when DGX is available/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear chat" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear chat" }));
    vi.mocked(api.clearBookChat).mockRejectedValueOnce(new Error("clear"));
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(await screen.findByText("Could not clear chat. Please try again.")).toBeTruthy();
    expect(screen.getByAltText("Page 1 of Inference Engineering")).toBeTruthy();
  });

  it("distinguishes a textless page from a DGX outage and suggests a usable scope", async () => {
    vi.mocked(api.bookChat).mockRejectedValueOnce({
      status: 409,
      code: "page_text_unavailable",
      detail: "This page has no extractable text.",
      retryable: false,
    });
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");

    fireEvent.click(screen.getByRole("button", { name: "What are the key ideas?" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText(/no selectable text/i)).toBeTruthy();
    expect(screen.getByText(/switch context to Whole book/i)).toBeTruthy();
    expect(screen.queryByText(/retry when DGX is available/i)).toBeNull();
  });

  it("maps remaining grounded-chat failures without losing their actionable detail", async () => {
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");
    const cases = [
      [{ status: 422, code: "page_context_too_large", detail: "large" }, /too large for exact-page chat/i],
      [{ status: 409, code: "http_409", detail: "No extracted source is ready." }, /No extracted source is ready/i],
      [{ status: 422, code: "http_422", detail: "Page is outside this book." }, /Page is outside this book/i],
      ["offline", /retry when DGX is available/i],
    ] as const;

    for (const [failure, expected] of cases) {
      vi.mocked(api.bookChat).mockRejectedValueOnce(failure);
      fireEvent.click(screen.getByRole("button", { name: "What are the key ideas?" }));
      fireEvent.click(screen.getByRole("button", { name: "Ask" }));
      expect(await screen.findByText(expected)).toBeTruthy();
    }
  });

  it("supports non-page chat keyboard submission, retry, clear success, and optional section display", async () => {
    vi.mocked(api.bookChatHistory).mockResolvedValueOnce([{ role: "assistant", content: "History", citations: [] }] as any);
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");
    fireEvent.click(screen.getByRole("button", { name: "Retry failed section" }));
    await waitFor(() => expect(api.retryBook).toHaveBeenCalledWith(7));
    fireEvent.change(screen.getByLabelText("Chat context"), { target: { value: "book" } });
    const textarea = screen.getByPlaceholderText("Ask a question grounded in this book…");
    fireEvent.change(textarea, { target: { value: "whole book" } });
    fireEvent.keyDown(textarea, { key: "Enter", ctrlKey: true });
    await waitFor(() => expect(api.bookChat).toHaveBeenCalledWith(7, "whole book", "book", undefined, undefined));
    fireEvent.click(screen.getByRole("button", { name: "Clear chat" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(api.clearBookChat).toHaveBeenCalledWith(7));
    expect(screen.getByPlaceholderText("Ask a question grounded in this book…")).toHaveFocus();
  });

  it("reports initial load failure and polls processing books until unmount", async () => {
    vi.mocked(api.books).mockRejectedValueOnce(new Error("offline"));
    const failed = render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    expect(await screen.findByText("Could not load your library.")).toBeTruthy();
    failed.unmount();

    const processing = { ...summary, status: "processing" };
    vi.mocked(api.books).mockResolvedValue([processing] as any);
    vi.mocked(api.book).mockResolvedValue({ ...detail, ...processing } as any);
    let poll: (() => void) | undefined;
    const interval = vi.spyOn(window, "setInterval").mockImplementation((callback) => {
      poll = callback as () => void;
      return 42 as any;
    });
    const clear = vi.spyOn(window, "clearInterval");
    const view = render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");
    expect(poll).toBeTypeOf("function");
    await act(async () => { poll?.(); });
    await waitFor(() => expect(api.book).toHaveBeenCalledTimes(2));
    view.unmount();
    expect(clear).toHaveBeenCalledWith(42);
    interval.mockRestore(); clear.mockRestore();
  });

  it("queues the newest progress while a save is in flight and ignores an old-book failure", async () => {
    const second = { ...summary, id: 8, title: "Second Book", status: "ready" };
    vi.mocked(api.books).mockResolvedValue([summary, second] as any);
    vi.mocked(api.book).mockImplementation(async (id) => ({ ...detail, ...(id === 8 ? second : summary), sections: [] }) as any);
    vi.mocked(api.bookReaderState).mockImplementation(async (id) => ({ book_id: id, page: 1, progress_updated_at: null, bookmarks: [] }) as any);
    let rejectSave: ((reason: Error) => void) | undefined;
    vi.mocked(api.saveBookProgress)
      .mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectSave = reject; }))
      .mockResolvedValue({ book_id: 7, page: 3, updated_at: "later" } as any);
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.click(await screen.findByRole("button", { name: "Next page" }));
    fireEvent.click(screen.getByRole("button", { name: /Second Book/ }));
    await screen.findByAltText("Page 1 of Second Book");
    await act(async () => { rejectSave?.(new Error("offline")); });
    await waitFor(() => expect(api.saveBookProgress).toHaveBeenLastCalledWith(7, 3));
    expect(screen.queryByText(/resume progress could not be saved/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Inference Engineering/ }));
    await screen.findByAltText("Page 1 of Inference Engineering");
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    fireEvent.click(await screen.findByRole("button", { name: "Previous page" }));
    expect(await screen.findByAltText("Page 1 of Inference Engineering")).toBeTruthy();
  });

  it("aborts stale search work and renders the singular exact-match label", async () => {
    const second = { ...summary, id: 8, title: "Second Book", status: "ready" };
    vi.mocked(api.books).mockResolvedValue([summary, second] as any);
    vi.mocked(api.book).mockImplementation(async (id) => ({ ...detail, ...(id === 8 ? second : summary), sections: [] }) as any);
    vi.mocked(api.bookReaderState).mockImplementation(async (id) => ({ book_id: id, page: 1, progress_updated_at: null, bookmarks: [] }) as any);
    vi.mocked(api.searchBook).mockImplementationOnce((_id, _query, signal) => new Promise((_resolve, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    }));
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");
    fireEvent.change(screen.getByLabelText("Search this book"), { target: { value: "pending" } });
    fireEvent.click(screen.getByRole("button", { name: "Search book" }));
    await waitFor(() => expect(api.searchBook).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: /Second Book/ }));
    expect(await screen.findByAltText("Page 1 of Second Book")).toBeTruthy();
    expect(screen.queryByText("Search could not be completed.")).toBeNull();

    vi.mocked(api.searchBook).mockResolvedValueOnce({ query: "one", results: [{ page: 2, snippet: "one", match_count: 1 }], truncated: false } as any);
    fireEvent.change(screen.getByLabelText("Search this book"), { target: { value: "one" } });
    fireEvent.click(screen.getByRole("button", { name: "Search book" }));
    expect(await screen.findByText("1 exact match")).toBeTruthy();
  });

  it("ignores a stale in-flight chat answer and non-submit Enter keys", async () => {
    const second = { ...summary, id: 8, title: "Second Book", status: "ready" };
    vi.mocked(api.books).mockResolvedValue([summary, second] as any);
    vi.mocked(api.book).mockImplementation(async (id) => ({ ...detail, ...(id === 8 ? second : summary), sections: id === 8 ? [{ ...detail.sections[0], summary: undefined, concept_id: undefined }] : detail.sections }) as any);
    vi.mocked(api.bookReaderState).mockImplementation(async (id) => ({ book_id: id, page: 1, progress_updated_at: null, bookmarks: [] }) as any);
    let resolveChat: ((value: any) => void) | undefined;
    vi.mocked(api.bookChat).mockImplementationOnce(() => new Promise((resolve) => { resolveChat = resolve; }));
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");
    const textarea = screen.getByPlaceholderText("Ask about page 1…");
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(api.bookChat).not.toHaveBeenCalled();
    fireEvent.change(textarea, { target: { value: "pending answer" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    fireEvent.change(textarea, { target: { value: "second while busy" } });
    fireEvent.keyDown(textarea, { key: "Enter", ctrlKey: true });
    expect(api.bookChat).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /Second Book/ }));
    await screen.findByAltText("Page 1 of Second Book");
    await act(async () => { resolveChat?.({ answer: "stale answer", citations: [] }); });
    expect(screen.queryByText("stale answer")).toBeNull();
    expect(screen.queryByRole("link", { name: "Open lesson →" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Inference Engineering/ }));
    await screen.findByAltText("Page 1 of Inference Engineering");
    let rejectChat: ((reason: unknown) => void) | undefined;
    vi.mocked(api.bookChat).mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectChat = reject; }));
    const firstBookQuestion = screen.getByPlaceholderText("Ask about page 1…");
    fireEvent.change(firstBookQuestion, { target: { value: "stale revoked request" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    fireEvent.click(screen.getByRole("button", { name: /Second Book/ }));
    await screen.findByAltText("Page 1 of Second Book");
    await act(async () => { rejectChat?.({ status: 404, detail: "Book not found" }); });
    expect(screen.queryByText("This book is no longer shared with you.")).toBeNull();
  });

  it("ignores stale bookmark mutations and permits books without generated sections", async () => {
    const second = { ...summary, id: 8, title: "Second Book", status: "ready" };
    vi.mocked(api.books).mockResolvedValue([summary, second] as any);
    vi.mocked(api.book).mockImplementation(async (id) => (
      id === 8 ? { ...detail, ...second, sections: undefined } : detail
    ) as any);
    vi.mocked(api.bookReaderState).mockImplementation(async (id) => ({
      book_id: id, page: 1, progress_updated_at: null,
      bookmarks: id === 7 ? [{ page: 1, note: "original", created_at: "then", updated_at: "then" }] : [],
    }) as any);
    let resolveSave: ((value: any) => void) | undefined;
    let resolveDelete: ((value?: unknown) => void) | undefined;
    vi.mocked(api.saveBookBookmark).mockImplementationOnce(() => new Promise((resolve) => { resolveSave = resolve; }));
    vi.mocked(api.deleteBookBookmark).mockImplementationOnce(() => new Promise((resolve) => { resolveDelete = resolve; }));
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    await screen.findByAltText("Page 1 of Inference Engineering");
    fireEvent.click(screen.getByRole("button", { name: "Save bookmark for page 1" }));
    fireEvent.click(screen.getByRole("button", { name: /Second Book/ }));
    await screen.findByAltText("Page 1 of Second Book");
    await act(async () => { resolveSave?.({ page: 1, note: "stale", created_at: "now", updated_at: "now" }); });
    expect(screen.queryByRole("heading", { name: "Jump by section" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Read page 2" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Inference Engineering/ }));
    await screen.findByAltText("Page 1 of Inference Engineering");
    fireEvent.click(screen.getByRole("button", { name: "Remove bookmark from page 1" }));
    fireEvent.click(screen.getByRole("button", { name: /Second Book/ }));
    await screen.findByAltText("Page 1 of Second Book");
    await act(async () => { resolveDelete?.(); });
    expect(screen.queryByText("original")).toBeNull();
  });

  it("does not clear the newly selected book when an old clear request finishes", async () => {
    const second = { ...summary, id: 8, title: "Second Book", status: "ready" };
    vi.mocked(api.books).mockResolvedValue([summary, second] as any);
    vi.mocked(api.book).mockImplementation(async (id) => ({ ...detail, ...(id === 8 ? second : summary), sections: [] }) as any);
    vi.mocked(api.bookReaderState).mockImplementation(async (id) => ({ book_id: id, page: 1, progress_updated_at: null, bookmarks: [] }) as any);
    vi.mocked(api.bookChatHistory).mockImplementation(async (id) => [{ role: "assistant", content: `History ${id}`, citations: [] }] as any);
    let resolveClear: ((value?: unknown) => void) | undefined;
    vi.mocked(api.clearBookChat).mockImplementationOnce(() => new Promise((resolve) => { resolveClear = resolve; }));
    render(<MemoryRouter><MakeMeLearn /></MemoryRouter>);
    expect(await screen.findByText("History 7")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear chat" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    fireEvent.click(screen.getByRole("button", { name: /Second Book/ }));
    expect(await screen.findByText("History 8")).toBeTruthy();
    await act(async () => { resolveClear?.(); });
    expect(screen.getByText("History 8")).toBeTruthy();
  });
});
