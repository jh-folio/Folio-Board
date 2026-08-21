import { useEffect, useState } from "react";
import { getJson } from "../../api";
import { compactAmount } from "./EarningsPanel";

/** 재무·투자 지표 — 예전 TradingView 펀더멘털 위젯의 네이티브 대체.
 *
 * **상세를 열 때만 부른다.** 티커당 provider 호출이다(실적 패널과 같은 이유).
 * 서버가 1시간 TTL + 하루 stale-while-revalidate 캐시를 갖고 있어 최근 본 종목은
 * 즉시 그려진다. 결측은 `—`로 보여준다 — provider가 실제로 비워 두는 칸이 있고
 * (삼성전자의 PER), 숨기면 이 종목만 그 지표가 없는 것처럼 읽힌다.
 */

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
  provider?: string;
};

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

export function fundamentalsRows(payload: FundamentalsPayload): Array<{ label: string; value: string }> {
  const currency = payload.currency || "USD";
  return [
    { label: "시가총액", value: compactAmount(payload.marketCap, currency) },
    { label: "PER", value: ratioText(payload.trailingPE) },
    { label: "선행 PER", value: ratioText(payload.forwardPE) },
    { label: "PBR", value: ratioText(payload.priceToBook, 2) },
    { label: "ROE", value: fractionPercentText(payload.returnOnEquity) },
    { label: "영업이익률", value: fractionPercentText(payload.operatingMargins) },
    { label: "순이익률", value: fractionPercentText(payload.profitMargins) },
    { label: "배당수익률", value: percentValueText(payload.dividendYield) },
    { label: "매출 성장(YoY)", value: fractionPercentText(payload.revenueGrowth) },
    { label: "베타", value: ratioText(payload.beta, 2) },
    { label: "52주 범위", value: rangeText(payload.fiftyTwoWeekLow, payload.fiftyTwoWeekHigh) },
  ];
}

export function FundamentalsPanel({ ticker }: { ticker: string }) {
  const [payload, setPayload] = useState<FundamentalsPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setPayload(null);
    setError("");
    if (!ticker) return undefined;
    getJson<FundamentalsPayload>(`/api/market/fundamentals?symbol=${encodeURIComponent(ticker)}`)
      .then((row) => { if (alive) setPayload(row); })
      .catch((reason) => { if (alive) setError(reason instanceof Error ? reason.message : "지표를 불러오지 못했습니다."); })
      .finally(() => undefined);
    return () => { alive = false; };
  }, [ticker]);

  if (!ticker) return null;
  if (error) return <p className="section-subtitle">{error}</p>;
  if (!payload) {
    // 고정 높이 스켈레톤 — 지표가 도착할 때 아래 차트·실적이 밀리지 않는다.
    return <p className="section-subtitle watchlist-fundamentals-skeleton">지표를 불러오는 중입니다.</p>;
  }
  return (
    <dl className="watchlist-fundamentals-grid">
      {fundamentalsRows(payload).map((row) => (
        <div key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}
