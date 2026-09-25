import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiRequestError,
  deleteJson,
  diagnosticListQuery,
  getJson,
  isAbortError,
  parseDiagnosticList,
  parseWorkLogList,
  postJson,
  type AgentProposalRecord,
  type DiagnosticListFilter,
  type DiagnosticListItem,
  type WorkLogClearPreview,
  type WorkLogClearResponse,
  type WorkLogEntry,
  type WorkLogFilter,
  type WorkLogList,
} from "../api";
import { boundedProposalDiff, boundedProposalSummary, PROPOSAL_LIFECYCLE_EVENT } from "./agentProposalLifecycle";
import { DiagnosticDetail } from "./DiagnosticDetail";
import { featureLabel, outcomeLabel, outcomeTone, reasonLabel } from "./diagnosticCopy";
import { captureReportError, isResponseLessError, ReportErrorDiagnostic, type CapturedReportError } from "./reportErrorDiagnostic";
import { workLogItemCopy, workLogLatestSummary } from "./workLogCopy";

type DiagPeriod = "all" | "today" | "7d" | "30d";

type DiagnosticRowOutcome = {
  readonly label: string;
  readonly tone: ReturnType<typeof outcomeTone>;
};

/** 프리셋 기간을 UTC `from` 경계로 바꾼다. `to`는 항상 비운다 — 미래 실행은 없으므로
 *  "지금까지"를 상한 없이 표현하는 쪽이 자정 경계 근처의 방금 실행을 놓치지 않는다. */
function periodFrom(period: DiagPeriod): string | undefined {
  if (period === "all") return undefined;
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  if (period === "7d") start.setDate(start.getDate() - 6);
  if (period === "30d") start.setDate(start.getDate() - 29);
  return start.toISOString();
}

function diagnosticRowOutcome(item: DiagnosticListItem): DiagnosticRowOutcome {
  if (item.outcome === null) {
    return {
      label: `관측: ${outcomeLabel(item.observedOutcome)} · 결과 미확정`,
      tone: "warning",
    };
  }
  return { label: outcomeLabel(item.outcome), tone: outcomeTone(item.outcome) };
}

type AgentWorkLogProps = {
  readonly surface: "home" | "deep-research";
  readonly pageSize?: number;
  readonly defaultFilter?: WorkLogFilter;
  readonly refreshKey?: number;
  readonly collapsible?: boolean;
};

type DialogKind = "clear" | null;

function errorCode(error: unknown) {
  if (error instanceof ApiRequestError) return error.code || `http_${error.status}`;
  if (error instanceof Error && /^[a-z0-9_]+$/.test(error.message)) return error.message;
  return "request_failed";
}

function displayTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "시간 확인 불가" : new Intl.DateTimeFormat("ko-KR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

export function AgentWorkLog({ surface, pageSize = 20, defaultFilter = "all", refreshKey = 0, collapsible = false }: AgentWorkLogProps) {
  const [filter, setFilter] = useState<WorkLogFilter>(defaultFilter);
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<WorkLogList | null>(null);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [listErrorDiagnostic, setListErrorDiagnostic] = useState<CapturedReportError | null>(null);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [clearPreview, setClearPreview] = useState<WorkLogClearPreview | null>(null);
  const [clearBusy, setClearBusy] = useState(false);
  const [clearError, setClearError] = useState("");
  const [clearErrorDiagnostic, setClearErrorDiagnostic] = useState<CapturedReportError | null>(null);
  const [clearErrorResponseLess, setClearErrorResponseLess] = useState(false);
  const [clearSuccess, setClearSuccess] = useState("");
  const [proposal, setProposal] = useState<AgentProposalRecord | null>(null);
  const [proposalLoading, setProposalLoading] = useState("");
  const [proposalError, setProposalError] = useState("");
  const [proposalErrorDiagnostic, setProposalErrorDiagnostic] = useState<CapturedReportError | null>(null);
  const [detailRefreshKey, setDetailRefreshKey] = useState(0);
  // 0.6 D3 다음 단계 — 공통 진단 목록 필터. 하나라도 기본값을 벗어나면 이 목록으로
  // 화면이 전환된다(진단 목록은 Work Log 26필드와 다른 계약이라 같은 화면에 겹쳐 그리지 않는다).
  const [diagFailedOnly, setDiagFailedOnly] = useState(false);
  const [diagFallbackOnly, setDiagFallbackOnly] = useState(false);
  const [diagPeriod, setDiagPeriod] = useState<DiagPeriod>("all");
  const [diagItems, setDiagItems] = useState<readonly DiagnosticListItem[]>([]);
  const [diagSnapshotAt, setDiagSnapshotAt] = useState("");
  const [diagCursor, setDiagCursor] = useState<string | null>(null);
  const [diagTruncated, setDiagTruncated] = useState(false);
  const [diagScanComplete, setDiagScanComplete] = useState(true);
  const [diagListErrors, setDiagListErrors] = useState<readonly { readonly code: string }[]>([]);
  const [diagLoading, setDiagLoading] = useState(false);
  const [diagLoadingMore, setDiagLoadingMore] = useState(false);
  const [diagError, setDiagError] = useState("");
  const [diagErrorDiagnostic, setDiagErrorDiagnostic] = useState<CapturedReportError | null>(null);
  const [diagMode, setDiagMode] = useState(false);
  const [workLogReturnId, setWorkLogReturnId] = useState<string | null>(null);
  const [workLogReturnMessage, setWorkLogReturnMessage] = useState("");
  const requestSequence = useRef(0);
  const activeController = useRef<AbortController | null>(null);
  const diagRequestSequence = useRef(0);
  const diagController = useRef<AbortController | null>(null);
  const diagBusy = useRef(false);
  const diagFromAt = useRef<string | undefined>(undefined);
  const clearInFlight = useRef(false);
  const clearRequestSequence = useRef(0);
  const clearController = useRef<AbortController | null>(null);
  const proposalInFlight = useRef(false);
  const proposalRequestSequence = useRef(0);
  const proposalController = useRef<AbortController | null>(null);
  const aliveRef = useRef(true);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const openerRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
      clearRequestSequence.current += 1;
      clearController.current?.abort();
      proposalRequestSequence.current += 1;
      proposalController.current?.abort();
    };
  }, []);

  const cancelWorkLogRequest = useCallback(() => {
    requestSequence.current += 1;
    activeController.current?.abort();
    activeController.current = null;
  }, []);

  const invalidateDiagnostics = useCallback((clearItems = true) => {
    diagRequestSequence.current += 1;
    diagController.current?.abort();
    diagController.current = null;
    diagBusy.current = false;
    diagFromAt.current = undefined;
    setDiagCursor(null);
    if (clearItems) {
      setDiagItems([]);
      setDiagSnapshotAt("");
      setDiagTruncated(false);
      setDiagScanComplete(false);
      setDiagListErrors([]);
    }
    setDiagLoading(false);
    setDiagLoadingMore(false);
    setDiagError("");
    setDiagErrorDiagnostic(null);
  }, []);

  const load = useCallback(async () => {
    const sequence = ++requestSequence.current;
    activeController.current?.abort();
    const controller = new AbortController();
    activeController.current = controller;
    setLoading(true);
    setListError("");
    setListErrorDiagnostic(null);
    try {
      const raw = await getJson<unknown>(`/api/agent/work-log?kind=${filter}&limit=${pageSize}&offset=${offset}`, { signal: controller.signal });
      const next = parseWorkLogList(raw);
      if (sequence !== requestSequence.current) return;
      setData(next);
    } catch (error) {
      if (isAbortError(error, controller.signal) || sequence !== requestSequence.current) return;
      setListError(errorCode(error));
      setListErrorDiagnostic(captureReportError(error, sequence));
    } finally {
      if (sequence === requestSequence.current) {
        activeController.current = null;
        setLoading(false);
      }
    }
  }, [filter, offset, pageSize]);

  useEffect(() => {
    setDetailRefreshKey((key) => key + 1);
    if (diagMode) return () => cancelWorkLogRequest();
    void load();
    return () => cancelWorkLogRequest();
  }, [cancelWorkLogRequest, diagMode, load, refreshKey]);

  const loadDiagnostics = useCallback(async (reset: boolean, isCursorRetry = false, preserveExisting = false) => {
    if (!reset && (diagBusy.current || !diagCursor)) return;
    if (reset) diagController.current?.abort();
    const sequence = ++diagRequestSequence.current;
    const from = reset ? periodFrom(diagPeriod) : diagFromAt.current;
    if (reset) {
      diagFromAt.current = from;
      setDiagCursor(null);
      if (!preserveExisting) {
        setDiagItems([]);
        setDiagSnapshotAt("");
        setDiagTruncated(false);
        setDiagScanComplete(false);
        setDiagListErrors([]);
      }
      setDiagError("");
      setDiagErrorDiagnostic(null);
      setDiagLoading(true);
      setDiagLoadingMore(false);
    } else {
      setDiagLoadingMore(true);
      setDiagError("");
      setDiagErrorDiagnostic(null);
    }
    diagBusy.current = true;
    const controller = new AbortController();
    diagController.current = controller;
    const filter: DiagnosticListFilter = {
      outcome: diagFailedOnly ? "failed" : "all",
      fallback: diagFallbackOnly ? "observed" : "all",
      from,
      limit: pageSize,
      cursor: reset ? undefined : diagCursor || undefined,
    };
    try {
      const raw = await getJson<unknown>(diagnosticListQuery(filter), { signal: controller.signal });
      const next = parseDiagnosticList(raw);
      if (sequence !== diagRequestSequence.current || controller.signal.aborted) return;
      if (!reset && diagSnapshotAt && next.snapshotAt !== diagSnapshotAt) {
        setDiagItems([]);
        setDiagSnapshotAt("");
        setDiagCursor(null);
        setDiagTruncated(false);
        setDiagScanComplete(false);
        setDiagError("diagnostic_snapshot_changed");
        setDiagErrorDiagnostic(null);
        return;
      }
      setDiagItems((previous) => (reset ? next.items : [...previous, ...next.items]));
      setDiagSnapshotAt(next.snapshotAt);
      setDiagCursor(next.nextCursor);
      setDiagTruncated(next.truncated);
      setDiagScanComplete(next.scan.complete);
      setDiagListErrors(next.errors);
    } catch (error) {
      if (isAbortError(error, controller.signal) || sequence !== diagRequestSequence.current) return;
      // 409(cursor 만료/변경/불일치)는 "현재 목록의 안전한 새 조회"로 회복한다(계약 §5) —
      // 사용자에게 오류를 보여주는 대신 처음부터 한 번만 다시 불러온다.
      if (!reset && !isCursorRetry && error instanceof ApiRequestError && error.status === 409) {
        invalidateDiagnostics(false);
        void loadDiagnostics(true, true, true);
        return;
      }
      setDiagError(errorCode(error));
      setDiagErrorDiagnostic(captureReportError(error, sequence));
    } finally {
      if (sequence === diagRequestSequence.current) {
        diagBusy.current = false;
        diagController.current = null;
        setDiagLoading(false);
        setDiagLoadingMore(false);
      }
    }
  }, [diagFailedOnly, diagFallbackOnly, diagPeriod, diagCursor, diagSnapshotAt, invalidateDiagnostics, pageSize]);

  const diagnosticQueryKey = `${diagMode}|${diagFailedOnly}|${diagFallbackOnly}|${diagPeriod}`;
  const previousDiagnosticQueryKey = useRef(diagnosticQueryKey);
  const previousDiagnosticRefreshKey = useRef(refreshKey);
  useEffect(() => {
    const queryChanged = previousDiagnosticQueryKey.current !== diagnosticQueryKey;
    const refreshChanged = previousDiagnosticRefreshKey.current !== refreshKey;
    previousDiagnosticQueryKey.current = diagnosticQueryKey;
    previousDiagnosticRefreshKey.current = refreshKey;
    if (!diagMode) return () => invalidateDiagnostics(false);
    // A filter/mode change creates a new identity and must remove old rows before
    // the request. A same-query refresh keeps mounted rows so open details can
    // refresh in place and stale rows are replaced only after the new snapshot.
    const preserveExisting = !queryChanged && refreshChanged;
    invalidateDiagnostics(!preserveExisting);
    void loadDiagnostics(true, false, preserveExisting);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loadDiagnostics already depends on every filter value below
    return () => invalidateDiagnostics(false);
  }, [diagnosticQueryKey, diagMode, invalidateDiagnostics, refreshKey]);

  const refreshLog = useCallback(() => {
    setDetailRefreshKey((key) => key + 1);
    if (diagMode) {
      invalidateDiagnostics(false);
      return loadDiagnostics(true, false, true);
    }
    return load();
  }, [diagMode, invalidateDiagnostics, load, loadDiagnostics]);

  useEffect(() => {
    const handleProposalLifecycle = () => {
      setProposal(null);
      if (diagMode) {
        invalidateDiagnostics(false);
        void loadDiagnostics(true, false, true);
      } else {
        void load();
      }
    };
    window.addEventListener(PROPOSAL_LIFECYCLE_EVENT, handleProposalLifecycle);
    return () => window.removeEventListener(PROPOSAL_LIFECYCLE_EVENT, handleProposalLifecycle);
  }, [diagMode, invalidateDiagnostics, load, loadDiagnostics]);

  useEffect(() => {
    if (!dialog) return;
    dialogRef.current?.querySelector<HTMLElement>("button:not([disabled]), input:not([disabled])")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeDialog();
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled])"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [dialog]);

  function closeDialog() {
    setDialog(null);
    setClearPreview(null);
    setClearError("");
    setClearErrorDiagnostic(null);
    setClearErrorResponseLess(false);
    window.setTimeout(() => openerRef.current?.focus(), 0);
  }

  function changeFilter(next: WorkLogFilter) {
    cancelWorkLogRequest();
    setFilter(next);
    setOffset(0);
    setData(null);
    setLoading(true);
    setWorkLogReturnId(null);
    setWorkLogReturnMessage("");
    setProposal(null);
    setProposalError("");
    setProposalErrorDiagnostic(null);
  }

  function enterDiagnostics() {
    cancelWorkLogRequest();
    invalidateDiagnostics();
    setData(null);
    setLoading(false);
    setDiagMode(true);
  }

  function leaveDiagnostics() {
    invalidateDiagnostics();
    setDiagMode(false);
    setDiagFailedOnly(false);
    setDiagFallbackOnly(false);
    setDiagPeriod("all");
    setData(null);
    setLoading(true);
  }

  function toggleDiagnosticFilter(kind: "failed" | "fallback") {
    cancelWorkLogRequest();
    invalidateDiagnostics();
    setDiagMode(true);
    if (kind === "failed") setDiagFailedOnly((value) => !value);
    else setDiagFallbackOnly((value) => !value);
  }

  function changeDiagnosticPeriod(next: DiagPeriod) {
    cancelWorkLogRequest();
    invalidateDiagnostics();
    setDiagMode(true);
    setDiagPeriod(next);
  }

  function returnToWorkLog(workLogId: string) {
    invalidateDiagnostics();
    cancelWorkLogRequest();
    setDiagMode(false);
    setDiagFailedOnly(false);
    setDiagFallbackOnly(false);
    setDiagPeriod("all");
    setFilter("all");
    setOffset(0);
    setData(null);
    setLoading(true);
    setWorkLogReturnId(workLogId);
    setWorkLogReturnMessage("");
  }

  async function previewClear(button: HTMLButtonElement) {
    if (clearInFlight.current) return;
    clearInFlight.current = true;
    openerRef.current = button;
    clearController.current?.abort();
    const sequence = ++clearRequestSequence.current;
    const controller = new AbortController();
    clearController.current = controller;
    setClearBusy(true);
    setClearError("");
    setClearErrorDiagnostic(null);
    setClearErrorResponseLess(false);
    setClearSuccess("");
    try {
      const preview = await postJson<WorkLogClearPreview>("/api/agent/work-log/clear-preview", { scope: filter }, { signal: controller.signal });
      if (!aliveRef.current || controller.signal.aborted || sequence !== clearRequestSequence.current) return;
      setClearPreview(preview);
      setDialog("clear");
    } catch (error) {
      if (!aliveRef.current || isAbortError(error, controller.signal) || sequence !== clearRequestSequence.current) return;
      setClearError(errorCode(error));
      setClearErrorDiagnostic(captureReportError(error, sequence));
      setClearErrorResponseLess(isResponseLessError(error));
    } finally {
      if (sequence === clearRequestSequence.current) {
        clearController.current = null;
        clearInFlight.current = false;
        if (aliveRef.current) setClearBusy(false);
      }
    }
  }

  async function confirmClear() {
    if (!clearPreview || clearInFlight.current) return;
    clearInFlight.current = true;
    clearController.current?.abort();
    const sequence = ++clearRequestSequence.current;
    const controller = new AbortController();
    clearController.current = controller;
    setClearBusy(true);
    setClearError("");
    setClearErrorDiagnostic(null);
    setClearErrorResponseLess(false);
    try {
      const result = await deleteJson<WorkLogClearResponse>("/api/agent/work-log", { scope: clearPreview.scope, previewToken: clearPreview.previewToken }, { signal: controller.signal });
      if (!aliveRef.current || controller.signal.aborted || sequence !== clearRequestSequence.current) return;
      setClearSuccess(`${result.hiddenCount}건을 목록에서 숨겼습니다.`);
      closeDialog();
      setOffset(0);
      await load();
    } catch (error) {
      if (!aliveRef.current || isAbortError(error, controller.signal) || sequence !== clearRequestSequence.current) return;
      setClearPreview(null);
      setClearError(errorCode(error));
      setClearErrorDiagnostic(captureReportError(error, sequence));
      setClearErrorResponseLess(isResponseLessError(error));
    } finally {
      if (sequence === clearRequestSequence.current) {
        clearController.current = null;
        clearInFlight.current = false;
        if (aliveRef.current) setClearBusy(false);
      }
    }
  }

  async function openProposal(entry: WorkLogEntry) {
    if (!entry.proposalId || proposalInFlight.current) return;
    proposalInFlight.current = true;
    proposalController.current?.abort();
    const sequence = ++proposalRequestSequence.current;
    const controller = new AbortController();
    proposalController.current = controller;
    setProposalLoading(entry.proposalId);
    setProposalError("");
    setProposalErrorDiagnostic(null);
    setProposal(null);
    try {
      const record = await getJson<AgentProposalRecord>(`/api/agent/proposals/${encodeURIComponent(entry.proposalId)}`, { signal: controller.signal });
      if (!aliveRef.current || controller.signal.aborted || sequence !== proposalRequestSequence.current) return;
      if (record.id !== entry.proposalId) throw new Error("proposal_identity_mismatch");
      if (record.status !== "pending" && record.status !== "applying") {
        throw new Error("proposal_not_active");
      }
      setProposal(record);
    } catch (error) {
      if (!aliveRef.current || isAbortError(error, controller.signal) || sequence !== proposalRequestSequence.current) return;
      setProposalError(errorCode(error));
      setProposalErrorDiagnostic(captureReportError(error, sequence));
      await load();
    } finally {
      if (sequence === proposalRequestSequence.current) {
        proposalController.current = null;
        proposalInFlight.current = false;
        if (aliveRef.current) setProposalLoading("");
      }
    }
  }

  useEffect(() => {
    if (!workLogReturnId || loading || !data) return;
    const target = Array.from(document.querySelectorAll<HTMLElement>("[data-work-log-id]"))
      .find((element) => element.dataset.workLogId === workLogReturnId);
    if (target) {
      target.focus({ preventScroll: true });
      target.scrollIntoView({ block: "center" });
      setWorkLogReturnId(null);
      setWorkLogReturnMessage("원래 작업 기록 항목으로 돌아왔습니다. 여기서 실행 결과와 승인 제안을 확인할 수 있습니다.");
      return;
    }
    setWorkLogReturnMessage((message) => message || "원래 작업 기록 항목이 현재 페이지에 없습니다. 작업 기록의 페이지를 넘겨 직접 확인하세요.");
  }, [data, loading, workLogReturnId]);

  const entries = data?.entries || [];
  const canNext = Boolean(data && offset + pageSize < data.total);
  const latestSummary = workLogLatestSummary(entries[0], loading && !data);
  // 고를 것이 없는 필터와 넘길 곳이 없는 페이지 이동은 그리지 않는다.
  // 이미 범주를 좁혀둔 상태라면 돌아갈 길이 필요하므로 필터는 남긴다.
  const showFilters = filter !== "all" || (data?.total ?? 0) > 1;
  const showPagination = Boolean(data && data.total > pageSize);
  const body = (
    <>
      {!collapsible && (
        <header className="work-log-head">
          <div><p className="section-kicker">Agent Work Log</p><h2>Agent 작업 기록</h2></div>
        </header>
      )}
      {/* 범주 필터와 새로고침은 같은 줄에 둔다. 접힌 머리말 아래에 빈 행이 생기지 않는다. */}
      <div className="work-log-toolbar">
        {showFilters ? (
          !diagMode ? <div className="work-log-filters" data-qa="work-log-filter" aria-label="작업 범주">
            {(["all", "companion", "task"] as const).map((value) => <button key={value} type="button" className="btn" data-qa={`work-log-filter-${value}`} aria-pressed={filter === value} onClick={() => changeFilter(value)}>{value === "all" ? "전체" : value === "companion" ? "대화" : "작업"}</button>)}
          </div> : <span aria-hidden="true" />
        ) : <span />}
        <button className="btn btn--icon" type="button" data-qa="work-log-refresh" disabled={diagMode ? diagLoading || diagLoadingMore : loading} onClick={() => void refreshLog()} aria-label="작업 기록 새로고침" data-tooltip="새로고침">
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9" /><path d="M13.5 2.5V6H10" /></svg>
        </button>
      </div>
      {/* 0.6 D3 다음 단계 — 공통 진단 목록. 조용히 접어 두고, 필터를 켜면 아래 목록이
          Work Log 26필드 대신 이 목록(자동화·RSS·색인·direct 실행 포함)으로 바뀐다. */}
      <details className="work-log-diag-filters" data-qa="work-log-diag-filters">
        <summary>실패·대체 실행 찾기</summary>
        <div className="work-log-diag-filter-row">
          <button type="button" className="btn btn--sm" data-qa="work-log-diag-failed" aria-pressed={diagFailedOnly} onClick={() => toggleDiagnosticFilter("failed")}>실패만</button>
          <button type="button" className="btn btn--sm" data-qa="work-log-diag-fallback" aria-pressed={diagFallbackOnly} onClick={() => toggleDiagnosticFilter("fallback")}>대체 실행만</button>
          <label className="work-log-diag-period">
            <span>기간</span>
            <select value={diagPeriod} data-qa="work-log-diag-period" onChange={(event) => changeDiagnosticPeriod(event.currentTarget.value as DiagPeriod)}>
              <option value="all">전체</option>
              <option value="today">오늘</option>
              <option value="7d">최근 7일</option>
              <option value="30d">최근 30일</option>
            </select>
          </label>
          {!diagMode && <button type="button" className="btn btn--sm" data-qa="work-log-diag-all" onClick={enterDiagnostics}>모든 실행 보기</button>}
          {diagMode && <button type="button" className="btn btn--sm btn--text" data-qa="work-log-diag-close" onClick={leaveDiagnostics}>작업 기록으로 돌아가기</button>}
        </div>
        {diagMode && <p className="work-log-diag-hint">Work Log 대상 밖(자동화·RSS·색인 등) 실행도 함께 찾습니다. 대화·작업 범주 필터는 이 목록에 적용하지 않습니다.</p>}
      </details>
      {!diagMode && loading && !data && <p data-qa="work-log-loading" role="status">작업 기록을 불러오는 중입니다.</p>}
       {!diagMode && listError && <p className="react-dashboard-error" data-qa="work-log-error" data-error-code={listError} role="alert">작업 기록을 불러오지 못했습니다. ({listError})</p>}
       {!diagMode && listErrorDiagnostic && <ReportErrorDiagnostic diagnostic={listErrorDiagnostic} />}
       {!diagMode && clearError && <p className="react-dashboard-error" data-qa="work-log-clear-error" data-error-code={clearError}>{clearErrorResponseLess ? "숨기기 결과를 확인할 수 없습니다. 목록 상태를 새로고침해 확인하세요." : "숨기기 미리보기가 만료되었거나 실패했습니다. 다시 미리보세요."} ({clearError})</p>}
       {!diagMode && clearErrorDiagnostic && <ReportErrorDiagnostic diagnostic={clearErrorDiagnostic} />}
      {!diagMode && clearSuccess && <p className="react-dashboard-warning" data-qa="work-log-clear-success" role="status">{clearSuccess}</p>}
       {!diagMode && proposalError && <p className="react-dashboard-error" data-qa="work-log-proposal-error" data-error-code={proposalError}>제안이 만료되었거나 현재 열 수 없습니다. ({proposalError})</p>}
       {!diagMode && proposalErrorDiagnostic && <ReportErrorDiagnostic diagnostic={proposalErrorDiagnostic} />}
      {!diagMode && workLogReturnMessage && <p className="react-dashboard-warning" data-qa="work-log-return-message" role="status">{workLogReturnMessage}</p>}
      {!diagMode && !loading && !listError && entries.length === 0 && <p className="work-log-empty" data-qa="work-log-empty">표시할 Agent 작업 기록이 없습니다.</p>}
      {!diagMode && entries.length > 0 && <div className="work-log-list" data-qa="work-log-list">
        {entries.map((entry) => {
          const copy = workLogItemCopy(entry);
          return (
            <article className={`work-log-item status-${entry.status} tone-${copy.tone}`} data-qa="work-log-item" data-work-log-id={entry.id} data-tone={copy.tone} tabIndex={-1} key={entry.id}>
              <div className="work-log-item-main">
                <div className="work-log-item-title">
                  <strong data-qa="work-log-task-type">{copy.title}</strong>
                  <span className="work-log-badge" data-qa="work-log-status" data-tone={copy.tone}>{copy.statusLabel}</span>
                </div>
                <p className="work-log-outcome" data-qa="work-log-outcome">{copy.outcome}</p>
                {copy.details.length > 0 && (
                  <p className="work-log-detail" data-qa="work-log-execution">{copy.details.join(" · ")}</p>
                )}
                {copy.attention && <p className="work-log-attention" data-qa="work-log-proposal-status">{copy.attention}</p>}
              </div>
              <div className="work-log-item-side">
                <time data-qa="work-log-time" dateTime={entry.updatedAt}>{displayTime(entry.finishedAt || entry.updatedAt)}</time>
                {entry.proposalId && (entry.proposalStatus === "pending" || entry.proposalStatus === "applying") && <button type="button" className="btn" data-qa="work-log-proposal-open" disabled={proposalLoading === entry.proposalId} onClick={() => void openProposal(entry)}>{proposalLoading === entry.proposalId ? <span data-qa="work-log-proposal-loading">불러오는 중</span> : "승인 검토"}</button>}
              </div>
              <DiagnosticDetail jobId={entry.jobId} revision={entry.updatedAt} refreshKey={detailRefreshKey} />
            </article>
          );
        })}
      </div>}
      {!diagMode && data && <footer className="work-log-footer">
        <div className="work-log-footer-note">
          <p data-qa="work-log-retention">최근 {data.retention.maxDays}일, 최대 {data.retention.maxEntries}건을 표시합니다.</p>
          <p>작업 내용 원문이나 개인 자료 없이 진행 상태 요약만 표시합니다.</p>
        </div>
        <div className="work-log-footer-actions">
          {showPagination && <div className="work-log-pagination"><span data-qa="work-log-page-summary">{data.total ? `${offset + 1}–${Math.min(offset + pageSize, data.total)} / ${data.total}` : "0 / 0"}</span><button type="button" data-qa="work-log-page-prev" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - pageSize))}>이전</button><button type="button" data-qa="work-log-page-next" disabled={!canNext || loading} onClick={() => setOffset(offset + pageSize)}>다음</button></div>}
          {entries.length > 0 && <button className="work-log-quiet-btn" type="button" data-qa="work-log-clear-preview" disabled={clearBusy} onClick={(event) => void previewClear(event.currentTarget)}>기록 숨기기</button>}
        </div>
      </footer>}

      {diagMode && diagLoading && <p data-qa="work-log-diag-loading" role="status">진단 목록을 불러오는 중입니다.</p>}
       {diagMode && diagError && <><p className="react-dashboard-error" data-qa="work-log-diag-error" data-error-code={diagError} role="alert">진단 목록을 불러오지 못했습니다. ({diagError}) <button type="button" className="btn btn--sm btn--text" data-qa="work-log-diag-retry" onClick={() => void loadDiagnostics(true, false, diagItems.length > 0)}>다시 시도</button></p>{diagErrorDiagnostic && <ReportErrorDiagnostic diagnostic={diagErrorDiagnostic} />}</>}
      {diagMode && diagListErrors.length > 0 && <p className="react-dashboard-warning" data-qa="work-log-diag-partial" role="status">일부 실행을 확인하지 못했습니다({diagListErrors.length}건). {diagItems.length === 0 ? "조건에 맞는 실행이 없다고 확정할 수 없습니다." : "확인된 실행은 그대로 표시합니다."}</p>}
      {diagMode && !diagLoading && !diagError && diagItems.length === 0 && diagScanComplete && !diagTruncated && diagListErrors.length === 0 && <p className="work-log-empty" data-qa="work-log-diag-empty">조건에 맞는 실행이 없습니다.</p>}
      {diagMode && diagItems.length > 0 && <div className="work-log-list" data-qa="work-log-diag-list">
        {diagItems.map((item) => <DiagnosticListRow key={item.runId} item={item} refreshKey={detailRefreshKey} onReturnToWorkLog={returnToWorkLog} />)}
      </div>}
      {diagMode && (diagItems.length > 0 || diagSnapshotAt || diagTruncated || diagCursor || diagListErrors.length > 0) && <footer className="work-log-footer work-log-diag-footer">
        <div className="work-log-footer-note">
          {diagSnapshotAt && <p data-qa="work-log-diag-snapshot">{displayTime(diagSnapshotAt)} 기준 목록입니다. 지금 상태와 다를 수 있습니다.</p>}
          {diagTruncated && <p data-qa="work-log-diag-progress" role="status">서버가 아직 전체 실행 기록을 다 확인하지 못했습니다. 계속 확인하면 다음 구간을 읽습니다.</p>}
          <p>작업 내용 원문이나 개인 자료 없이 진행 상태 요약만 표시합니다.</p>
        </div>
        <div className="work-log-footer-actions">
          {diagTruncated
            ? <button type="button" className="btn" data-qa="work-log-diag-continue" disabled={diagLoading || diagLoadingMore} onClick={() => void loadDiagnostics(true)}>계속 확인하기</button>
            : diagCursor && <button type="button" className="btn" data-qa="work-log-diag-more" disabled={diagLoading || diagLoadingMore} onClick={() => void loadDiagnostics(false)}>{diagLoadingMore ? "불러오는 중" : "더 불러오기"}</button>}
        </div>
      </footer>}

      {dialog === "clear" && clearPreview && <div className="work-log-dialog-backdrop"><div className="work-log-dialog" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="work-log-clear-title" data-qa="work-log-clear-dialog"><h3 id="work-log-clear-title">작업 기록 숨기기</h3><p data-qa="work-log-clear-count">현재 범위 {clearPreview.count}건</p><p>목록에서만 숨깁니다. 공유 작업, 보고서, 제안, 레거시 파일은 삭제하지 않습니다.</p><div className="work-log-dialog-actions"><button type="button" data-qa="work-log-clear-confirm" disabled={clearBusy} onClick={() => void confirmClear()}>숨기기 확인</button><button type="button" data-qa="work-log-clear-cancel" onClick={closeDialog}>취소</button></div></div></div>}
      {proposal && <aside className="work-log-proposal-surface" data-qa="proposal-approval-surface" aria-label="활성 제안 승인 검토"><div><p className="section-kicker">승인 필요</p><h3>{boundedProposalSummary(proposal.summary) || "저장 변경 제안"}</h3><p>이 내용은 작업 기록이 아니라 요청 시 별도로 불러온 승인 제안입니다.</p></div>{proposal.diff && <pre>{boundedProposalDiff(proposal.diff)}</pre>}<button type="button" className="btn" onClick={() => setProposal(null)}>닫기</button></aside>}
    </>
  );
  return (
    <section className={`work-log work-log-${surface}${collapsible ? " work-log-collapsible" : ""}`} data-qa="work-log" aria-busy={diagMode ? diagLoading || diagLoadingMore : loading}>
      {collapsible ? (
        <details className="work-log-collapse">
          <summary>
            <span className="section-kicker">Agent Work Log</span>
            <strong>Agent 작업 기록</strong>
            <span className="work-log-latest" data-qa="work-log-latest">{latestSummary}</span>
          </summary>
          {body}
        </details>
      ) : body}
    </section>
  );
}

/** 공통 진단 목록의 한 행. Work Log 26필드가 없는 non-job 실행(자동화·RSS·색인·direct)도
 *  섞여 나오므로 featureCode를 직접 번역하고, `DiagnosticDetail`로 같은 상세를 연다. */
function DiagnosticListRow({ item, refreshKey, onReturnToWorkLog }: { item: DiagnosticListItem; refreshKey: number; onReturnToWorkLog: (workLogId: string) => void }) {
  const outcome = diagnosticRowOutcome(item);
  return (
    <article className="work-log-item" data-qa="work-log-diag-item" data-tone={outcome.tone}>
      <div className="work-log-item-main">
        <div className="work-log-item-title">
          <strong data-qa="work-log-diag-feature">{featureLabel(item.featureCode)}</strong>
          <span className="diag-state-badge" data-qa="work-log-diag-outcome" data-tone={outcome.tone}>{outcome.label}</span>
          {item.fallbackObserved && <span className="diag-state-badge" data-tone="muted">대체 실행</span>}
          {item.workLogId && <span className="diag-state-badge" data-tone="muted">Work Log 연결됨</span>}
        </div>
        {item.failureReasonCode && <p className="work-log-outcome" data-qa="work-log-diag-reason">{reasonLabel(item.failureReasonCode)}</p>}
      </div>
      <div className="work-log-item-side">
        <time data-qa="work-log-diag-time" dateTime={item.createdAt}>{displayTime(item.createdAt)}</time>
        {item.workLogId && <button type="button" className="btn btn--sm btn--text" data-qa="work-log-diag-return" onClick={() => onReturnToWorkLog(item.workLogId as string)}>원래 작업 기록 보기</button>}
      </div>
      <DiagnosticDetail runId={item.runId} refreshKey={refreshKey} />
    </article>
  );
}
