import { useEffect, useState } from "react";
import { getJson } from "../../api";
import { compactAmount } from "./EarningsPanel";

/** 재무·투자 지표 — 예전 TradingView 펀더멘털 위젯의 네이티브 대체.
 *
 * **상세를 열 때만 부른다.** 티커당 provider 호출이다(실적 패널과 같은 이유).
 * 서버가 1시간 TTL + 하루 stale-while-revalidate 캐시를 갖고 있어 최근 본 종목은
 * 즉시 그려진다. 결측은 `—`로 보여준다 — provider가 실제로 비워 두는 칸이 있고
 * (삼성전자의 PER), 숨기면 이 종목만 그 지표가 없는 것처럼 읽힌다.
 *
 * 각 지표에는 계산식 한 줄을 붙인다. 라벨만으로는 PBR과 PER을 처음 보는 사람이
 * 구분할 수 없고, 설명 없이 숫자만 나열하면 항목이 서로 구분되지 않는다는 피드백이
 * 이 구성의 출발점이다. 분기 이익 차트(매출·영업이익·순이익)와 분기별 값 표가
 * 표의 시각화 짝이다.
 */

export type FundamentalsQuarter = {
  quarter?: string;
  revenue?: number | null;
  operatingIncome?: number | null;
  netIncome?: number | null;
};

export type FundamentalsPayload = {
  symbol?: string;
  currentPrice?: number | null;
  previousClose?: number | null;
  marketCap?: number | null;
  trailingPE?: number | null;
  forwardPE?: number | null;
  priceToBook?: number | null;
  returnOnEquity?: number | null;
  operatingMargins?: number | null;
  profitMargins?: number | null;
  dividendYield?: number | null;
  beta?: number | null;
  fiftyTwoWeekLow?: number | null;
  fiftyTwoWeekHigh?: number | null;
  revenueGrowth?: number | null;
  currency?: string;
  sector?: string;
  industry?: string;
  longBusinessSummary?: string;
  provider?: string;
  quarters?: FundamentalsQuarter[];
};

/** 헤더 가격과 지표 패널이 한 응답을 나눠 쓴다 — 같은 payload를 두 번 받지 않는다. */
export function useFundamentals(ticker: string): { payload: FundamentalsPayload | null; error: string } {
  const [payload, setPayload] = useState<FundamentalsPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setPayload(null);
    setError("");
    if (!ticker) return undefined;
    getJson<FundamentalsPayload>(`/api/market/fundamentals?symbol=${encodeURIComponent(ticker)}`)
      .then((row) => { if (alive) setPayload(row); })
      .catch((reason) => { if (alive) setError(reason instanceof Error ? reason.message : "지표를 불러오지 못했습니다."); });
    return () => { alive = false; };
  }, [ticker]);

  return { payload, error };
}

export function ratioText(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString("ko-KR", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

/** 소수 비율(0.31)을 %로. provider가 fraction으로 주는 칸(ROE·마진·성장률) 전용. */
export function fractionPercentText(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${(value * 100).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`;
}

/** 배당수익률은 yfinance가 이미 % 단위로 준다(도요타 3.26 = 3.26%). fraction으로
 *  오해해 100을 곱하면 326%가 된다 — 실측값 기준으로 그대로 쓴다. */
export function percentValueText(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%`;
}

export function rangeText(low: number | null | undefined, high: number | null | undefined): string {
  if (low === null || low === undefined || high === null || high === undefined) return "—";
  if (!Number.isFinite(low) || !Number.isFinite(high)) return "—";
  const digits = Math.max(Math.abs(low), Math.abs(high)) >= 1000 ? 0 : 2;
  const text = (value: number) => value.toLocaleString("ko-KR", { maximumFractionDigits: digits });
  return `${text(low)} ~ ${text(high)}`;
}

export function fundamentalsRows(payload: FundamentalsPayload): Array<{ label: string; hint: string; value: string }> {
  const currency = payload.currency || "USD";
  return [
    { label: "시가총액", hint: "주가 × 발행주식수", value: compactAmount(payload.marketCap, currency) },
    { label: "PER", hint: "주가 ÷ 최근 4분기 EPS", value: ratioText(payload.trailingPE) },
    { label: "선행 PER", hint: "주가 ÷ 예상 EPS", value: ratioText(payload.forwardPE) },
    { label: "PBR", hint: "주가 ÷ 주당순자산", value: ratioText(payload.priceToBook, 2) },
    { label: "ROE", hint: "순이익 ÷ 자기자본", value: fractionPercentText(payload.returnOnEquity) },
    { label: "영업이익률", hint: "영업이익 ÷ 매출", value: fractionPercentText(payload.operatingMargins) },
    { label: "순이익률", hint: "순이익 ÷ 매출", value: fractionPercentText(payload.profitMargins) },
    { label: "배당수익률", hint: "연간 배당 ÷ 주가", value: percentValueText(payload.dividendYield) },
    { label: "매출 성장", hint: "전년 동기 대비", value: fractionPercentText(payload.revenueGrowth) },
    { label: "베타", hint: "시장 대비 변동성", value: ratioText(payload.beta, 2) },
    { label: "52주 범위", hint: "최근 1년 저가 ~ 고가", value: rangeText(payload.fiftyTwoWeekLow, payload.fiftyTwoWeekHigh) },
  ];
}

const QUARTER_SERIES = [
  { key: "revenue", label: "매출" },
  { key: "operatingIncome", label: "영업이익" },
  { key: "netIncome", label: "순이익" },
] as const;

/** 분기 키(2026-06-30)를 축 라벨로 — 레퍼런스와 같은 "26년 6월" 형태. */
export function quarterAxisLabel(quarter: string | undefined): string {
  const text = String(quarter || "");
  if (!/^\d{4}-\d{2}/.test(text)) return "";
  return `${text.slice(2, 4)}년 ${Number(text.slice(5, 7))}월`;
}

/** 막대 스케일. 적자 분기(음수)가 있으면 기준선 아래로 내려가야 한다 —
 *  0으로 접으면 적자가 "이익 없음"으로 보인다. */
export function barScale(quarters: FundamentalsQuarter[]): { max: number; min: number } {
  let max = 0;
  let min = 0;
  for (const row of quarters) {
    for (const series of QUARTER_SERIES) {
      const value = row[series.key];
      if (value === null || value === undefined || !Number.isFinite(value)) continue;
      max = Math.max(max, value);
      min = Math.min(min, value);
    }
  }
  return { max, min };
}

function QuarterlyEarningsChart({ quarters, currency }: { quarters: FundamentalsQuarter[]; currency: string }) {
  const rows = (quarters || []).filter((row) => QUARTER_SERIES.some((series) => row[series.key] != null));
  if (rows.length < 2) return null;
  const { max, min } = barScale(rows);
  const span = max - min;
  if (span <= 0) return null;
  const width = 560;
  const plotHeight = 190;
  const labelHeight = 24;
  const groupWidth = width / rows.length;
  const barWidth = Math.min(30, (groupWidth - 20) / QUARTER_SERIES.length);
  const zeroY = (max / span) * plotHeight;
  const yOf = (value: number) => ((max - value) / span) * plotHeight;
  const latest = rows[rows.length - 1];
  const summary = QUARTER_SERIES
    .map((series) => `${series.label} ${compactAmount(latest[series.key], currency)}`)
    .join(", ");
  return (
    <figure className="watchlist-quarterly">
      <svg
        viewBox={`0 0 ${width} ${plotHeight + labelHeight}`}
        role="img"
        aria-label={`최근 ${rows.length}개 분기 매출·영업이익·순이익. 최신 분기 ${summary}.`}
      >
        {/* 수평 그리드 — 막대 높이를 견줄 기준선이 없으면 상대 비교만 남는다. */}
        {[0.25, 0.5, 0.75].map((step) => (
          <line key={step} x1={0} x2={width} y1={plotHeight * step} y2={plotHeight * step} className="watchlist-quarterly__grid" />
        ))}
        <line x1={0} x2={width} y1={zeroY} y2={zeroY} className="watchlist-quarterly__baseline" />
        {rows.map((row, index) => {
          const groupLeft = index * groupWidth + (groupWidth - barWidth * QUARTER_SERIES.length - 10) / 2;
          return (
            <g key={row.quarter || index}>
              {QUARTER_SERIES.map((series, seriesIndex) => {
                const value = row[series.key];
                if (value === null || value === undefined || !Number.isFinite(value)) return null;
                const top = Math.min(yOf(value), zeroY);
                const height = Math.max(2, Math.abs(yOf(value) - zeroY));
                return (
                  <rect
                    key={series.key}
                    className={`watchlist-quarterly__bar watchlist-quarterly__bar--${series.key}`}
                    x={groupLeft + seriesIndex * (barWidth + 5)}
                    y={top}
                    width={barWidth}
                    height={height}
                    rx={4}
                  />
                );
              })}
              <text x={index * groupWidth + groupWidth / 2} y={plotHeight + 17} textAnchor="middle" className="watchlist-quarterly__axis">
                {quarterAxisLabel(row.quarter)}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="watchlist-quarterly__legend">
        {QUARTER_SERIES.map((series) => (
          <span key={series.key}>
            <i className={`watchlist-quarterly__dot watchlist-quarterly__dot--${series.key}`} aria-hidden="true" />
            {series.label}
          </span>
        ))}
      </figcaption>
      {/* 분기별 값 표 — 막대만으로는 정확한 값을 읽을 수 없다. 넓으면 표가 스스로 스크롤한다. */}
      <div className="watchlist-quarterly__table-wrap">
        <table className="watchlist-quarterly__table">
          <thead>
            <tr>
              <th scope="col">항목</th>
              {rows.map((row) => <th scope="col" key={row.quarter}>{quarterAxisLabel(row.quarter)}</th>)}
            </tr>
          </thead>
          <tbody>
            {QUARTER_SERIES.map((series) => (
              <tr key={series.key}>
                <th scope="row">
                  <i className={`watchlist-quarterly__dot watchlist-quarterly__dot--${series.key}`} aria-hidden="true" />
                  {series.label}
                </th>
                {rows.map((row) => <td key={row.quarter}>{compactAmount(row[series.key], currency)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

/** 회사 소개 + 섹터·산업. 소개는 provider 원문(영문)이라 세 줄로 접고 더보기로 편다. */
function CompanyProfile({ payload }: { payload: FundamentalsPayload }) {
  const [expanded, setExpanded] = useState(false);
  const summary = String(payload.longBusinessSummary || "").trim();
  const facts = [
    { label: "섹터", value: payload.sector || "" },
    { label: "산업", value: payload.industry || "" },
  ].filter((row) => row.value);
  if (!summary && !facts.length) return null;
  return (
    <div className="watchlist-profile">
      {summary && (
        <p className={expanded ? "watchlist-profile__summary" : "watchlist-profile__summary watchlist-profile__summary--clamped"}>
          {summary}
          {!expanded && <span className="watchlist-profile__fade" aria-hidden="true" />}
        </p>
      )}
      {summary && (
        <button type="button" className="btn btn--text watchlist-profile__more" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
          {expanded ? "접기" : "더보기"}
        </button>
      )}
      {facts.map((row) => (
        <div className="watchlist-fundamentals-row" key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </div>
  );
}

export function FundamentalsPanel({ ticker, payload, error }: { ticker: string; payload: FundamentalsPayload | null; error: string }) {
  if (!ticker) return null;
  if (error) return <p className="section-subtitle">{error}</p>;
  if (!payload) {
    // 고정 높이 스켈레톤 — 지표가 도착할 때 아래 차트·실적이 밀리지 않는다.
    return <p className="section-subtitle watchlist-fundamentals-skeleton">지표를 불러오는 중입니다.</p>;
  }
  const currency = payload.currency || "USD";
  return (
    <div className="watchlist-fundamentals">
      <div>
        <CompanyProfile payload={payload} />
        <dl className="watchlist-fundamentals-rows">
          {fundamentalsRows(payload).map((row) => (
            <div className="watchlist-fundamentals-row" key={row.label}>
              <dt>
                {row.label}
                <small>{row.hint}</small>
              </dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <QuarterlyEarningsChart quarters={payload.quarters || []} currency={currency} />
    </div>
  );
}
