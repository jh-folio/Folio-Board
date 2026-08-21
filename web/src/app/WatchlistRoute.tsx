import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useCompanyResolution } from "./companyAnalysis/useCompanyResolution";
import { getJson, postJson } from "../api";
import { setReactAgentContextScope } from "./agentContext";
import { RouteHero } from "./RouteHero";
import { useThemePreference } from "./themePreference";
import { ConsultationEntry } from "./watchlist/ConsultationEntry";
import {
  ddayLabel,
  fetchNextEarnings,
  formatEarningsDate,
  isEstimated,
  type EarningsEvent,
} from "./watchlistEarnings";

type WatchlistOverviewItem = {
  item?: string;
  ticker?: string;
  companyName?: string;
  name?: string;
  tags?: string[];
  count?: number;
};

type WatchlistCompany = {
  name?: string;
  ticker?: string;
  market?: string;
  tradingViewSymbol?: string;
};

type WatchlistNews = {
  source?: string;
  date?: string;
  title?: string;
  url?: string;
  path?: string;
  snippet?: string;
};

type WatchlistDetail = {
  item?: string;
  company?: WatchlistCompany;
  news?: WatchlistNews[];
  newsCount?: number;
  warnings?: string[];
};

function normalizeItems(items: unknown[]) {
  const seen = new Set<string>();
  return items
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .filter((item) => {
      const key = item.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function cardTicker(item: WatchlistOverviewItem) {
  return item.ticker || item.item || "";
}

function cardCompanyName(item: WatchlistOverviewItem) {
  return item.companyName || item.name || item.item || cardTicker(item);
}

function detailLabel(detail: WatchlistDetail | null, fallback = "") {
  return detail?.company?.name || detail?.item || fallback || "상세 보기";
}

function detailMeta(detail: WatchlistDetail | null) {
  if (!detail) return "상세 정보를 불러오는 중입니다.";
  const company = detail.company || {};
  return [
    company.ticker || "",
    company.market || "",
    company.tradingViewSymbol || "",
    detail.newsCount ? `${detail.newsCount}개 뉴스` : "",
  ].filter(Boolean).join(" · ") || "확인된 심볼 정보가 없습니다.";
}

function sortNewsLatestFirst(news: WatchlistNews[] = []) {
  return [...news].sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")));
}

function newsTitle(news: WatchlistNews) {
  return news.title || news.url || news.path || "자료";
}

function sourceLabel(news: WatchlistNews) {
  return [news.source, news.date].filter(Boolean).join(" · ");
}

// 회사 정식명에 붙는 법인 형태. 이것만 남은 조각은 종목도 주제도 아니다.
const LEGAL_SUFFIX_ONLY = /^(?:co|inc|ltd|corp|llc|plc|ag|nv|sa|se|kk|gmbh|s\.?a\.?s|co\.?,?\s*ltd)\.?$/i;

/** 입력을 등록할 항목들로 가른다.
 *
 * 쉼표는 여러 개를 한 번에 넣는 구분자이면서 동시에 회사 정식명의 일부다
 * (`Hitachi, Ltd.` · `Nintendo Co., Ltd.`). 그래서 후보에서 고른 이름을 그대로
 * 쪼개 `Hitachi`와 `Ltd.` 두 개가 등록됐고, 남은 `Ltd.`는 아무 회사도 아닌 채
 * 이후 모든 목록 갱신에서 검색과 회사해석을 계속 차지했다. 일본 기업은 정식명에
 * `, Ltd.`가 붙는 경우가 많아 일본 종목을 추가할 때마다 이 항목이 하나씩 늘었다.
 *
 * 입력 전체가 이미 한 회사로 해석됐다면 쪼개지 않는다. 쪼개는 것은 사용자가 직접
 * 여러 개를 나열했을 때뿐이고, 그때도 법인 형태만 남은 조각은 버린다.
 */
export function splitAddInput(raw: string, resolvedWhole: boolean) {
  const text = String(raw || "").trim();
  if (!text) return [];
  if (resolvedWhole) return [text];
  return text
    .split(/[,;\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => !LEGAL_SUFFIX_ONLY.test(item));
}

function setWatchlistHash(item?: string) {
  window.location.hash = item ? `#/watchlist/${encodeURIComponent(item)}` : "#/watchlist";
}

function readWatchlistDetailItem() {
  const match = window.location.hash.match(/^#\/?watchlist\/(.+)$/);
  return match ? decodeURIComponent(match[1]) : "";
}

function isWatchlistHash() {
  return window.location.hash.replace(/^#\/?/, "").split("/")[0] === "watchlist";
}

// TradingView 위젯 bridge. 대시보드 Legacy 보드가 갖고 있던 선언인데, 그 화면을
// 0.5에서 삭제하면서 위젯을 계속 쓰는 이쪽으로 옮겼다.
declare global {
  interface Window {
    FolioTradingViewWidgets?: {
      renderWatchlistDetail?: (target: HTMLElement, detail: unknown) => void;
      cleanup?: (root?: ParentNode) => void;
    };
  }
}

export function WatchlistRoute() {
  const { resolved: resolvedTheme } = useThemePreference();
  const [items, setItems] = useState<string[]>([]);
  const [cards, setCards] = useState<WatchlistOverviewItem[]>([]);
  const [keyword, setKeyword] = useState("");
  const [detailItem, setDetailItem] = useState(() => readWatchlistDetailItem());
  const [detail, setDetail] = useState<WatchlistDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const widgetsRef = useRef<HTMLDivElement | null>(null);
  // 티커별 다음 실적. 카드마다 부르지 않고 한 번에 묻는다 — 종목 20개짜리
  // 워치리스트가 20개의 요청을 만들면 목록이 그만큼 늦게 뜬다.
  const [earnings, setEarnings] = useState<Record<string, EarningsEvent>>({});

  const loadOverview = useCallback(async (nextItems: string[]) => {
    if (!nextItems.length) {
      setCards([]);
      return;
    }
    const overview = await getJson<{ items?: WatchlistOverviewItem[] }>("/api/watchlist/overview");
    const rows = Array.isArray(overview.items) ? overview.items : [];
    setCards(rows);
    // 실적 조회는 목록을 막지 않는다. 실패하면 배지만 없다.
    fetchNextEarnings(rows.map((row) => row.ticker || "").filter(Boolean)).then(setEarnings);
  }, []);

  const loadWatchlist = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const payload = await getJson<string[]>("/api/watchlist");
      const normalized = normalizeItems(Array.isArray(payload) ? payload : []);
      setItems(normalized);
      await loadOverview(normalized);
      setReactAgentContextScope("watchlist", { surface: "watchlist", viewId: "watchlist", reportKind: "", reportId: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "워치리스트를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, [loadOverview]);

  useEffect(() => {
    loadWatchlist();
  }, [loadWatchlist]);

  useEffect(() => {
    const handleHashChange = () => {
      if (!isWatchlistHash()) return;
      setDetailItem(readWatchlistDetailItem());
    };
    window.addEventListener("hashchange", handleHashChange);
    handleHashChange();
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  useEffect(() => {
    let alive = true;
    async function loadDetail(item: string) {
      setDetailLoading(true);
      setError("");
      setDetail({ item });
      setReactAgentContextScope("watchlist", { surface: "watchlist_detail", viewId: "watchlist", reportKind: "watchlist", reportId: item, marketScope: "" });
      try {
        const payload = await getJson<WatchlistDetail>(`/api/watchlist/detail?item=${encodeURIComponent(item)}&limit=12`);
        if (!alive) return;
        setDetail(payload);
      } catch (err) {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "상세 정보를 불러오지 못했습니다.");
      } finally {
        if (alive) setDetailLoading(false);
      }
    }

    if (detailItem) {
      loadDetail(detailItem);
    } else {
      setDetail(null);
      setReactAgentContextScope("watchlist", { surface: "watchlist", viewId: "watchlist", reportKind: "", reportId: "" });
    }
    return () => {
      alive = false;
    };
  }, [detailItem]);

  useEffect(() => {
    const target = widgetsRef.current;
    if (!target || !detail || detailLoading) return undefined;
    window.FolioTradingViewWidgets?.cleanup?.(target);
    target.innerHTML = '<div class="tradingview-widget-unavailable">TradingView 위젯을 준비하는 중입니다.</div>';
    window.FolioTradingViewWidgets?.renderWatchlistDetail?.(target, detail);
    return () => {
      window.FolioTradingViewWidgets?.cleanup?.(target);
    };
  }, [detail, detailLoading, resolvedTheme]);

  async function persistWatchlist(nextItems: string[], message?: string) {
    setSaving(true);
    setError("");
    try {
      const saved = await postJson<string[]>("/api/watchlist", { items: nextItems });
      const normalized = normalizeItems(Array.isArray(saved) ? saved : []);
      setItems(normalized);
      await loadOverview(normalized);
      if (message) setStatus(message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "워치리스트 저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  }

  // 워치리스트는 회사를 따라다니는 화면이라 도쿄에 상장된 도요타를 봐야 한다.
  // 미국 ADR(TM)은 통화도 시간대도 가격도 다른 별개의 증권이다.
  const { resolution, pending: resolvePending, picked, pick } = useCompanyResolution(keyword, { preferHome: true });
  // 입력 전체가 한 회사로 확정됐는가. 확정됐으면 그 이름 안의 쉼표는 구분자가 아니다.
  const resolvedWholeInput = Boolean(picked) || resolution?.status === "confident";
  const watchlistResolutionMessage = (() => {
    const text = keyword.trim();
    if (!text) return "종목은 이름이나 티커로, 관심 주제는 그대로 적으면 됩니다.";
    if (picked) return `${picked.name}로 추가합니다.`;
    if (resolvePending) return "확인 중…";
    if (resolution?.status === "confident" && resolution.match) return `${resolution.match.name}로 추가합니다.`;
    if (resolution?.status === "ambiguous" && resolution.candidates.some((row) => row.strong)) {
      return "여러 기업이 맞습니다. 고르거나, 이대로 주제 키워드로 추가합니다.";
    }
    return "주제 키워드로 추가합니다.";
  })();

  async function resolveKeyword(raw: string) {
    try {
      const result = await getJson<{ keyword?: string }>(`/api/watchlist/resolve?keyword=${encodeURIComponent(raw)}`);
      return result.keyword || raw;
    } catch {
      return raw;
    }
  }

  async function addKeyword() {
    const parts = splitAddInput(keyword, resolvedWholeInput);
    if (!parts.length) return;
    const next = [...items];
    for (const raw of parts) {
      const resolved = await resolveKeyword(raw);
      if (resolved && !next.some((existing) => existing.toLowerCase() === resolved.toLowerCase())) next.push(resolved);
    }
    setKeyword("");
    if (next.length === items.length) return;
    await persistWatchlist(next, "워치리스트에 추가했습니다.");
  }

  async function removeItem(item: string) {
    await persistWatchlist(items.filter((row) => row !== item), "워치리스트에서 삭제했습니다.");
    if (detailItem === item) setWatchlistHash();
  }

  const newsRows = useMemo(() => sortNewsLatestFirst(detail?.news || []), [detail]);
  const selectedLabel = detailLabel(detail, detailItem);
  // 상세의 실적은 카드 표에서 찾는다. 카드가 아는 티커와 상세가 아는 티커가 같다.
  const detailEarnings = earningsFor(
    cards.find((row) => (row.item || cardCompanyName(row)) === detailItem) || null,
  ) || earnings[String(detail?.company?.ticker || "").toUpperCase()];

  function earningsFor(card: WatchlistOverviewItem | null): EarningsEvent | undefined {
    const ticker = String(card?.ticker || "").toUpperCase();
    return ticker ? earnings[ticker] : undefined;
  }

  if (detailItem) {
    return (
      <div className="react-watchlist-route" data-watchlist-route>
        <div className="watchlist-detail-inline">
          <nav className="reader-breadcrumb" aria-label="현재 위치">
            <button type="button" className="reader-crumb-link" onClick={() => setWatchlistHash()}>워치리스트</button>
            <span className="reader-breadcrumb-sep" aria-hidden="true">›</span>
            <span className="reader-breadcrumb-leaf">{selectedLabel}</span>
          </nav>
          <section className="watchlist-detail-dialog" role="region" aria-labelledby="watchlistDetailTitle">
            <div className="watchlist-detail-head">
              <div>
                <p className="section-kicker">WATCHLIST</p>
                <h2 id="watchlistDetailTitle">{selectedLabel}</h2>
                <p className="section-subtitle">{detailMeta(detail)}</p>
              </div>
              <div className="watchlist-detail-actions">
                <ConsultationEntry item={detailItem} />
                <button className="btn btn--icon" type="button" aria-label="닫기" data-tooltip="닫기" data-tooltip-pos="left" onClick={() => setWatchlistHash()}>×</button>
              </div>
            </div>
            {error && <p className="react-dashboard-error">{error}</p>}
            <div ref={widgetsRef} className="watchlist-detail-widgets">
              <div className="tradingview-widget-unavailable">TradingView 위젯을 준비하는 중입니다.</div>
            </div>
            {/* 위젯과 뉴스 사이. 다음 실적은 종목을 보러 온 사람이 가장 먼저 찾는 일정이다. */}
            {detailEarnings?.startsAt && (
              <div className="watchlist-detail-earnings">
                <h3>다음 실적 일정</h3>
                <p className="watchlist-detail-earnings-line">
                  <strong>{formatEarningsDate(detailEarnings.startsAt)}</strong>
                  {ddayLabel(detailEarnings.startsAt) && (
                    <span className="chip watchlist-earnings-chip" data-estimated={isEstimated(detailEarnings) ? "true" : undefined}>
                      {ddayLabel(detailEarnings.startsAt)}
                    </span>
                  )}
                  <span className="section-subtitle">
                    {isEstimated(detailEarnings)
                      // 확정 일정이 아니라는 사실을 숨기지 않는다. 회사 IR이 권위다.
                      ? "제3자 예정치입니다. 회사 IR 공지로 다시 확인하세요."
                      : "공식 일정입니다."}
                  </span>
                </p>
              </div>
            )}
            <div className="watchlist-detail-news">
              <h3>수집한 뉴스</h3>
              {detailLoading ? (
                <p className="section-subtitle">관련 뉴스를 불러오는 중입니다.</p>
              ) : newsRows.length ? (
                <div className="watchlist-detail-news-list">
                  {newsRows.map((row, index) => (
                    <article className="compact-item" key={`${newsTitle(row)}-${index}`}>
                      <div className="meta">{sourceLabel(row)}</div>
                      <h4>
                        {row.url ? (
                          <a href={row.url} target="_blank" rel="noopener noreferrer">{newsTitle(row)}</a>
                        ) : (
                          <span>{newsTitle(row)}</span>
                        )}
                      </h4>
                      {row.snippet && <p>{row.snippet}</p>}
                    </article>
                  ))}
                </div>
              ) : (
                <p className="section-subtitle">수집된 관련 뉴스가 없습니다.</p>
              )}
            </div>
          </section>
        </div>
      </div>
    );
  }

  return (
    <div className="react-watchlist-route" data-watchlist-route>
      <RouteHero
        eyebrow="Watchlist"
        title="워치리스트"
        description="관심 기업, 섹터, 테마를 추적하고 관련 뉴스와 시장 반응을 확인합니다."
        actions={(
        <div className="brief-controls">
          <button className="btn" type="button" onClick={loadWatchlist} disabled={loading}>
            {loading ? "불러오는 중" : "다시 읽기"}
          </button>
          <button className="btn btn--primary" type="button" onClick={() => persistWatchlist(items, "워치리스트를 저장했습니다.")} disabled={saving}>
            {saving ? "저장 중" : "저장"}
          </button>
        </div>
        )}
      />
      <div className="watchlist-editor input-panel">
        <div className="input-panel-header">
          <h3>키워드 추가</h3>
          <p>관심 기업, 섹터, 테마를 하나씩 추가해 뉴스와 브리핑 추적 범위를 관리합니다.</p>
        </div>
        <label className="portfolio-ticker-field watchlist-add-field">
          <span className="sr-only">추가할 종목 또는 키워드</span>
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                addKeyword();
              }
            }}
            placeholder="예: NVDA, 삼성전자, AI"
            aria-describedby="watchlist-resolution"
            autoComplete="off"
          />
          {/* 주제어에는 이름 일부만 겹친 약한 후보가 걸린다. 그 경우 목록을 띄우지 않는다. */}
          {resolution?.status === "ambiguous" && resolution.candidates.some((row) => row.strong) && !picked && (
            <div className="ticker-suggest" role="listbox" aria-label="후보 기업">
              {resolution.candidates.map((candidate) => (
                <button
                  type="button"
                  role="option"
                  aria-selected={false}
                  key={`${candidate.market}:${candidate.ticker}`}
                  // 선택과 입력칸 변경을 훅에 함께 알린다. 따로 하면 훅이 그 변경을
                  // 새 타이핑으로 읽어 방금 고른 후보를 지운다.
                  onClick={() => { pick(candidate, candidate.name); setKeyword(candidate.name); }}
                >
                  <strong>{candidate.ticker}</strong>
                  <span>{candidate.name}</span>
                </button>
              ))}
            </div>
          )}
        </label>
        <button className="btn" type="button" onClick={addKeyword} disabled={saving}>추가</button>
      </div>
      {/* 워치리스트는 테마 키워드도 받는다. 못 알아본 입력은 오류가 아니라 키워드다. */}
      <p className="analysis-resolution" id="watchlist-resolution" data-status={keyword.trim() ? (picked ? "picked" : resolution?.status || "idle") : "idle"}>
        {watchlistResolutionMessage}
      </p>
      {error && <p className="react-dashboard-error">{error}</p>}
      {status && <p className="react-dashboard-warning">{status}</p>}
      <div className="watchlist-grid">
        {cards.length ? cards.map((card) => {
          const item = card.item || cardCompanyName(card);
          return (
            <article
              className="watchlist-card"
              data-watchlist-detail-item={item}
              tabIndex={0}
              role="button"
              aria-label={`${item} 상세 보기`}
              key={item}
              onClick={() => setWatchlistHash(item)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setWatchlistHash(item);
                }
              }}
            >
              <span className="watchlist-card-accent" aria-hidden="true" />
              <button
                className="btn btn--icon watchlist-card-delete"
                type="button"
                aria-label={`${item} 워치리스트에서 삭제`}
                data-tooltip="삭제"
                // 카드가 overflow: hidden이라 기본 위치(버튼 위)의 툴팁은 카드 밖으로 나가 잘린다.
                data-tooltip-pos="bottom"
                onClick={(event) => {
                  event.stopPropagation();
                  removeItem(item);
                }}
              >
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M2.5 4h11M6 4V2.5h4V4M5 4l.5 9h5L11 4" />
                </svg>
              </button>
              <div className="watchlist-card-top">
                <strong className="watchlist-ticker">{cardTicker(card)}</strong>
                <h3>{cardCompanyName(card)}</h3>
              </div>
              <div className="watchlist-card-meta">
                {card.tags?.length ? (
                  <div className="tags">
                    {card.tags.slice(0, 5).map((tag) => <span className="tag" key={tag}>{tag}</span>)}
                  </div>
                ) : null}
                {/* 다음 실적. 제3자 예정치는 날짜가 움직이므로 확정과 구분해 보여준다. */}
                {(() => {
                  const event = earningsFor(card);
                  if (!event?.startsAt) return null;
                  const dday = ddayLabel(event.startsAt);
                  if (!dday) return null;
                  return (
                    <span
                      className="chip watchlist-earnings-chip"
                      data-estimated={isEstimated(event) ? "true" : undefined}
                      title={`실적 ${formatEarningsDate(event.startsAt)}${isEstimated(event) ? " (예정치)" : ""}`}
                    >
                      실적 {dday}{isEstimated(event) ? "*" : ""}
                    </span>
                  );
                })()}
                <span className="watchlist-news-count">{card.count || 0}건</span>
              </div>
            </article>
          );
        }) : (
          <div className="result">
            <p>워치리스트 항목을 저장하면 항목별 최신 뉴스 카드가 표시됩니다.</p>
          </div>
        )}
      </div>
    </div>
  );
}
