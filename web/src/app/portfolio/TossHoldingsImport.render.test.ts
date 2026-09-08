import { DOMImplementation } from "@xmldom/xmldom";
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TossHoldingsImport } from "./TossHoldingsImport";
import { PortfolioRoute } from "../PortfolioRoute";

type MiniElement = HTMLElement & Record<string, unknown>;

const accountPayload = {
  accounts: [{ label: "•••• 9012", accountType: "BROKERAGE", selectable: true, reason: "", selectionId: "selection" }],
  provider: "toss_open_api", openApiVersion: "1.2.14",
};
const previewPayload = {
  previewId: "preview", expectedRevision: 0, canConfirm: true, status: "ready", provider: "toss_open_api", openApiVersion: "1.2.14",
  buckets: { additions: ["US:USD:AAPL"], updates: [], preservedManual: [], unchanged: [], conflicts: [], unsupported: [] },
  details: [],
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function installMiniDom() {
  const document = new DOMImplementation().createDocument("http://www.w3.org/1999/xhtml", "html", null) as Document & Record<string, unknown>;
  const listeners = new WeakMap<object, Map<string, Set<EventListener>>>();
  const decorate = <T extends MiniElement>(node: T): T => {
    Object.defineProperty(node, "style", { configurable: true, value: {} });
    node.addEventListener = ((type: string, listener: EventListener) => {
      const own = listeners.get(node) || new Map<string, Set<EventListener>>();
      const group = own.get(type) || new Set<EventListener>();
      group.add(listener); own.set(type, group); listeners.set(node, own);
    }) as typeof node.addEventListener;
    node.removeEventListener = (() => {}) as typeof node.removeEventListener;
    node.focus = (() => {}) as typeof node.focus;
    return node;
  };
  const createElement = document.createElement.bind(document);
  const createElementNS = document.createElementNS.bind(document);
  document.createElement = ((name: string) => decorate(createElement(name) as unknown as MiniElement)) as typeof document.createElement;
  document.createElementNS = ((namespace: string | null, name: string) => decorate(createElementNS(namespace, name) as unknown as MiniElement)) as typeof document.createElementNS;
  const container = decorate(document.createElement("div") as unknown as MiniElement);
  decorate(document as unknown as MiniElement);
  document.documentElement.appendChild(container);
  const elementCtor = container.constructor as typeof Element;
  const win: Record<string, unknown> = {
    document, window: null, Node: Object.getPrototypeOf(container).constructor,
    Element: elementCtor, HTMLElement: elementCtor, HTMLIFrameElement: class {},
    addEventListener() {}, removeEventListener() {}, setTimeout, clearTimeout,
    getSelection: () => null,
  };
  win.window = win;
  Object.defineProperty(document, "defaultView", { configurable: true, value: win });
  Object.defineProperty(document, "activeElement", { configurable: true, get: () => null });
  Object.assign(globalThis, { window: win, document, Node: win.Node, Element: elementCtor, HTMLElement: elementCtor, HTMLIFrameElement: win.HTMLIFrameElement, IS_REACT_ACT_ENVIRONMENT: true });
  return { container, cleanup: () => { delete (globalThis as Record<string, unknown>).window; delete (globalThis as Record<string, unknown>).document; } };
}

function all(root: Node, predicate: (node: MiniElement) => boolean): MiniElement[] {
  const found: MiniElement[] = [];
  const visit = (node: Node) => {
    if (node.nodeType === 1 && predicate(node as MiniElement)) found.push(node as MiniElement);
    for (const child of node.childNodes ? Array.from(node.childNodes) : []) visit(child);
  };
  visit(root);
  return found;
}

function button(root: Node, copy: string): MiniElement {
  const found = all(root, (node) => node.nodeName.toLowerCase() === "button" && node.textContent?.includes(copy));
  if (!found[0]) throw new Error(`button not found: ${copy}`);
  return found[0];
}

async function click(node: MiniElement) {
  const propKey = Object.keys(node).find((key) => key.startsWith("__reactProps$"));
  const props = propKey ? node[propKey] as { onClick?: (event: { preventDefault(): void }) => void } : undefined;
  await act(async () => { props?.onClick?.({ preventDefault() {} }); });
}

async function render(root: Root, dirty: boolean) {
  await act(async () => {
    root.render(createElement(TossHoldingsImport, { portfolio: { revision: 0, positions: [] }, dirty, onCommitted: () => {} }));
  });
}

async function renderPortfolioRoute(root: Root) {
  await act(async () => { root.render(createElement(PortfolioRoute)); });
}

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("TossHoldingsImport rendered async safety", () => {
  const originalFetch = globalThis.fetch;
  afterEach(() => { globalThis.fetch = originalFetch; });

  it("does not request for a dirty draft and ignores accounts/preview that resolve after it becomes dirty", async () => {
    const accounts = deferred<Response>();
    const preview = deferred<Response>();
    const fetchMock = vi.fn((path: RequestInfo | URL) => String(path).endsWith("/accounts") ? accounts.promise : preview.promise);
    globalThis.fetch = fetchMock as typeof fetch;
    const dom = installMiniDom(); const root = createRoot(dom.container);
    try {
      await render(root, true);
      await click(button(dom.container, "Toss 계좌 불러오기"));
      expect(fetchMock).not.toHaveBeenCalled();
      expect(dom.container.textContent).toContain("저장되지 않았습니다");

      await render(root, false);
      await click(button(dom.container, "Toss 계좌 불러오기"));
      expect(dom.container.textContent).toContain("계좌를 확인하고 있습니다");
      expect(all(dom.container, (node) => node.getAttribute("role") === "status" && node.textContent?.includes("계좌를 확인"))).toHaveLength(1);
      await render(root, true);
      accounts.resolve(response(accountPayload));
      await act(async () => { await Promise.resolve(); });
      expect(dom.container.textContent).not.toContain("•••• 9012");

      await render(root, false);
      // A fresh accounts response is required before selecting/previewing.
      const nextAccounts = response(accountPayload);
      fetchMock.mockImplementationOnce(() => Promise.resolve(nextAccounts));
      await click(button(dom.container, "Toss 계좌 불러오기"));
      await click(button(dom.container, "•••• 9012"));
      await click(button(dom.container, "미리보기"));
      await render(root, true);
      preview.resolve(response(previewPayload));
      await act(async () => { await Promise.resolve(); });
      expect(dom.container.textContent).not.toContain("변경 미리보기");
    } finally {
      await act(async () => root.unmount()); dom.cleanup();
    }
  });

  it("clears a rendered preview after a terminal confirm error and keeps bounded copy/status/list semantics", async () => {
    const fetchMock = vi.fn((path: RequestInfo | URL) => {
      const value = String(path);
      if (value.endsWith("/accounts")) return Promise.resolve(response(accountPayload));
      if (value.endsWith("/preview")) return Promise.resolve(response(previewPayload));
      return Promise.resolve(response({ detail: { code: "preview_stale" } }, 409));
    });
    globalThis.fetch = fetchMock as typeof fetch;
    const dom = installMiniDom(); const root = createRoot(dom.container);
    try {
      await render(root, false);
      await click(button(dom.container, "Toss 계좌 불러오기"));
      await click(button(dom.container, "•••• 9012"));
      expect(all(dom.container, (node) => node.getAttribute("role") === "listitem")).toHaveLength(1);
      await click(button(dom.container, "미리보기"));
      await click(button(dom.container, "가져오기 확정"));
      expect(dom.container.textContent).not.toContain("변경 미리보기");
      expect(all(dom.container, (node) => node.nodeName.toLowerCase() === "button" && node.textContent?.includes("가져오기 확정"))).toHaveLength(0);
      expect(dom.container.textContent).toContain("새 미리보기");

      fetchMock.mockImplementationOnce(() => Promise.resolve(response({ detail: { code: "provider_contract_invalid" } }, 503)));
      await click(button(dom.container, "Toss 계좌 불러오기"));
      expect(dom.container.textContent).toContain("응답 형식");
      expect(dom.container.textContent).not.toContain("provider_contract_invalid");
    } finally {
      await act(async () => root.unmount()); dom.cleanup();
    }
  });

  it("renders every repeated conflict and unsupported issue without duplicate React keys", async () => {
    const duplicatePreview = {
      ...previewPayload,
      canConfirm: false,
      buckets: {
        additions: [], updates: [], preservedManual: [], unchanged: [],
        conflicts: [
          { positionKey: "US:USD:AAPL", issueCodes: ["duplicate_existing_ticker"] },
          { positionKey: "US:USD:AAPL", issueCodes: ["duplicate_existing_ticker"] },
          { positionKey: "KR:KRW:AAPL", issueCodes: ["duplicate_existing_ticker"] },
        ],
        unsupported: [
          { positionKey: null, issueCodes: ["missing_required_field"] },
          { positionKey: null, issueCodes: ["missing_required_field"] },
        ],
      },
    };
    const fetchMock = vi.fn((path: RequestInfo | URL) => {
      const value = String(path);
      if (value.endsWith("/accounts")) return Promise.resolve(response(accountPayload));
      return Promise.resolve(response(duplicatePreview));
    });
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    globalThis.fetch = fetchMock as typeof fetch;
    const dom = installMiniDom(); const root = createRoot(dom.container);
    try {
      await render(root, false);
      await click(button(dom.container, "Toss 계좌 불러오기"));
      await click(button(dom.container, "•••• 9012"));
      await click(button(dom.container, "미리보기"));
      const issueRows = all(dom.container, (node) => node.nodeName.toLowerCase() === "li" && (node.textContent?.includes("충돌") || node.textContent?.includes("지원하지 않음")));
      expect(issueRows).toHaveLength(5);
      expect(consoleError.mock.calls.filter((args) => args.some((value) => String(value).includes("same key")))).toHaveLength(0);
    } finally {
      consoleError.mockRestore();
      await act(async () => root.unmount()); dom.cleanup();
    }
  });

  it("blocks edits and writes before authority is ready, then opens an explicit saveable draft", async () => {
    const authority = deferred<Response>();
    const saved = { revision: 8, positions: [{ ticker: "", quantity: "", averagePrice: "" }], cash: [] };
    const fetchMock = vi.fn((path: RequestInfo | URL, init?: RequestInit) => {
      const value = String(path);
      if (value === "/api/portfolio" && !init?.method) return authority.promise;
      if (value === "/api/portfolio" && init?.method === "POST") return Promise.resolve(response(saved));
      return Promise.resolve(response({ detail: { code: "unavailable" } }, 503));
    });
    globalThis.fetch = fetchMock as typeof fetch;
    const dom = installMiniDom(); const root = createRoot(dom.container);
    try {
      await renderPortfolioRoute(root);
      expect(all(dom.container, (node) => node.nodeName.toLowerCase() === "button" && node.textContent?.includes("보유 편집"))).toHaveLength(0);
      expect(all(dom.container, (node) => node.nodeName.toLowerCase() === "button" && node.textContent?.includes("Toss 계좌 불러오기"))).toHaveLength(0);
      expect(dom.container.textContent).toContain("저장된 보유 내역을 불러오는 중입니다");
      expect(fetchMock.mock.calls.some(([path, init]) => String(path) === "/api/portfolio" && (init as RequestInit | undefined)?.method === "POST")).toBe(false);
      authority.resolve(response({ revision: 7, positions: [], cash: [] }));
      await act(async () => { await Promise.resolve(); });
      await click(button(dom.container, "보유 편집"));
      await click(button(dom.container, "종목 추가"));
      const tickerInput = all(dom.container, (node) => node.nodeName.toLowerCase() === "input" && node.getAttribute("aria-label") === "1번 종목")[0] as unknown as { value?: string; getAttribute(name: string): string | null };
      expect(tickerInput.value ?? tickerInput.getAttribute("value")).toBe("");
      const saveButton = button(dom.container, "Portfolio 저장");
      await click(saveButton);
      expect(fetchMock.mock.calls.some(([path, init]) => String(path) === "/api/portfolio" && (init as RequestInit | undefined)?.method === "POST")).toBe(true);
      expect(dom.container.textContent).toContain("보유 변경을 저장했습니다.");
    } finally {
      await act(async () => root.unmount()); dom.cleanup();
    }
  });
});
