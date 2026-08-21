import { useEffect, useState } from "react";
import { getJson } from "../../api";
import { changeRatio, compactAmount, percentText, toneOf } from "./EarningsPanel";

/** 재무·투자 지표 — 예전 TradingView 펀더멘털 위젯의 네이티브 대체.
 *
 * **상세를 열 때만 부른다.** 티커당 provider 호출이다(실적 패널과 같은 이유).
 * 서버가 1시간 TTL + 하루 stale-while-revalidate 캐시를 갖고 있어 최근 본 종목은
 * 즉시 그려진다. 결측은 `—`로 보여준다 — provider가 실제로 비워 두는 칸이 있고
 * (삼성전자의 PER), 숨기면 이 종목만 그 지표가 없는 것처럼 읽힌다.
 *
 * 각 지표에는 계산식 한 줄을 붙인다. 라벨만으로는 PBR과 PER을 처음 보는 사람이
 * 구분할 수 없고, 설명 없이 숫자만 나열하면 항목이 서로 구분되지 않는다는 피드백이
 * 이 구성의 출발점이다. 분기 차트(이익/재무/현금흐름 전환)와 분기별 값 표가
 * 표의 시각화 짝이고, hover 상자·판독 패널은 기업분석 차트와 같은 양식을 쓴다
 * (`analysis-chart-hover`/`analysis-chart-readout` 클래스 재사용).
 *
 * 회사 소개는 provider 원문(영문) 그대로다. LLM 번역을 붙였다가 뺐다 — 키가 있는
 * 설치만 한국어가 되는 반쪽 기능은 없느니만 못하다(2026-08-22 사용자 결정).
 */

export type FundamentalsQuarter = {
  quarter?: string;
  revenue?: number | null;
  operatingIncome?: number | null;
  netIncome?: number | null;
  currentAssets?: number | null;
  currentLiabilities?: number | null;
  nonCurrentLiabilities?: number | null;
  totalDebt?: number | null;
  stockholdersEquity?: number | null;
  operatingCashFlow?: number | null;
  freeCashFlow?: number | null;
  capitalExpenditure?: number | null;
};

export type FundamentalsPayload = {
  symbol?: string;
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

/** 지표 패널의 payload fetch. 라우트가 한 번 부르고 패널에 내려준다. */
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

type SeriesDef = { label: string; of: (row: FundamentalsQuarter) => number | null | undefined };
type ChartSet = {
  key: string;
  label: string;
  mode: "bars" | "lines";
  /** amount는 통화 축약(6.72B), percent는 %다. 증감도 갈린다 — 금액은 %, 비율은 %p. */
  format: "amount" | "percent";
  colors: string[];
  series: Array<{ key: string } & SeriesDef>;
};

/** `분자 ÷ 분모 × 100`. 분모가 0이거나 비면 계산하지 않는다. */
export function balanceRatio(numerator: number | null | undefined, denominator: number | null | undefined): number | null {
  if (numerator === null || numerator === undefined || !Number.isFinite(numerator)) return null;
  if (denominator === null || denominator === undefined || !Number.isFinite(denominator) || denominator === 0) return null;
  return (numerator / denominator) * 100;
}

// 세트마다 자기 색 농담을 갖는다 — 한 세트 안에 여러 색을 섞으면 알록달록하고, 네 세트가
// 같은 색이면 지금 어느 탭인지 색이 말해 주지 않는다. 첫 계열(규모 기준)은 공통 중립 잉크,
// 세트의 정체성은 둘째·셋째 계열 색이 만든다.
const INK = "color-mix(in srgb, var(--folio-ink) 42%, transparent)";
const tint = (token: string) => `color-mix(in srgb, ${token} 45%, transparent)`;

/** 이익만으로는 반쪽이다 — 재무 구조·안정성 비율·현금 창출력이 같은 자리에서 전환된다.
 *  안정성(비율)은 별도 탭의 **선 차트**다. 금액 막대와 한 그림에 두면 축을 섞거나
 *  밴드를 위아래로 쌓아야 하는데, 실제로 쌓아 보니 한 차트처럼 읽히지 않았다
 *  (2026-08-22 사용자 피드백) — 탭이 넷이 되는 쪽이 그림마다 정직하다. */
export const CHART_SETS: ChartSet[] = [
  {
    key: "earnings", label: "이익", mode: "bars", format: "amount",
    colors: [INK, "var(--folio-green)", tint("var(--folio-green)")],
    series: [
      { key: "revenue", label: "매출", of: (row) => row.revenue },
      { key: "operatingIncome", label: "영업이익", of: (row) => row.operatingIncome },
      { key: "netIncome", label: "순이익", of: (row) => row.netIncome },
    ],
  },
  {
    key: "balance", label: "재무", mode: "bars", format: "amount",
    colors: [INK, "var(--folio-chart-1)", tint("var(--folio-chart-1)")],
    series: [
      { key: "currentAssets", label: "유동자산", of: (row) => row.currentAssets },
      { key: "currentLiabilities", label: "유동부채", of: (row) => row.currentLiabilities },
      { key: "nonCurrentLiabilities", label: "비유동부채", of: (row) => row.nonCurrentLiabilities },
    ],
  },
  {
    key: "stability", label: "안정성", mode: "lines", format: "percent",
    // 유동비율은 높을수록, 부채비율은 낮을수록 안전하다 — 의미색이 곧 데이터색이다.
    colors: ["var(--folio-green)", "var(--folio-burgundy)"],
    series: [
      { key: "currentRatio", label: "유동비율", of: (row) => balanceRatio(row.currentAssets, row.currentLiabilities) },
      { key: "debtRatio", label: "부채비율", of: (row) => balanceRatio(row.totalDebt, row.stockholdersEquity) },
    ],
  },
  {
    key: "cashflow", label: "현금흐름", mode: "bars", format: "amount",
    colors: [INK, "var(--folio-gold)", tint("var(--folio-gold)")],
    series: [
      { key: "operatingCashFlow", label: "영업현금흐름", of: (row) => row.operatingCashFlow },
      { key: "freeCashFlow", label: "잉여현금흐름", of: (row) => row.freeCashFlow },
      { key: "capitalExpenditure", label: "설비투자", of: (row) => row.capitalExpenditure },
    ],
  },
];

/** 분기 키(2026-06-30)를 축 라벨로 — 레퍼런스와 같은 "26년 6월" 형태. */
export function quarterAxisLabel(quarter: string | undefined): string {
  const text = String(quarter || "");
  if (!/^\d{4}-\d{2}/.test(text)) return "";
  return `${text.slice(2, 4)}년 ${Number(text.slice(5, 7))}월`;
}

/** 세트의 값 스케일.
 *  막대는 0을 반드시 포함한다 — 적자·순유출 분기(음수)는 기준선 아래로 내려가야 하고,
 *  0으로 접으면 적자가 "이익 없음"으로 보인다. 선(비율)은 0을 강제하지 않는다 —
 *  부채비율 29~35% 구간을 0부터 그리면 변화가 바닥에 눌려 보이지 않는다. */
export function chartScale(values: Array<number | null>, mode: "bars" | "lines"): { max: number; min: number } {
  const numbers = values.filter((value): value is number => value !== null && Number.isFinite(value));
  if (!numbers.length) return { max: 0, min: 0 };
  let max = Math.max(...numbers);
  let min = Math.min(...numbers);
  if (mode === "bars") {
    max = Math.max(max, 0);
    min = Math.min(min, 0);
  } else {
    const pad = (max - min || Math.abs(max) || 1) * 0.15;
    max += pad;
    min -= pad;
  }
  return { max, min };
}

function QuarterlyStatementChart({ quarters, currency }: { quarters: FundamentalsQuarter[]; currency: string }) {
  const [setKey, setSetKey] = useState<string>(CHART_SETS[0].key);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [anchor, setAnchor] = useState<number | null>(null);
  const chartSet = CHART_SETS.find((row) => row.key === setKey) || CHART_SETS[0];
  const rows = (quarters || []).filter((row) => chartSet.series.some((series) => series.of(row) != null));
  // 세트마다 자료가 있는 분기가 다르다(손익 5분기 vs 재무 4분기) — 세트가 바뀌면
  // 남아 있던 인덱스가 밖을 가리킬 수 있어 마지막 분기로 되돌린다.
  const last = Math.max(0, rows.length - 1);
  const index = Math.min(activeIndex ?? last, last);
  const previous = index - 1;
  const values = chartSet.series.map((series) => rows.map((row) => {
    const value = series.of(row);
    return value === null || value === undefined || !Number.isFinite(value) ? null : value;
  }));
  const scale = chartScale(values.flat(), chartSet.mode);
  const span = scale.max - scale.min;
  const width = 560;
  const plotHeight = 190;
  const labelHeight = 24;
  const groupWidth = rows.length ? width / rows.length : width;
  const barWidth = Math.min(30, (groupWidth - 20) / chartSet.series.length);
  const zeroY = span > 0 ? (scale.max / span) * plotHeight : plotHeight;
  const yOf = (value: number) => ((scale.max - value) / span) * plotHeight;
  const centreX = (rowIndex: number) => rowIndex * groupWidth + groupWidth / 2;
  const formatValue = (value: number | null | undefined) =>
    chartSet.format === "percent" ? percentValueText(value) : compactAmount(value, currency);
  const deltaText = (value: number | null, before: number | null) => {
    if (value === null || before === null) return { text: "—", tone: "flat" as const };
    if (chartSet.format === "percent") {
      // 비율의 변화는 %p 차이가 정직하다 — 비율을 비율로 나누면 두 번 나눈 수가 된다.
      const delta = value - before;
      return { text: `${delta > 0 ? "+" : ""}${delta.toFixed(1)}%p`, tone: toneOf(delta / 100) };
    }
    const ratio = changeRatio(value, before);
    return { text: ratio === null ? "—" : percentText(ratio), tone: toneOf(ratio) };
  };

  const pickSet = (key: string) => {
    setSetKey(key);
    setActiveIndex(null);
    setAnchor(null);
  };
  const segment = (
    <div className="segment" role="group" aria-label="분기 차트 종류">
      {CHART_SETS.map((row) => (
        <button type="button" key={row.key} aria-pressed={row.key === setKey} onClick={() => pickSet(row.key)}>
          {row.label}
        </button>
      ))}
    </div>
  );

  if (rows.length < 2 || span <= 0) {
    return (
      <figure className="watchlist-quarterly">
        {segment}
        <p className="section-subtitle">이 종목은 {chartSet.label} 분기 자료를 받지 못했습니다.</p>
      </figure>
    );
  }

  return (
    <figure className="watchlist-quarterly">
      {segment}
      <div className="watchlist-quarterly__plot" onMouseLeave={() => setAnchor(null)}>
        <svg
          viewBox={`0 0 ${width} ${plotHeight + labelHeight}`}
          role="img"
          aria-label={`최근 ${rows.length}개 분기 ${chartSet.series.map((row) => row.label).join("·")}.`}
        >
          {/* 수평 그리드 — 값 높이를 견줄 기준선이 없으면 상대 비교만 남는다. */}
          {[0.25, 0.5, 0.75].map((step) => (
            <line key={step} x1={0} x2={width} y1={plotHeight * step} y2={plotHeight * step} className="watchlist-quarterly__grid" />
          ))}
          {chartSet.mode === "bars" && <line x1={0} x2={width} y1={zeroY} y2={zeroY} className="watchlist-quarterly__baseline" />}
          {rows.map((row, rowIndex) => (
            <text key={row.quarter || rowIndex} x={centreX(rowIndex)} y={plotHeight + 17} textAnchor="middle" className="watchlist-quarterly__axis">
              {quarterAxisLabel(row.quarter)}
            </text>
          ))}
          {chartSet.mode === "bars" && rows.map((row, rowIndex) => {
            const groupLeft = rowIndex * groupWidth + (groupWidth - barWidth * chartSet.series.length - 10) / 2;
            return (
              <g key={row.quarter || rowIndex}>
                {chartSet.series.map((series, seriesIndex) => {
                  const value = values[seriesIndex][rowIndex];
                  if (value === null) return null;
                  const top = Math.min(yOf(value), zeroY);
                  const barHeight = Math.max(2, Math.abs(yOf(value) - zeroY));
                  return (
                    <rect
                      key={series.key}
                      className="watchlist-quarterly__bar"
                      fill={chartSet.colors[seriesIndex % chartSet.colors.length]}
                      opacity={rowIndex === index ? 1 : 0.75}
                      x={groupLeft + seriesIndex * (barWidth + 5)}
                      y={top}
                      width={barWidth}
                      height={barHeight}
                      rx={4}
                    />
                  );
                })}
              </g>
            );
          })}
          {chartSet.mode === "lines" && chartSet.series.map((series, seriesIndex) => (
            <g key={series.key}>
              <polyline
                className="watchlist-quarterly__line"
                stroke={chartSet.colors[seriesIndex % chartSet.colors.length]}
                points={values[seriesIndex]
                  .map((value, rowIndex) => (value === null ? null : `${centreX(rowIndex).toFixed(1)},${yOf(value).toFixed(1)}`))
                  .filter(Boolean)
                  .join(" ")}
              />
              {values[seriesIndex].map((value, rowIndex) => (
                value === null ? null : (
                  <circle
                    key={rowIndex}
                    cx={centreX(rowIndex)}
                    cy={yOf(value)}
                    r={rowIndex === index ? 4.5 : 3}
                    fill={chartSet.colors[seriesIndex % chartSet.colors.length]}
                  />
                )
              ))}
            </g>
          ))}
          {/* 기간 구간이 hover 대상이다 — 기업분석 차트와 같은 계약. */}
          {rows.map((row, rowIndex) => (
            <rect
              key={`hit-${row.quarter || rowIndex}`}
              className="watchlist-quarterly__hit"
              x={rowIndex * groupWidth}
              y={0}
              width={groupWidth}
              height={plotHeight + labelHeight}
              tabIndex={0}
              role="button"
              aria-label={`${quarterAxisLabel(row.quarter)} 수치 보기`}
              onMouseEnter={() => { setActiveIndex(rowIndex); setAnchor((rowIndex + 0.5) / rows.length); }}
              onFocus={() => { setActiveIndex(rowIndex); setAnchor((rowIndex + 0.5) / rows.length); }}
            />
          ))}
        </svg>
        {anchor !== null && (
          <div
            className="analysis-chart-hover"
            data-side={anchor > 0.5 ? "left" : "right"}
            style={anchor > 0.5 ? { right: `${(1 - anchor) * 100}%` } : { left: `${anchor * 100}%` }}
          >
            <b>{quarterAxisLabel(rows[index]?.quarter)}</b>
            {chartSet.series.map((series, seriesIndex) => (
              <p key={series.key}>
                <span className="analysis-chart-swatch" style={{ background: chartSet.colors[seriesIndex % chartSet.colors.length] }} />
                <span>{series.label}</span>
                <em>{formatValue(values[seriesIndex][index])}</em>
              </p>
            ))}
          </div>
        )}
      </div>
      {/* 마우스를 올리지 않아도 최신 분기 숫자가 보인다 — 기업분석 차트의 판독 패널과 같은 양식. */}
      <div className="analysis-chart-readout">
        <p className="analysis-chart-readout-head">
          <strong>{quarterAxisLabel(rows[index]?.quarter)}</strong>
          {previous >= 0 && <span>{quarterAxisLabel(rows[previous]?.quarter)} 대비</span>}
        </p>
        {chartSet.series.map((series, seriesIndex) => {
          const value = values[seriesIndex][index];
          const before = previous >= 0 ? values[seriesIndex][previous] : null;
          const delta = deltaText(value, before);
          return (
            <p className="analysis-chart-readout-row" key={series.key}>
              <span className="analysis-chart-swatch" style={{ background: chartSet.colors[seriesIndex % chartSet.colors.length] }} />
              <span>{series.label}</span>
              <b>{formatValue(value)}</b>
              <em data-direction={delta.tone}>{delta.text}</em>
            </p>
          );
        })}
      </div>
      {/* 분기별 값 표 — 그림만으로는 정확한 값을 읽을 수 없다. 넓으면 표가 스스로 스크롤한다. */}
      <div className="watchlist-quarterly__table-wrap">
        <table className="watchlist-quarterly__table">
          <thead>
            <tr>
              <th scope="col">항목</th>
              {rows.map((row) => <th scope="col" key={row.quarter}>{quarterAxisLabel(row.quarter)}</th>)}
            </tr>
          </thead>
          <tbody>
            {chartSet.series.map((series, seriesIndex) => (
              <tr key={series.key}>
                <th scope="row">
                  <i className="watchlist-quarterly__dot" style={{ background: chartSet.colors[seriesIndex % chartSet.colors.length] }} aria-hidden="true" />
                  {series.label}
                </th>
                {rows.map((row, rowIndex) => <td key={row.quarter}>{formatValue(values[seriesIndex][rowIndex])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

/** 회사 소개 + 섹터·산업. 소개는 provider 원문(영문)이다. 세 줄로 접고 더보기로 편다. */
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
      <QuarterlyStatementChart quarters={payload.quarters || []} currency={currency} />
    </div>
  );
}
