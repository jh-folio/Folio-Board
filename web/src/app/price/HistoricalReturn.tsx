import { useEffect, useState } from "react";
import { getJson } from "../../api";
import { GuideSection } from "./Guide";
import { money, multiple, ratioText, reasonText, timesText } from "./format";
import type { AttributionBlock, Reason, SnapshotView } from "./types";

export function attributionReason(reason?: Reason): string {
  const y0 = reason?.startFiscalYear, y1 = reason?.endFiscalYear;
  const code = reason?.code ?? "comparison_inputs_missing";
  const sides = reason?.endpoints ?? ["start", "end"];
  const sideWords = sides.map(side => side === "start" ? "시작" : "끝").join("·");
  if (code === "attribution_history_too_short") return reason?.subCode === "years_too_few"
    ? `재무 기록은 FY${reason.firstFiscalYear ?? "—"}~FY${y1 ?? "—"}이며, 선택한 ${reason.requestedYears ?? ""}년의 시작 연도 FY${y0 ?? "—"} 자료가 없어 이익과 PER로 나누지 않았습니다.`
    : `${sideWords} 연도 ${sides.map(side => `FY${(side === "start" ? y0 : y1) ?? "—"}`).join("·")}의 주당이익이 없어 이익과 PER로 나누지 않았습니다.`;
  if (code === "endpoint_price_missing" && reason?.requestedDate) return `${reason.endpoint === "start" ? "시작" : "끝"} 가격(${reason.requestedDate})을 확인하지 못해 이 기간의 주가 수익을 계산하지 않았습니다.`;
  if (code === "benchmark_date_missing" && reason?.startDate) return `종목의 ${sideWords} 가격 날짜 ${sides.map(side => side === "start" ? reason.startDate : reason.endDate).join("·")}에 지수 기록이 없어 같은 날짜 비교를 표시하지 않습니다.`;
  if (code === "non_positive_start_eps") return `시작 연도 FY${y0} 주당이익이 0 이하라 이익과 PER로 나누지 않았습니다.`;
  if (code === "non_positive_end_eps") return `끝 연도 FY${y1} 주당이익이 0 이하라 이익과 PER로 나누지 않았습니다.`;
  const texts: Record<string, string> = {
    non_positive_both_eps: "시작·끝 연도의 주당이익이 모두 0 이하라 이익과 PER로 나누지 않았습니다.",
    comparison_inputs_missing: "이 계산 기록에는 날짜별 비교 입력이 없습니다. 다시 계산하면 준비할 수 있습니다.",
    comparison_input_conflict: "기준 종가와 날짜별 비교 입력이 달라 이 비교를 계산하지 않았습니다.",
    invalid_period: "시작과 끝 가격 날짜가 같거나 순서가 맞지 않아 이 기간을 계산하지 않았습니다.",
    price_event_unverified: "선택한 기간의 가격에 주식 수 변화가 반영됐는지 확인하지 못해 주가 수익을 계산하지 않았습니다.",
    share_event_unknown: "주식 수가 바뀐 사건을 확인하지 못해 이익과 PER로 나누지 않았습니다.",
    endpoint_price_missing: "시작 또는 끝 가격을 확인하지 못해 이 기간의 주가 수익을 계산하지 않았습니다.",
    dividend_history_unavailable: "선택한 기간의 날짜별 배당 기록을 확인하지 못해 배당 포함 전체 수익을 계산하지 않았습니다.",
    dividend_unit_unverified: "배당 금액의 주식 단위를 확인하지 못해 배당 포함 전체 수익을 계산하지 않았습니다.",
    unsupported_distribution_event: "현금배당·분할만으로 반영할 수 없는 분배 사건이 있어 전체 수익을 계산하지 않았습니다.",
    benchmark_unavailable: "시장지수 자료를 확인하지 못해 지수 비교를 표시하지 않습니다. 종목 계산은 유지합니다.",
    benchmark_date_missing: "종목의 시작 또는 끝 가격 날짜에 지수 기록이 없어 같은 날짜 비교를 표시하지 않습니다.",
  };
  return texts[code] ?? reasonText(reason);
}

// 이미 % 단위로 반올림된 표시값(예: "1345.7")에 부호·천 단위 구분을 붙인다.
const signed = (s?: string, unit = "%p") => s === undefined ? "—" : `${Number(s) > 0 ? "+" : Number(s) < 0 ? "−" : ""}${Math.abs(Number(s)).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}${unit}`;

/**
 * 첫 문장의 결론. 사실만 말하고 원인은 단정하지 않는다. "거의 그대로"는 변화 10% 미만.
 * 어느 쪽 몫이 더 컸는지는 배수의 로그 크기로 비교한다(주가 = 주당이익 × PER).
 */
export function attributionConclusion(epsFactor: number, peFactor: number, priceUp: boolean): string {
  const small = (f: number) => Math.abs(f - 1) < 0.1, up = (f: number) => f > 1;
  if (small(epsFactor) && small(peFactor)) return "주당이익과 PER 모두 크게 변하지 않았습니다.";
  if (small(peFactor)) return `거의 주당이익이 ${up(epsFactor) ? "늘어난" : "줄어든"} 만큼 움직였고, PER은 거의 그대로였습니다.`;
  if (small(epsFactor)) return `주당이익은 거의 그대로였고, 대부분 PER이 ${up(peFactor) ? "오른" : "내린"} 몫입니다.`;
  const bigger = Math.abs(Math.log(epsFactor)) >= Math.abs(Math.log(peFactor)) ? "주당이익" : "PER";
  if (up(epsFactor) && up(peFactor)) return `주당이익 증가와 PER 상승이 함께 끌어올렸고, ${bigger} 쪽 몫이 더 컸습니다.`;
  if (!up(epsFactor) && !up(peFactor)) return `주당이익 감소와 PER 하락이 함께 끌어내렸고, ${bigger} 쪽 몫이 더 컸습니다.`;
  if (up(epsFactor)) return `주당이익은 늘었지만 PER이 낮아져, 이익이 늘어난 만큼 ${priceUp ? "오르지는" : "버티지"} 못했습니다.`;
  return "주당이익은 줄었지만 PER이 올라, 이익이 줄어든 만큼 내리지는 않았습니다.";
}

type FactorRow = { key: string; label: string; factor: number; className?: string; kind?: "result" | "bench" };
const TICKS = [0.01, 0.03, 0.1, 0.3, 0.5, 1, 2, 3, 10, 30, 100];
const MAJOR = new Set([0.01, 0.1, 1, 10, 100]);

/** 배수 막대: ×1 기준선을 가운데 두고 로그 눈금. 기준선 쪽은 직각, 뻗어 나간 끝만 둥글다. 결과(주가)는 구분선 아래. */
function FactorBars({ rows, picked }: { rows: FactorRow[]; picked: string | null }) {
  const factors = rows.map(r => r.factor).concat([1]);
  const span = Math.max(Math.log10(Math.max(...factors)), -Math.log10(Math.min(...factors)), Math.log10(2)) * 1.06;
  const at = (f: number) => 50 + (Math.log10(f) / span) * 46;
  // 좁은 화면에서는 10배 단위 눈금만 남긴다. 배수 폭이 작아 그런 눈금이 셋 미만이면 ×0.5·×1·×2를 남긴다.
  const visible = TICKS.filter(t => Math.abs(Math.log10(t)) <= span + 1e-9);
  const decades = visible.filter(t => MAJOR.has(t));
  const major = new Set(decades.length >= 3 ? decades : visible.filter(t => t === 0.5 || t === 1 || t === 2));
  return (
    <div className="price-xbars" role="img" aria-label={rows.map(r => `${r.label} ${timesText(r.factor)}`).join(", ")}>
      {rows.map(r => {
        const a = at(Math.min(1, r.factor)), b = at(Math.max(1, r.factor));
        const dim = picked !== null && picked !== r.key && !r.kind ? " is-dim" : "";
        return (
          <div key={r.key} className={`price-xbar${r.kind ? ` is-${r.kind}` : ""}`}>
            <span>{r.label}</span>
            <div className="price-xbar__track"><i className="price-xbar__one" /><i className={`price-xbar__fill ${r.factor >= 1 ? "is-right" : "is-left"} ${r.className ?? ""}${dim}`} style={{ left: `${a.toFixed(2)}%`, width: `${(b - a).toFixed(2)}%` }} /></div>
            <strong>{timesText(r.factor)}</strong>
          </div>
        );
      })}
      <div className="price-xbars__axis" aria-hidden="true">
        {visible.map(t => <span key={t} className={major.has(t) ? undefined : "is-minor"} style={{ left: `${at(t).toFixed(2)}%` }}>×{t}</span>)}
      </div>
    </div>
  );
}

function EpsSource({ label, eps }: { label: string; eps: Record<string, unknown> | null }) {
  const period = eps?.period as { start?: string; end?: string } | undefined;
  return <p>{label} EPS 근거: {eps ? <>
    공시 {String(eps.form ?? "공식 연간 자료")} · 제출 {String(eps.filed ?? "—")} · 공시 번호 {String(eps.accession ?? eps.receiptNo ?? "—")} · 회계기간 {period?.start ?? "—"} → {period?.end ?? "—"} · 항목 {String(eps.concept ?? eps.sourceField ?? "희석 주당이익")} · 원값 {String(eps.rawValue ?? eps.value)} → 같은 주식 단위 {String(eps.value)} ({String(eps.unit ?? "주당")})
  </> : "주당이익 자료 없음"}</p>;
}

function PriceSource({ source }: { source: Record<string, unknown> }) {
  const request = source.request as { provider?: string; providerSymbol?: string; start?: string; endExclusive?: string } | undefined;
  return <p>가격 출처: {request?.provider ?? "저장된 가격 제공자"} · 종목 {request?.providerSymbol ?? "—"} · 제공자 프로그램 버전 {String(source.sourceVersion ?? "—")} · 요청 일봉 기간 {request?.start ?? "—"} → {request?.endExclusive ?? "—"}(끝 날짜 제외) · 배당 미조정 종가 · {String(source.currency ?? "통화 미확인")}</p>;
}

type Movement = { status: string; startDate?: string; endDate?: string; priceReturn?: string };

export function HistoricalReturnSection({ view }: { view: SnapshotView }) {
  const [years, setYears] = useState<1 | 3 | 5>(5);
  const [block, setBlock] = useState<AttributionBlock | undefined>(view.historicalReturnAttribution);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const [after, setAfter] = useState<Movement | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setPicked(null); setError("");
    if (years === 5) { setBlock(view.historicalReturnAttribution); setLoading(false); return; }
    setLoading(true); setBlock(undefined);
    getJson<SnapshotView>(`/api/price-snapshots/${encodeURIComponent(view.snapshotId)}?attributionYears=${years}`, { signal: controller.signal })
      .then(next => { if (!controller.signal.aborted) setBlock(next.historicalReturnAttribution); })
      .catch(() => { if (!controller.signal.aborted) setError("이 기간의 기록을 읽지 못했습니다. 기간을 바꿔 다시 읽어 주세요."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [view, years]);
  // 기간 끝(회계연도 말) 뒤 계산 기준일까지의 주가. 저장된 입력만 읽고(분할 반영), 나누지 않는다.
  const endDate = block?.status === "available" ? block.endDate : undefined;
  useEffect(() => {
    setAfter(null);
    if (!endDate || endDate >= view.asOf) return;
    const controller = new AbortController();
    getJson<Movement>(`/api/price-movement?instrumentId=${encodeURIComponent(view.instrumentId)}&startDate=${endDate}&endDate=${view.asOf}&snapshotId=${encodeURIComponent(view.snapshotId)}`, { signal: controller.signal })
      .then(next => { if (!controller.signal.aborted && next.status === "available") setAfter(next); })
      .catch(() => {});
    return () => controller.abort();
  }, [view, endDate]);

  const ready = block?.status === "available", display = block?.display ?? {};
  const currency = view.inputSummary.price.currency;
  const earn = block?.earnings, bench = block?.benchmark;
  const priceFactor = 1 + Number(block?.priceReturn ?? 0);
  const word = priceFactor >= 1 ? "올랐습니다" : "내렸습니다";
  const epsFactor = earn?.status === "available" ? Number(earn.endEps) / Number(earn.startEps) : null;
  const peFactor = earn?.status === "available" ? Number(earn.endPE) / Number(earn.startPE) : null;
  const split = epsFactor !== null && peFactor !== null;
  const benchRow: FactorRow[] = bench?.status === "available" && bench.display?.index !== undefined
    ? [{ key: "bench", label: bench.id ?? "시장지수", factor: 1 + Number(bench.display.index) / 100, kind: "bench" }] : [];
  const dividendReady = block?.dividend?.status === "available";
  const explanations: Record<string, string> = {
    growth: split ? `주당이익이 ${money(earn?.startEps, currency)}에서 ${money(earn?.endEps, currency)}로 ${ratioText(epsFactor - 1, 0)} 바뀌었습니다. PER이 그대로였다면 주가도 같은 비율로 움직였을 것입니다. 아래 '지난 5년 이익 성장은 어디서 왔나'에서 매출·이익률·주식 수로 이어 볼 수 있습니다.` : "",
    rerating: split ? `PER(주가 ÷ 주당이익)이 ${multiple(earn?.startPE)}에서 ${multiple(earn?.endPE)}로 ${ratioText(peFactor - 1, 0)} 바뀌었습니다. 같은 이익을 시장이 더 비싸게(또는 싸게) 쳐준 정도입니다. 왜 바뀌었는지는 이 숫자만으로 알 수 없습니다.` : "",
    dividend: `기간 안 배당락일의 현금배당 ${block?.dividend?.amount ?? "—"}을 세전·재투자 없이 더해 시작 주가로 나눈 값입니다. 실제 입금 날짜나 세금은 반영하지 않습니다.`,
  };
  // 지수 비교용 종목 주가 수익은 독립 표시값(spec-5 §4.3). 지수가 없어도 종목 값은 남긴다.
  const benchSentence = bench?.status === "available"
    ? ` 시장 비교(배당 제외): 종목 ${signed(bench.display?.stock, "%")} / ${bench.id} ${signed(bench.display?.index, "%")}, 차이 ${signed(bench.display?.difference)}.`
    : ` 배당 제외 주가 수익: 종목 ${signed(display.price, "%")}.`;
  const additive = `덧셈으로 나누면 이익 ${signed(display.growth)}, PER ${signed(display.rerating)}${display.dividend !== undefined ? `, 배당 ${signed(display.dividend)}` : ""}입니다(두 변화가 겹치는 몫은 PER 쪽에 넣음).`;
  const calc = !ready ? undefined : split
    ? `주가 = 주당이익 × PER(주가 ÷ 주당이익)이므로, 주가 변화 = 주당이익 변화 × PER 변화입니다. (${money(earn?.endEps, currency)} ÷ ${money(earn?.startEps, currency)}) × (${multiple(earn?.endPE)} ÷ ${multiple(earn?.startPE)}) = ${timesText(epsFactor)} × ${timesText(peFactor)} = ${timesText(priceFactor)}.${block?.total?.status === "available" ? ` 받은 배당까지 더하면 전체 ${signed(display.total, "%")}입니다.` : ""} ${additive}${benchSentence}`
    : `주가 변화 = 끝 종가 ÷ 시작 종가 − 1 = ${signed(display.price, "%")}.${bench?.status === "available" ? benchSentence : ""}`;
  const read = !ready ? undefined : split
    ? "주당이익 쪽이 크면 회사가 실제로 더 벌어서 오른 것이고, PER 쪽이 크면 같은 이익을 더 비싸게(또는 싸게) 쳐준 것입니다. PER이 왜 바뀌었는지는 이 숫자만으로 알 수 없습니다. 회계연도 말 종가끼리 비교했습니다."
    : "적자 구간에서는 PER(주가 ÷ 주당이익)이 의미를 잃어 나누지 않습니다. 주가와 시장지수의 움직임만 사실로 보여 줍니다.";
  const cards = split ? [
    { key: "growth", label: "주당이익", swatch: "price-c1", value: ratioText(epsFactor - 1, 0), sub: `${money(earn?.startEps, currency)} → ${money(earn?.endEps, currency)}` },
    { key: "rerating", label: "PER", swatch: "price-swatch-cut", value: ratioText(peFactor - 1, 0), sub: `${multiple(earn?.startPE)} → ${multiple(earn?.endPE)}` },
    { key: "dividend", label: "받은 배당", swatch: "price-c3", value: dividendReady ? ratioText(Number(block?.dividend?.contribution)) : "—", sub: dividendReady ? "시작 주가 대비" : "배당 기록 확인 불가" },
  ] : [];

  const basis = ready && <details className="price-details price-attribution-basis"><summary>이 기간의 계산 원값과 출처</summary>
      <p>실제 종가 날짜 {block.startDate} → {block.endDate} · 기간 전체 누적 수익 · 배당은 배당락일 기준, 세전·재투자 없음</p>
      <p>시작 가격 {block.startClose} → 끝 가격 {block.endClose} {currency} · 시작 주당이익 {String(block.basis?.start.eps?.value ?? earn?.startEps ?? "—")} → 끝 주당이익 {String(block.basis?.end.eps?.value ?? earn?.endEps ?? "—")}</p>
      <p>기간 배당 합계 {block.dividend?.amount ?? "—"} · 저장 기준일 {view.asOf}{block.dividend?.basis === "provider_record_no_dividend" ? " · 제공자 기록상 배당 없음" : ""}</p>
      <p>가격 수익 = {block.endClose} ÷ {block.startClose} − 1. 이익 기여 = 끝 주당이익 ÷ 시작 주당이익 − 1. PER 기여 = 가격 수익 − 이익 기여. 배당 기여 = 기간 배당 ÷ 시작 가격.</p>
      {block.calculation && <>
        <p>반올림 전 비율: 가격 {block.calculation.rawPriceReturn} · 이익 {block.calculation.rawGrowth ?? "—"} · PER {block.calculation.rawRerating ?? "—"} · 배당 {block.calculation.rawDividend ?? "—"} · 전체 {block.calculation.rawTotal ?? "—"}</p>
        <p>응답 4자리 비율: 이익 {block.calculation.response.growth ?? "—"} + PER {block.calculation.response.rerating ?? "—"} + 배당 {block.calculation.response.dividend ?? "—"} = 전체 {block.calculation.response.total ?? "—"}</p>
        <p>화면 %p 조정: 이익 {display.growth ?? "—"} + PER {display.rerating ?? "—"} + 배당 {display.dividend ?? "—"} = 전체 {display.total ?? "—"}%</p>
      </>}
      {block.basis && <><EpsSource label="시작" eps={block.basis.start.eps} /><EpsSource label="끝" eps={block.basis.end.eps} /><PriceSource source={block.basis.priceSource} /></>}
      <p>{years === 5 && view.results.decomposition.status === "available" && view.results.decomposition.recentWindow[0] === block.startFiscalYear && view.results.decomposition.recentWindow[1] === block.endFiscalYear
        ? "아래 '지난 5년 이익 성장은 어디서 왔나'는 같은 회계연도 구간입니다. 공시 주당이익과 순이익÷주식 수의 차이는 그 섹션의 계산 안내에 남깁니다."
        : view.results.decomposition.status === "available" ? `아래 이익 성장 섹션은 별도의 5년 구간(FY${view.results.decomposition.recentWindow[0]}~FY${view.results.decomposition.recentWindow[1]})입니다.` : ""}</p>
    </details>;

  return <GuideSection id="price-historical-return-title" title="지난 주가 수익은 어디서 왔나"
    meta={ready ? `FY${block.startFiscalYear} 말 → FY${block.endFiscalYear} 말` : "회계연도 말끼리 비교"}
    question="회사가 돈을 더 벌어서 올랐는지, 시장이 더 비싸게 쳐줘서 올랐는지 나눠 봅니다."
    hint={ready && split ? "카드를 누르면 설명이 나옵니다" : undefined}
    calc={calc} read={read} footer={basis}>
    {view.methodVersion === "price-scenario-5" && <div className="price-horizon"><span id="historical-period-label">과거 기간</span><div className="segment" role="group" aria-labelledby="historical-period-label">
      {([1, 3, 5] as const).map(n => <button key={n} type="button" aria-pressed={years === n} onClick={() => setYears(n)}>{n}년</button>)}
    </div></div>}
    {loading ? <div className="macro-skeleton" role="status" aria-label="과거 수익 기록을 읽고 있습니다"><span className="macro-skeleton__line" /></div>
      : error ? <p role="alert">{error}</p> : !ready ? <p className="price-lead">{attributionReason(block?.reason)}</p> : <>
        <p className="price-lead">이 기간 주가는 <strong>{ratioText(priceFactor - 1)}</strong>({timesText(priceFactor)}) {word}. {split ? attributionConclusion(epsFactor, peFactor, priceFactor >= 1) : attributionReason(earn?.reason)}</p>
        {split ? <div className="price-dec">
          <div className="price-dec__cards" role="group" aria-label="주가 수익 요인 선택: 누르면 설명합니다">
            {cards.map(c => <button key={c.key} type="button" className="price-dec__card" aria-pressed={picked === c.key} onClick={() => setPicked(current => current === c.key ? null : c.key)}>
              <i className={c.swatch} /><span>{c.label}</span><strong>{c.value}</strong><em className="price-dec__sub">{c.sub}</em>
            </button>)}
          </div>
          <FactorBars picked={picked} rows={[{ key: "growth", label: "주당이익", factor: epsFactor, className: "price-c1" }, { key: "rerating", label: "PER", factor: peFactor, className: "is-hatch" }, { key: "price", label: "주가", factor: priceFactor, kind: "result" }, ...benchRow]} />
          {picked && <p className="price-explain" aria-live="polite">{explanations[picked]}</p>}
        </div> : <FactorBars picked={null} rows={[{ key: "price", label: "주가", factor: priceFactor, kind: "result" }, ...benchRow]} />}
        {bench?.status !== "available" && <p className="price-meta">{attributionReason(bench?.reason)}</p>}
        {!dividendReady && split && <p className="price-meta">{attributionReason(block.dividend?.reason)}</p>}
        {after?.priceReturn !== undefined && <p className="price-meta">그 뒤 계산 기준일({view.asOf})까지 주가는 {ratioText(Number(after.priceReturn))} 움직였습니다. 이 구간은 아직 연간 실적이 없어 나누지 않았습니다.</p>}
      </>}
  </GuideSection>;
}
