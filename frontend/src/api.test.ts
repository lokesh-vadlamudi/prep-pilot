import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, catClass, describeApiError, diffClass, newRequestId, trackClass } from "./api";

describe("inference course API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("uses the course-scoped contracts and preserves mutation identity", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ ok: true }), {
      status: 200, headers: { "content-type": "application/json" },
    })));
    vi.stubGlobal("fetch", fetchMock);

    const controller = new AbortController();
    await api.courseOverview(controller.signal);
    await api.courseModule("IC-03", controller.signal);
    await api.courseLinkedTopic("IC-03", 17, controller.signal);
    await api.courseEnroll({ request_id: "enroll-1", catalog_version: "v1" });

    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      "/api/courses/inference-engineering",
      "/api/courses/inference-engineering/modules/IC-03",
      "/api/courses/inference-engineering/modules/IC-03/linked-topics/17",
      "/api/courses/inference-engineering/enroll",
    ]);
    const enrollCall = fetchMock.mock.calls[3] as unknown as [string, RequestInit];
    const enrollOptions = enrollCall[1];
    expect(JSON.parse(String(enrollOptions.body))).toEqual({ request_id: "enroll-1", catalog_version: "v1" });
    expect(fetchMock.mock.calls.slice(0, 3).every(([, options]) => options.signal === controller.signal)).toBe(true);
  });

  it("surfaces typed server and offline failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({
      error: { code: "stale_revision", detail: "Refresh this mission.", retryable: true },
    }), { status: 409, headers: { "content-type": "application/json" } })));

    await expect(api.courseModule("IC-03")).rejects.toMatchObject({
      status: 409, code: "stale_revision", detail: "Refresh this mission.", retryable: true,
    });

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network")));
    await expect(api.courseOverview()).rejects.toEqual(expect.objectContaining({ status: 0, code: "offline" } as Partial<ApiError>));
  });

  it("keeps every public endpoint wrapper executable with its transport contract", async () => {
    const fetchMock = vi.fn((path: string) => Promise.resolve(new Response(JSON.stringify(
      path === "/api/books/1" ? {
        id: 1, title: "Book", page_count: 1, access: "owner", is_owner: true,
        shared_with_all: false, status: "ready", total_sections: 0, completed_sections: 0,
        generated_lessons: 0, failed_sections: 0, remaining_sections: 0, activated: false,
        sections: [],
      } : { ok: true },
    ), { status: 200, headers: { "content-type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["book"], "book.txt", { type: "text/plain" });
    const requests = [
      () => api.needsSetup(), () => api.setup("secret", "pilot"), () => api.me(), () => api.login("pilot", "secret"),
      () => api.register("pilot", "secret", "invite", "senior", "typescript"), () => api.logout(), () => api.adminAudit(), () => api.health(),
      () => api.today(), () => api.learnNext(), () => api.diagnoseLearnNext(), () => api.roadmap(), () => api.books(), () => api.book(1), () => api.uploadBook(file),
      () => api.activateBook(1), () => api.retryBook(1), () => api.bookChat(1, "question", "section", 2), () => api.bookChatHistory(1), () => api.clearBookChat(1),
      () => api.bookPage(1, 1), () => api.bookReaderState(1), () => api.saveBookProgress(1, 3), () => api.saveBookBookmark(1, 3, "Key proof"),
      () => api.deleteBookBookmark(1, 3), () => api.searchBook(1, "GPU + cache"),
      () => api.card(1), () => api.submit({ card_id: 1, user_answer: "answer" }), () => api.progress(), () => api.topics(), () => api.topic(1),
      () => api.topicStatus(1, true), () => api.ask("question", "context", [{ role: "user", content: "prior" }]), () => api.brainHealth(), () => api.generateNow(),
      () => api.problems(), () => api.problem(1), () => api.problemStats(), () => api.problemOfTheDay(), () => api.problemApproach(1), () => api.problemStatus(1, { status: "attempted" }),
      () => api.problemCoach(1, "plan"), () => api.problemHints(1), () => api.starter(1, "python"), () => api.runCode(1, "python", "print(1)"),
      () => api.mentor(1, { language: "python", code: "print(1)", mode: "review" }), () => api.targetStatus(), () => api.setTarget({ daily_problem_target: 1 }),
      () => api.jobs(), () => api.addJob({ company: "OpenAI", role: "Engineer" }),
      () => api.updateJob(1, { status: "applied" }), () => api.deleteJob(1), () => api.setJobTarget(2),
      () => api.mockStart({ kind: "system-design" }), () => api.mockReply(1, "reply"), () => api.mockFinish(1), () => api.mockHistory(),
      () => api.courseReconciliationPreview("IC 03", true), () => api.courseReconcile({ request_id: "r" }), () => api.courseDeleteLink(1, { request_id: "r" }),
      () => api.courseSaveArtifact("IC 03", "artifact/1", { request_id: "r" }), () => api.courseCheckpoint("checkpoint/1", { request_id: "r" }),
      () => api.courseOralTurn("IC 03", { request_id: "r" }), () => api.courseOralSelfRecord("IC 03", { request_id: "r" }),
      () => api.courseOralComplete("IC 03", { request_id: "r" }), () => api.courseOralReview("IC 03", { request_id: "r" }),
    ];
    for (const request of requests) await request();
    expect(fetchMock).toHaveBeenCalledTimes(66);
    const requestPaths = fetchMock.mock.calls as unknown as [string, RequestInit?][];
    expect(requestPaths.some(([path]) => path.includes("IC%2003"))).toBe(true);
    expect(requestPaths.slice(-9).map(([path, options]) => [
      path, options?.method, options?.body ? JSON.parse(String(options.body)) : undefined,
    ])).toEqual([
      ["/api/courses/inference-engineering/reconcile/IC%2003?scan=true", undefined, undefined],
      ["/api/courses/inference-engineering/reconcile", "POST", { request_id: "r" }],
      ["/api/courses/inference-engineering/links/1", "DELETE", { request_id: "r" }],
      ["/api/courses/inference-engineering/missions/IC%2003/artifacts/artifact%2F1", "PUT", { request_id: "r" }],
      ["/api/courses/inference-engineering/checkpoints/checkpoint%2F1/submit", "POST", { request_id: "r" }],
      ["/api/courses/inference-engineering/oral/IC%2003/turn", "POST", { request_id: "r" }],
      ["/api/courses/inference-engineering/oral/IC%2003/self-record", "POST", { request_id: "r" }],
      ["/api/courses/inference-engineering/oral/IC%2003/complete", "POST", { request_id: "r" }],
      ["/api/courses/inference-engineering/oral/IC%2003/review", "POST", { request_id: "r" }],
    ]);
  });

  it("keeps private reader state, bookmark, progress, and literal-search request shapes exact", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ ok: true }), {
      status: 200, headers: { "content-type": "application/json" },
    })));
    vi.stubGlobal("fetch", fetchMock);

    const controller = new AbortController();
    expect(api.bookPageUrl(7, 2)).toBe("/api/books/7/pages/2");
    await api.bookPage(7, 2, controller.signal);
    await api.bookReaderState(7, controller.signal);
    await api.saveBookProgress(7, 2);
    await api.saveBookBookmark(7, 2, "  keep spacing  ");
    await api.deleteBookBookmark(7, 2);
    await api.searchBook(7, "GPU + cache", controller.signal);

    expect(fetchMock.mock.calls).toEqual([
      ["/api/books/7/pages/2", expect.objectContaining({ credentials: "same-origin", signal: controller.signal })],
      ["/api/books/7/reader-state", expect.objectContaining({ credentials: "same-origin", signal: controller.signal })],
      ["/api/books/7/progress", expect.objectContaining({ method: "PUT", body: JSON.stringify({ page: 2 }) })],
      ["/api/books/7/bookmarks/2", expect.objectContaining({ method: "PUT", body: JSON.stringify({ note: "  keep spacing  " }) })],
      ["/api/books/7/bookmarks/2", expect.objectContaining({ method: "DELETE" })],
      ["/api/books/7/search?q=GPU%20%2B%20cache", expect.objectContaining({ credentials: "same-origin", signal: controller.signal })],
    ]);
  });

  it("returns authenticated page blobs and preserves typed page failures", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response(new Blob(["png"], { type: "image/png" }), {
        status: 200, headers: { "content-type": "image/png" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Book not found" }), {
        status: 404, headers: { "content-type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response("upstream failed", { status: 500 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        error: { code: "page_unavailable", detail: "No page", retryable: false },
      }), { status: 503, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({}), {
        status: 401, headers: { "content-type": "application/json" },
      }))
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockRejectedValueOnce(new DOMException("stop", "AbortError")));

    await expect(api.bookPage(4, 2)).resolves.toBeInstanceOf(Blob);
    await expect(api.bookPage(4, 2)).rejects.toMatchObject({ status: 404, detail: "Book not found" });
    await expect(api.bookPage(4, 2)).rejects.toMatchObject({ status: 500, code: "http_500", retryable: true });
    await expect(api.bookPage(4, 2)).rejects.toMatchObject({ status: 503, code: "page_unavailable", retryable: false });
    await expect(api.bookPage(4, 2)).rejects.toMatchObject({ status: 401, code: "unauthorized", detail: "Your session expired." });
    await expect(api.bookPage(4, 2)).rejects.toMatchObject({ status: 0, code: "offline" });
    await expect(api.bookPage(4, 2)).rejects.toMatchObject({ name: "AbortError" });
  });

  it("validates owner/shared book contracts and sends the sharing mutation exactly", async () => {
    const response = (value: unknown) => new Response(JSON.stringify(value), {
      status: 200, headers: { "content-type": "application/json" },
    });
    const owner = {
      id: 1, title: "Mine", page_count: 3, access: "owner", is_owner: true,
      shared_with_all: false, status: "ready", total_sections: 1, completed_sections: 1,
      generated_lessons: 1, failed_sections: 0, remaining_sections: 0, activated: false,
    };
    const shared = {
      id: 2, title: "Shared", page_count: 4, access: "shared", is_owner: false,
      shared_with_all: true,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([owner, shared, { ...shared, id: 3, shared_with_all: false }]))
      .mockResolvedValueOnce(response({ ...shared, sections: [{
        id: 8, chapter: "Serving", label: "Batching", page_start: 2, page_end: 3,
        citation: "pages 2-3",
      }] }))
      .mockResolvedValueOnce(response({
        book_id: 1, access: "owner", is_owner: true, shared_with_all: true,
        updated_at: "now", changed: true,
      }))
      .mockResolvedValueOnce(response({ ...shared, status: "ready" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.books()).resolves.toEqual([owner, shared]);
    await expect(api.book(2)).resolves.toEqual({ ...shared, sections: [expect.objectContaining({ id: 8 })] });
    await expect(api.shareBook(1, true)).resolves.toMatchObject({ shared_with_all: true, changed: true });
    expect(fetchMock.mock.calls[2]).toEqual([
      "/api/books/1/sharing",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ shared_with_all: true }) }),
    ]);
    await expect(api.book(2)).rejects.toMatchObject({ code: "invalid_book_response" });
  });

  it("rejects malformed owner and shared book details without leaking partial records", async () => {
    const response = (value: unknown) => new Response(JSON.stringify(value), {
      status: 200, headers: { "content-type": "application/json" },
    });
    const shared = {
      id: 2, title: "Shared", page_count: 4, access: "shared", is_owner: false,
      shared_with_all: true,
    };
    const owner = {
      id: 1, title: "Mine", page_count: 3, access: "owner", is_owner: true,
      shared_with_all: false, status: "ready", total_sections: 1, completed_sections: 1,
      generated_lessons: 1, failed_sections: 0, remaining_sections: 0, activated: false,
    };
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(response(null))
      .mockResolvedValueOnce(response({ id: 0, title: "Invalid", page_count: 1 }))
      .mockResolvedValueOnce(response({ ...shared, sections: [{
        id: 8, chapter: "Serving", label: "Batching", page_start: 2, page_end: 2,
        citation: "private", concept_id: 99,
      }] }))
      .mockResolvedValueOnce(response({ ...shared, sections: [{
        id: 8, chapter: "Serving", label: "Batching", page_start: 3, page_end: 2, citation: "bad",
      }] }))
      .mockResolvedValueOnce(response({ ...owner, activated: "false", sections: [] }))
      .mockResolvedValueOnce(response({ ...owner, sections: "private" }))
      .mockResolvedValueOnce(response({ ...shared, sections: null }))
      .mockResolvedValueOnce(response({ records: [owner] })));

    for (const id of [2, 2, 2, 2, 1, 1, 2]) {
      await expect(api.book(id)).rejects.toMatchObject({ code: "invalid_book_response" });
    }
    await expect(api.books()).resolves.toEqual([]);
  });

  it("defensively decodes typed chat citations before exposing them to the reader", async () => {
    const reply = (value: unknown) => new Response(JSON.stringify(value), {
      status: 200, headers: { "content-type": "application/json" },
    });
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(reply({
        answer: "Grounded",
        citations: [
          { section_id: 2, citation: "page 2", page_start: 2, page_end: 2 },
          { section_id: null, citation: "nullable", page_start: 1, page_end: 1 },
          { section_id: null, citation: "boolean", page_start: true, page_end: true },
          { section_id: null, citation: "reverse", page_start: 3, page_end: 2 },
          { section_id: "2", citation: "section string", page_start: 2, page_end: 2 },
          { section_id: null, citation: "zero", page_start: 0, page_end: 1 },
          { section_id: null, citation: 4, page_start: 1, page_end: 1 },
          null,
        ],
      }))
      .mockResolvedValueOnce(reply(null))
      .mockResolvedValueOnce(reply({ answer: 4, citations: {} }))
      .mockResolvedValueOnce(reply({ ok: true }))
      .mockResolvedValueOnce(reply([
        null, 4, { role: "assistant" }, { content: "missing role" },
        { role: 4, content: "bad role" }, { role: "assistant", content: 4 },
        { role: "assistant", content: "History", citations: [
          { citation: "page 1", page_start: 1, page_end: 1 },
          { citation: "fraction", page_start: 1.5, page_end: 2 },
        ] },
      ])));

    await expect(api.bookChat(7, "question", "page", undefined, 2)).resolves.toEqual({
      answer: "Grounded",
      citations: [
        { section_id: 2, citation: "page 2", page_start: 2, page_end: 2 },
        { section_id: null, citation: "nullable", page_start: 1, page_end: 1 },
      ],
    });
    await expect(api.bookChat(7, "null")).resolves.toEqual({ answer: "", citations: [] });
    await expect(api.bookChat(7, "wrong types")).resolves.toEqual({ answer: "", citations: [] });
    await expect(api.bookChatHistory(7)).resolves.toEqual([]);
    await expect(api.bookChatHistory(7)).resolves.toEqual([{
      role: "assistant", content: "History",
      citations: [{ section_id: null, citation: "page 1", page_start: 1, page_end: 1 }],
    }]);
  });

  it("describes every typed course failure without numeric learner feedback", () => {
    expect(describeApiError(new Error("plain"))).toContain("Try again");
    expect(describeApiError(new ApiError(401, "unauthorized", "expired"))).toContain("session expired");
    expect(describeApiError(new ApiError(404, "missing", "missing"))).toContain("no longer available");
    expect(describeApiError(new ApiError(409, "stale", "Refresh now"))).toBe("Refresh now");
    expect(describeApiError(new ApiError(409, "stale", ""))).toContain("mission changed");
    expect(describeApiError(new ApiError(422, "invalid", "Fix evidence"))).toBe("Fix evidence");
    expect(describeApiError(new ApiError(422, "invalid", ""))).toContain("required evidence");
    expect(describeApiError(new ApiError(429, "busy", "busy"))).toContain("busy");
    expect(describeApiError(new ApiError(503, "down", "Try later"))).toBe("Try later");
    expect(describeApiError(new ApiError(503, "down", ""))).toContain("could not reach");
    expect(new ApiError(500, "down", "down").retryable).toBe(true);
    expect(new ApiError(400, "bad", "bad").retryable).toBe(false);
  });

  it("covers transport fallbacks, aborts, request ids, and visual classifiers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("plain failure", { status: 500 })));
    await expect(api.health()).rejects.toMatchObject({ status: 500, code: "http_500", retryable: true });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: [{ loc: ["body", "answers"], msg: "Field required", type: "missing" }] }), { status: 422, headers: { "content-type": "application/json" } })));
    await expect(api.health()).rejects.toMatchObject({ status: 422, detail: "body.answers: Field required" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: "explicit", detail: "No retry", retryable: false } }), { status: 500, headers: { "content-type": "application/json" } })));
    await expect(api.health()).rejects.toMatchObject({ retryable: false });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: [null, { msg: { reason: "nested" } }, { loc: "body", msg: "Readable" }] }), { status: 422, headers: { "content-type": "application/json" } })));
    await expect(api.health()).rejects.toMatchObject({ detail: expect.stringContaining("Readable") });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: "" }), { status: 503, headers: { "content-type": "application/json" } })));
    await expect(api.health()).rejects.toMatchObject({ detail: "Request failed (503).", retryable: true });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new DOMException("stop", "AbortError")));
    await expect(api.courseOverview()).rejects.toMatchObject({ name: "AbortError" });
    expect(newRequestId()).toBeTruthy();
    vi.stubGlobal("crypto", undefined);
    expect(newRequestId()).toMatch(/^course-/);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("plain success", { status: 200 })));
    await expect(api.health()).resolves.toBe("plain success");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: "payload detail" }), { status: 400, headers: { "content-type": "application/json" } })));
    await expect(api.health()).rejects.toMatchObject({ detail: "payload detail", code: "http_400" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({}), { status: 401, headers: { "content-type": "application/json" } })));
    await expect(api.health()).rejects.toMatchObject({ detail: "Your session expired.", code: "unauthorized" });
    ["Arrays & Hashing", "Two Pointers", "Sliding Window", "1-D DP", "2-D DP", "Greedy", "Graphs", "Advanced Graphs", "Trees", "Tries", "unknown"].forEach((value) => expect(catClass(value)).toBeTypeOf("string"));
    ["Easy", "Medium", "Hard", "unknown"].forEach((value) => expect(diffClass(value)).toBeTypeOf("string"));
    ["DSA", "System Design", "CS Fundamentals", "Behavioral", "unknown"].forEach((value) => expect(trackClass(value)).toBeTypeOf("string"));
  });

  it("handles an absent content type and an empty validation detail array", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(null, { status: 204 })));
    await expect(api.health()).resolves.toBe("");

    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: [] }), {
      status: 422, headers: { "content-type": "application/json" },
    })));
    await expect(api.health()).rejects.toMatchObject({
      status: 422, code: "http_422", detail: "Request failed (422).", retryable: false,
    });

    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
      status: 200, headers: { "content-type": "application/json" },
    })));
    await api.courseReconciliationPreview("IC-00");
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/courses/inference-engineering/reconcile/IC-00?scan=false",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });
});
