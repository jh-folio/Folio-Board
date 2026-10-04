import { useEffect, useRef, useState } from "react";
import { getJson } from "../../api";
import { openReactAgentDock } from "../agentContext";
import { attributionReason } from "./HistoricalReturn";
import type { Reason } from "./types";

type Movement = { status: string; reason?: Reason; snapshotId?: string; asOf?: string; startDate?: string; endDate?: string;
  startClose?: string; endClose?: string;
  displayPriceReturn?: string; benchmark?: { status: string; id?: string; display?: Record<string, string>; reason?: Reason } };
const signed = (value?: string) => value === undefined ? "확인하지 못함" : `${Number(value)>0?"+":""}${value}%`;

export function ChartReturnActions({ instrumentId, startDate, endDate, selectedDate, intraday, chartStartClose, chartEndClose, onOpenPrice }: {
  instrumentId: string; startDate: string; endDate: string; selectedDate: string | null; intraday: boolean;
  chartStartClose?: number; chartEndClose?: number; onOpenPrice?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [missing, setMissing] = useState(false);
  const request = useRef<AbortController | null>(null);
  const start = selectedDate ?? startDate;
  useEffect(() => { setBusy(false); setNotice(""); setMissing(false); return () => request.current?.abort(); }, [instrumentId, start, endDate, intraday, chartStartClose, chartEndClose]);
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(start) && /^\d{4}-\d{2}-\d{2}$/.test(endDate) && start < endDate;
  async function ask() {
    if (busy || !valid || intraday) return;
    const control = new AbortController(); request.current?.abort(); request.current = control; setBusy(true); setNotice("");
    try {
      const facts = await getJson<Movement>(`/api/price-movement?instrumentId=${encodeURIComponent(instrumentId)}&startDate=${start}&endDate=${endDate}`, { signal: control.signal });
      if (control.signal.aborted) return;
      const differs = facts.status === "available" && ((facts.startDate === start && chartStartClose !== undefined && Number(facts.startClose) !== chartStartClose)
        || (facts.endDate === endDate && chartEndClose !== undefined && Number(facts.endClose) !== chartEndClose));
      const text = facts.status === "available"
        ? `${instrumentId}의 실제 종가 날짜 ${facts.startDate}~${facts.endDate} 주가 수익은 배당 제외 ${signed(facts.displayPriceReturn)}입니다. ${facts.benchmark?.status === "available" ? `같은 날짜 ${facts.benchmark.id} 가격지수는 ${signed(facts.benchmark.display?.index)}입니다.` : attributionReason(facts.benchmark?.reason)} 비교 입력은 ${facts.asOf} 저장 기록입니다.`
        : `${instrumentId}의 요청 기간 ${start}~${endDate} 비교는 ${attributionReason(facts.reason)}`;
      setMissing(facts.status !== "available");
      setNotice(facts.status === "available" ? `비교 입력: ${facts.asOf} 기록 · 실제 ${facts.startDate} → ${facts.endDate}${differs ? ` · 차트 종가와 저장 종가가 다릅니다. 비교에는 저장 종가 ${facts.startClose} → ${facts.endClose}를 사용했습니다.` : ""}` : "선택한 기간의 비교 입력이 없습니다. 가격 탭에서 다시 계산해 주세요.");
      openReactAgentDock({ chartMovement: { instrumentId, snapshotId: facts.snapshotId ?? null, startDate: start, endDate },
        prompt: `${text}${differs ? " 차트 종가와 저장 종가가 달라 비교에는 저장 종가를 사용했습니다." : ""} 이 움직임을 이해하려면 어떤 자료를 확인해야 하나요? 가능한 설명과 확인되지 않은 부분을 구분해 주세요.`, autoSubmit: true });
    } catch { if (!control.signal.aborted) setNotice("비교 기록을 읽지 못했습니다. 다시 시도해 주세요."); }
    finally { if (!control.signal.aborted) setBusy(false); }
  }
  return <div className="price-stack chart-return-actions">
    <div className="price-row">
      <button type="button" className="btn btn--sm" disabled={busy || !valid || intraday} onClick={() => void ask()}>{busy ? "비교 기록 읽는 중…" : "이 움직임 물어보기"}</button>
      {selectedDate && <a className="btn btn--sm" href={`#/macro/state?market=${instrumentId.startsWith("KR:") ? "KR" : "US"}&compareDate=${selectedDate}`}>기준일 이후 네 축 변화 비교</a>}
    </div>
    <p className="price-meta">{intraday ? "장중 봉은 완료 종가가 아닙니다. 일봉 기간을 골라 비교해 주세요." : `요청 기간 ${start || "—"} → ${endDate || "—"} · 날짜를 고르면 그날부터 끝까지 비교합니다.`} · 차트 클릭 또는 방향키로 날짜를 고를 수 있습니다.</p>
    <p role="status" className="price-meta">{notice}</p>
    {missing && onOpenPrice && <button type="button" className="btn btn--sm" onClick={onOpenPrice}>가격 탭에서 비교 입력 준비하기</button>}
  </div>;
}
