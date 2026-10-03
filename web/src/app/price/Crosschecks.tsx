import { useState } from "react";
import { GuideSection, SECTION_IDS } from "./Guide";
import {
  cashPerHundred, cashSpan, irrValue, money, moneyShort, multiple, pct, percentOne, plainOne, reasonText, rowFor, signedOne, toNumber, showReferenceFacts,
} from "./format";
import type { CashConversion, Projection, SnapshotView } from "./types";

export function ReferenceFactsSection({ view }: { view: SnapshotView }) {
  const block = view.results.referenceFacts;
  if (!showReferenceFacts(view) || !block || block.status !== "available") return null;
  const latest = block.years[block.years.length - 1];
  const pe = block.peNow;
  const peText = pe.status === "unavailable" ? reasonText(pe.reason) : pe.state === "loss" ? "최근 연도 적자"
    : pe.state === "zero" ? "최근 연도 주당이익 0" : multiple(pe.value);
  const psText = block.psNow.status === "available" ? multiple(block.psNow.value) : reasonText(block.psNow.reason);
  const cashText = latest?.fcfMargin != null ? pct(latest.fcfMargin) : reasonText(latest?.reasons.fcfMargin ?? "missing_value");
  const cell = (value: string | null, reason: Parameters<typeof reasonText>[0], amount = false) => value === null
    ? <span className="price-meta">{reasonText(reason)}</span> : amount ? moneyShort(value, block.currency) : pct(value);
  return (
    <GuideSection id="price-reference-title" title="수익률 대신 볼 수 있는 숫자" meta={latest ? `FY${latest.fiscalYear} · ${block.currency}` : block.currency}
      question="수익률을 계산할 수 없을 때, 지금 가격과 회사의 기록을 사실 그대로 봅니다."
      calc="지금 PER은 종가 ÷ 최근 주당이익, 매출 대비 주가는 종가 ÷ 최근 주당 매출입니다. 남은 현금 비율은 남은 현금 ÷ 매출입니다."
      read="공시에서 읽거나 계산한 참고 숫자입니다. 적자 회사는 순이익률과 남은 현금이 어느 방향으로 움직이는지 함께 보세요.">
      <div className="price-dec__cards">
        {[["지금 PER", peText], ["매출 대비 주가 (PSR)", psText], ["최근 연도 남은 현금 비율", cashText]].map(([label, text]) => (
          <div className="price-dec__card price-dec__card--static" key={label}><i className="price-swatch-grey" /><span>{label}</span><strong>{text}</strong></div>
        ))}
      </div>
      {block.notices.map(n => <p className="price-meta" key={n.code}>{n.code === "sbc_missing_years"
        ? `일부 연도(${n.years?.map(y => `FY${y}`).join("·")})에 주식 보상 비용 공시가 없어, 모든 연도에서 빼지 않고 계산했습니다.`
        : n.code === "stale_financials" ? "최근 재무제표가 15개월 넘게 지난 자료입니다."
          : "한국 공시는 주식 보상 비용을 같은 방식으로 읽을 수 없어 빼지 않고 계산했습니다."}</p>)}
      <details className="price-details price-cash-details"><summary>연도별 참고 숫자 ({block.years.length}개 회계연도)</summary>
        <div className="price-cash-table" tabIndex={0} role="region" aria-label={`연도별 참고 숫자, ${block.currency}`}>
          <table className="price-table"><caption>연도별 참고 숫자 · {block.currency}</caption>
            <thead><tr><th scope="col">회계연도</th><th scope="col">매출 성장</th><th scope="col">순이익률</th><th scope="col">남은 현금</th></tr></thead>
            <tbody>{block.years.map(y => <tr key={y.fiscalYear}><th scope="row">FY{y.fiscalYear}</th>
              <td>{cell(y.revenueGrowth, y.reasons.revenueGrowth)}</td><td>{cell(y.netMargin, y.reasons.netMargin)}</td><td>{cell(y.fcf, y.reasons.fcf, true)}</td></tr>)}</tbody>
          </table>
        </div>
        <p className="price-meta">남은 현금은 영업현금 − 설비투자{block.sbcBasis === "deducted" ? " − 주식 보상 비용" : ""}이며, 아래 현금 비교와 같은 기준입니다.</p>
      </details>
    </GuideSection>
  );
}

// spec-4 교차 확인 세 섹션(A 수익률 세 조각 · B 성장이 없다면 · C 이익이 현금으로 남았나).
// 계산은 서버가 했다. 여기서는 저장된 값을 글·카드·막대로 옮긴다.

const LABELS = ["conservative", "base", "optimistic"] as const;
const NAMES = { conservative: "보수", base: "기본", optimistic: "낙관" };
const LEVEL = { conservative: "과거 낮은 편", base: "과거 보통 수준", optimistic: "과거 높은 편" };

type PartKey = "g" | "d" | "r";

/** A — 결론 카드에서 고른 시나리오·보유 기간의 수익률을 이익 성장·배당·PER 변화로 나눈다. */
export function ReturnPartsSection({ view, horizon, selected }: { view: SnapshotView; horizon: 5 | 10; selected: number }) {
  const [picked, setPicked] = useState<PartKey | null>(null);
  const label = LABELS[selected];
  const parts = Array.isArray(view.results.returnParts) ? view.results.returnParts : null;
  const part = parts?.find(row => row.label === label && row.horizon === horizon);
  const scenario = rowFor(view.results.scenarios, label, horizon);
  const question = "위에서 고른 시나리오의 수익률이 무엇으로 이뤄지는지 나눠 봅니다. 결론 카드와 보유 기간을 바꾸면 함께 바뀝니다.";
  const meta = `${NAMES[label]} · ${horizon}년 보유`;
  const irr = irrValue(scenario);
  if (!parts || !part || part.status !== "available" || irr === null) {
    const code = !parts ? "previous_method" : part && part.status !== "available" ? part.reason : scenario && scenario.status !== "available" ? scenario.reason : "irr_above_range";
    return <GuideSection id={SECTION_IDS.parts} title="수익률은 어디서 나오나" meta={meta} question={question}><p className="price-note">{reasonText(code)}.</p></GuideSection>;
  }
  // 화면 숫자(소수 1자리)끼리 합이 맞도록 PER 변화는 표시 수익률에서 표시 성장·배당을 뺀 값으로 보인다(spec-4 §2 저장 규칙과 같은 생각).
  const I = percentOne(irr) ?? 0;
  const G = percentOne(part.growth) ?? 0;
  const D = percentOne(part.dividend) ?? 0;
  const R = Math.round((I - G - D) * 10) / 10;
  const F = percentOne(part.irrFlat) ?? 0;
  const payout = scenario && scenario.status === "available" ? scenario.payout : null;
  const peNow = multiple(part.peNow);
  const peExit = multiple(part.exitPE);
  const scale = Math.max(F, G + D, I, 0.1);
  const at = (value: number) => Math.max(0, Math.min(100, (value / scale) * 100));
  const dim = (key: PartKey) => (picked !== null && picked !== key ? " is-dim" : "");
  const explain: Record<PartKey, string> = {
    g: `이익 성장 ${signedOne(G)}: 주당이익이 매년 ${plainOne(G)}씩 늘면, 주가 수준(PER)이 그대로일 때 주가도 같은 속도로 오릅니다. ${LEVEL[label]}의 과거 성장률을 쓴 값입니다.`,
    d: `배당 ${signedOne(D)}: 이익의 ${pct(payout, 0)}를 배당으로 받는다고 볼 때 배당이 수익률에 더하는 몫입니다. 배당성향이 높고 지금 PER이 낮을수록 커집니다.`,
    r: R < 0
      ? `PER 변화 ${signedOne(R)}: 주가 수준(PER)이 지금 ${peNow}에서 ${horizon}년 뒤 ${peExit}로 내려가면, 이익이 늘어도 주가는 그만큼 덜 오릅니다. 그 효과를 1년 평균으로 나눈 값이며, 막대의 빗금 부분입니다.`
      : R > 0
        ? `PER 변화 ${signedOne(R)}: 주가 수준(PER)이 지금 ${peNow}에서 ${horizon}년 뒤 ${peExit}로 올라가면, 주가는 이익보다 더 많이 오릅니다. 그 효과를 1년 평균으로 나눈 값입니다.`
        : "PER 변화: PER이 지금과 같다고 본 계산이라 이 몫이 없습니다.",
  };
  const calc = R < 0
    ? `PER이 지금 ${peNow} 그대로라면 연 ${plainOne(F)}입니다. ${LEVEL[label]}인 ${peExit}로 내려간다고 보면 ${Math.abs(R).toFixed(1)}%p가 깎여 연 ${plainOne(I)}가 됩니다.`
    : R > 0
      ? `PER이 지금 ${peNow} 그대로라면 연 ${plainOne(F)}입니다. ${LEVEL[label]}인 ${peExit}로 올라간다고 보면 ${R.toFixed(1)}%p가 더해져 연 ${plainOne(I)}가 됩니다.`
      : `PER이 지금과 같은 ${peExit}라고 본 계산입니다. 이익 성장 ${plainOne(G)} + 배당 ${plainOne(D)} = 연 ${plainOne(I)}.`;
  return (
    <GuideSection id={SECTION_IDS.parts} title="수익률은 어디서 나오나" meta={meta} question={question} calc={calc}
      read="PER 변화가 크게 마이너스면 ‘주가 수준이 지금보다 내려간다’는 가정이 이미 들어 있다는 뜻이고, 플러스면 주가 수준이 오른다는 가정에 기대고 있다는 뜻입니다.">
      <p className="price-lead">연 <strong>{plainOne(I)}</strong>를 나눠 보면: <span className="price-hint">카드를 누르면 설명이 나옵니다</span></p>
      <div className="price-dec">
        <div className="price-dec__cards" role="group" aria-label="수익률 조각 선택: 누르면 막대에서 강조하고 설명합니다">
          {([["g", "price-c1", "이익 성장", G], ["d", "price-c3", "배당", D], ["r", "price-swatch-cut", "PER 변화", R]] as const).map(([key, color, title, value]) => (
            <button key={key} type="button" className="price-dec__card" aria-pressed={picked === key} onClick={() => setPicked(current => (current === key ? null : key))}>
              <i className={color} /><span>{title}{key === "r" && <em className="price-dec__sub">{peNow} → {peExit}</em>}</span><strong>{signedOne(value)}</strong>
            </button>
          ))}
        </div>
        <div className="price-dec__bar price-parts-bar" role="img" aria-label={`이익 성장 ${signedOne(G)}, 배당 ${signedOne(D)}, PER 변화 ${signedOne(R)}, 합계 연 ${plainOne(I)}`}>
          <span className={`price-c1${dim("g")}`} style={{ width: `${at(G).toFixed(2)}%` }} />
          <span className={`price-c3${dim("d")}`} style={{ width: `${(at(G + D) - at(G)).toFixed(2)}%` }} />
          {R < 0 && <i className={`price-cutseg${dim("r")}`} style={{ left: `${at(Math.max(I, 0)).toFixed(2)}%`, width: `${(at(F) - at(Math.max(I, 0))).toFixed(2)}%` }} />}
          {R > 0 && <span className={`price-c5${dim("r")}`} style={{ width: `${(at(I) - at(G + D)).toFixed(2)}%` }} />}
        </div>
        <div className="price-bar-legend price-bar-legend--two">
          <span className="is-l">0%</span>
          {I > 0 && <span style={{ left: `${at(I).toFixed(2)}%`, transform: at(I) > 88 ? "translateX(-100%)" : at(I) < 12 ? "none" : undefined }}>연 {plainOne(I)}</span>}
          <span className="is-r is-row2">PER이 그대로라면 연 {plainOne(F)}{R < 0 ? " (빗금까지 포함한 막대 끝)" : ""}</span>
        </div>
        {picked && <p className="price-explain" aria-live="polite">{explain[picked]}</p>}
      </div>
    </GuideSection>
  );
}

/** 이전 계산 열기 창에서 쓰는 짧은 한 줄. */
export function ReturnPartsSummary({ view, horizon }: { view: SnapshotView; horizon: 5 | 10 }) {
  const parts = Array.isArray(view.results.returnParts) ? view.results.returnParts : null;
  const part = parts?.find(row => row.label === "base" && row.horizon === horizon);
  const irr = irrValue(rowFor(view.results.scenarios, "base", horizon));
  if (!parts) return <p className="price-meta">수익률의 세 조각: {reasonText("previous_method")}.</p>;
  if (!part || part.status !== "available" || irr === null) return <p className="price-meta">기본 {horizon}년 수익률의 세 조각: {reasonText(part && part.status !== "available" ? part.reason : undefined)}.</p>;
  const I = percentOne(irr) ?? 0, G = percentOne(part.growth) ?? 0, D = percentOne(part.dividend) ?? 0;
  return <p className="price-meta">기본 {horizon}년: 이익 성장 {signedOne(G)} · 배당 {signedOne(D)} · PER 변화 {signedOne(Math.round((I - G - D) * 10) / 10)} = 연 {plainOne(I)}</p>;
}

/** B — 성장이 전혀 없다면 지금 가격 중 얼마가 설명되나. 값은 내 기준으로 읽을 때 계산된다(판정 없음). */
export function NoGrowthSection({ view, projection, onSetCriteria }: { view: SnapshotView; projection: Projection | null; onSetCriteria: () => void }) {
  const block = projection?.noGrowth;
  const source = view.results.noGrowth;
  const currency = view.inputSummary.price.currency;
  const price = view.inputSummary.price.value;
  const question = "앞으로 이익이 전혀 늘지 않는다면, 지금 가격 중 얼마가 설명되는지 봅니다.";
  const read = "이 몫이 클수록 지금 가격이 앞으로의 성장에 더 많이 기대고 있습니다. 이익이 모두 주주 몫으로 남는다고 본 계산이라, 실제로 현금이 남는지는 ③ ‘이익이 현금으로 남았나’에서 함께 보세요.";
  if (!block || block.status !== "available") {
    const code = !block ? "previous_method" : block.reason.code;
    return (
      <GuideSection id={SECTION_IDS.noGrowth} title="성장이 없다면" question={question}>
        {code === "criteria_not_set"
          ? <div className="price-row"><p className="price-note">원하는 수익률(내 기준)을 정하면, 지금 가격 중 성장에 거는 몫을 계산해 보여 드립니다.</p><button className="btn btn--sm" type="button" onClick={onSetCriteria}>기준 정하기</button></div>
          : <p className="price-note">{reasonText(block?.reason ?? code)}.</p>}
      </GuideSection>
    );
  }
  const required = plainOne(percentOne(block.requiredReturn) ?? 0).replace(".0%", "%");
  const valueN = toNumber(block.value) ?? 0;
  const priceN = toNumber(price) ?? 0;
  const growthAmount = Math.max(priceN - valueN, 0);
  const coverage = Math.min(Math.max((toNumber(block.priceCoverage) ?? 0) * 100, 0), 100);
  const share = cashPerHundred(block.growthShare);
  const calcHead = source && source.status === "available"
    ? `주당이익 ${money(source.normEps, currency)}(주당 매출 ${money(source.rps0, currency)} × 과거 보통 순이익률 ${pct(source.marginP50)}, ${source.marginN}개 연도) ÷ 내 기준 ${required} = ${money(block.value, currency)}`
    : `성장 없는 가치 ${money(block.value, currency)}(내 기준 ${required})`;
  const calc = `${calcHead}${block.hasGrowthShare ? ` → ${money(price, currency)} − ${money(block.value, currency)} = ${money(growthAmount, currency)} (가격의 ${share}%)` : ""}${source && source.status === "available" && source.recentEps ? `. 최근 주당이익은 ${money(source.recentEps, currency)}입니다.` : ""}`;
  return (
    <GuideSection id={SECTION_IDS.noGrowth} title="성장이 없다면" meta={`내 기준 연 ${required}로 계산`} question={question} calc={calc} read={read}>
      {block.hasGrowthShare
        ? <p className="price-lead">지금 가격의 약 <strong>{share}%</strong>는 앞으로의 성장에 거는 몫입니다.</p>
        : <p className="price-lead">성장이 없어도 지금 가격이 설명됩니다(성장 없는 가치가 가격의 {multiple(block.priceCoverage, 1)}).</p>}
      <div className="price-dec">
        <div className="price-dec__cards price-dec__cards--two">
          <div className="price-dec__card price-dec__card--static"><i className="price-c1" /><span>성장이 없어도 설명되는 가치</span><strong>{money(block.value, currency)}</strong></div>
          {block.hasGrowthShare
            ? <div className="price-dec__card price-dec__card--static"><i className="price-c5" /><span>앞으로의 성장에 거는 몫</span><strong>{money(growthAmount, currency)}</strong></div>
            : <div className="price-dec__card price-dec__card--static"><i className="price-swatch-grey" /><span>지금 가격</span><strong>{money(price, currency)}</strong></div>}
        </div>
        {block.hasGrowthShare && (
          <>
            <div className="price-dec__bar" role="img" aria-label={`지금 가격 ${money(price, currency)} 중 성장 없는 가치 ${money(block.value, currency)}, 성장에 거는 몫 ${money(growthAmount, currency)}`}>
              <span className="price-c1" style={{ width: `${coverage.toFixed(1)}%` }} /><span className="price-c5" style={{ width: `${(100 - coverage).toFixed(1)}%` }} />
            </div>
            <div className="price-bar-legend">
              <span className="is-l">{money(0, currency)}</span>
              {coverage > 12 && coverage < 75 && <span style={{ left: `${coverage.toFixed(1)}%` }}>{money(block.value, currency)}</span>}
              <span className="is-r">지금 가격 {money(price, currency)}</span>
            </div>
          </>
        )}
      </div>
    </GuideSection>
  );
}

/** C — 회계상 이익이 실제 현금으로 얼마나 남았나. 회사 전체 금액끼리의 비율이라 주당 제한 종목에도 보인다. */
export function CashConversionSection({ block, id = SECTION_IDS.cash, tableInside = true }: { block?: CashConversion; id?: string; tableInside?: boolean }) {
  const current = block && block.status !== "not_applicable" ? block : null;
  const years = current?.years ?? [];
  const span = cashSpan(years);
  const currency = current?.currency ?? "";
  const deducted = current?.sbcBasis === "deducted";
  const question = "회계상 이익이 실제 현금으로 얼마나 남았는지 봅니다.";
  const meta = [span, currency].filter(Boolean).join(" · ") || "공시 원본 기준";
  const notices = (current?.notices ?? []).map(n => (
    <p key={n.code} className="price-meta">{n.code === "stale_financials" ? "최근 재무제표가 15개월 넘게 지난 자료입니다. 지난 기간의 합계로 계산했습니다."
      : n.code === "sbc_missing_years" ? `일부 연도(${n.years?.map(y => `FY${y}`).join("·")})에 주식 보상 비용 공시가 없어, 모든 연도에서 빼지 않고 계산했습니다.`
        : "한국 공시는 주식 보상 비용을 같은 방식으로 읽을 수 없어 빼지 않고 계산했습니다."}</p>
  ));
  if (!block || block.status !== "available") {
    const text = block?.status === "unavailable" && block.reason.code === "currency_unknown" ? "재무제표 통화를 확인하지 못해 현금 비교를 하지 않았습니다" : reasonText(block?.reason ?? "previous_method");
    return (
      <GuideSection id={id} title="이익이 현금으로 남았나" meta={meta} question={question}>
        <p className="price-note">{text}.</p>
        {notices}
        {tableInside && years.length > 0 && <CashTableDetails block={block} />}
      </GuideSection>
    );
  }
  const ratio = toNumber(block.ratio) ?? 0;
  const fill = Math.min(Math.max(ratio * 100, 0), 100);
  const calc = `남은 현금(영업현금 − 설비투자${deducted ? " − 주식 보상 비용" : ""})의 ${span} 합계 ${moneyShort(block.sumFcf, currency)} ÷ 순이익 합계 ${moneyShort(block.sumNetIncome, currency)} = ${ratio.toFixed(2)}${deducted ? "" : ". 주식 보상 비용은 빼지 않았습니다"}`;
  return (
    <GuideSection id={id} title="이익이 현금으로 남았나" meta={meta} question={question} calc={calc}
      read="100에 가까울수록 이익이 현금으로 잘 남았다는 뜻입니다. 크게 낮으면 이익이 설비투자나 운전자본에 묶였을 수 있습니다.">
      <p className="price-lead">{ratio < 0
        ? "같은 기간 순이익은 플러스였지만 설비투자를 뺀 현금은 마이너스였습니다."
        : <>순이익 100당 현금이 약 <strong>{cashPerHundred(block.ratio)}</strong> 남았습니다.</>}</p>
      <div className="price-dec">
        <div className="price-dec__cards price-dec__cards--two">
          <div className="price-dec__card price-dec__card--static"><i className="price-swatch-grey" /><span>{years.length}개 회계연도 순이익 합계</span><strong>{moneyShort(block.sumNetIncome, currency)}</strong></div>
          <div className="price-dec__card price-dec__card--static"><i className="price-c3" /><span>실제로 남은 현금 합계</span><strong>{moneyShort(block.sumFcf, currency)}</strong></div>
        </div>
        <div className="price-dec__bar" role="img" aria-label={`순이익 100당 현금 ${cashPerHundred(block.ratio)}`}><span className="price-c3" style={{ width: `${fill.toFixed(1)}%` }} /></div>
        <div className="price-bar-legend"><span className="is-l">0</span><span className="is-r">막대 전체 = 순이익 100 · 채운 부분 = 남은 현금 {cashPerHundred(block.ratio)}{ratio > 1 ? " (100을 넘어 막대를 다 채움)" : ""}</span></div>
      </div>
      {block.class !== "cash_in_line" && <p className="price-note">{block.class === "cash_below_earnings"
        ? "회계 이익보다 현금이 적게 남았습니다. 설비투자나 운전자본 증가가 이유일 수 있습니다."
        : `회계 이익보다 현금이 많이 남았습니다. 감가상각이 설비투자보다 크거나 운전자본이 줄었을 수 있습니다.${!deducted ? " 주식 보상 비용을 빼지 않았습니다." : ""}`}</p>}
      {notices}
      {tableInside && <CashTableDetails block={block} />}
    </GuideSection>
  );
}

/** 연도별 현금 근거(접기). 금액은 신고 통화로, 짧은 표기로 보인다. */
export function CashTableDetails({ block }: { block?: CashConversion }) {
  const current = block && block.status !== "not_applicable" ? block : null;
  const years = current?.years ?? [];
  if (!current || !years.length) return null;
  const currency = current.currency ?? "";
  const deducted = current.sbcBasis === "deducted";
  return (
    <details className="price-details price-cash-details"><summary>연도별 현금 근거 ({years.length}개 회계연도)</summary>
      <div className="price-cash-table" tabIndex={0} role="region" aria-label={`연도별 현금 근거, ${currency}`}>
        <table className="price-table"><caption>연도별 금액 · {currency}</caption>
          <thead><tr><th scope="col">회계연도</th><th scope="col">순이익</th><th scope="col">영업현금</th><th scope="col">설비투자</th>{deducted && <th scope="col">주식 보상 비용</th>}<th scope="col">남은 현금</th></tr></thead>
          <tbody>{years.map(r => <tr key={r.fiscalYear}><th scope="row">{r.fiscalYear}</th><td>{moneyShort(r.netIncome, currency)}</td><td>{moneyShort(r.ocf, currency)}</td><td>{moneyShort(r.capexOut, currency)}</td>{deducted && <td>{moneyShort(r.sbc, currency)}</td>}<td>{moneyShort(r.fcf, currency)}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="price-meta">합산 순이익 {moneyShort(current.sumNetIncome, currency)} · 합산 현금 {moneyShort(current.sumFcf, currency)}.</p>
      <p className="price-meta">영업현금 − 설비투자{deducted ? " − 주식 보상 비용" : ""}입니다. 순이익은 지배주주 기준이고 영업현금에는 비지배지분이 포함될 수 있습니다. 기업 가치 계산(DCF)의 현금 정의와 다릅니다.</p>
    </details>
  );
}
