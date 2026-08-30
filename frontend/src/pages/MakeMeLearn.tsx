import { type CSSProperties, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Book, type BookBookmark, type BookSearchResult, type BookSection } from "../api";
type Message = { role: string; content: string; citations?: unknown };
type ChatScope = "page" | "book" | "chapter" | "topic";
type Citation = { citation: string; page_start: number; page_end: number };

function validCitation(value: unknown, pageCount: number): Citation | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  if (typeof item.citation !== "string" || !Number.isInteger(item.page_start) || !Number.isInteger(item.page_end)) return null;
  const start = item.page_start as number;
  const end = item.page_end as number;
  return start >= 1 && start <= end && end <= pageCount ? { citation: item.citation, page_start: start, page_end: end } : null;
}

function citationText(value: unknown): string {
  return value && typeof value === "object" && typeof (value as Record<string, unknown>).citation === "string"
    ? String((value as Record<string, unknown>).citation)
    : "Citation unavailable";
}

function failureText(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && typeof (error as Record<string, unknown>).detail === "string") {
    return String((error as Record<string, unknown>).detail);
  }
  return fallback;
}

function isRevokedBook(error: unknown): boolean {
  return !!error && typeof error === "object" && (error as Record<string, unknown>).status === 404;
}

function chatFailureText(error: unknown): string {
  if (error && typeof error === "object") {
    const failure = error as Record<string, unknown>;
    if (failure.code === "page_text_unavailable") {
      return "This page has no selectable text for DGX to read. Try a text page or switch context to Whole book.";
    }
    if (failure.code === "page_context_too_large") {
      return "This page is too large for exact-page chat. Switch context to Whole book to ask across extracted sections.";
    }
    if ((failure.status === 409 || failure.status === 422) && typeof failure.detail === "string") {
      return failure.detail;
    }
  }
  return "DGX could not answer from this scope. Your page is preserved; retry when DGX is available.";
}

function clampChatWidth(value: number): number {
  const maximum = Math.min(620, Math.max(340, window.innerWidth * 0.5));
  return Math.min(Math.max(value, 340), maximum);
}

export default function MakeMeLearn() {
  const [books, setBooks] = useState<Book[]>([]);
  const [active, setActive] = useState<Book | null>(null);
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [scope, setScope] = useState<ChatScope>("page");
  const [sectionId, setSectionId] = useState<number | undefined>();
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(100);
  const [pageFit, setPageFit] = useState<"width" | "page" | "custom">("width");
  const [readingFocus, setReadingFocus] = useState(false);
  const [chatWidth, setChatWidth] = useState(420);
  const [pageLoading, setPageLoading] = useState(false);
  const [pageError, setPageError] = useState("");
  const [pageReload, setPageReload] = useState(0);
  const [pageImageUrl, setPageImageUrl] = useState("");
  const [bookmarks, setBookmarks] = useState<BookBookmark[]>([]);
  const [bookmarkNote, setBookmarkNote] = useState("");
  const [bookmarkBusy, setBookmarkBusy] = useState(false);
  const [bookmarkError, setBookmarkError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<BookSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchComplete, setSearchComplete] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [focusTextarea, setFocusTextarea] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [confirmingShare, setConfirmingShare] = useState(false);
  const [shareError, setShareError] = useState("");
  const triggerRef = useRef<HTMLButtonElement>(null);
  const confirmBtnRef = useRef<HTMLButtonElement>(null);
  const readerRef = useRef<HTMLElement>(null);
  const activeRef = useRef<Book | null>(null);
  const loadTokenRef = useRef(0);
  const searchTokenRef = useRef(0);
  const searchControllerRef = useRef<AbortController | null>(null);
  const searchTimerRef = useRef<number | null>(null);
  const resizingChatRef = useRef(false);
  const sharingRef = useRef(false);
  const progressPendingRef = useRef<{ bookId: number; page: number } | null>(null);
  const progressSavingRef = useRef(false);

  async function refresh(selectId?: number) {
    const token = ++loadTokenRef.current;
    const list = await api.books();
    if (token !== loadTokenRef.current) return;
    setBooks(list);
    const preferredId = selectId ?? activeRef.current?.id;
    const id = preferredId && list.some((book) => book.id === preferredId) ? preferredId : list[0]?.id;
    if (!id) {
      activeRef.current = null;
      setActive(null); setMessages([]); setBookmarks([]);
      return;
    }
    let detail: Book;
    let history: Message[];
    let readerState: Awaited<ReturnType<typeof api.bookReaderState>> | null;
    try {
      const [loadedBook, loadedHistory, readerResult] = await Promise.all([
        api.book(id), api.bookChatHistory(id),
        api.bookReaderState(id).then((value) => ({ value })).catch((caught) => ({ caught })),
      ]);
      if ("caught" in readerResult && isRevokedBook(readerResult.caught)) throw readerResult.caught;
      detail = loadedBook;
      history = loadedHistory;
      readerState = "value" in readerResult ? readerResult.value : null;
    } catch (caught) {
      if (!isRevokedBook(caught)) throw caught;
      const remaining = (await api.books()).filter((book) => book.id !== id);
      if (token !== loadTokenRef.current) return;
      setBooks(remaining);
      activeRef.current = null;
      setActive(null); setMessages([]); setBookmarks([]);
      if (remaining[0]) await refresh(remaining[0].id);
      return;
    }
    if (token !== loadTokenRef.current) return;
    activeRef.current = detail;
    setActive(detail); setMessages(history);
    if (!readerState) setError("Resume state could not be loaded. Starting at page 1.");
    setBookmarks(readerState?.bookmarks ?? []);
    setPage(Math.min(Math.max(readerState?.page ?? 1, 1), Math.max(detail.page_count, 1)));
  }

  async function refreshStatus(id: number) {
    const [list, detail] = await Promise.all([api.books(), api.book(id)]);
    if (activeRef.current?.id !== id) return;
    activeRef.current = detail;
    setBooks(list); setActive(detail);
  }

  useEffect(() => { refresh().catch(() => setError("Could not load your library.")); }, []);
  useEffect(() => {
    if (!active?.is_owner || !["queued", "processing", "extracting"].includes(active.status)) return;
    const timer = window.setInterval(() => refreshStatus(active.id).catch(() => {}), 4000);
    return () => clearInterval(timer);
  }, [active?.id, active?.is_owner, active?.is_owner ? active.status : undefined]);
  useEffect(() => {
    if (!active) { setPageImageUrl(""); return; }
    const bookId = active.id;
    const controller = new AbortController();
    let objectUrl = "";
    setPageImageUrl(""); setPageLoading(true); setPageError("");
    void api.bookPage(bookId, page, controller.signal).then((blob) => {
      if (controller.signal.aborted || activeRef.current?.id !== bookId) return;
      objectUrl = URL.createObjectURL(blob);
      setPageImageUrl(objectUrl);
    }).catch(async (caught) => {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      if (await recoverRevocation(caught, bookId)) return;
      if (activeRef.current?.id === bookId) {
        setPageLoading(false); setPageError("This page could not be rendered.");
      }
    });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [active?.id, page, pageReload]);
  useEffect(() => {
    const bookmark = bookmarks.find((item) => item.page === page);
    setBookmarkNote(bookmark?.note || ""); setBookmarkError("");
  }, [active?.id, page, bookmarks]);
  useEffect(() => {
    if (confirmingClear) confirmBtnRef.current?.focus();
    else triggerRef.current?.focus();
  }, [confirmingClear]);
  useEffect(() => {
    if (!focusTextarea) return;
    const texts = document.querySelectorAll(".chat-input textarea");
    (texts[texts.length - 1] as HTMLTextAreaElement)?.focus();
    setFocusTextarea(false);
  }, [focusTextarea, active?.id, busy]);
  useEffect(() => () => {
    searchControllerRef.current?.abort();
    if (searchTimerRef.current !== null) window.clearTimeout(searchTimerRef.current);
  }, []);

  function resetTransient() {
    searchControllerRef.current?.abort();
    if (searchTimerRef.current !== null) window.clearTimeout(searchTimerRef.current);
    searchTimerRef.current = null; searchTokenRef.current += 1;
    setSearchQuery(""); setSearchResults([]); setSearchError(""); setSearchComplete(false); setSearching(false);
    setQuestion(""); setError(""); setPageError(""); setBookmarkError("");
    setConfirmingShare(false); setShareError("");
    setMessages([]); setBookmarks([]); setBookmarkNote("");
  }

  async function recoverRevocation(caught: unknown, bookId: number): Promise<boolean> {
    if (!isRevokedBook(caught)) return false;
    if (!activeRef.current || activeRef.current.id !== bookId) return true;
    let list: Book[];
    try { list = await api.books(); }
    catch { return false; }
    if (!activeRef.current || activeRef.current.id !== bookId) return true;
    if (list.some((book) => book.id === bookId)) return false;
    setBooks(list);
    activeRef.current = null; setActive(null); resetTransient();
    if (list[0]) {
      try { await refresh(list[0].id); }
      catch { setBooks([]); }
    }
    setError("This book is no longer shared with you.");
    return true;
  }

  async function selectBook(id: number) {
    loadTokenRef.current += 1;
    activeRef.current = null; setActive(null);
    setPage(1); setZoom(100); setPageFit("width"); setSectionId(undefined); setScope("page"); resetTransient();
    try { await refresh(id); }
    catch (caught) {
      if (!(await recoverRevocation(caught, id))) setError("Could not load that book.");
    }
  }

  async function upload(file?: File) {
    if (!file) return;
    setBusy(true); setError("");
    try {
      const book = await api.uploadBook(file);
      activeRef.current = null; setActive(null); setPage(1); resetTransient();
      await refresh(book.id);
    } catch {
      setError("Import failed. Use a text-based, unencrypted PDF under 50 MB / 500 pages.");
    } finally { setBusy(false); }
  }

  async function flushProgress() {
    if (progressSavingRef.current) return;
    progressSavingRef.current = true;
    try {
      while (progressPendingRef.current) {
        const next = progressPendingRef.current;
        progressPendingRef.current = null;
        try { await api.saveBookProgress(next.bookId, next.page); }
        catch (caught) {
          if (await recoverRevocation(caught, next.bookId)) continue;
          if (activeRef.current?.id === next.bookId) setError("Your page changed, but resume progress could not be saved. Try again.");
        }
      }
    } finally { progressSavingRef.current = false; }
  }

  function goToPage(next: number) {
    const book = activeRef.current!;
    const bounded = Math.min(Math.max(Math.round(next) || 1, 1), Math.max(book.page_count, 1));
    setPage(bounded);
    progressPendingRef.current = { bookId: book.id, page: bounded };
    void flushProgress();
  }

  async function saveBookmark() {
    const book = activeRef.current!;
    setBookmarkBusy(true); setBookmarkError("");
    try {
      const saved = await api.saveBookBookmark(book.id, page, bookmarkNote);
      if (activeRef.current?.id !== book.id) return;
      setBookmarks((items) => [...items.filter((item) => item.page !== page), saved].sort((a, b) => a.page - b.page));
    } catch (caught) {
      if (!(await recoverRevocation(caught, book.id))) setBookmarkError(failureText(caught, "Could not save this bookmark note."));
    }
    finally { setBookmarkBusy(false); }
  }

  async function removeBookmark() {
    const book = activeRef.current!;
    setBookmarkBusy(true); setBookmarkError("");
    try {
      await api.deleteBookBookmark(book.id, page);
      if (activeRef.current?.id !== book.id) return;
      setBookmarks((items) => items.filter((item) => item.page !== page)); setBookmarkNote("");
    } catch (caught) {
      if (!(await recoverRevocation(caught, book.id))) setBookmarkError(failureText(caught, "Could not remove this bookmark."));
    }
    finally { setBookmarkBusy(false); }
  }

  function submitSearch() {
    const book = activeRef.current!;
    const token = ++searchTokenRef.current;
    const query = searchQuery;
    searchControllerRef.current?.abort();
    if (searchTimerRef.current !== null) window.clearTimeout(searchTimerRef.current);
    const controller = new AbortController();
    searchControllerRef.current = controller;
    setSearching(true); setSearchError(""); setSearchComplete(false); setSearchResults([]);
    searchTimerRef.current = window.setTimeout(async () => {
      try {
        const response = await api.searchBook(book.id, query, controller.signal);
        if (token !== searchTokenRef.current || activeRef.current?.id !== book.id) return;
        setSearchResults(response.results); setSearchComplete(true);
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        if (await recoverRevocation(caught, book.id)) return;
        if (token === searchTokenRef.current) setSearchError(failureText(caught, "Search could not be completed."));
      } finally { if (token === searchTokenRef.current) setSearching(false); }
    }, 120);
  }

  async function ask() {
    const q = question.trim();
    if (!q || asking) return;
    const book = activeRef.current!;
    setQuestion(""); setAsking(true);
    setMessages((items) => [...items, { role: "user", content: q }]);
    try {
      const scopedSectionId = scope === "chapter" || scope === "topic" ? sectionId : undefined;
      const response = await api.bookChat(book.id, q, scope, scopedSectionId, scope === "page" ? page : undefined);
      if (activeRef.current?.id !== book.id) return;
      setMessages((items) => [...items, { role: "assistant", content: response.answer, citations: response.citations }]);
    } catch (caught) {
      if (await recoverRevocation(caught, book.id)) return;
      if (activeRef.current?.id === book.id) setMessages((items) => [...items, { role: "assistant", content: chatFailureText(caught) }]);
    } finally { setAsking(false); }
  }

  async function clearChat() {
    const book = activeRef.current!;
    setClearing(true); setConfirmingClear(false);
    try {
      await api.clearBookChat(book.id);
      if (activeRef.current?.id === book.id) setMessages([]);
      setFocusTextarea(true);
    } catch (caught) {
      if (!(await recoverRevocation(caught, book.id))) setError("Could not clear chat. Please try again.");
    }
    finally { setClearing(false); }
  }

  async function updateSharing(sharedWithAll: boolean) {
    const book = activeRef.current;
    if (!book?.is_owner || sharingRef.current) return;
    sharingRef.current = true;
    setSharing(true); setShareError("");
    try {
      const result = await api.shareBook(book.id, sharedWithAll);
      if (activeRef.current?.id !== book.id || !activeRef.current.is_owner) return;
      const updated: Book = { ...activeRef.current, shared_with_all: result.shared_with_all };
      activeRef.current = updated;
      setActive(updated);
      setBooks((items) => items.map((item) => item.id === updated.id ? { ...item, shared_with_all: result.shared_with_all } as Book : item));
      setConfirmingShare(false);
    } catch (caught) {
      if (activeRef.current?.id === book.id && activeRef.current.is_owner) {
        setShareError(failureText(caught, sharedWithAll ? "Could not share this book." : "Could not stop sharing this book."));
      }
    } finally { sharingRef.current = false; setSharing(false); }
  }

  function openSection(section: BookSection) {
    goToPage(section.page_start);
    setSectionId(section.id); setScope("page");
    readerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const currentBookmark = bookmarks.find((item) => item.page === page);
  const workspaceStyle = { "--book-chat-width": `${chatWidth}px` } as CSSProperties;

  return <div className={`book-workspace${readingFocus ? " is-reading-focus" : ""}`} style={workspaceStyle}>
    <div className="book-main">
      <header className="book-page-head book-overlay-head"><Link className="btn" to="/" aria-label="Back to PrepPilot">← PrepPilot</Link><div><span className="eyebrow">PRIVATE READER</span><h1>Read a book</h1>{active && <small>{active.title} · page {page} of {active.page_count}</small>}</div>
        <label className="btn primary">{busy ? "Importing…" : "Add PDF"}<input hidden type="file" accept="application/pdf,.pdf" disabled={busy} onChange={(event) => upload(event.target.files?.[0])} /></label>
      </header>
      {error && <div className="notice error" role="status">{error}</div>}
      {!books.length && <section className="panel book-empty"><h2>Your private library is empty</h2><p>Add a digitally readable PDF. Processing stays on the Mac mini and private DGX; OCR is not included yet.</p><p className="muted">Maximum 50 MB and 500 pages. Only upload material you have rights to process.</p></section>}
      {!!books.length && <div className="book-picker" aria-label="Your books">{books.map((book) => <button className={active?.id === book.id ? "active" : ""} key={book.id} onClick={() => selectBook(book.id)}>{book.title}<small>{book.page_count} pages · {book.is_owner ? (book.shared_with_all ? "shared" : book.status) : "Shared with you"}</small></button>)}</div>}

      {active && <section className="panel book-reader" ref={readerRef} aria-label={`Reading ${active.title}`}>
        <div className="book-reader-toolbar">
          <div className="book-page-nav">
            <button className="btn" onClick={() => goToPage(page - 1)} disabled={page <= 1} aria-label="Previous page">←</button>
            <label>Page <input aria-label="Page number" type="number" min={1} max={active.page_count} value={page} onChange={(event) => goToPage(Number(event.target.value))} /> / {active.page_count}</label>
            <button className="btn" onClick={() => goToPage(page + 1)} disabled={page >= active.page_count} aria-label="Next page">→</button>
          </div>
          <div className="book-zoom" role="group" aria-label="Page zoom"><button className="btn" onClick={() => { setPageFit("custom"); setZoom((value) => Math.max(70, value - 10)); }} aria-label="Zoom out">−</button><span>{zoom}%</span><button className="btn" onClick={() => { setPageFit("custom"); setZoom((value) => Math.min(180, value + 10)); }} aria-label="Zoom in">+</button></div>
          <div className="book-view-controls" role="group" aria-label="Reader view">
            <button className="btn" onClick={() => { setPageFit("width"); setZoom(100); }} aria-label="Fit width" aria-pressed={pageFit === "width"}>Width</button>
            <button className="btn" onClick={() => setPageFit("page")} aria-label="Fit page" aria-pressed={pageFit === "page"}>Page</button>
            <button className="btn reader-focus-toggle" onClick={() => setReadingFocus((value) => !value)} aria-pressed={readingFocus} aria-label={readingFocus ? "Exit reading focus" : "Enter reading focus"}>{readingFocus ? "Exit" : "Focus"}</button>
          </div>
        </div>
        <div className="book-reader-surface">
          {pageLoading && !pageError && <span className="loading book-page-loading">rendering page</span>}
          {pageError && <div className="notice error">{pageError}<button className="btn" onClick={() => setPageReload((value) => value + 1)}>Retry page render</button></div>}
          {pageImageUrl && <img className={`book-page-image fit-${pageFit}`} key={`${active.id}-${page}-${pageReload}`} src={pageImageUrl} alt={`Page ${page} of ${active.title}`} style={pageFit === "custom" ? { width: `${zoom}%` } : undefined} onLoad={() => setPageLoading(false)} onError={() => { setPageLoading(false); setPageError("This page could not be rendered."); }} />}
        </div>
        <div className="book-companion-tools">
          <form className="book-search" onSubmit={(event) => { event.preventDefault(); submitSearch(); }}>
            <label htmlFor="book-search-query">Search this book</label>
            <div><input id="book-search-query" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Exact phrase, 3–200 characters" /><button className="btn" type="submit" disabled={searching}>{searching ? "Searching…" : "Search book"}</button></div>
            <div className="book-search-status" aria-live="polite">{searchError && <span className="notice error">{searchError}</span>}{searchComplete && !searchResults.length && <span>No exact matches found.</span>}{searchResults.map((result) => <button type="button" key={result.page} onClick={() => goToPage(result.page)} aria-label={`Go to search result on page ${result.page}`}><strong>Page {result.page}</strong><span>{result.snippet}</span><small>{result.match_count} exact {result.match_count === 1 ? "match" : "matches"}</small></button>)}</div>
          </form>
          <div className="book-bookmarks">
            <label htmlFor="bookmark-note">Bookmark note for page {page}</label>
            <textarea id="bookmark-note" value={bookmarkNote} onChange={(event) => setBookmarkNote(event.target.value)} maxLength={2000} placeholder="Optional private note" />
            <div className="bookmark-actions"><button className="btn" onClick={saveBookmark} disabled={bookmarkBusy} aria-label={`Save bookmark for page ${page}`}>{currentBookmark ? "Update bookmark" : "Bookmark page"}</button>{currentBookmark && <button className="btn" onClick={removeBookmark} disabled={bookmarkBusy} aria-label={`Remove bookmark from page ${page}`}>Remove</button>}</div>
            {bookmarkError && <span className="notice error" role="status">{bookmarkError}</span>}
            {!!bookmarks.length && <div className="bookmark-list" aria-label="Bookmarks">{bookmarks.map((bookmark) => <button key={bookmark.page} onClick={() => goToPage(bookmark.page)} aria-label={`Go to bookmarked page ${bookmark.page}`}><strong>Page {bookmark.page}</strong>{bookmark.note && <span>{bookmark.note}</span>}</button>)}</div>}
          </div>
        </div>
      </section>}

      {active && <section className="panel book-overview"><details><summary aria-label={`Book details for ${active.title}`}><span><span className="eyebrow">{active.is_owner ? active.status : "Shared with you"}</span><strong>{active.title}</strong><small>{active.is_owner ? `${active.page_count} pages · ${active.generated_lessons} optional lessons ready${active.failed_sections ? ` · ${active.failed_sections} section needs retry` : ""}` : `${active.page_count} pages · shared reader access`}</small></span><span>Book details</span></summary><p>{active.is_owner ? "Generated lessons are optional; reading, search, bookmarks, and grounded page chat work independently." : "Your page, bookmarks, private notes, and DGX chat stay separate from every other reader."}</p></details>
        {active.is_owner && <div className="book-overview-actions">
          <span className={`book-sharing-badge ${active.shared_with_all ? "shared" : "private"}`}>{active.shared_with_all ? "Shared with everyone" : "Private"}</span>
          {!active.activated && ["ready", "partial"].includes(active.status) && <button className="btn" onClick={async () => { await api.activateBook(active.id); await refreshStatus(active.id); }}>Add lessons to syllabus</button>}
          {active.status === "partial" && <button className="btn" onClick={async () => { await api.retryBook(active.id); await refreshStatus(active.id); }}>Retry failed section</button>}
          {active.shared_with_all
            ? <button className="btn" onClick={() => updateSharing(false)} disabled={sharing}>Stop sharing</button>
            : <button className="btn" onClick={() => { setConfirmingShare(true); setShareError(""); }} disabled={sharing || !["ready", "partial"].includes(active.status)}>Share with all users</button>}
        </div>}
        {active.is_owner && confirmingShare && <div className="book-sharing-confirm" role="group" aria-label="Confirm sharing"><p>Every signed-in user can read, search, and chat with this book. Their progress, bookmarks, private notes, and chat history stay separate.</p><div><button className="btn primary" onClick={() => updateSharing(true)} disabled={sharing}>Confirm sharing</button><button className="btn" onClick={() => setConfirmingShare(false)} disabled={sharing}>Cancel</button></div></div>}
        {shareError && <span className="notice error" role="status">{shareError}</span>}
      </section>}
    </div>

    <aside className="book-chat"><div className="book-chat-resizer" role="separator" aria-label="Resize DGX chat" aria-orientation="vertical" aria-valuemin={340} aria-valuemax={Math.round(Math.min(620, Math.max(340, window.innerWidth * 0.5)))} aria-valuenow={chatWidth} tabIndex={0}
        onKeyDown={(event) => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); setChatWidth((value) => clampChatWidth(value + (event.key === "ArrowLeft" ? 24 : -24))); } }}
        onPointerDown={(event) => { resizingChatRef.current = true; event.currentTarget.setPointerCapture(event.pointerId); }}
        onPointerMove={(event) => { if (resizingChatRef.current) setChatWidth(clampChatWidth(window.innerWidth - event.clientX)); }}
        onPointerUp={(event) => { resizingChatRef.current = false; event.currentTarget.releasePointerCapture(event.pointerId); }}
        onPointerCancel={() => { resizingChatRef.current = false; }} />
      <div className="book-chat-head"><div><span className="eyebrow">DGX · GROUNDED</span><h2 tabIndex={-1}>{active && scope === "page" ? `Ask page ${page}` : "Ask this book"}</h2></div>
        {confirmingClear ? active ? <div className="clear-confirm"><span>Clear all messages for <em>{active.title}</em>?</span><div className="clear-confirm-actions"><button className="btn" ref={confirmBtnRef} onClick={clearChat} disabled={clearing || busy}>Clear</button><button className="btn" onClick={() => setConfirmingClear(false)} disabled={clearing || busy}>Cancel</button></div></div> : null : messages.length > 0 ? <button className="btn clear-chat-btn" ref={triggerRef} onClick={() => setConfirmingClear(true)} disabled={busy || clearing}>Clear chat</button> : null}
      </div>
      {!active ? <p className="muted">Add or select a book to begin.</p> : <>
        <label className="book-chat-scope">Use context from<select aria-label="Chat context" value={scope} onChange={(event) => setScope(event.target.value as ChatScope)}><option value="page">Current page · {page}</option><option value="book">Whole book</option><option value="chapter" disabled={!sectionId}>Selected chapter</option><option value="topic" disabled={!sectionId}>{active.is_owner ? "Selected generated lesson" : "Selected section"}</option></select></label>
        <div className="chat-scroll" aria-live="polite">{messages.map((message, index) => <div className={`chat-msg ${message.role}`} key={index}><strong>{message.role === "user" ? "You" : "DGX"}</strong><p>{message.content}</p>{Array.isArray(message.citations) && message.citations.map((citation, citationIndex) => { const valid = validCitation(citation, active.page_count); return valid ? <button className="book-citation" key={citationIndex} onClick={() => goToPage(valid.page_start)} aria-label={`Go to cited page ${valid.page_start}`}>{valid.citation}</button> : <small key={citationIndex}>{citationText(citation)}</small>; })}</div>)}{asking && <span className="loading">reading</span>}</div>
        <div className="chat-prompts">{["Explain this page simply", "Quiz me on this page", "What are the key ideas?"].map((prompt) => <button key={prompt} onClick={() => setQuestion(prompt)}>{prompt}</button>)}</div>
        <div className="chat-input"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) ask(); }} placeholder={scope === "page" ? `Ask about page ${page}…` : "Ask a question grounded in this book…"}/><button className="btn primary" onClick={ask} disabled={asking || !question.trim()}>Ask</button></div>
      </>}
    </aside>

    {active && <section className="panel chapter-journey"><h2>Jump by section</h2><div className="topic-path">{active.sections?.map((section) => <div className={`topic-node${section.status ? ` ${section.status}` : ""}`} key={section.id}><div><strong>{section.topic_title || section.label}</strong>{section.summary && <p>{section.summary}</p>}<small>{section.citation}</small></div>{section.status && <span>{section.status}</span>}<button className="btn" onClick={() => openSection(section)}>Read page {section.page_start}</button>{active.is_owner && section.concept_id && <Link to={`/topics/${section.concept_id}`}>Open lesson →</Link>}</div>)}</div></section>}
  </div>;
}
