import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useContentRevision } from "./useContentRevision";
import { engineNote, groupMeta, listDate } from "./savedListFormat";
import { useCompanyResolution } from "./companyAnalysis/useCompanyResolution";
import { deleteJson, getJson, isAbortError, isActiveJobStatus, postJson, type JobStatus } from "../api";
import { openReactAgentDock, setReactAgentContextScope } from "./agentContext";
import { PROPOSAL_LIFECYCLE_EVENT, proposalTargetsContext, type ProposalLifecycleResult } from "./agentProposalLifecycle";
import { CompanyAnalysisBody } from "./reportReader/CompanyAnalysisBody";
import { stableNoteKey } from "./reportReader/FolioNotePanel";
import { ReaderActionButton, ReaderActionGroup } from "./reportReader/ReaderActions";
import { ReportReaderShell } from "./reportReader/ReportReaderShell";
import { RouteHero } from "./RouteHero";
import { parsePersonalOverlayPayload } from "./deepResearchPayload";
import { ANALYSIS_HANDOFF_KEY } from "./watchlist/EarningsPanel";
import { captureReportError, ReportErrorDiagnostic, reportErrorMessage, type CapturedReportError } from "./reportErrorDiagnostic";

type AnalysisViewMode = "recent" | "company" | "month";
type AnalysisStyle = "beginner" | "advanced";

type Company = {
  name?: string;
  ticker?: string;
};

type AnalysisReport = {
  id?: string;
  query?: string;
  company?: Company;
  generatedAt?: string;
  mode?: string;
  engine?: string;
  engineDetail?: string;
  headline?: string;
  markdown?: string;
  analysisStyle?: AnalysisStyle | string;
  saved?: boolean;
  generation?: { message?: string; mode?: string; webSearch?: boolean; generatedAt?: string };
  sources?: Array<{ source?: string; date?: string; type?: string; title?: string; url?: string; path?: string }>;
  analysisCharts?: { available?: boolean; reason?: string; charts?: unknown[] };
  dataGaps?: DataGap[] | { gaps?: DataGap[]; summary?: Record<string, number> };
  canonicalRevision?: unknown;
  personalOverlay?: unknown;
};

type DataGap = {
  field?: string;
  label?: string;
  category?: string;
  severity?: string;
  status?: string;
  message?: string;
  suggestedAction?: string;
  resolvedBy?: string;
  attempts?: string[];
};

type AgentJob = {
  id: string;
  kind?: string;
  status: JobStatus;
  message?: string;
  error?: string;
  result?: { reportId?: string; artifactId?: string };
};

type ExportResult = {
  notionUrl?: string;
  title?: string;
  filename?: string;
  company?: string;
};

type OverlayResult = {
  personalOverlay?: unknown;
};

const ANALYSIS_STYLES: Array<{ value: AnalysisStyle; label: string; description: string }> = [
  { value: "beginner", label: "기본", description: "쉽게 설명" },
  { value: "advanced", label: "심화", description: "정밀 분석" },
];
const RECENT_ANALYSIS_LIMIT = 20;

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isAgentJob(value: unknown): value is AgentJob {
  const job = value as AgentJob;
  return Boolean(job?.id && isActiveJobStatus(job.status));
}

async function pollJob(job: AgentJob): Promise<AgentJob> {
  let current = job;
  while (isActiveJobStatus(current.status)) {
    await sleep(1000);
    current = await getJson<AgentJob>(`/api/jobs/${encodeURIComponent(current.id)}`);
  }
  if (current.status !== "done") {
    throw new Error(current.message || current.error || "기업 분석 생성에 실패했습니다.");
  }
  return current;
}

function splitReportTitle(markdown = "", fallback = "기업 분석") {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const firstContentIndex = lines.findIndex((line) => line.trim());
  if (firstContentIndex < 0) return { title: fallback, body: "" };
  const titleMatch = lines[firstContentIndex].trim().match(/^#\s+(.+)$/);
  if (!titleMatch) return { title: fallback, body: markdown };
  return {
    title: titleMatch[1],
    body: lines.slice(firstContentIndex + 1).join("\n").trim(),
  };
}

function tickerOf(report: AnalysisReport) {
  return String(report.company?.ticker || report.query || report.company?.name || "").trim().toUpperCase();
}

function companyNameOf(report: AnalysisReport) {
  return String(report.company?.name || report.query || tickerOf(report) || "").trim();
}

function reportLabel(report: AnalysisReport) {
  const ticker = tickerOf(report);
  const name = companyNameOf(report);
  return ticker && name && ticker !== name ? `${ticker} · ${name}` : name || ticker || "기업 분석";
}

function analysisFeedTitle(report: AnalysisReport) {
  const markdownTitle = splitReportTitle(String(report.markdown || ""), "").title.trim();
  return markdownTitle || String(report.headline || "").trim() || reportLabel(report);
}

function displayDate(value?: string) {
  return listDate(value) || "미상";
}

function analysisStyleLabel(value?: string) {
  return ANALYSIS_STYLES.find((style) => style.value === value)?.label || "";
}

function gapSeverityLabel(value?: string) {
  if (value === "high") return "높음";
  if (value === "medium") return "중간";
  if (value === "low") return "낮음";
  return value || "확인 필요";
}

function dataGapRows(report?: AnalysisReport | null) {
  const raw = report?.dataGaps;
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  return Array.isArray(raw.gaps) ? raw.gaps : [];
}

function dedupeDataGaps(gaps: DataGap[]) {
  const seen = new Set<string>();
  return gaps.filter((gap) => {
    const key = [
      normalizeText(gap.field),
      normalizeText(gap.label),
      normalizeText(gap.category),
      normalizeText(gap.message || gap.suggestedAction),
    ].join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function unresolvedDataGaps(report?: AnalysisReport | null) {
  const severityRank: Record<string, number> = { high: 0, medium: 1, low: 2 };
  return dedupeDataGaps(
    dataGapRows(report)
      .filter((gap) => gap.status !== "resolved")
      .sort((a, b) => (severityRank[a.severity || ""] ?? 9) - (severityRank[b.severity || ""] ?? 9)),
  );
}

function displayMonth(value?: string) {
  if (!value) return "월 미상";
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return `${parsed.getFullYear()}.${String(parsed.getMonth() + 1).padStart(2, "0")}`;
  }
  const match = String(value).match(/^(\d{4})[-.](\d{1,2})/);
  return match ? `${match[1]}.${String(match[2]).padStart(2, "0")}` : "월 미상";
}

function normalizeText(value?: string) {
  return String(value || "").trim().toLowerCase();
}

function sourceLabel(source: NonNullable<AnalysisReport["sources"]>[number]) {
  return [source.source, source.date, source.type].filter(Boolean).join(" · ");
}

function sourceTitle(source: NonNullable<AnalysisReport["sources"]>[number]) {
  return source.title || source.url || source.path || "자료";
}

function analysisBodyMarkdown(report: AnalysisReport) {
  const raw = String(report.markdown || "");
  if (report.generation?.webSearch) return raw.trim();
  return raw.split(/\n(?=#{1,3}\s*(?:8\.\s*)?(?:Sources Used|사용 자료)\b)/i)[0].trim();
}

function setAnalysisHash(reportId?: string) {
  window.location.hash = reportId ? `#/analysis/${encodeURIComponent(reportId)}` : "#/analysis";
}

function readAnalysisDetailId() {
  const match = window.location.hash.match(/^#\/?analysis\/(.+)$/);
  return match ? decodeURIComponent(match[1]) : "";
}

function isAnalysisHash() {
  return window.location.hash.replace(/^#\/?/, "").split("/")[0] === "analysis";
}

export function CompanyAnalysisRoute() {
  const contentRevision = useContentRevision("companyAnalysis");
  const [reports, setReports] = useState<AnalysisReport[]>([]);
  const [selected, setSelected] = useState<AnalysisReport | null>(null);
  const [detailId, setDetailId] = useState(() => readAnalysisDetailId());
  const [query, setQuery] = useState("");
  const { resolution, pending: resolvePending, picked, setPicked, effective } = useCompanyResolution(query);

  // 0.5.0 기업분석은 SEC 제출사와 한국 종목만 다룬다. 자국에만 상장된 유럽·일본
  // 기업은 공식 자료 경로가 아직 없다 — 조용히 빈 보고서를 내는 대신 이유를 말한다.
  const target = picked || (resolution?.status === "confident" ? resolution.match : null);
  const outOfScope = Boolean(target && !target.cik && (target.market === "EUROPE" || target.market === "JP"));
  const resolutionStatus = outOfScope
    ? "out-of-scope"
    : picked ? "picked" : resolvePending ? "pending" : resolution?.status || "idle";
  const resolutionMessage = (() => {
    if (!query.trim()) return "티커, 회사명, 한글 표기 중 무엇으로 적어도 됩니다.";
    if (outOfScope && target) {
      const where = target.market === "JP" ? "일본" : "유럽";
      return `${target.name}는 ${where} 거래소에만 상장되어 있어 아직 분석할 수 없습니다. 미국에도 상장된 기업은 그 티커로 적어 보세요.`;
    }
    if (picked) return `${picked.name} (${picked.ticker})으로 분석합니다.`;
    if (resolvePending) return "확인 중…";
    if (!resolution) return "";
    if (resolution.status === "confident" && resolution.match) {
      return `${resolution.match.name} (${resolution.match.ticker})으로 분석합니다.`;
    }
    if (resolution.status === "ambiguous") return "여러 기업이 맞습니다. 아래에서 고르세요.";
    return "아는 기업이 없습니다. 티커로 적어 보세요. 이대로 진행하면 자료가 거의 없는 보고서가 나옵니다.";
  })();
  const [analysisStyle, setAnalysisStyle] = useState<AnalysisStyle>("beginner");
  const [reportQuery, setReportQuery] = useState("");
  const [reportView, setReportView] = useState<AnalysisViewMode>("recent");
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [actionBusy, setActionBusy] = useState("");
  const [error, setError] = useState("");
  const [generationError, setGenerationError] = useState<CapturedReportError | null>(null);
  const [generationErrorMessage, setGenerationErrorMessage] = useState("");
  const generationOperationId = useRef(0);
  const [listErrorMessage, setListErrorMessage] = useState("");
  const [listErrorDiagnostic, setListErrorDiagnostic] = useState<CapturedReportError | null>(null);
  const [readErrorMessage, setReadErrorMessage] = useState("");
  const [readErrorDiagnostic, setReadErrorDiagnostic] = useState<CapturedReportError | null>(null);
  const [actionErrorMessage, setActionErrorMessage] = useState("");
  const [actionErrorDiagnostic, setActionErrorDiagnostic] = useState<CapturedReportError | null>(null);
  const listRequestId = useRef(0);
  const listController = useRef<AbortController | null>(null);
  const readRequestId = useRef(0);
  const actionRequestId = useRef(0);
  const actionController = useRef<AbortController | null>(null);
  const [status, setStatus] = useState("");
  const [proposalReloadKey, setProposalReloadKey] = useState(0);

  function clearGenerationDiagnostic() {
    setGenerationError(null);
    setGenerationErrorMessage("");
  }

  function beginGenerationDiagnostic() {
    generationOperationId.current += 1;
    clearGenerationDiagnostic();
    return generationOperationId.current;
  }

  function invalidateGenerationDiagnostic() {
    generationOperationId.current += 1;
    clearGenerationDiagnostic();
  }

  function beginReportAction() {
    actionController.current?.abort();
    const id = ++actionRequestId.current;
    const controller = new AbortController();
    actionController.current = controller;
    setActionErrorMessage("");
    setActionErrorDiagnostic(null);
    return { id, controller };
  }

  function isCurrentReportAction(id: number, controller: AbortController) {
    return id === actionRequestId.current && actionController.current === controller && !controller.signal.aborted;
  }

  function invalidateReportAction() {
    actionRequestId.current += 1;
    actionController.current?.abort();
    actionController.current = null;
    setActionErrorMessage("");
    setActionErrorDiagnostic(null);
    setActionBusy("");
  }

  const loadReports = useCallback(async () => {
    const requestId = ++listRequestId.current;
    listController.current?.abort();
    const controller = new AbortController();
    listController.current = controller;
    setLoading(true);
    setListErrorMessage("");
    setListErrorDiagnostic(null);
    try {
      const payload = await getJson<AnalysisReport[]>("/api/analysis-reports", { signal: controller.signal });
      if (controller.signal.aborted || requestId !== listRequestId.current) return;
      setReports(Array.isArray(payload) ? payload : []);
      setReactAgentContextScope("analysis", { surface: "analysis", viewId: "analysis", reportKind: "", reportId: "" });
    } catch (err) {
      if (isAbortError(err, controller.signal) || requestId !== listRequestId.current) return;
      const message = reportErrorMessage(err, "기업 분석 목록을 불러오지 못했습니다.");
      setListErrorMessage(message);
      setListErrorDiagnostic(captureReportError(err, requestId));
    } finally {
      if (requestId === listRequestId.current) {
        listController.current = null;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    loadReports();
  // 생성·수집이 어디서 일어나든 목록이 따라온다(자동화, 다른 탭, Agent 도크 포함).
  }, [loadReports, contentRevision]);

  useEffect(() => {
    const handleHashChange = () => {
      if (!isAnalysisHash()) return;
      setDetailId(readAnalysisDetailId());
      // 워치리스트 실적 패널이 넘긴 종목. 한 번만 쓰고 지운다 — 남겨 두면 다음에
      // 이 화면을 그냥 열었을 때 지난번 종목이 입력칸에 다시 들어앉는다.
      try {
        const handoff = window.sessionStorage.getItem(ANALYSIS_HANDOFF_KEY);
        if (handoff) {
          window.sessionStorage.removeItem(ANALYSIS_HANDOFF_KEY);
          setQuery(handoff);
        }
      } catch { /* 세션 저장소가 막혀 있으면 그냥 빈 입력칸이다 */ }
    };
    window.addEventListener("hashchange", handleHashChange);
    handleHashChange();
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  useEffect(() => {
    const handleProposalLifecycle = (event: Event) => {
      const result = (event as CustomEvent<ProposalLifecycleResult>).detail;
      if (proposalTargetsContext(result, window.FolioAgent?.currentContext)) setProposalReloadKey((value) => value + 1);
    };
    window.addEventListener(PROPOSAL_LIFECYCLE_EVENT, handleProposalLifecycle);
    return () => window.removeEventListener(PROPOSAL_LIFECYCLE_EVENT, handleProposalLifecycle);
  }, []);

  useEffect(() => {
    let alive = true;
    let controller: AbortController | null = null;
    async function loadDetail(reportId: string) {
      const requestId = ++readRequestId.current;
      const requestController = new AbortController();
      controller = requestController;
      setLoading(true);
      invalidateGenerationDiagnostic();
      invalidateReportAction();
      setReadErrorMessage("");
      setReadErrorDiagnostic(null);
      setError("");
      try {
        const report = await getJson<AnalysisReport>(`/api/analysis-reports/${encodeURIComponent(reportId)}?includePersonal=true`, { signal: requestController.signal });
        if (!alive || requestController.signal.aborted || requestId !== readRequestId.current) return;
        setSelected(report);
        setReactAgentContextScope("analysis", {
          surface: "analysis_reader",
          viewId: "analysis",
          reportKind: "company_analysis",
          reportId: report.id || reportId,
          ticker: tickerOf(report),
        });
      } catch (err) {
        if (!alive || isAbortError(err, requestController.signal) || requestId !== readRequestId.current) return;
        const message = reportErrorMessage(err, "저장된 기업 분석 보고서를 열지 못했습니다.");
        setReadErrorMessage(message);
        setReadErrorDiagnostic(captureReportError(err, requestId));
        setSelected(null);
        setError(message);
      } finally {
        if (alive && requestId === readRequestId.current && !requestController.signal.aborted) setLoading(false);
      }
    }

    if (detailId) {
      loadDetail(detailId);
    } else {
      invalidateReportAction();
      readRequestId.current += 1;
      setReadErrorMessage("");
      setReadErrorDiagnostic(null);
      setSelected(null);
      setReactAgentContextScope("analysis", { surface: "analysis", viewId: "analysis", reportKind: "", reportId: "" });
    }
    return () => {
      alive = false;
      controller?.abort();
      readRequestId.current += 1;
    };
  }, [detailId, proposalReloadKey]);

  async function generateAnalysis(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    setGenerating(true);
    const operationId = beginGenerationDiagnostic();
    setError("");
    setStatus("기업 자료를 읽고 분석 보고서를 생성하는 중입니다.");
    try {
      const params = new URLSearchParams({
        // 해석이 끝났으면 원문이 아니라 확정된 티커를 보낸다. "마이크론"을 그대로
        // 넘기면 서버가 다시 추측하고, 사용자가 화면에서 고른 것과 달라질 수 있다.
        q: effective?.ticker || trimmed,
        analysisStyle,
      });
      const response = await getJson<AnalysisReport | AgentJob>(`/api/analyze?${params.toString()}`);
      let report: AnalysisReport;
      if (isAgentJob(response)) {
        const done = await pollJob(response);
        const reportId = done.result?.reportId || done.result?.artifactId || "";
        if (!reportId) throw new Error("생성된 보고서 ID를 확인하지 못했습니다.");
        report = await getJson<AnalysisReport>(`/api/analysis-reports/${encodeURIComponent(reportId)}?includePersonal=true`);
      } else {
        report = response;
      }
      // Show the returned candidate before refreshing the feed. A list refresh
      // is secondary: it must not hide a usable report or turn its generation
      // into a failure. Only an explicit `saved: true` proves that the detail
      // URL points at durable storage.
      setSelected(report);
      const saved = report.saved === true;
      if (saved && report.id) setAnalysisHash(report.id);
      try {
        await loadReports();
      } catch {
        // loadReports normally reports its own bounded list error; keep this
        // guard for injected/transport failures after the report is visible.
      }
      setStatus(saved
        ? "기업 분석 보고서를 생성하고 자동 저장했습니다."
        : "기업 분석 보고서는 생성했지만 저장 여부를 확인하지 못했습니다.");
    } catch (err) {
      if (isAbortError(err) || operationId !== generationOperationId.current) return;
      setGenerationError(captureReportError(err, operationId));
      const message = reportErrorMessage(err, "기업 분석 생성에 실패했습니다.");
      setGenerationErrorMessage(message);
      setError(message);
      setStatus("");
    } finally {
      setGenerating(false);
    }
  }

  async function openReport(reportId?: string) {
    if (!reportId) return;
    setAnalysisHash(reportId);
  }

  function closeSelectedReport() {
    // An unsaved candidate has no detail hash to clear. Reset local selection
    // explicitly so closing still works when the URL was already unchanged.
    setSelected(null);
    setAnalysisHash();
  }

  async function deleteReport(report: AnalysisReport) {
    if (!report.id) return;
    if (!window.confirm(`${reportLabel(report)} 보고서를 삭제할까요?`)) return;
    const action = beginReportAction();
    setActionBusy(`delete-${report.id}`);
    invalidateGenerationDiagnostic();
    setError("");
    try {
      const result = await deleteJson<{ readonly deleted?: boolean }>(`/api/analysis-reports/${encodeURIComponent(report.id)}`, {}, { signal: action.controller.signal });
      if (!result || result.deleted !== true) throw new Error("기업 분석 삭제 결과를 확인하지 못했습니다.");
      if (!isCurrentReportAction(action.id, action.controller)) return;
      if (selected?.id === report.id) setAnalysisHash();
      await loadReports();
      setStatus("저장된 기업 분석 보고서를 삭제했습니다.");
    } catch (err) {
      if (!isCurrentReportAction(action.id, action.controller) || isAbortError(err, action.controller.signal)) return;
      setActionErrorDiagnostic(captureReportError(err, action.id));
      const message = reportErrorMessage(err, "보고서 삭제에 실패했습니다.");
      setActionErrorMessage(message);
      setError(message);
    } finally {
      if (isCurrentReportAction(action.id, action.controller)) {
        actionController.current = null;
        setActionBusy("");
      }
    }
  }

  async function exportAnalysis(target: "notion" | "obsidian") {
    if (!selected) return;
    const action = beginReportAction();
    setActionBusy(target);
    setStatus(target === "notion" ? "Notion으로 내보내는 중..." : "Obsidian으로 내보내는 중...");
    try {
      const result = target === "notion"
        ? await postJson<ExportResult>("/api/export-notion/analysis", selected, { signal: action.controller.signal })
        : await postJson<ExportResult>("/api/export-obsidian/analysis", selected, { signal: action.controller.signal });
      if (!isCurrentReportAction(action.id, action.controller)) return;
      setStatus(target === "notion"
        ? `Notion으로 내보냈습니다${result.title ? `: ${result.title}` : ""}`
        : `Obsidian으로 내보냈습니다${result.company || result.filename ? `: ${result.company || result.filename}` : ""}`);
    } catch (err) {
      if (!isCurrentReportAction(action.id, action.controller) || isAbortError(err, action.controller.signal)) return;
      setActionErrorDiagnostic(captureReportError(err, action.id));
      const message = reportErrorMessage(err, "내보내기에 실패했습니다.");
      setActionErrorMessage(message);
      setStatus(message);
    } finally {
      if (isCurrentReportAction(action.id, action.controller)) {
        actionController.current = null;
        setActionBusy("");
      }
    }
  }

  async function generatePersonalOverlay() {
    if (!selected?.id) return;
    setActionBusy("overlay");
    setStatus("내 노트와 연결하는 중...");
    try {
      const response = await postJson<OverlayResult | AgentJob>(`/api/analysis-reports/${encodeURIComponent(selected.id)}/personal-overlay`, {});
      if (isAgentJob(response)) await pollJob(response);
      const updated = await getJson<AnalysisReport>(`/api/analysis-reports/${encodeURIComponent(selected.id)}?includePersonal=true`);
      setSelected(updated);
      setStatus("내 노트와 연결했습니다.");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "내 노트 연결에 실패했습니다.");
    } finally {
      setActionBusy("");
    }
  }

  const filteredReports = useMemo(() => {
    const q = normalizeText(reportQuery);
    if (!q) return reports;
    return reports.filter((report) => {
      const haystack = normalizeText([
        tickerOf(report),
        companyNameOf(report),
        reportLabel(report),
        report.headline,
        report.mode,
        report.generatedAt,
        displayDate(report.generatedAt),
      ].filter(Boolean).join(" "));
      return haystack.includes(q);
    });
  }, [reportQuery, reports]);

  const visibleReportGroups = useMemo(() => {
    const sorted = [...filteredReports].sort((a, b) => String(b.generatedAt || "").localeCompare(String(a.generatedAt || "")));
    if (reportView === "recent") {
      if (!sorted.length) return [];
      return [{
        key: "recent",
        label: `최근 보고서 ${Math.min(sorted.length, RECENT_ANALYSIS_LIMIT)}건`,
        rows: sorted.slice(0, RECENT_ANALYSIS_LIMIT),
      }];
    }
    if (reportView === "month") {
      const groups = new Map<string, AnalysisReport[]>();
      for (const report of sorted) {
        const key = displayMonth(report.generatedAt);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key)?.push(report);
      }
      return Array.from(groups.entries()).map(([key, rows]) => ({ key, label: key, rows }));
    }
    const groups = new Map<string, AnalysisReport[]>();
    for (const report of sorted) {
      const key = tickerOf(report) || analysisFeedTitle(report);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)?.push(report);
    }
    return Array.from(groups.entries())
      .map(([key, rows]) => ({
        key,
        label: analysisFeedTitle(rows[0] || {}),
        rows: rows.sort((a, b) => String(b.generatedAt || "").localeCompare(String(a.generatedAt || ""))),
      }))
      .sort((a, b) => String(b.rows[0]?.generatedAt || "").localeCompare(String(a.rows[0]?.generatedAt || "")));
  }, [filteredReports, reportView]);

  const readerMarkdown = analysisBodyMarkdown(selected || {});
  const readerContent = splitReportTitle(readerMarkdown, selected?.headline || reportLabel(selected || {}));
  const sources = selected?.sources || [];
  const readerDataGaps = unresolvedDataGaps(selected);

  if (selected) {
    return (
      <div className="react-company-analysis-route" data-company-analysis-route>
        {readErrorMessage && <p className="react-dashboard-error">{readErrorMessage}</p>}
        {error && !readErrorMessage && <p className="react-dashboard-error">{error}</p>}
        {readErrorDiagnostic && <ReportErrorDiagnostic diagnostic={readErrorDiagnostic} />}
        <ReportReaderShell
          eyebrow={`COMPANY ANALYSIS${tickerOf(selected) ? ` · ${tickerOf(selected)}` : ""}`}
          title={readerContent.title}
          meta={[selected.generatedAt ? `생성일 ${displayDate(selected.generatedAt)}` : "", analysisStyleLabel(selected.analysisStyle)].filter(Boolean).join(" · ")}
          agentContext={{
            surface: "analysis_reader",
            viewId: "analysis",
            reportKind: "company_analysis",
            reportId: selected.id || "",
            ticker: tickerOf(selected),
          }}
          breadcrumb={(
            <>
              <button type="button" onClick={closeSelectedReport}>
                기업 분석
              </button>
              <span>{readerContent.title}</span>
            </>
          )}
          onClose={closeSelectedReport}
          actionSlot={(
            <>
              <ReaderActionGroup title="AI">
                <ReaderActionButton
                  icon="agent"
                  onClick={() => openReactAgentDock({
                    surface: "analysis_reader",
                    reportKind: "company_analysis",
                    reportId: selected.id || "",
                    ticker: tickerOf(selected),
                    message: `${readerContent.title}에서 투자 판단에 중요한 핵심, 리스크, 추가 확인 질문을 정리해줘.`,
                    autoSubmit: true,
                  })}
                >
                  Agent에게 묻기
                </ReaderActionButton>
              </ReaderActionGroup>
              <ReaderActionGroup title="노트">
                <ReaderActionButton icon="link" disabled={actionBusy === "overlay" || !selected.id} onClick={generatePersonalOverlay}>
                  {actionBusy === "overlay" ? "연결 중" : "내 노트와 연결"}
                </ReaderActionButton>
              </ReaderActionGroup>
              <ReaderActionGroup title="내보내기">
                <ReaderActionButton icon="notion" disabled={actionBusy === "notion"} onClick={() => exportAnalysis("notion")}>
                  {actionBusy === "notion" ? "내보내는 중" : "Notion으로 내보내기"}
                </ReaderActionButton>
                <ReaderActionButton icon="obsidian" disabled={actionBusy === "obsidian"} onClick={() => exportAnalysis("obsidian")}>
                  {actionBusy === "obsidian" ? "내보내는 중" : "Obsidian으로 내보내기"}
                </ReaderActionButton>
              </ReaderActionGroup>
              {readerDataGaps.length > 0 && (
                <ReaderActionGroup title="자료 한계">
                  <div className="react-reader-gap-list">
                    {readerDataGaps.slice(0, 3).map((gap, index) => (
                      <div className="react-reader-gap" key={`${gap.field || gap.category || "gap"}-${index}`}>
                        <span>{gapSeverityLabel(gap.severity)}</span>
                        <strong>{gap.label || gap.category || "추가 확인 필요"}</strong>
                        <p>{gap.message || gap.suggestedAction || "보고서 해석 시 확인이 필요한 자료 한계입니다."}</p>
                      </div>
                    ))}
                  </div>
                </ReaderActionGroup>
              )}
              {selected.generation?.message && <p className="react-reader-status">{selected.generation.message}</p>}
              {status && <p className="react-reader-status">{status}</p>}
              {actionErrorMessage && <p className="react-reader-status react-dashboard-error">{actionErrorMessage}</p>}
              {actionErrorDiagnostic && <ReportErrorDiagnostic diagnostic={actionErrorDiagnostic} />}
            </>
          )}
          noteIdentity={{
            id: stableNoteKey("company", tickerOf(selected) || selected.headline || "company"),
            noteType: "company_thesis",
            title: tickerOf(selected) ? `${tickerOf(selected)} 투자 노트` : "기업 투자 노트",
            ticker: tickerOf(selected),
            company: selected.company?.name || "",
            label: tickerOf(selected),
            reportKind: "company_analysis",
            reportId: tickerOf(selected),
            linkedReports: [readerContent.title].filter(Boolean),
          }}
          noteLinkedTitle={readerContent.title}
          noteOverlay={parsePersonalOverlayPayload(selected.personalOverlay, selected.canonicalRevision)}
        >
          <CompanyAnalysisBody markdown={readerContent.body || readerMarkdown} charts={selected.analysisCharts} />
          {sources.length > 0 && (
            <section className="source-panel react-analysis-sources">
              <h4>참고자료</h4>
              <div className="sources">
                {sources.map((source, index) => (
                  <div className="meta" key={`${sourceTitle(source)}-${index}`}>
                    <span>{sourceLabel(source)}</span>
                    {source.url ? (
                      <a href={source.url} target="_blank" rel="noopener noreferrer">{sourceTitle(source)}</a>
                    ) : (
                      <span>{sourceTitle(source)}</span>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </ReportReaderShell>
      </div>
    );
  }

  return (
    <div className="react-company-analysis-route" data-company-analysis-route>
      <RouteHero
        eyebrow="Company Analysis"
        title="기업 분석"
        description="SEC, DART, 시장 데이터와 로컬 자료를 활용해 기업 분석 보고서를 생성합니다."
        actions={(
          <button className="btn" type="button" onClick={loadReports} disabled={loading}>
            {loading ? "불러오는 중" : "새로고침"}
          </button>
        )}
      />

      <form className="react-analysis-form" onSubmit={generateAnalysis}>
        <div className="react-analysis-api-note" role="note">
          <strong>API 연동 안내</strong>
          <span>미국 기업은 SEC 자료를 우선 사용하고, 한국 기업은 DART API Key를 설정하면 공시 확인 정확도가 높아집니다.</span>
        </div>
        <div className="react-analysis-query">
          <label className="portfolio-ticker-field">
            <span>분석 대상</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.currentTarget.value)}
              placeholder="예: NVDA, 삼성전자, SK하이닉스"
              aria-describedby="analysis-resolution"
              autoComplete="off"
            />
            {resolution?.status === "ambiguous" && resolution.candidates.length > 0 && !picked && (
              <div className="ticker-suggest" role="listbox" aria-label="후보 기업">
                {resolution.candidates.map((candidate) => (
                  <button
                    type="button"
                    role="option"
                    aria-selected={false}
                    key={`${candidate.market}:${candidate.ticker}`}
                    onClick={() => setPicked(candidate)}
                  >
                    <strong>{candidate.ticker}</strong>
                    <span>{candidate.name}</span>
                  </button>
                ))}
              </div>
            )}
          </label>
          {/* 무엇으로 해석했는지 생성 전에 보여준다. 예전에는 입력 문자열이 그대로
              티커가 되어 빈 보고서가 나올 때까지 알 수 없었다. */}
          <p className="analysis-resolution" id="analysis-resolution" data-status={resolutionStatus}>
            {resolutionMessage}
          </p>
        </div>
        <fieldset className="react-analysis-style" aria-label="보고서 모드">
          <legend>보고서 모드</legend>
          <div className="segment react-analysis-style-toggle" data-style={analysisStyle}>
            {ANALYSIS_STYLES.map((style) => (
              <button
                type="button"
                key={style.value}
                aria-pressed={analysisStyle === style.value}
                onClick={() => setAnalysisStyle(style.value)}
                data-tooltip={style.description}
              >
                {style.label}
              </button>
            ))}
          </div>
        </fieldset>
        <button className="btn btn--primary" type="submit" disabled={generating || !query.trim()}>
          {generating ? "분석 중" : "분석"}
        </button>
      </form>

      {generationErrorMessage && <p className="react-dashboard-error">{generationErrorMessage}</p>}
      {generationError && <ReportErrorDiagnostic diagnostic={generationError} />}
      {readErrorMessage && <p className="react-dashboard-error">{readErrorMessage}</p>}
      {readErrorDiagnostic && <ReportErrorDiagnostic diagnostic={readErrorDiagnostic} />}
      {listErrorMessage && <p className="react-dashboard-error">{listErrorMessage}</p>}
      {listErrorDiagnostic && <ReportErrorDiagnostic diagnostic={listErrorDiagnostic} />}
      {!selected && actionErrorMessage && <p className="react-dashboard-error">{actionErrorMessage}</p>}
      {!selected && actionErrorDiagnostic && <ReportErrorDiagnostic diagnostic={actionErrorDiagnostic} />}
      {error && !generationErrorMessage && !readErrorMessage && !listErrorMessage && !actionErrorMessage && <p className="react-dashboard-error">{error}</p>}
      {status && <p className="react-dashboard-warning">{status}</p>}

      {/* 찾기 바(zone ②). 검색은 패널 안, `보기`는 패널 밖에 떠 있었다. */}
      <section className="find-bar" aria-label="저장 기업 분석 검색">
        <input
          className="find-bar__search"
          type="search"
          value={reportQuery}
          onChange={(event) => setReportQuery(event.currentTarget.value)}
          placeholder="티커·회사명·보고서 검색"
          aria-label="저장 기업 분석 검색"
        />
        <label className="find-bar__field">
          <span>보기</span>
          <select
            aria-label="기업 분석 보기 방식"
            value={reportView}
            onChange={(event) => setReportView(event.currentTarget.value as AnalysisViewMode)}
          >
            <option value="recent">최근</option>
            <option value="company">기업별</option>
            <option value="month">월별</option>
          </select>
        </label>
        <button
          className="btn btn--text find-bar__reset"
          type="button"
          onClick={() => { setReportQuery(""); setReportView("recent"); }}
        >
          초기화
        </button>
      </section>

      <section className="react-analysis-feed" aria-label="저장된 기업 분석">
        <div className="react-section-heading">
          <div>
            <p className="section-kicker">Saved Reports</p>
            <h2>저장된 기업 분석</h2>
          </div>
          <span aria-live="polite">{loading ? "불러오는 중..." : `${filteredReports.length}건${reportQuery ? " · 검색 결과" : ""}`}</span>
        </div>
        {visibleReportGroups.length ? visibleReportGroups.map((group) => (
          <section className="report-feed-group" key={group.key}>
            <div className="report-feed-group-head">
              <span className="report-feed-group-name">{group.label}</span>
              <span className="report-feed-group-meta">{groupMeta(group.rows.length, group.rows[0]?.generatedAt)}</span>
            </div>
            <div className="report-feed-group-cards">
              {group.rows.map((report) => {
                const deleting = actionBusy === `delete-${report.id}`;
                return (
                  <div className="report-feed-card-wrap" key={report.id || `${analysisFeedTitle(report)}-${report.generatedAt}`}>
                    <button className="report-feed-card is-analysis" type="button" onClick={() => openReport(report.id)}>
                      <span className="report-feed-card-meta">
                        {/* "LLM"만으로는 세 보고서가 다른 모델로 쓰였어도 구분되지 않는다. */}
                        {(report.engine || report.mode) && (
                          <span className="report-feed-badge">
                            {report.engine || String(report.mode).toUpperCase()}
                            {engineNote(report.engine, report.engineDetail) && (
                              <em>{engineNote(report.engine, report.engineDetail)}</em>
                            )}
                          </span>
                        )}
                        {report.analysisStyle && <span className="report-feed-badge">{analysisStyleLabel(report.analysisStyle) || String(report.analysisStyle).toUpperCase()}</span>}
                      </span>
                      <strong>{analysisFeedTitle(report)}</strong>
                      <span className="report-feed-card-foot">생성일 {displayDate(report.generatedAt)}</span>
                    </button>
                    <button
                      type="button"
                      className="btn btn--icon report-feed-card-delete"
                      disabled={deleting}
                      onClick={() => deleteReport(report)}
                      aria-label={`${reportLabel(report)} 삭제`}
                      data-tooltip="삭제"
                      data-tooltip-pos="bottom"
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M2.5 4h11M6 4V2.5h4V4M5 4l.5 9h5L11 4" />
                      </svg>
                    </button>
                  </div>
                );
              })}
            </div>
          </section>
        )) : (
          <article className="react-dashboard-panel">
            <h2>저장된 기업 분석 보고서가 없습니다.</h2>
            <p>분석 대상을 입력해 첫 보고서를 생성하세요.</p>
          </article>
        )}
      </section>
    </div>
  );
}
