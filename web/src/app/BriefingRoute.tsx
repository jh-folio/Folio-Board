import { useCallback, useEffect, useMemo, useState } from "react";
import { useContentRevision } from "./useContentRevision";
import { groupMeta, listDate } from "./savedListFormat";
import { useMarketScope } from "./useMarketScope";
import { getJson, isActiveJobStatus, postJson, MARKET_CODE_LABELS, type JobStatus } from "../api";
import { openReactAgentDock, setReactAgentContextScope } from "./agentContext";
import { PROPOSAL_LIFECYCLE_EVENT, proposalTargetsContext, type ProposalLifecycleResult } from "./agentProposalLifecycle";
import { legacyBridge } from "./legacyBridge";
import { ReaderActionButton, ReaderActionGroup } from "./reportReader/ReaderActions";
import { ReportBody } from "./reportReader/ReportBody";
import { ReportReaderShell } from "./reportReader/ReportReaderShell";
import { RouteHero } from "./RouteHero";
import { parsePersonalOverlayPayload } from "./deepResearchPayload";
import { BriefingChangeStrip } from "./briefing/BriefingChangeStrip";
import type { ChangeEvent } from "./changeEvents";

// `all`은 네 시장 생성 범위, `both`는 US/KR만 담은 예전 저장본이다.
type MarketScope = "us" | "kr" | "europe" | "jp" | "all" | "both" | "multi";
// 브리핑 종류. `briefingType`(편집 강조점)과 직교한다.
type BriefingKind = "daily" | "weekly";
type ArchiveKindFilter = "all" | BriefingKind;
// 아카이브 필터의 `all`은 "시장 필터 없음"이라 생성 범위 `all`과 다른 말이다.
type ArchiveMarketFilter = "all" | "aggregate" | MarketScope;
const SINGLE_MARKETS = ["us", "kr", "europe", "jp"] as const;
type SingleMarket = (typeof SINGLE_MARKETS)[number];
// 좁은 다중 선택 트랙이라 코드로 쓴다. 한글 라벨 4개는 한 줄에 들어가지 않아
// 알약 트랙이 두 줄로 접혔다. 읽는 문장에는 계속 한글(MARKET_KO_LABELS)을 쓴다.
const MARKET_CHOICE_LABELS: Record<SingleMarket, string> = {
  us: MARKET_CODE_LABELS.us, kr: MARKET_CODE_LABELS.kr,
  europe: MARKET_CODE_LABELS.europe, jp: MARKET_CODE_LABELS.jp,
};

// 조합에 이름이 없을 수 있다. `all`/`both`는 늘 뜻하던 집합에만 쓰고,
// 나머지는 `multi`로 표시한다 — 실제 커버리지는 서버가 목록으로 돌려준다.
function selectionScope(markets: SingleMarket[]): MarketScope {
  if (markets.length === 1) return markets[0];
  if (markets.length === SINGLE_MARKETS.length) return "all";
  if (markets.length === 2 && markets.includes("us") && markets.includes("kr")) return "both";
  return "multi";
}
const ALL_SCOPES: MarketScope[] = [...SINGLE_MARKETS, "all", "both", "multi"];
type ArchiveViewMode = "recent" | "month" | "market";

type BriefingArchiveItem = {
  id?: string;
  title?: string;
  reportDate?: string;
  date?: string;
  marketScope?: string;
  scope?: string;
  generatedAt?: string;
  sessionDate?: string;
  briefingType?: string;
  kind?: BriefingKind;
  weekStart?: string;
  weekEnd?: string;
  tags?: string[];
  engine?: string;
  engineDetail?: string;
};

type BriefingArchivePayload = {
  items?: BriefingArchiveItem[];
  total?: number;
  offset?: number;
  limit?: number;
};

type Briefing = {
  title?: string;
  date?: string;
  publicationDate?: string;
  sessionDate?: string;
  sessionMode?: string;
  marketScope?: string;
  kind?: BriefingKind;
  weekStart?: string;
  weekEnd?: string;
  markdown?: string;
  generation?: { message?: string; mode?: string; generatedAt?: string };
  canonicalRevision?: unknown;
  personalOverlay?: unknown;
  changeSummary?: ChangeEvent;
};

type AgentJob = {
  id: string;
  kind?: string;
  status: JobStatus;
  message?: string;
  error?: string;
  result?: { date?: string; artifactId?: string };
};

type ExportResult = {
  notionUrl?: string;
  title?: string;
  filename?: string;
};

type OverlayResult = {
  personalOverlay?: Briefing["personalOverlay"];
  status?: string;
};

type BriefingDetailRoute = {
  date: string;
  scope: MarketScope;
  kind: BriefingKind;
};

const SCOPE_LABELS: Record<MarketScope, string> = {
  us: "미국",
  kr: "한국",
  europe: "유럽",
  jp: "일본",
  all: "통합",
  both: "통합",
  multi: "선택 시장",
};

const MARKET_BADGE: Record<MarketScope, string> = {
  us: "US", kr: "KR", europe: "EU", jp: "JP", all: "ALL", both: "US/KR", multi: "MULTI",
};
const BRIEFING_MARKET_TAGS = new Set(["미국장", "한국장", "유럽장", "일본장", "종합", "선택 시장"]);
const BRIEFING_TYPE_LABELS: Record<string, string> = {
  default: "기본",
  market_focused: "시황 중심",
  concise: "요약",
};
// 브리핑 **종류**. 편집 강조점(`유형`)과 다른 축이라 컨트롤을 따로 둔다 — 유형 셋은
// 모두 "기존 섹션 구성을 유지"하라는 지시라 골격이 다른 주간을 거기 섞을 수 없다.
const BRIEFING_KIND_LABELS: Record<BriefingKind, string> = {
  daily: "일간",
  weekly: "주간 요약",
};
const RECENT_BRIEFING_LIMIT = 20;

function formatArchiveDate(date: string) {
  return String(date || "").replace(/^(\d{4})-(\d{2})-(\d{2})$/, "$1.$2.$3");
}

function formatArchiveMonth(date: string) {
  const match = String(date || "").match(/^(\d{4})-(\d{2})/);
  return match ? `${match[1]}.${match[2]}` : "월 미상";
}

function todayIsoDate() {
  const date = new Date();
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function stripTitleDate(title: string) {
  return String(title || "").replace(/\s+[—–-]\s+\d{4}[.-]\d{2}[.-]\d{2}\s*$/, "").trim();
}

// 레거시 briefingArchiveCard()와 동일한 표시 규칙(제목·배지·기준일/생성 시각).
function archiveCardView(item: BriefingArchiveItem) {
  const date = displayDate(item);
  const scope = displayScope(item);
  const kind = displayKind(item);
  const displayTitle = scope === "us"
    ? "US Market Briefing"
    : scope === "kr"
      ? "KR Market Briefing"
      : stripTitleDate(item.title || "Daily Market Briefing");
  const formatted = formatArchiveDate(date);
  const title = item.title || (formatted ? `${displayTitle} — ${formatted}` : displayTitle);
  const chips = (item.tags || []).filter((tag) => !BRIEFING_MARKET_TAGS.has(String(tag || "").trim()));
  // 브리핑은 발행일과 세션일이 다르고 그 구분이 이 화면의 핵심이라 `KST 발행`을 남긴다.
  // 초 단위 생성 시각은 목록에서 쓸 일이 없어 뺀다 — 이 카드만 유독 길어지는 원인이었다.
  const publication = formatted ? `${listDate(item.reportDate || item.date)} KST 발행` : "발행일 미상";
  return { date, scope, kind, title, chips, engine: item.engine || "", engineDetail: item.engineDetail || "", foot: publication };
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function normalizedScope(value?: string): MarketScope {
  return ALL_SCOPES.includes(value as MarketScope) ? (value as MarketScope) : "both";
}

function normalizedKind(value?: string): BriefingKind {
  return value === "weekly" ? "weekly" : "daily";
}

// 해시를 쓰는 쪽(setBriefingHash)과 읽는 쪽이 같은 scope 집합을 써야 한다. `multi`가
// 빠져 있어 미국+일본 같은 조합으로 생성하면 주소만 바뀌고 리더가 열리지 않았다 —
// 서버는 `multi`를 정식 scope로 저장·조회한다(features/daily_briefing/schema.py::MARKET_SCOPES).
function readBriefingDetailRoute(): BriefingDetailRoute | null {
  // 종류가 해시에 없으면 같은 날 두 보고서 중 어느 쪽을 열지 정할 수 없다 — 주간 카드를
  // 눌러도 그날 일간 브리핑이 열린다.
  const match = window.location.hash.match(
    /^#\/?briefing\/(\d{4}-\d{2}-\d{2})(?:\/(us|kr|europe|jp|all|both|multi))?(?:\/(daily|weekly))?$/,
  );
  if (!match) return null;
  return { date: match[1], scope: normalizedScope(match[2]), kind: normalizedKind(match[3]) };
}

function isBriefingHash() {
  return window.location.hash.replace(/^#\/?/, "").split("/")[0] === "briefing";
}

function setBriefingHash(date?: string, scope: MarketScope = "both", kind: BriefingKind = "daily") {
  window.location.hash = date ? `#/briefing/${date}/${scope}/${kind}` : "#/briefing";
}

function splitReportTitle(markdown = "", fallback = "시장 브리핑") {
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

function displayDate(item: BriefingArchiveItem) {
  return item.reportDate || item.date || "";
}

function displayScope(item: BriefingArchiveItem): MarketScope {
  return normalizedScope(item.marketScope || item.scope);
}

function displayKind(item: BriefingArchiveItem): BriefingKind {
  return normalizedKind(item.kind);
}

/** 기간 판정은 서버와 같은 규칙이다 — 발행일과 세션일 중 **하나라도** 범위에 들면 통과한다
 *  (features/daily_briefing/archive.py::query의 `searchable_dates`).
 *
 *  발행일만 보면 카드에 `2026.08.07 마감`이라 적힌 미국장 브리핑(발행일 08-10 저장)이
 *  08-07로 기간을 잡은 순간 사라진다. 미국장·유럽장은 세션일과 발행일이 다른 날이다. */
export function archiveDateInRange(item: BriefingArchiveItem, start: string, end: string) {
  if (!start && !end) return true;
  const dates = [displayDate(item), item.sessionDate || ""].filter(Boolean);
  return dates.some((value) => (!start || value >= start) && (!end || value <= end));
}

function stableNoteKey(prefix: string, text: string) {
  const raw = String(text || prefix || "note");
  let hash = 2166136261;
  for (let i = 0; i < raw.length; i += 1) {
    hash ^= raw.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return `${prefix}-${hash.toString(36)}`;
}

function briefingNoteIdentity(date: string, scope: MarketScope) {
  return {
    id: stableNoteKey("brief", `${date}:${scope}`),
    noteType: "market_memo",
    title: date ? `브리핑 ${date} 투자 노트` : "브리핑 투자 노트",
    label: date ? `브리핑 ${date}` : "브리핑",
    topic: scope,
    reportKind: "briefing",
    reportId: date,
    linkedReports: [date ? `Daily Market Briefing — ${date}` : ""].filter(Boolean),
  };
}

function isAgentJob(value: unknown): value is AgentJob {
  const job = value as AgentJob;
  return Boolean(job?.id && isActiveJobStatus(job.status));
}

/** 고른 세션일에서 시장별 발행일이 갈리면 서버가 작업을 나눠 만든다.
 *  (미국장 금요일 세션의 발행일은 월요일, 한국장은 금요일 그대로) */
function splitJobs(value: unknown): AgentJob[] | null {
  const jobs = (value as { jobs?: unknown })?.jobs;
  return Array.isArray(jobs) && jobs.every(isAgentJob) ? (jobs as AgentJob[]) : null;
}

function splitReports(value: unknown): Briefing[] | null {
  const reports = (value as { reports?: unknown })?.reports;
  return Array.isArray(reports) && reports.length > 0 ? (reports as Briefing[]) : null;
}

async function pollAgentJob(job: AgentJob): Promise<AgentJob> {
  let current = job;
  while (isActiveJobStatus(current.status)) {
    await sleep(1000);
    current = await getJson<AgentJob>(`/api/jobs/${encodeURIComponent(current.id)}`);
  }
  if (current.status !== "done") throw new Error(current.message || current.error || "브리핑 생성에 실패했습니다.");
  return current;
}

export function BriefingRoute() {
  const contentRevision = useContentRevision("briefing");
  const [archive, setArchive] = useState<BriefingArchivePayload | null>(null);
  const [detailRoute, setDetailRoute] = useState<BriefingDetailRoute | null>(() => readBriefingDetailRoute());
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [actionStatus, setActionStatus] = useState("");
  const [actionBusy, setActionBusy] = useState("");
  // 생성 대상은 시장 집합이다. 하나만 고르면 그 시장, 여럿이면 각각 만들어진다.
  const [selectedMarkets, setSelectedMarkets] = useState<SingleMarket[]>(["us"]);
  // 관심 시장 범위가 생성 선택지의 상한이다. 범위 밖 시장은 체크박스가 사라진다.
  const { isSelected: marketInScope } = useMarketScope();
  const scopedMarkets = SINGLE_MARKETS.filter((market) => marketInScope(market));
  const marketScope = selectionScope(selectedMarkets);

  // 시장 순서는 계약을 따른다. 클릭 순서로 두면 같은 조합이 다르게 저장된다.
  function toggleMarket(market: SingleMarket) {
    setSelectedMarkets((current) => {
      const next = current.includes(market)
        ? current.filter((item) => item !== market)
        : [...current, market];
      // 전부 끄면 생성할 대상이 없다. 마지막 하나는 끄지 않는다.
      if (!next.length) return current;
      return SINGLE_MARKETS.filter((item) => next.includes(item));
    });
  }
  const [briefingType, setBriefingType] = useState("default");
  const [briefingKind, setBriefingKind] = useState<BriefingKind>("daily");
  const [briefingDate, setBriefingDate] = useState(() => todayIsoDate());
  const [archiveQuery, setArchiveQuery] = useState("");
  const [archiveMarket, setArchiveMarket] = useState<ArchiveMarketFilter>("all");
  const [archiveType, setArchiveType] = useState("all");
  const [archiveKind, setArchiveKind] = useState<ArchiveKindFilter>("all");
  const [archiveStart, setArchiveStart] = useState("");
  const [archiveEnd, setArchiveEnd] = useState("");
  const [archiveView, setArchiveView] = useState<ArchiveViewMode>("recent");
  const [proposalReloadKey, setProposalReloadKey] = useState(0);

  const loadArchive = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({
        offset: "0",
        limit: "100",
        q: archiveQuery,
        marketScope: archiveMarket,
        briefingType: archiveType,
        kind: archiveKind,
        dateFrom: archiveStart,
        dateTo: archiveEnd,
      });
      const payload = await getJson<BriefingArchivePayload>(`/api/briefings/index?${params}`);
      setArchive(payload);
      setReactAgentContextScope("briefing", { surface: "briefing", viewId: "briefing", reportKind: "", reportId: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "브리핑 목록을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, [archiveEnd, archiveKind, archiveMarket, archiveQuery, archiveStart, archiveType]);

  useEffect(() => {
    loadArchive();
  // 생성·수집이 어디서 일어나든 목록이 따라온다(자동화, 다른 탭, Agent 도크 포함).
  }, [loadArchive, contentRevision]);

  useEffect(() => {
    const handleHashChange = () => {
      if (!isBriefingHash()) return;
      setDetailRoute(readBriefingDetailRoute());
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
    async function loadDetail(date: string, scope: MarketScope, kind: BriefingKind) {
      setLoading(true);
      setError("");
      try {
        const payload = await getJson<Briefing>(`/api/briefings/${encodeURIComponent(date)}?includePersonal=true&marketScope=${encodeURIComponent(scope)}&kind=${encodeURIComponent(kind)}`);
        if (!alive) return;
        setBriefing(payload);
        setReactAgentContextScope("briefing", {
          surface: "briefing_reader",
          viewId: "briefing",
          reportKind: "briefing",
          reportId: date,
          marketScope: scope,
        });
      } catch (err) {
        if (!alive) return;
        setBriefing(null);
        setError(err instanceof Error ? err.message : "브리핑을 불러오지 못했습니다.");
      } finally {
        if (alive) setLoading(false);
      }
    }

    if (detailRoute) {
      loadDetail(detailRoute.date, detailRoute.scope, detailRoute.kind);
    } else {
      setBriefing(null);
      setReactAgentContextScope("briefing", { surface: "briefing", viewId: "briefing", reportKind: "", reportId: "" });
    }
    return () => {
      alive = false;
    };
  }, [detailRoute, proposalReloadKey]);

  async function exportBriefing(target: "notion" | "obsidian") {
    const date = briefing?.date || detailRoute?.date || "";
    const scope = normalizedScope(briefing?.marketScope || detailRoute?.scope);
    // **종류를 빼면 주간 보고서를 열어 두고 그날 일간을 내보낸다** — 주간의 저장 키는
    // 발행일이라 같은 날 일간과 날짜가 겹친다. 일간이 없는 날이면 404가 된다.
    const kind = normalizedKind(briefing?.kind || detailRoute?.kind);
    if (!date) return;
    setActionBusy(target);
    setActionStatus(target === "notion" ? "Notion에 내보내는 중..." : "Obsidian에 내보내는 중...");
    try {
      const query = `marketScope=${encodeURIComponent(scope)}&kind=${encodeURIComponent(kind)}`;
      const result = target === "notion"
        ? await postJson<ExportResult>(`/api/briefings/${encodeURIComponent(date)}/export-notion?${query}`, { marketScope: scope, kind })
        : await postJson<ExportResult>(`/api/briefings/${encodeURIComponent(date)}/export-obsidian?${query}`, { marketScope: scope, kind });
      if (target === "notion") {
        setActionStatus(result.notionUrl ? `Notion 내보냄: ${result.title || result.notionUrl}` : "Notion에 내보냈습니다.");
      } else {
        setActionStatus(`Obsidian 내보냄: ${result.filename || date}`);
      }
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : "내보내기에 실패했습니다.");
    } finally {
      setActionBusy("");
    }
  }

  async function generatePersonalOverlay() {
    const date = briefing?.date || detailRoute?.date || "";
    const scope = normalizedScope(briefing?.marketScope || detailRoute?.scope);
    // 종류를 빼면 개인 해석이 그날 **일간** 보고서에 얹히고, 이어지는 재조회가 화면의
    // 주간 보고서를 일간으로 바꿔치기한다.
    const kind = normalizedKind(briefing?.kind || detailRoute?.kind);
    if (!date) return;
    setActionBusy("overlay");
    setActionStatus("개인 해석을 생성하는 중...");
    try {
      const query = `marketScope=${encodeURIComponent(scope)}&kind=${encodeURIComponent(kind)}`;
      const response = await postJson<OverlayResult | AgentJob>(`/api/briefings/${encodeURIComponent(date)}/personal-overlay?${query}`, {
        marketScope: scope,
        kind,
      });
      if (isAgentJob(response)) await pollAgentJob(response);
      const updated = await getJson<Briefing>(`/api/briefings/${encodeURIComponent(date)}?includePersonal=true&${query}`);
      setBriefing(updated);
      setActionStatus("개인 해석을 생성했습니다.");
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : "개인 해석 생성에 실패했습니다.");
    } finally {
      setActionBusy("");
    }
  }

  async function deleteBriefing(date: string, scope: MarketScope, kind: BriefingKind = "daily") {
    if (!date) return;
    if (!window.confirm(`${date} ${SCOPE_LABELS[scope]} ${BRIEFING_KIND_LABELS[kind]} 브리핑을 삭제할까요?`)) return;
    setActionBusy(`delete-${date}-${scope}-${kind}`);
    try {
      // 통합 범위 삭제는 그 날짜 전체를 지운다. 시장 하나만 지울 때만 market을 붙인다.
      // `multi`도 통합이다 — 서버가 아는 단일 시장(us/kr/europe/jp)이 아니라서
      // `?market=multi`를 붙이면 400으로 되돌아왔다.
      //
      // **종류는 항상 붙인다.** 빼면 주간 카드의 삭제가 그날 일간 브리핑을 지운다.
      const isAggregate = scope === "both" || scope === "all" || scope === "multi";
      const params = new URLSearchParams({ kind });
      if (!isAggregate) params.set("market", scope);
      const query = `?${params}`;
      const res = await fetch(`/api/briefings/${encodeURIComponent(date)}${query}`, { method: "DELETE" });
      // 응답을 보지 않으면 400·404가 성공처럼 보이고 목록만 그대로 다시 그려진다.
      if (!res.ok) throw new Error(res.status === 404 ? "삭제할 브리핑을 찾지 못했습니다." : "브리핑 삭제에 실패했습니다.");
      await loadArchive();
    } catch (err) {
      setError(err instanceof Error ? err.message : "브리핑 삭제에 실패했습니다.");
    } finally {
      setActionBusy("");
    }
  }

  async function generateBriefing(targetDate?: string) {
    setGenerating(true);
    setError("");
    try {
      const strictDate = Boolean(targetDate);
      const response = await postJson<Briefing | AgentJob>("/api/briefings", {
        date: targetDate || undefined,
        strictDate,
        markets: selectedMarkets,
        briefingType,
        kind: briefingKind,
      });
      const jobs = splitJobs(response);
      if (jobs) {
        // 둘 다 끝나야 끝난 것이다. 하나만 기다리면 아직 만들어지지 않은 시장을
        // 아카이브에서 찾게 된다.
        const finished = await Promise.all(jobs.map(pollAgentJob));
        await loadArchive();
        const date = finished[0]?.result?.date || finished[0]?.result?.artifactId || "";
        if (date) setBriefingHash(date, marketScope, briefingKind);
        return;
      }
      if (isAgentJob(response)) {
        const done = await pollAgentJob(response);
        const date = done.result?.date || done.result?.artifactId || targetDate || "";
        await loadArchive();
        if (date) setBriefingHash(date, marketScope, briefingKind);
        return;
      }
      const reports = splitReports(response);
      if (reports) {
        await loadArchive();
        const first = reports[0];
        if (first?.date) setBriefingHash(first.date, normalizedScope(first.marketScope || marketScope), briefingKind);
        return;
      }
      const date = response.date || targetDate || "";
      await loadArchive();
      if (date) setBriefingHash(date, normalizedScope(response.marketScope || marketScope), briefingKind);
    } catch (err) {
      setError(err instanceof Error ? err.message : "브리핑 생성에 실패했습니다.");
    } finally {
      setGenerating(false);
    }
  }

  const items = archive?.items || [];
  // 검색어는 다시 거르지 않는다. 서버가 제목·요약·**본문**까지 합친 문자열로 이미
  // 필터링하는데(archive.py::_scan의 `searchText`), 화면이 제목·날짜·태그만으로 다시
  // 좁히면 본문이나 요약에서만 일치한 브리핑이 통째로 사라진다 — 안내 문구는
  // `제목·요약·본문 검색`인데 실측으로 내용 검색이 전부 0건이었다.
  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      const scope = displayScope(item);
      const type = item.briefingType || "default";
      // `aggregate`는 시장 하나가 아니라 다중 시장 카드 전체를 고른다.
      if (archiveMarket === "aggregate") {
        if (scope !== "all" && scope !== "both" && scope !== "multi") return false;
      } else if (archiveMarket !== "all" && scope !== archiveMarket) return false;
      if (archiveType !== "all" && type !== archiveType) return false;
      if (archiveKind !== "all" && displayKind(item) !== archiveKind) return false;
      return archiveDateInRange(item, archiveStart, archiveEnd);
    });
  }, [archiveEnd, archiveKind, archiveMarket, archiveStart, archiveType, items]);
  const visibleGroups = useMemo(() => {
    const sorted = [...filteredItems].sort((a, b) => String(displayDate(b) || b.generatedAt || "").localeCompare(String(displayDate(a) || a.generatedAt || "")));
    if (archiveView === "recent") {
      if (!sorted.length) return [];
      // 건수는 그룹 머리 오른쪽이 맡는다. 이름에 또 넣으면 같은 줄에 두 번 적힌다.
      return [{ label: "최근 브리핑", rows: sorted.slice(0, RECENT_BRIEFING_LIMIT) }];
    }
    if (archiveView === "month") {
      const byMonth = new Map<string, BriefingArchiveItem[]>();
      for (const item of sorted) {
        const key = formatArchiveMonth(displayDate(item));
        if (!byMonth.has(key)) byMonth.set(key, []);
        byMonth.get(key)?.push(item);
      }
      return Array.from(byMonth.entries()).map(([label, rows]) => ({ label, rows }));
    }
    // 0.5는 네 시장이다. us/kr만 두면 유럽·일본 브리핑이 시장별 보기에서 사라진다.
    const order: MarketScope[] = ["us", "kr", "europe", "jp", "both"];
    return order
      .map((scope) => ({
        label: `${SCOPE_LABELS[scope]} 시장`,
        rows: sorted.filter((item) => displayScope(item) === scope),
      }))
      .filter((group) => group.rows.length > 0);
  }, [archiveView, filteredItems]);
  const readerContent = useMemo(() => splitReportTitle(briefing?.markdown || "", briefing?.title || "시장 브리핑"), [briefing?.markdown, briefing?.title]);
  const readerTitle = briefing?.title || readerContent.title;
  const publicationDate = briefing?.publicationDate || briefing?.date || detailRoute?.date || "";

  if (detailRoute && briefing) {
    return (
      <div className="react-briefing-route" data-briefing-route>
        {error && <p className="react-dashboard-error">{error}</p>}
        <ReportReaderShell
          eyebrow={detailRoute.kind === "weekly" ? "WEEKLY BRIEFING" : "DAILY BRIEFING"}
          title={readerTitle}
          meta={`${formatArchiveDate(publicationDate)} KST 발행`}
          agentContext={{
            surface: "briefing_reader",
            viewId: "briefing",
            reportKind: "briefing",
            reportId: briefing.date || detailRoute.date,
            marketScope: normalizedScope(briefing.marketScope || detailRoute.scope),
          }}
          breadcrumb={(
            <>
              <button type="button" onClick={() => setBriefingHash()}>
                브리핑
              </button>
              <span>{readerTitle}</span>
            </>
          )}
          onClose={() => setBriefingHash()}
          actionSlot={(
            <>
              <ReaderActionGroup title="AI">
                <ReaderActionButton
                  icon="agent"
                  onClick={() => openReactAgentDock({
                    surface: "briefing_reader",
                    reportKind: "briefing",
                    reportId: briefing.date || detailRoute.date,
                    marketScope: normalizedScope(briefing.marketScope || detailRoute.scope),
                    message: `${readerTitle}의 핵심과 투자 판단 체크포인트를 요약해줘.`,
                    autoSubmit: true,
                  })}
                >
                  Agent에게 묻기
                </ReaderActionButton>
              </ReaderActionGroup>
              <ReaderActionGroup title="노트">
                <ReaderActionButton icon="link" disabled={actionBusy === "overlay"} onClick={generatePersonalOverlay}>
                  {actionBusy === "overlay" ? "생성 중" : "내 노트와 연결"}
                </ReaderActionButton>
              </ReaderActionGroup>
              <ReaderActionGroup title="내보내기">
                <ReaderActionButton icon="notion" disabled={actionBusy === "notion"} onClick={() => exportBriefing("notion")}>
                  {actionBusy === "notion" ? "내보내는 중" : "Notion으로 내보내기"}
                </ReaderActionButton>
                <ReaderActionButton icon="obsidian" disabled={actionBusy === "obsidian"} onClick={() => exportBriefing("obsidian")}>
                  {actionBusy === "obsidian" ? "내보내는 중" : "Obsidian으로 내보내기"}
                </ReaderActionButton>
              </ReaderActionGroup>
              {actionStatus && <p className="react-reader-status">{actionStatus}</p>}
            </>
          )}
          noteIdentity={briefingNoteIdentity(
            briefing.date || detailRoute.date,
            normalizedScope(briefing.marketScope || detailRoute.scope),
          )}
          noteLinkedTitle={readerTitle}
          noteOverlay={parsePersonalOverlayPayload(briefing.personalOverlay, briefing.canonicalRevision)}
        >
          <BriefingChangeStrip summary={briefing.changeSummary} />
          <ReportBody
            markdown={readerContent.body || briefing.markdown || ""}
            marketScope={normalizedScope(briefing.marketScope || detailRoute.scope)}
            briefing={briefing}
            sourcePanelHtml={legacyBridge().briefingSourcePanelHtml?.(briefing) || ""}
          />
        </ReportReaderShell>
      </div>
    );
  }

  return (
    <div className="react-briefing-route" data-briefing-route>
      <RouteHero
        eyebrow="Briefing"
        title="브리핑"
        description="수집된 최신 뉴스와 시장 데이터로 미국·한국·유럽·일본장 흐름을 요약합니다."
        actions={(
          <button className="btn" type="button" onClick={loadArchive} disabled={loading}>
            {loading ? "불러오는 중" : "새로고침"}
          </button>
        )}
      />

      <section className="brief-gen-box input-panel react-briefing-generation" aria-label="브리핑 생성">
        <section className="brief-gen-panel brief-gen-settings">
          <div className="brief-gen-panel-head">
            <h3>브리핑 설정</h3>
          </div>
          <div className="brief-gen-settings-row">
            <div className="brief-gen-field brief-gen-market-field">
              <div className="brief-market-segment" role="group" aria-label="생성할 시장" data-scope={marketScope}>
                <span className="brief-market-segment-title">시장</span>
                {(scopedMarkets.length ? scopedMarkets : SINGLE_MARKETS).map((value) => (
                  <label key={value}>
                    <input
                      type="checkbox"
                      name="reactBriefingMarkets"
                      value={value}
                      checked={selectedMarkets.includes(value)}
                      onChange={() => toggleMarket(value)}
                    />
                    <span>{MARKET_CHOICE_LABELS[value]}</span>
                  </label>
                ))}
              </div>
            </div>
            <label className="gen-option quality-option">
              <span>종류</span>
              <select
                value={briefingKind}
                onChange={(event) => setBriefingKind(event.currentTarget.value as BriefingKind)}
              >
                {Object.entries(BRIEFING_KIND_LABELS).map(([value, label]) => (
                  <option value={value} key={value}>{label}</option>
                ))}
              </select>
            </label>
            {/* 편집 강조점은 일간 골격 위에서만 뜻이 있다. 주간은 섹션 구성이 달라
                이 셋("기존 섹션 구성을 유지")이 성립하지 않는다. */}
            {briefingKind === "daily" && (
              <label className="gen-option quality-option">
                <span>유형</span>
                <select value={briefingType} onChange={(event) => setBriefingType(event.currentTarget.value)}>
                  {Object.entries(BRIEFING_TYPE_LABELS).map(([value, label]) => (
                    <option value={value} key={value}>{label}</option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <div className="brief-gen-actionbar">
            <button className="btn btn--primary" type="button" onClick={() => generateBriefing()} disabled={generating}>
              {generating ? "생성 중" : briefingKind === "weekly" ? "이번 주 요약 생성" : "오늘 브리핑 생성"}
            </button>
            <span className="brief-gen-alt">또는</span>
            {/* 일간은 발행일이 아니라 시장 세션일이다(미국장 8/3 세션은 8/4에 발행).
                주간에는 세션이 없어 이 값이 곧 발행일이고, 지난 7일이 그 구간이다. */}
            <input
              type="date"
              value={briefingDate}
              onChange={(event) => setBriefingDate(event.currentTarget.value)}
              aria-label={briefingKind === "weekly" ? "주간 발행일" : `${SCOPE_LABELS[marketScope]} 기준일`}
              title={briefingKind === "weekly"
                ? "이 날짜까지의 지난 7일을 요약하고 다음주 일정을 붙입니다"
                : `${SCOPE_LABELS[marketScope]} 세션 기준일`}
            />
            <button className="btn" type="button" onClick={() => generateBriefing(briefingDate)} disabled={generating || !briefingDate}>
              {briefingKind === "weekly" ? "이 날짜까지 요약" : "이 기준일로 생성"}
            </button>
          </div>
        </section>
      </section>

      {error && <p className="react-dashboard-error">{error}</p>}

      {/* 찾기 바. 필터가 패널 안(검색·날짜)과 패널 밖(시장·유형·보기)으로 갈라져 있었다.
          한 줄에 모으고 건수는 목록 헤더로 올린다. */}
      <section className="find-bar" aria-label="저장 브리핑 검색">
        <input
          className="find-bar__search"
          type="search"
          value={archiveQuery}
          onChange={(event) => setArchiveQuery(event.currentTarget.value)}
          placeholder="제목·요약·본문 검색"
          aria-label="저장 브리핑 검색"
        />
        <label className="find-bar__field">
          <span>시장</span>
          <select
            aria-label="브리핑 시장"
            value={archiveMarket}
            onChange={(event) => setArchiveMarket(event.currentTarget.value as ArchiveMarketFilter)}
          >
            <option value="all">전체</option>
            <option value="us">미국장</option>
            <option value="kr">한국장</option>
            <option value="europe">유럽장</option>
            <option value="jp">일본장</option>
            <option value="aggregate">종합 보고서</option>
          </select>
        </label>
        <label className="find-bar__field">
          <span>종류</span>
          <select
            aria-label="브리핑 종류"
            value={archiveKind}
            onChange={(event) => setArchiveKind(event.currentTarget.value as ArchiveKindFilter)}
          >
            <option value="all">전체</option>
            {Object.entries(BRIEFING_KIND_LABELS).map(([value, label]) => (
              <option value={value} key={value}>{label}</option>
            ))}
          </select>
        </label>
        <label className="find-bar__field">
          <span>유형</span>
          <select
            aria-label="브리핑 유형"
            value={archiveType}
            onChange={(event) => setArchiveType(event.currentTarget.value)}
          >
            <option value="all">전체</option>
            {Object.entries(BRIEFING_TYPE_LABELS).map(([value, label]) => (
              <option value={value} key={value}>{label}</option>
            ))}
          </select>
        </label>
        <label className="find-bar__field">
          <span>기간</span>
          <input type="date" aria-label="시작일" value={archiveStart} onChange={(event) => setArchiveStart(event.currentTarget.value)} />
          <input type="date" aria-label="종료일" value={archiveEnd} onChange={(event) => setArchiveEnd(event.currentTarget.value)} />
        </label>
        <label className="find-bar__field">
          <span>보기</span>
          <select
            aria-label="브리핑 보기 방식"
            value={archiveView}
            onChange={(event) => setArchiveView(event.currentTarget.value as ArchiveViewMode)}
          >
            <option value="recent">최근</option>
            <option value="month">월별</option>
            <option value="market">시장별</option>
          </select>
        </label>
        <button
          className="btn btn--text find-bar__reset"
          type="button"
          onClick={() => {
            setArchiveQuery("");
            setArchiveMarket("all");
            setArchiveType("all");
            setArchiveKind("all");
            setArchiveStart("");
            setArchiveEnd("");
            setArchiveView("recent");
          }}
        >
          초기화
        </button>
      </section>

      {/* 레거시 briefing-archive-card 클래스를 그대로 재사용해 디자인 언어를 통일한다. */}
      <section className="briefing-archive-feed" aria-label="저장 브리핑">
        <div className="react-section-heading">
          <div>
            <p className="section-kicker">Saved Briefings</p>
            <h2>저장된 브리핑</h2>
          </div>
          <span aria-live="polite">
            {loading ? "불러오는 중..." : `${filteredItems.length}건${archiveQuery ? " · 검색 결과" : ""}`}
          </span>
        </div>
        {visibleGroups.length ? visibleGroups.map((group) => (
          <div className="briefing-archive-date-group" key={group.label}>
            <div className="report-feed-group-head">
              <span className="report-feed-group-name">{group.label}</span>
              <span className="report-feed-group-meta">{groupMeta(group.rows.length, group.rows[0]?.generatedAt)}</span>
            </div>
            {group.rows.map((item) => {
              const view = archiveCardView(item);
              const deleting = actionBusy === `delete-${view.date}-${view.scope}-${view.kind}`;
              return (
                <div className="briefing-archive-card-wrap" key={item.id || `${view.date}-${view.scope}-${view.kind}`}>
                  <button
                    type="button"
                    className={`briefing-archive-card is-${view.scope}`}
                    onClick={() => view.date && setBriefingHash(view.date, view.scope, view.kind)}
                  >
                    <span className="briefing-archive-card-meta">
                      <span className="briefing-archive-market">{MARKET_BADGE[view.scope]}</span>
                      {view.chips.map((chip) => (
                        <span className="chip briefing-archive-chip" key={chip}>{chip}</span>
                      ))}
                      {view.engine && (
                        <span className="chip briefing-archive-chip">{view.engine}</span>
                      )}
                    </span>
                    <strong>{view.title}</strong>
                    <span className="briefing-archive-card-foot">{view.foot}</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn--icon briefing-archive-card-delete"
                    disabled={deleting}
                    onClick={() => deleteBriefing(view.date, view.scope, view.kind)}
                    aria-label={`${view.date} ${BRIEFING_KIND_LABELS[view.kind]} 브리핑 삭제`}
                    data-tooltip="삭제"
                    data-tooltip-pos="bottom"
                  >
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M2.5 4h11M6 4V2.5h4V4M5 4l.5 9h5L11 4" />
                    </svg>
                  </button>
                </div>
              );
            })}
          </div>
        )) : (
          <div className="briefing-archive-empty">조건에 맞는 저장 브리핑이 없습니다.</div>
        )}
      </section>
    </div>
  );
}
