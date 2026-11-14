import { afterEach, describe, expect, it, vi } from "vitest";
import { api, request, sseParser, streamRun } from "./api";
import type { RunEvent } from "./types";
afterEach(() => vi.unstubAllGlobals());
describe("audit event transport", () => {
  it("does not mistake current runtime tool errors without a recoverable flag for terminal failure", async () => {
    const body = new ReadableStream({ start(controller) {
      controller.enqueue(new TextEncoder().encode('data: {"type":"error","message":"Tool unavailable","payload":{}}\n\n'));
      controller.enqueue(new TextEncoder().encode('data: {"type":"done","payload":{}}\n\n'));
    } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
    const events: RunEvent[] = [];
    await streamRun("run", (event) => events.push(event), new AbortController().signal);
    expect(events.map((event) => event.type)).toEqual(["error", "done"]);
  });
  it("skips replayed questions when following a resumed run", async () => {
    const history: RunEvent[] = [
      { type: "question", message: "Old question", payload: {} },
      { type: "stage_done", message: "Answer applied", payload: {} },
      { type: "question", message: "Next question", payload: {} },
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(history.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(""))));
    const events: RunEvent[] = [];
    await streamRun("run", (event) => events.push(event), new AbortController().signal, { afterEvents: 1 });
    expect(events.map((event) => event.message)).toEqual(["Answer applied", "Next question"]);
  });
  it("drains a completed replay through earlier questions and done events to the re-plan's done", async () => {
    const history = ["question", "done", "stage_started", "done"].map((type, i) => ({ type, message: String(i), payload: {} }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(history.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(""))));
    const events: RunEvent[] = [];
    await streamRun("run", (event) => events.push(event), new AbortController().signal, { followToEnd: true });
    expect(events.map((event) => event.message)).toEqual(["0", "1", "2", "3"]);
  });
  it("ignores unknown additive event types while preserving subsequent known events", () => {
    const events: RunEvent[] = [];
    const parse = sseParser((e) => events.push(e));
    parse(
      'data: {"type":"future_progress","payload":{}}\n\ndata: {"type":"done","payload":{}}\n\n',
    );
    expect(events.map((e) => e.type)).toEqual(["done"]);
  });
  it("keeps following the stream after a recoverable tool error", async () => {
    const body = new ReadableStream({
      start(c) {
        c.enqueue(
          new TextEncoder().encode(
            'data: {"type":"error","message":"Temporary imagery failure","payload":{"recoverable":true}}\n\n',
          ),
        );
        c.enqueue(
          new TextEncoder().encode('data: {"type":"done","payload":{}}\n\n'),
        );
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
    const events: RunEvent[] = [];
    await streamRun("1", (e) => events.push(e), new AbortController().signal);
    expect(events.map((e) => e.type)).toEqual(["error", "done"]);
  });
  it("handles split CRLF boundaries, comments, named events, and multiline JSON", () => {
    const events: RunEvent[] = [];
    const parse = sseParser((e) => events.push(e));
    parse(
      ': keepalive\r\n\r\nevent: question\r\ndata: {"message": "Insulation?",\r\n',
    );
    parse('data: "payload": {"id":"q1"}}\r');
    parse("\n\r");
    parse("\n");
    expect(events).toEqual([
      { type: "question", message: "Insulation?", payload: { id: "q1" } },
    ]);
  });
  it("accepts several events per chunk and flushes the final event", () => {
    const events: RunEvent[] = [];
    const parse = sseParser((e) => events.push(e));
    parse(
      'data: {"type":"stage_started"}\n\ndata: {"type":"stage_done"}\n\ndata: {"type":"done"}',
      true,
    );
    expect(events.map((e) => e.type)).toEqual([
      "stage_started",
      "stage_done",
      "done",
    ]);
  });
  it("preserves UTF-8 across streamed byte boundaries and cancels after a question", async () => {
    const bytes = new TextEncoder().encode(
      'data: {"type":"question","message":"CO₂?","payload":{}}\n\n',
    );
    let cancelled = false;
    const body = new ReadableStream({
      start(c) {
        const offset = bytes.indexOf(0xe2);
        c.enqueue(bytes.slice(0, offset + 1));
        c.enqueue(bytes.slice(offset + 1));
      },
      cancel() {
        cancelled = true;
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
    const events: RunEvent[] = [];
    await streamRun(
      "run/1",
      (e) => events.push(e),
      new AbortController().signal,
    );
    expect(events[0].message).toBe("CO₂?");
    expect(cancelled).toBe(true);
  });
  it("surfaces malformed event data rather than silently losing audit events", () => {
    expect(() => sseParser(() => {})("data: {invalid}\n\n")).toThrow();
  });
  it("stops a non-terminating stream immediately on completion", async () => {
    const body = new ReadableStream({
      start(c) {
        c.enqueue(
          new TextEncoder().encode(
            'data: {"type":"done","message":"Ready","payload":{}}\n\n',
          ),
        );
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body)));
    const events: RunEvent[] = [];
    await streamRun("1", (e) => events.push(e), new AbortController().signal);
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("done");
  });
});
describe("backend contract", () => {
  it("forwards computed-analysis mode together with the requested constraints", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response('{"run_id":"computed"}'));
    vi.stubGlobal("fetch", fetch);
    const request = {
      sid: "ZSPaQbkGcJJ",
      mode: "analysis" as const,
      budget_usd: 10000000,
      role: "landlord" as const,
      desks_requested: 12,
      bills: { electricity_kwh: Array(12).fill(100), first_month: "2025-01" },
    };
    await expect(api.start(request)).resolves.toEqual({ run_id: "computed" });
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("/api/runs");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual(request);
  });
  it("shows structured backend errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "NO_COVERAGE",
              message: "Property is outside coverage",
            },
          }),
          { status: 422 },
        ),
      ),
    );
    await expect(request("/runs")).rejects.toThrow(
      "Property is outside coverage",
    );
  });
  it("handles non-JSON proxy errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response("backend unavailable", { status: 502 }),
        ),
    );
    await expect(request("/health")).rejects.toThrow("502");
  });
  it("sends answers without truthiness conversion, preserving false, zero, and unknown", async () => {
    const fetch = vi
      .fn()
      .mockImplementation(() => Promise.resolve(new Response('{"ok":true}')));
    vi.stubGlobal("fetch", fetch);
    for (const value of [false, 0, null]) {
      await api.answer("a/b", "q", value);
      expect(fetch).toHaveBeenLastCalledWith(
        "/api/runs/a%2Fb/answers",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ question_id: "q", value }),
        }),
      );
    }
  });
});
