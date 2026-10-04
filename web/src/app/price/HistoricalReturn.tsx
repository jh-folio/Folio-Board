import { useEffect, useState } from "react";
import { getJson } from "../../api";
import { GuideSection } from "./Guide";
import { multiple, reasonText } from "./format";
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

const signed = (s?: string, unit = "%p") => s === undefined ? "—" : `${Number(s) > 0 ? "+" : Number(s) < 0 ? "−" : ""}${Math.abs(Number(s)).toFixed(1)}${unit}`;

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

export function HistoricalReturnSection({ view }: { view: SnapshotView }) {
  const [years, setYears] = useState<1 | 3 | 5>(5);
  const [block, setBlock] = useState<AttributionBlock | undefined>(view.historicalReturnAttribution);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
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
  const ready = block?.status === "available", display = block?.display ?? {};
  const parts = [["growth", "이익 성장", "price-c1"], ["rerating", "PER 변화", "price-c5"], ["dividend", "배당", "price-c3"]] as const;
  const max = Math.max(1, ...parts.map(([key]) => Math.abs(Number(display[key] ?? 0))));
  const explanations: Record<string, string> = {
    growth: "양 끝 연간 주당이익의 증가율을 먼저 반영했습니다. 아래의 매출·이익률·주식 수 변화와 이어 읽을 수 있습니다.",
    rerating: "주가 수익에서 이익 성장 기여를 뺀 차액입니다. 이익과 PER이 함께 변한 효과도 여기에 포함됩니다. PER 변화의 원인은 단정하지 않습니다.",
    dividend: "기간 안 배당락일의 현금배당을 세전·재투자 없이 합산했습니다. 실제 계좌에 입금된 날짜나 세금은 반영하지 않습니다.",
  };
  return <GuideSection id="price-historical-return-title" title="지난 주가 수익은 어디서 왔나"
    meta={ready ? `FY${block.startFiscalYear} 말 → FY${block.endFiscalYear} 말` : "회계연도 말끼리 비교"}
    question="선택한 기간의 가격·이익·배당 기록을 같은 주식 한 주 기준으로 나눠 봅니다. 지금 가격까지의 수익은 아닙니다."
    calc="배당 포함 전체 수익 = 이익 성장 기여 + PER 변화 기여 + 배당 기여입니다. 이익을 먼저 반영하고 남은 주가 변화는 PER에 넣습니다. 화면 반올림 차액도 PER에 반영해 합계를 맞췄습니다."
    read="확인된 과거 기록을 이 규칙으로 나눈 값입니다. PER 변화의 이유나 앞으로 같은 수익이 이어질지는 이 숫자만으로 알 수 없습니다.">
    {view.methodVersion === "price-scenario-5" && <div className="price-row"><span id="historical-period-label">과거 비교 기간</span><div className="segment" role="group" aria-labelledby="historical-period-label">
      {([1, 3, 5] as const).map(n => <button key={n} type="button" aria-pressed={years === n} onClick={() => setYears(n)}>{n}년</button>)}
    </div></div>}
    {loading ? <div className="macro-skeleton" role="status" aria-label="과거 수익 기록을 읽고 있습니다"><span className="macro-skeleton__line" /></div>
      : error ? <p role="alert">{error}</p> : !ready ? <p className="price-meta">{attributionReason(block?.reason)}</p> : <>
        <p className="price-lead">이 기록의 배당 포함 전체 수익 <strong>{signed(display.total, "%")}</strong></p>
        <p className="price-meta">실제 종가 날짜 {block.startDate} → {block.endDate} · 기간 전체 누적 수익 · 배당락일 기준, 세전·재투자 없음</p>
        <div className="price-dec__cards" role="group" aria-label="과거 수익 조각 선택">
          {parts.map(([key, label, color]) => <button className="price-dec__card" key={key} type="button" aria-pressed={picked === key} onClick={() => setPicked(p => p === key ? null : key)}>
            <i className={color} /><span>{label}</span><strong>{signed(display[key])}</strong>
            {key === "rerating" && block.earnings?.status === "available" && <span>{multiple(block.earnings.startPE)} → {multiple(block.earnings.endPE)}</span>}
          </button>)}
        </div>
        <div className="price-attribution-bars" role="img" aria-label={parts.map(([k, l]) => `${l} ${signed(display[k])}`).join(", ")}>
          {parts.map(([key, label, color]) => <div className="price-attribution-bar" key={key}><span>{label}</span><div>
            <i className={color} style={{ left: Number(display[key]) < 0 ? `${50-Math.abs(Number(display[key]))/max*50}%` : "50%", width: `${Math.abs(Number(display[key] ?? 0))/max*50}%` }} />
          </div><b>{signed(display[key])}</b></div>)}
        </div>
        <p className="price-meta">막대 중앙은 0%p이며 왼쪽은 음수, 오른쪽은 양수입니다. 수익 원인의 점유율이 아닙니다.</p>
        {picked && <p className="price-explain" aria-live="polite">{explanations[picked]}</p>}
        {block.earnings?.status !== "available" && <p className="price-meta">{attributionReason(block.earnings?.reason)}</p>}
        {block.dividend?.status !== "available" && <p className="price-meta">{attributionReason(block.dividend?.reason)}</p>}
        {block.dividend?.basis === "provider_record_no_dividend" && <p className="price-meta">제공자 기록상 배당 없음</p>}
        <div className="surface surface--inset price-calc">
          {block.benchmark?.status === "available" ? <p>배당 제외 주가 수익: 종목 {signed(block.benchmark.display?.stock, "%")} / {block.benchmark.id} {signed(block.benchmark.display?.index, "%")} · 차이 {signed(block.benchmark.display?.difference)}</p>
            : <><p>배당 제외 주가 수익: 종목 {signed(display.price, "%")}</p><p>{attributionReason(block.benchmark?.reason)}</p></>}
          <p className="price-meta">시장 비교는 종목·지수 모두 배당 제외입니다. 한국 종목의 비교 지수는 KOSPI입니다.</p>
        </div>
        <details className="price-details"><summary>이 기간의 계산 원값과 출처</summary>
          <p>시작 가격 {block.startClose} → 끝 가격 {block.endClose} {view.inputSummary.price.currency} · 시작 주당이익 {String(block.basis?.start.eps?.value ?? block.earnings?.startEps ?? "—")} → 끝 주당이익 {String(block.basis?.end.eps?.value ?? block.earnings?.endEps ?? "—")}</p>
          <p>기간 배당 합계 {block.dividend?.amount ?? "—"} · 저장 기준일 {view.asOf}</p>
          <p>가격 수익 = {block.endClose} ÷ {block.startClose} − 1. 이익 기여 = 끝 주당이익 ÷ 시작 주당이익 − 1. PER 기여 = 가격 수익 − 이익 기여. 배당 기여 = 기간 배당 ÷ 시작 가격.</p>
          {block.calculation && <>
            <p>반올림 전 비율: 가격 {block.calculation.rawPriceReturn} · 이익 {block.calculation.rawGrowth ?? "—"} · PER {block.calculation.rawRerating ?? "—"} · 배당 {block.calculation.rawDividend ?? "—"} · 전체 {block.calculation.rawTotal ?? "—"}</p>
            <p>응답 4자리 비율: 이익 {block.calculation.response.growth ?? "—"} + PER {block.calculation.response.rerating ?? "—"} + 배당 {block.calculation.response.dividend ?? "—"} = 전체 {block.calculation.response.total ?? "—"}</p>
            <p>화면 %p 조정: 이익 {display.growth ?? "—"} + PER {display.rerating ?? "—"} + 배당 {display.dividend ?? "—"} = 전체 {display.total ?? "—"}%</p>
          </>}
          {block.basis && <><EpsSource label="시작" eps={block.basis.start.eps} /><EpsSource label="끝" eps={block.basis.end.eps} /><PriceSource source={block.basis.priceSource} /></>}
        </details>
        <p className="price-meta">{years === 5 && view.results.decomposition.status === "available" && view.results.decomposition.recentWindow[0] === block.startFiscalYear && view.results.decomposition.recentWindow[1] === block.endFiscalYear
          ? "같은 회계연도 구간의 이익 성장 기록을 아래에서 이어 보세요. 공시 주당이익과 순이익÷주식 수의 차이는 아래 계산 안내에 남깁니다."
          : view.results.decomposition.status === "available" ? `아래는 별도의 5년 이익 성장 구간(FY${view.results.decomposition.recentWindow[0]}~FY${view.results.decomposition.recentWindow[1]})입니다.` : "아래 이익 성장 구간은 별도 계산입니다."}</p>
      </>}
  </GuideSection>;
}
