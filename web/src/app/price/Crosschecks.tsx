import { cashPerHundred, money, multiple, pct, pctSigned, reasonText, rowFor } from "./format";
import type { CashConversion, Projection, SnapshotView } from "./types";

const LABELS = ["conservative", "base", "optimistic"] as const;
const NAMES = { conservative: "보수", base: "기본", optimistic: "낙관" };

export function ReturnPartsLine({ view, horizon, selected = 1 }: { view: SnapshotView; horizon: 5 | 10; selected?: number }) {
  const parts = view.results.returnParts;
  if (!parts || !Array.isArray(parts)) return <p className="price-meta">수익률의 세 조각: {reasonText("previous_method")}.</p>;
  const label = LABELS[selected];
  const part = parts.find(r => r.label === label && r.horizon === horizon);
  const scenario = rowFor(view.results.scenarios, label, horizon);
  if (!part || part.status !== "available") return <p className="price-meta">{NAMES[label]} {horizon}년 수익률의 세 조각: {reasonText(part?.reason.code)}.</p>;
  return <div className="price-return-parts" aria-live="polite">
    <p className="price-note">{NAMES[label]} {horizon}년: 이익 성장 {pctSigned(part.growth, 2)} + 배당 {pctSigned(part.dividend, 2)} + PER 변화 {pctSigned(part.rerating, 2)} = 연 {pct(scenario?.status === "available" ? scenario.irr : null, 2)}</p>
    <p className="price-meta">현재 PER {part.peNow}배 → 끝날 때 {part.exitPE}배. PER이 그대로라면 연 {pct(part.irrFlat, 2)}입니다. 차이로 나눈 설명이며 독립적인 기여도를 뜻하지 않습니다.</p>
  </div>;
}

export function NoGrowthLine({ view, projection }: { view: SnapshotView; projection: Projection | null }) {
  const block = projection?.noGrowth;
  const source = view.results.noGrowth;
  if (!block || block.status !== "available") return <p className="price-meta">성장이 없다면: {reasonText(block?.reason.code ?? "previous_method")}.</p>;
  return <div className="price-no-growth">
    <p className="price-note">{block.hasGrowthShare
      ? `성장이 없다면, 이 가격의 약 ${cashPerHundred(block.growthShare)}%는 앞으로의 성장에 거는 몫입니다.`
      : `성장이 없어도 지금 가격이 설명됩니다(성장 없는 가치가 가격의 ${multiple(block.priceCoverage, 1)}).`}</p>
    <p className="price-meta">성장 없는 가치 {money(block.value, view.inputSummary.price.currency)} · 내 요구수익률 연 {pct(block.requiredReturn, 2)} 기준. {source?.status === "available" && <>주당 매출 {money(source.rps0, view.inputSummary.price.currency)} × 과거 보통 이익률 {pct(source.marginP50, 2)}({source.marginN}개 연도)로 주당이익 {money(source.normEps, view.inputSummary.price.currency)}를 구했습니다. 최근 주당이익 {source.recentEps === null ? "자료 없음" : money(source.recentEps, view.inputSummary.price.currency)}. </>}실현 가능성과 내 기준 충족을 판정하지 않습니다.</p>
    <p className="price-meta">이 계산은 이익이 모두 주주 몫으로 남는다고 봅니다. 실제로 현금이 얼마나 남는지는 '이익이 현금으로 남았나'에서 봅니다.</p>
  </div>;
}

export function CashConversionSection({ block, id = "price-cash" }: { block?: CashConversion; id?: string }) {
  const current = block && block.status !== "not_applicable" ? block : null;
  const years = current?.years ?? [];
  const contiguous = years.every((r, i) => i === 0 || r.fiscalYear === years[i - 1].fiscalYear + 1);
  const span = `${contiguous ? `지난 ${years.length}년` : `${years.length}개 회계연도`}(FY${years[0]?.fiscalYear}–FY${years[years.length - 1]?.fiscalYear})`;
  const deducted = current?.sbcBasis === "deducted";
  const basis = deducted ? "주식 보상 비용 차감 후" : "주식 보상 비용 차감 전";
  return <section className="price-section" aria-labelledby={id}>
    <div className="watchlist-detail-section__head"><h3 id={id}>이익이 현금으로 남았나</h3><span className="price-meta">{current?.currency ? `공시 통화 ${current.currency}` : "공시 원본 기준"}</span></div>
    {block?.status === "available" ? <>
      <p className="price-note">{Number(block.ratio) < 0
        ? "같은 기간 순이익은 플러스였지만 설비투자를 뺀 현금은 마이너스였습니다."
        : `순이익 100당 현금이 약 ${cashPerHundred(block.ratio)} 남았습니다.`}</p>
      <p className="price-meta">{span} · {basis}. 연도별 비율의 평균이 아니라 합계를 비교했습니다.</p>
      {block.class !== "cash_in_line" && <p className="price-meta">{block.class === "cash_below_earnings"
        ? "회계 이익보다 현금이 적게 남았습니다. 설비투자나 운전자본 증가가 이유일 수 있습니다."
        : `회계 이익보다 현금이 많이 남았습니다. 감가상각이 설비투자보다 크거나 운전자본이 줄었을 수 있습니다.${!deducted ? " 주식 보상 비용을 빼지 않았습니다." : ""}`}</p>}
    </> : <p className="price-note">{block?.reason.code === "currency_unknown" ? "재무제표 통화를 확인하지 못해 현금 비교를 하지 않았습니다" : reasonText(block?.reason.code ?? "previous_method")}.</p>}
    {current?.notices?.map(n => <p key={n.code} className="price-meta">{n.code === "stale_financials" ? "최근 재무제표가 15개월 넘게 지난 자료입니다. 지난 기간의 합계로 계산했습니다."
      : n.code === "sbc_missing_years" ? `일부 연도(${n.years?.map(y => `FY${y}`).join("·")})에 주식 보상 비용 공시가 없어, 모든 연도에서 빼지 않고 계산했습니다.`
      : "한국 공시는 주식 보상 비용을 같은 방식으로 읽을 수 없어 빼지 않고 계산했습니다."}</p>)}
    {years.length > 0 && <details className="price-details price-cash-details"><summary>연도별 현금 근거 ({years.length}개 회계연도)</summary>
      <div className="price-cash-table" tabIndex={0} role="region" aria-label={`연도별 현금 근거, ${current?.currency}`}>
        <table className="price-table"><caption>공시 원본 금액 · {current?.currency}</caption><thead><tr><th scope="col">회계연도</th><th scope="col">순이익</th><th scope="col">영업현금</th><th scope="col">자본지출</th>{deducted && <th scope="col">주식 보상 비용</th>}<th scope="col">남은 현금</th></tr></thead>
          <tbody>{years.map(r => <tr key={r.fiscalYear}><th scope="row">{r.fiscalYear}</th><td>{money(r.netIncome, current?.currency ?? "")}</td><td>{money(r.ocf, current?.currency ?? "")}</td><td>{money(r.capexOut, current?.currency ?? "")}</td>{deducted && <td>{money(r.sbc, current?.currency ?? "")}</td>}<td>{money(r.fcf, current?.currency ?? "")}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="price-meta">합산 순이익 {money(current?.sumNetIncome, current?.currency ?? "")} · 합산 현금 {money(current?.sumFcf, current?.currency ?? "")}.</p>
      <p className="price-meta">영업현금 − 자본지출{deducted ? " − 주식 보상 비용" : ""}입니다. 순이익은 지배주주 기준이고 영업현금에는 비지배지분이 포함될 수 있습니다. 기업 가치 계산(DCF)의 현금 정의와 다릅니다.</p>
    </details>}
  </section>;
}
