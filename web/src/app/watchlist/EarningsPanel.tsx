import { useEffect, useState } from "react";
import { getJson } from "../../api";
import { ddayLabel, formatEarningsDate } from "../watchlistEarnings";

/** 발표된 실적과 다음 발표 컨센서스.
 *
 * **상세를 열 때만 부른다.** 티커당 provider 호출이라 카드 그리드에 걸면 종목 수만큼
 * 네트워크가 된다 — 목록에는 시장 캘린더에서 온 D-day 배지만 남긴다.
 *
 * 숫자는 yfinance다. 기업분석은 SEC companyfacts를 최우선으로 쓰므로(§6 절대 규칙 6)
 * 같은 앱 안에서 등급이 다른 숫자다 — 패널이 출처를 적어 그 차이를 숨기지 않는다.
 */

type EarningsRow = {
  quarter?: string;
  label?: string;
  epsActual?: number | null;
  epsEstimate?: number | null;
  surprisePercent?: number | null;
  epsPriorQuarter?: number | null;
  epsPriorYear?: number | null;
  revenueActual?: number | null;
  revenuePriorQuarter?: number | null;
  revenuePriorYear?: number | null;
  // 보고 EPS 이력이 1년을 못 채우면 서버가 손익계산서 기본 EPS로 채운다. 그때는
  // **분자도** 같은 계열이어야 해서 그 분기의 기본 EPS를 함께 보낸다.
  epsActualStatement?: number | null;
  epsPriorYearBasis?: string;
};

type EarningsPayload = {
  ticker?: string;
  currency?: string;
  next?: {
    date?: string;
    epsEstimate?: number | null;
    revenueEstimate?: number | null;
    status?: string;
  };
  history?: EarningsRow[];
  provider?: string;
  freshness?: string;
  warnings?: string[];
};

/** 비교 기준. 세 가지를 나란히 두는 이유는 하나만으로는 오해하기 쉽기 때문이다 —
 *  직전 분기는 계절성에 흔들리고, 예측치는 매출 쪽이 아예 없다. */
type Basis = "estimate" | "priorQuarter" | "priorYear";

/** 기업분석 화면으로 종목 하나를 넘기는 자리. 쓰는 쪽이 읽고 즉시 지운다. */
export const ANALYSIS_HANDOFF_KEY = "folio:analysis-query";

const BASIS_LABELS: Record<Basis, string> = {
  estimate: "예측치",
  priorQuarter: "지난 분기",
  priorYear: "작년 동기간",
};

const COMPACT_UNITS: ReadonlyArray<{ limit: number; suffix: string }> = [
  { limit: 1e12, suffix: "조" },
  { limit: 1e8, suffix: "억" },
];

/** 매출은 조·억 단위가 아니면 자릿수만으로는 읽히지 않는다(삼성전자 133,873,444,000,000). */
export function compactAmount(value: number | null | undefined, currency = "USD"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (currency === "KRW" || currency === "JPY") {
    for (const unit of COMPACT_UNITS) {
      if (Math.abs(value) >= unit.limit) {
        return `${(value / unit.limit).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}${unit.suffix}`;
      }
    }
    return value.toLocaleString("ko-KR", { maximumFractionDigits: 0 });
  }
  const scaled = Math.abs(value) >= 1e9 ? { div: 1e9, suffix: "B" } : Math.abs(value) >= 1e6 ? { div: 1e6, suffix: "M" } : null;
  return scaled
    ? `${(value / scaled.div).toLocaleString("en-US", { maximumFractionDigits: 2 })}${scaled.suffix}`
    : value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export function formatEps(value: number | null | undefined, currency = "USD"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  // 원·엔 EPS는 소수점이 의미 없다(삼성전자 10,849원).
  const digits = currency === "KRW" || currency === "JPY" ? 0 : 2;
  return value.toLocaleString("ko-KR", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

/** 기준 대비 증감률. 기준이 0이거나 없으면 계산하지 않는다. */
export function changeRatio(actual: number | null | undefined, base: number | null | undefined): number | null {
  if (actual === null || actual === undefined || !Number.isFinite(actual)) return null;
  if (base === null || base === undefined || !Number.isFinite(base) || base === 0) return null;
  // 기준이 음수면 부호가 뒤집혀 "적자 축소"가 하락으로 읽힌다. 크기로 나눈다.
  return (actual - base) / Math.abs(base);
}

export function percentText(ratio: number | null): string {
  if (ratio === null) return "—";
  return `${ratio > 0 ? "+" : ""}${(ratio * 100).toFixed(1)}%`;
}

function toneOf(ratio: number | null): "up" | "down" | "flat" {
  if (ratio === null || Math.abs(ratio) < 0.0005) return "flat";
  return ratio > 0 ? "up" : "down";
}

/** 이 기준에서 비교할 값. 매출의 `estimate`는 **없다**(provider가 다음 분기 것만 준다).
 *
 * `epsBase`는 증감률의 분모이고 `epsTop`은 분자다. 둘이 갈리는 경우가 하나 있다 —
 * 작년 동기 EPS를 손익계산서에서 채웠을 때. 그때는 분자도 같은 계열(기본 EPS)이라야
 * 조정 폭이 증감률로 둔갑하지 않는다. */
export function basisValues(row: EarningsRow, basis: Basis): {
  eps: number | null | undefined;
  revenue: number | null | undefined;
  epsTop: number | null | undefined;
  fromStatement: boolean;
} {
  if (basis === "priorQuarter") {
    return { eps: row.epsPriorQuarter, revenue: row.revenuePriorQuarter, epsTop: row.epsActual, fromStatement: false };
  }
  if (basis === "priorYear") {
    const fromStatement = row.epsPriorYearBasis === "statement";
    return {
      eps: row.epsPriorYear,
      revenue: row.revenuePriorYear,
      epsTop: fromStatement ? row.epsActualStatement : row.epsActual,
      fromStatement,
    };
  }
  return { eps: row.epsEstimate, revenue: undefined, epsTop: row.epsActual, fromStatement: false };
}

/** EPS 비교 기준 줄.
 *
 * 손익계산서로 채운 경우 증감률의 **분자도** 그쪽 값이라, 화면의 큰 숫자(보고 EPS)와
 * 나눈 값이 다를 수 있다. 그러면 읽는 사람이 직접 나눠 봤을 때 숫자가 안 맞는다 —
 * 무엇을 무엇으로 나눴는지 그 줄에서 밝힌다.
 */
export function epsBaseText(
  row: EarningsRow, basis: Basis, currency: string,
  values = basisValues(row, basis),
): string {
  const base = `${BASIS_LABELS[basis]} ${formatEps(values.eps, currency)}`;
  if (!values.fromStatement || values.eps === null || values.eps === undefined) return base;
  if (values.epsTop === row.epsActual) return `${base} · 손익계산서 기본 EPS 기준`;
  return `${base} · 손익계산서 기본 EPS ${formatEps(values.epsTop, currency)} 대비`;
}

export function EarningsPanel({ ticker }: { ticker: string }) {
  const [payload, setPayload] = useState<EarningsPayload | null>(null);
  const [basis, setBasis] = useState<Basis>("estimate");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    if (!ticker) { setPayload(null); return undefined; }
    setLoading(true);
    setError("");
    getJson<EarningsPayload>(`/api/market/earnings?ticker=${encodeURIComponent(ticker)}`)
      .then((row) => { if (alive) setPayload(row); })
      .catch((reason) => { if (alive) setError(reason instanceof Error ? reason.message : "실적을 불러오지 못했습니다."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [ticker]);

  if (!ticker) return null;
  if (loading && !payload) {
    // 고정 높이로 자리를 잡아 뒤에 오는 뉴스가 밀려 올라갔다 내려오지 않게 한다.
    return (
      <div className="watchlist-earnings-panel">
        <h3>실적</h3>
        <p className="section-subtitle watchlist-earnings-skeleton">실적을 불러오는 중입니다.</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="watchlist-earnings-panel">
        <h3>실적</h3>
        <p className="section-subtitle">{error}</p>
      </div>
    );
  }
  const currency = payload?.currency || "USD";
  const next = payload?.next || {};
  const latest = (payload?.history || [])[0];
  if (!next.date && !latest) {
    return (
      <div className="watchlist-earnings-panel">
        <h3>실적</h3>
        <p className="section-subtitle">이 종목의 실적 데이터를 받지 못했습니다. (출처 {payload?.provider || "yfinance"})</p>
      </div>
    );
  }
  const compare = latest ? basisValues(latest, basis) : { eps: null, revenue: null, epsTop: null, fromStatement: false };
  const epsRatio = latest ? changeRatio(compare.epsTop, compare.eps) : null;
  const revenueRatio = latest ? changeRatio(latest.revenueActual, compare.revenue) : null;

  return (
    <div className="watchlist-earnings-panel">
      <div className="watchlist-earnings-panel__head">
        <h3>실적</h3>
        {/* 기업분석 화면은 hash에 질의를 담지 못한다(`parseHashRoute`가 `/` 앞만 읽는다).
            라우트 파싱을 넓히는 대신 종목만 넘겨 두고 그쪽이 집어 간다 — 안 집어 가도
            화면은 그냥 빈 입력칸으로 열린다. */}
        <button type="button" className="btn btn--text" onClick={() => {
          try { window.sessionStorage.setItem(ANALYSIS_HANDOFF_KEY, ticker); } catch { /* 저장이 막혀도 이동은 한다 */ }
          window.location.hash = "#/analysis";
        }}>
          기업분석 열기
        </button>
      </div>

      {next.date && (
        <div className="watchlist-earnings-next">
          <div className="watchlist-earnings-next__date">
            <span className="section-kicker">다음 발표</span>
            <strong>{formatEarningsDate(next.date)}</strong>
            {ddayLabel(next.date) && (
              // 제3자 예정치다. 확정 배지를 붙이지 않는다 — 공식 IR 소스가 없다.
              <span className="chip watchlist-earnings-chip" data-estimated="true">{ddayLabel(next.date)}</span>
            )}
          </div>
          <dl className="watchlist-earnings-consensus">
            <div><dt>EPS 컨센서스</dt><dd>{formatEps(next.epsEstimate, currency)}</dd></div>
            <div><dt>매출 컨센서스</dt><dd>{compactAmount(next.revenueEstimate, currency)}</dd></div>
          </dl>
          <p className="section-subtitle">제3자 예정치입니다. 날짜와 컨센서스 모두 회사 IR 공지로 다시 확인하세요.</p>
        </div>
      )}

      {latest && (
        <div className="watchlist-earnings-recent">
          <div className="watchlist-earnings-recent__head">
            <span className="section-kicker">최근 발표 · {latest.label || latest.quarter}</span>
            <div className="segment" role="group" aria-label="비교 기준">
              {(Object.keys(BASIS_LABELS) as Basis[]).map((value) => (
                <button type="button" key={value} aria-pressed={basis === value} onClick={() => setBasis(value)}>
                  {BASIS_LABELS[value]}
                </button>
              ))}
            </div>
          </div>
          <div className="watchlist-earnings-grid">
            <div className="watchlist-earnings-metric">
              <span className="watchlist-earnings-metric__label">EPS</span>
              <strong>{formatEps(latest.epsActual, currency)}</strong>
              <span className="watchlist-earnings-metric__base">{epsBaseText(latest, basis, currency, compare)}</span>
              <span className="watchlist-earnings-metric__delta" data-tone={toneOf(epsRatio)}>
                {percentText(epsRatio)}
              </span>
            </div>
            <div className="watchlist-earnings-metric">
              <span className="watchlist-earnings-metric__label">매출</span>
              <strong>{compactAmount(latest.revenueActual, currency)}</strong>
              <span className="watchlist-earnings-metric__base">
                {/* 지난 분기의 매출 컨센서스는 provider가 주지 않는다. 빈칸으로 두면
                    이 종목만 없는 것처럼 읽히므로 이유를 적는다. */}
                {basis === "estimate" ? "매출 컨센서스 없음" : `${BASIS_LABELS[basis]} ${compactAmount(compare.revenue, currency)}`}
              </span>
              <span className="watchlist-earnings-metric__delta" data-tone={toneOf(revenueRatio)}>
                {basis === "estimate" ? "—" : percentText(revenueRatio)}
              </span>
            </div>
          </div>
          {latest.surprisePercent != null && (
            <p className="section-subtitle">
              EPS 서프라이즈 <b data-tone={toneOf(latest.surprisePercent)}>{percentText(latest.surprisePercent)}</b> · 예측치 기준
            </p>
          )}
        </div>
      )}

      <p className="section-subtitle watchlist-earnings-source">
        출처 {payload?.provider || "yfinance"} · 기업분석의 SEC 기준 숫자와 등급이 다릅니다.
      </p>
    </div>
  );
}
