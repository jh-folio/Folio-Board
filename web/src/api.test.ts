import { afterEach, describe, expect, it } from "vitest";

import {
  ApiRequestError,
  ApiResponseReadError,
  ApiTransportError,
  getJson,
  isAbortError,
} from "./api";

const REQUEST_ID = "req_12345678-1234-4234-8234-123456789abc";
const RUN_ID = "run_abcdefab-cdef-4abc-8def-abcdefabcdef";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

function response(body: string, status: number, headers: Record<string, string> = {}) {
  return new Response(body, { status, headers });
}

describe("request diagnostic headers", () => {
  it("keeps validated request and run IDs on an HTTP error", async () => {
    globalThis.fetch = (async () => response(
      JSON.stringify({ error: "generation_failed", detail: { code: "generation_failed" } }),
      502,
      { "X-Folio-Request-Id": REQUEST_ID, "X-Folio-Run-Id": RUN_ID },
    )) as typeof fetch;

    await expect(getJson("/api/briefings")).rejects.toMatchObject({
      status: 502,
      code: "generation_failed",
      requestId: REQUEST_ID,
      runId: RUN_ID,
    });
  });

  it("drops absent, malformed, uppercase, and trailing-newline IDs", async () => {
    globalThis.fetch = (async () => response(
      JSON.stringify({ error: "bad" }),
      500,
      {
        "X-Folio-Request-Id": `${REQUEST_ID}x`,
        "X-Folio-Run-Id": "RUN_abcdefab-cdef-4abc-8def-abcdefabcdef",
      },
    )) as typeof fetch;

    await expect(getJson("/api/briefings")).rejects.toMatchObject({ requestId: null, runId: null });
  });

  it("leaves both IDs null when the headers are absent", async () => {
    globalThis.fetch = (async () => response(JSON.stringify({ error: "bad" }), 500)) as typeof fetch;

    await expect(getJson("/api/briefings")).rejects.toMatchObject({ requestId: null, runId: null });
  });

  it("preserves status and validated IDs for a non-JSON HTTP 500", async () => {
    globalThis.fetch = (async () => response("upstream did not return JSON", 500, {
      "X-Folio-Request-Id": REQUEST_ID,
      "X-Folio-Run-Id": RUN_ID,
    })) as typeof fetch;

    await expect(getJson("/api/briefings")).rejects.toMatchObject({
      status: 500,
      code: "request_failed",
      payload: null,
      requestId: REQUEST_ID,
      runId: RUN_ID,
    });
  });
});

describe("response-less request failures", () => {
  it("uses a typed safe error for a fetch rejection without retrying", async () => {
    let sends = 0;
    globalThis.fetch = (async () => {
      sends += 1;
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;

    await expect(getJson("/api/briefings")).rejects.toBeInstanceOf(ApiTransportError);
    expect(sends).toBe(1);
  });

  it("preserves AbortError from the fetch boundary", async () => {
    const abort = new DOMException("Request cancelled", "AbortError");
    globalThis.fetch = (async () => { throw abort; }) as typeof fetch;

    await expect(getJson("/api/briefings")).rejects.toBe(abort);
    expect(isAbortError(abort)).toBe(true);
  });

  it("treats an aborted signal as cancellation even if fetch reports TypeError", async () => {
    const controller = new AbortController();
    controller.abort();
    const transportFailure = new TypeError("Failed to fetch");
    globalThis.fetch = (async () => { throw transportFailure; }) as typeof fetch;

    await expect(getJson("/api/briefings", { signal: controller.signal })).rejects.toBe(transportFailure);
    expect(isAbortError(transportFailure, controller.signal)).toBe(true);
  });

  it("does not call a successful response with an unreadable body a server failure", async () => {
    const unreadableResponse = new Response("", { status: 200 });
    unreadableResponse.json = async () => { throw new TypeError("body stream closed"); };
    globalThis.fetch = (async () => unreadableResponse) as typeof fetch;

    await expect(getJson("/api/briefings")).rejects.toBeInstanceOf(ApiResponseReadError);
  });

  it("keeps known HTTP status and IDs when an error body cannot be read", async () => {
    const unreadableResponse = new Response("", {
      status: 500,
      headers: { "X-Folio-Request-Id": REQUEST_ID, "X-Folio-Run-Id": RUN_ID },
    });
    unreadableResponse.json = async () => { throw new TypeError("body stream closed"); };
    globalThis.fetch = (async () => unreadableResponse) as typeof fetch;

    await expect(getJson("/api/briefings")).rejects.toMatchObject({
      status: 500,
      payload: null,
      requestId: REQUEST_ID,
      runId: RUN_ID,
    });
  });
});

describe("ApiRequestError compatibility", () => {
  it("keeps the old constructor shape and validates additive IDs", () => {
    const error = new ApiRequestError("/api/briefings", 500, "request_failed", null, REQUEST_ID, RUN_ID);
    expect(error.path).toBe("/api/briefings");
    expect(error.status).toBe(500);
    expect(error.code).toBe("request_failed");
    expect(error.payload).toBeNull();
    expect(error.requestId).toBe(REQUEST_ID);
    expect(error.runId).toBe(RUN_ID);
    expect(new ApiRequestError("/api/briefings", 500, "request_failed", null, `${REQUEST_ID}\r`, RUN_ID).requestId).toBeNull();
  });
});
