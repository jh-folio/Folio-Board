import { useCallback, useEffect, useMemo, useState, useRef } from "react";
import { useContentRevision } from "./useContentRevision";
import { useMarketScope } from "./useMarketScope";
import { getJson, isActiveJobStatus, postJson, type JobStatus } from "../api";
import { setReactAgentContextScope } from "./agentContext";
import { RouteHero } from "./RouteHero";

type RssItem = {
  title?: string;
  url?: string;
  description?: string;
  media?: string;
  source?: string;
  markets?: string[] | string;
  market?: string;
  timestamp?: string;
  date?: string;
};

type RssPayload = {
  items?: RssItem[];
  total?: number;
  offset?: number;
  limit?: number;
  has_more?: boolean;
  sources?: string[];
  languages?: string[];
};

type RssFilters = {
  start: string;
  end: string;
  source: string;
  market: string;
  language: string;
};

type SearchDocument = {
  title?: string;
  headline?: string;
  url?: string;
  sourceUrl?: string;
  link?: string;
  summary?: string;
  snippet?: string;
  text?: string;
  content?: string;
  media?: string;
  source?: string;
  collector?: string;
  timestamp?: string;
  date?: string;
  publishedAt?: string;
  published?: string;
  path?: string;
};

type AgentJob = {
  id: string;
  kind?: string;
  status: JobStatus;
  message?: string;
  error?: string;
  result?: Record<string, unknown>;
};

// 서버가 돌려주는 것은 코드(`workspace_moved`)뿐이다. 안내문에는 원본·목적지 경로가
// 실릴 수 있어 결과에 담지 않고 화면이 갖는다.
const WORKSPACE_MOVED_NOTICE =
  "자료 위치를 옮겼습니다. 서버를 재시작하기 전까지는 RSS 수집과 보관 기간 정리를 실행하지 않습니다 — 지금 수집하면 새 자료가 옛 폴더와 새 폴더로 갈립니다.";

const EMPTY_FILTERS: RssFilters = { start: "", end: "", source: "", market: "", language: "" };
const pageSize = 20;
const MARKET_OPTIONS = [
  { value: "", label: "전체 시장" },
  { value: "US", label: "미국" },
  { value: "KR", label: "한국" },
  { value: "EUROPE", label: "유럽" },
  { value: "JP", label: "일본" },
  { value: "GLOBAL", label: "글로벌" },
];

// 국가 필터는 없앴다. 태그된 피드에서 언어와 정확히 1:1이었고(DE↔de, FR↔fr, …) 국제
// 통신사(Reuters·FT)에서는 정의 자체가 안 됐다. 축은 셋이다 — 시장은 "무엇에 대한
// 기사인가", 언어는 "읽을 수 있는가", 소스는 "어느 매체인가".
const LANGUAGE_LABELS: Record<string, string> = {
  en: "영어", de: "독일어", fr: "프랑스어", nl: "네덜란드어", it: "이탈리아어", es: "스페인어", ja: "일본어", ko: "한국어",
};

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function displayTimestamp(item: RssItem) {
  const raw = item.timestamp || item.date || "";
  if (!raw) return "시간 정보 없음";
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? raw : parsed.toLocaleString("ko-KR");
}

function filterLabel(filters: RssFilters) {
  const parts = [
    filters.start ? `${filters.start} 이후` : "",
    filters.end ? `${filters.end} 이전` : "",
    filters.source ? filters.source : "",
    filters.market ? MARKET_OPTIONS.find((item) => item.value === filters.market)?.label || filters.market : "",
    filters.language ? LANGUAGE_LABELS[filters.language] || filters.language : "",
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "전체 RSS 피드";
}

function buildParams(page: number, filters: RssFilters) {
  const params = new URLSearchParams({
    offset: String((Math.max(1, page) - 1) * pageSize),
    limit: String(pageSize),
  });
  if (filters.start) params.set("start", filters.start);
  if (filters.end) params.set("end", filters.end);
  if (filters.source) params.set("source", filters.source);
  if (filters.market) params.set("market", filters.market);
  if (filters.language) params.set("language", filters.language);
  return params;
}

function normalizeMarketTags(item: Pick<RssItem, "markets" | "market">) {
  const rawMarkets = item.markets;
  const values = Array.isArray(rawMarkets)
    ? rawMarkets
    : typeof rawMarkets === "string"
      ? rawMarkets.split(",")
      : String(item.market || "").split(",");
  const seen = new Set<string>();
  return values
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .filter((value) => {
      if (seen.has(value)) return false;
      seen.add(value);
      return true;
    });
}

async function pollJob(job: AgentJob): Promise<AgentJob> {
  let current = job;
  while (isActiveJobStatus(current.status)) {
    await sleep(1000);
    current = await getJson<AgentJob>(`/api/jobs/${encodeURIComponent(current.id)}`);
  }
  if (current.status !== "done") {
    throw new Error(current.message || current.error || "RSS 수집 작업에 실패했습니다.");
  }
  return current;
}

function stableItemKey(item: RssItem, index: number) {
  return item.url || `${item.title || "rss"}-${item.timestamp || item.date || index}`;
}

function mapSearchDocument(doc: SearchDocument): RssItem {
  return {
    title: doc.title || doc.headline || doc.path || "검색 결과",
    url: doc.url || doc.sourceUrl || doc.link || "",
    description: doc.summary || doc.snippet || doc.text || doc.content || "",
    media: doc.media || doc.source || doc.collector || "",
    source: doc.source || doc.media || doc.collector || "",
    markets: normalizeMarketTags({
      markets: (doc as { markets?: unknown }).markets as RssItem["markets"],
      market: String((doc as { market?: string }).market || ""),
    }),
    market: String((doc as { market?: string }).market || ""),
    timestamp: doc.timestamp || doc.date || doc.publishedAt || doc.published || "",
    date: doc.date || doc.publishedAt || doc.published || doc.timestamp || "",
  };
}

export function RssRoute() {
  // 관심 시장 범위가 필터의 상한이다. 범위 밖 시장은 선택지에서 사라진다.
  const { isSelected } = useMarketScope();
  const contentRevision = useContentRevision("rss");
  const [indexedCount, setIndexedCount] = useState<number | null>(null);
  const [payload, setPayload] = useState<RssPayload | null>(null);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<RssFilters>(EMPTY_FILTERS);
  const [draftFilters, setDraftFilters] = useState<RssFilters>(EMPTY_FILTERS);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  // 검색 결과는 한 번에 다 받은 목록이라 페이지가 없다. 그런데 payload를 통째로
  // 갈아끼우다 보니 `total`이 결과 수로 바뀌어도 페이지 계산은 그대로 돌았고,
  // 페이지 버튼을 누르면 검색 결과가 아니라 일반 피드로 되돌아갔다.
  const [searchMode, setSearchMode] = useState(false);

  const items = payload?.items || [];
  const total = payload?.total ?? items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const sources = useMemo(() => payload?.sources || [], [payload?.sources]);
  const languages = useMemo(() => payload?.languages || [], [payload?.languages]);

  const loadItems = useCallback(async (nextPage = page, nextFilters = filters) => {
    setLoading(true);
    setError("");
    try {
      const params = buildParams(nextPage, nextFilters);
      const nextPayload = await getJson<RssPayload>(`/api/rss/items?${params.toString()}`);
      setPayload(nextPayload);
      setSearchMode(false);
      setPage(nextPage);
      setFilters(nextFilters);
      setDraftFilters(nextFilters);
      setReactAgentContextScope("rss", { surface: "rss", viewId: "rssfeed", reportKind: "", reportId: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "RSS 피드를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  const refreshIndexedCount = useCallback(async () => {
    try {
      const dashboard = await getJson<{ index?: { newsCount?: number; count?: number } }>("/api/dashboard");
      const count = dashboard.index?.newsCount ?? dashboard.index?.count;
      if (Number.isFinite(Number(count))) setIndexedCount(Number(count));
    } catch {
      // 색인 수치 조회 실패는 피드 로딩과 무관하므로 조용히 무시한다.
    }
  }, []);

  useEffect(() => {
    loadItems(1, filters);
    refreshIndexedCount();
    // 첫 진입 시 한 번만 현재 필터를 로드한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 수집이 끝나면 목록이 따라온다. 자동화가 돌렸든 다른 탭에서 돌렸든 같다.
  // 첫 렌더의 기준점 잡기는 훅이 하므로 여기서 다시 읽지 않는다.
  const firstRevision = useRef(true);
  useEffect(() => {
    if (firstRevision.current) {
      firstRevision.current = false;
      return;
    }
    void loadItems(1, filters);
    void refreshIndexedCount();
    // 신호에만 반응한다. 필터 변경은 각자의 핸들러가 이미 다시 읽는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contentRevision]);

  async function updateFilter(patch: Partial<RssFilters>) {
    const next = { ...draftFilters, ...patch };
    setDraftFilters(next);
    if (next.start && next.end && next.start > next.end) {
      setError("시작 시간은 종료 시간보다 앞서야 합니다.");
      return;
    }
    setError("");
    setStatus("");
    await loadItems(1, next);
  }

  async function clearFilters() {
    setStatus("");
    setSearchQuery("");
    setDraftFilters(EMPTY_FILTERS);
    await loadItems(1, EMPTY_FILTERS);
  }

  // 필터 폼 안의 버튼에서도 호출되므로 이벤트 없이도 동작해야 한다.
  async function searchNews(event?: React.SyntheticEvent) {
    event?.preventDefault();
    const query = searchQuery.trim();
    if (!query) {
      setError("검색어를 입력해 주세요.");
      return;
    }
    setSearching(true);
    setError("");
    setStatus("");
    try {
      const params = new URLSearchParams({ query, scope: "news", limit: "50" });
      const result = await getJson<SearchDocument[] | { items?: SearchDocument[] }>(`/api/search?${params.toString()}`);
      const rows = Array.isArray(result) ? result : result.items || [];
      setPayload({
        items: rows.map(mapSearchDocument),
        total: rows.length,
        offset: 0,
        limit: rows.length,
        has_more: false,
        sources,
      });
      setSearchMode(true);
      setPage(1);
      setStatus(`뉴스 검색 결과 ${rows.length}개`);
      setReactAgentContextScope("rss", { surface: "rss", viewId: "rssfeed", reportKind: "news_search", reportId: query });
    } catch (err) {
      setError(err instanceof Error ? err.message : "뉴스 검색에 실패했습니다.");
    } finally {
      setSearching(false);
    }
  }

  async function importRss() {
    setImporting(true);
    setError("");
    setStatus("RSS 수집 작업을 시작했습니다.");
    try {
      const job = await postJson<AgentJob>("/api/rssarchive/import", {});
      const done = await pollJob(job);
      // 자료 위치를 옮긴 뒤 재시작 전까지는 수집이 쉰다. 그 사실을 말하지 않으면
      // "신규 0개"로 보여서, 수집이 도는 줄 알고 며칠을 보낸다.
      if (done.result?.skipped === "workspace_moved") {
        setStatus(WORKSPACE_MOVED_NOTICE);
        return;
      }
      const added = Number.isFinite(Number(done.result?.added)) ? ` 신규 ${done.result?.added}개` : "";
      setStatus(`RSS 수집 완료.${added}`);
      await loadItems(1, filters);
      await refreshIndexedCount();
    } catch (err) {
      setError(err instanceof Error ? err.message : "RSS 수집에 실패했습니다.");
      setStatus("");
    } finally {
      setImporting(false);
    }
  }

  const currentPage = Math.min(Math.max(page, 1), totalPages);
  const pageStart = Math.max(1, currentPage - 2);
  const pageEnd = Math.min(totalPages, currentPage + 2);
  // 검색 결과에는 `1/N` 쪽수를 붙이지 않는다. 넘길 페이지가 없다.
  const countLabel = total > 0 ? (searchMode ? `${total}개` : `${total}개 · ${currentPage}/${totalPages}`) : "0개";

  return (
    <div className="react-rss-route" data-rss-route>
      <RouteHero
        eyebrow="RSS Feed"
        title="RSS 피드"
        description="시장·국가·언어·기간·소스로 좁히거나 본문까지 검색합니다. 시간은 UTC+9 기준입니다."
        actions={(
          <div className="react-rss-hero-actions">
            <span className="react-rss-stat-pill">
              <strong>LOADED</strong>
              {countLabel}
            </span>
            <span className="react-rss-stat-pill">
              <strong>INDEXED</strong>
              {indexedCount === null ? "…" : `${indexedCount}개 문서`}
            </span>
            <button className="btn btn--primary" type="button" onClick={importRss} disabled={importing}>
              {importing ? "수집 중" : "RSS 수집/가져오기"}
            </button>
          </div>
        )}
      />

      {/* 필터 표면이 셋으로 흩어져 있었다: 기간·소스 폼, 별도 검색 폼, 그리고 목록 옆에서
          즉시 적용되던 시장 드롭다운. 한 패널에 같은 양식으로 모으고 적용 방식도 통일한다.
          시장·국가·언어가 함께 있어야 유럽 6개국을 갈라 볼 수 있다. */}
      {/* 필터 표면이 셋으로 흩어져 있었다: 기간·소스 폼, 별도 검색 폼, 목록 옆에서 즉시
          적용되던 시장 드롭다운. 한 패널로 모으되 두 동작은 구분해 둔다 — 검색은 본문까지
          훑어 다른 결과 목록을 만들고, 필터는 지금 보는 피드를 좁힌다. */}
      <section className="find-bar find-bar--stacked" aria-label="RSS 필터와 검색">
        <div className="find-bar__row">
          <input
            type="search"
            aria-label="본문 검색어"
            value={searchQuery}
            placeholder="기업, 티커, 섹터 또는 이슈"
            onChange={(event) => setSearchQuery(event.currentTarget.value)}
            onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); searchNews(); } }}
            className="find-bar__search"
          />
          <button className="btn" type="button" onClick={() => searchNews()} disabled={searching}>
            {searching ? "검색 중" : "본문 검색"}
          </button>
        </div>

        <div className="find-bar__more">
          <label className="find-bar__field">
            <span>시장</span>
            <select value={draftFilters.market} onChange={(event) => void updateFilter({ market: event.currentTarget.value })}>
              {MARKET_OPTIONS.filter((option) => !option.value || isSelected(option.value)).map((option) => (
                <option key={option.value || "all-market"} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className="find-bar__field">
            <span>소스</span>
            <select value={draftFilters.source} onChange={(event) => void updateFilter({ source: event.currentTarget.value })}>
              <option value="">전체 소스</option>
              {sources.map((source) => <option key={source} value={source}>{source}</option>)}
            </select>
          </label>
          <label className="find-bar__field">
            <span>기간</span>
            <input type="datetime-local" aria-label="시작" value={draftFilters.start} onChange={(event) => void updateFilter({ start: event.currentTarget.value })} />
            <input type="datetime-local" aria-label="종료" value={draftFilters.end} onChange={(event) => void updateFilter({ end: event.currentTarget.value })} />
          </label>
          {/* 언어는 시장과 겹치는 좁힘 조건이라 평소에는 접어 둔다.
              한 줄에 다 늘어놓으면 매일 쓰는 시장·소스가 묻힌다. */}
          <details className="find-bar__detail">
            <summary>상세</summary>
            <label className="find-bar__field">
              <span>언어</span>
              <select value={draftFilters.language} onChange={(event) => void updateFilter({ language: event.currentTarget.value })}>
                <option value="">전체 언어</option>
                {languages.map((code) => <option key={code} value={code}>{LANGUAGE_LABELS[code] || code}</option>)}
              </select>
            </label>
          </details>
          <button className="btn btn--text find-bar__reset" type="button" onClick={clearFilters} disabled={loading}>초기화</button>
        </div>
      </section>

      <div className="react-rss-summary">
        <strong>{searchMode ? `"${searchQuery.trim()}" 검색 결과` : filterLabel(filters)}</strong>
        <span>{countLabel}</span>
      </div>

      {error && <p className="react-dashboard-error">{error}</p>}
      {status && <p className="react-dashboard-warning">{status}</p>}

      <section className="react-rss-feed" aria-label="RSS feed items">
        {items.length ? items.map((item, index) => {
          const key = stableItemKey(item, index);
          const description = String(item.description || "").trim();
          const marketTags = normalizeMarketTags(item);
          return (
            <article className="react-rss-card" key={key}>
              <div className="react-rss-card-main">
                <h2>
                  {item.url ? (
                    <a href={item.url} target="_blank" rel="noopener noreferrer">{item.title || "제목 없음"}</a>
                  ) : item.title || "제목 없음"}
                </h2>
                <div className="react-rss-card-meta">
                  {/* 매체 이름은 고유명사다 — 대문자로 바꾸거나 자간을 벌리지 않는다.
                      레거시 `.pill`이 그렇게 했고 한글 매체명은 자간만 늘어났다. */}
                  {(item.media || item.source) && <span className="chip">{item.media || item.source}</span>}
                  {marketTags.length ? (
                    <span className="chip">{marketTags.join(" · ")}</span>
                  ) : null}
                  <span>{displayTimestamp(item)}</span>
                </div>
                {description && <p>{description}</p>}
              </div>
              <div className="react-rss-card-actions">
                {item.url && <a className="btn" href={item.url} target="_blank" rel="noopener noreferrer">기사 열기</a>}
              </div>
            </article>
          );
        }) : (
          <article className="react-dashboard-panel">
            <h2>{loading ? "불러오는 중" : "표시할 RSS 피드가 없습니다."}</h2>
            <p>{loading ? "수집된 항목을 확인하고 있습니다." : "RSS 수집을 실행하거나 필터를 초기화해 보세요."}</p>
          </article>
        )}
      </section>

      {!searchMode && totalPages > 1 && (
        <nav className="react-rss-pagination" aria-label="RSS pagination">
          <button className="btn" type="button" disabled={currentPage === 1 || loading} onClick={() => loadItems(currentPage - 1, filters)}>
            이전
          </button>
          {pageStart > 1 && (
            <>
              <button className="btn" type="button" onClick={() => loadItems(1, filters)}>1</button>
              {pageStart > 2 && <span>...</span>}
            </>
          )}
          {Array.from({ length: pageEnd - pageStart + 1 }, (_, index) => pageStart + index).map((pageNumber) => (
            <button
              className="btn"
              type="button"
              key={pageNumber}
              aria-current={pageNumber === currentPage ? "page" : undefined}
              disabled={loading}
              onClick={() => loadItems(pageNumber, filters)}
            >
              {pageNumber}
            </button>
          ))}
          {pageEnd < totalPages && (
            <>
              {pageEnd < totalPages - 1 && <span>...</span>}
              <button className="btn" type="button" onClick={() => loadItems(totalPages, filters)}>{totalPages}</button>
            </>
          )}
          <button className="btn" type="button" disabled={currentPage === totalPages || loading} onClick={() => loadItems(currentPage + 1, filters)}>
            다음
          </button>
        </nav>
      )}
    </div>
  );
}
