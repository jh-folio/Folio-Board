import { useEffect, useRef, useState } from "react";
import { getJson } from "../../api";
import type { CompanyResolution } from "../companyAnalysis/useCompanyResolution";
import { money, percent, signOf, type PositionRow } from "./portfolioTypes";

export type PositionDraft = {
  ticker: string;
  quantity: number | string;
  averagePrice?: number | string;
  market?: string;
  currency?: string;
  /** 화면 전용 행 식별자다. 저장 요청에는 넣지 않는다. */
  _draftId?: string;
};

export type PositionFieldError = { readonly row: number; readonly field: "ticker" | "quantity" | "averagePrice" | string; readonly code: string };

export function positionFieldErrorCopy(code: string): string {
  const copy: Record<string, string> = {
    required: "종목을 입력하세요.",
    invalid_decimal: "유한한 숫자만 입력할 수 있습니다.",
    invalid_quantity: "수량은 0보다 커야 합니다.",
    invalid_average_price: "평균단가는 0 이상이어야 합니다.",
    precision_unsupported: "최대 128자리, 지수 -1000~1000 범위의 값을 입력하세요.",
  };
  return copy[code] || "입력값을 확인하세요.";
}

function normalizedTicker(value: string): string { return value.trim().toUpperCase(); }

export function HoldingsTable({ positions, onChange, errors = [], disabled = false, resolverEpoch = 0, onResolverInvalidated }: {
  positions: PositionDraft[];
  onChange: (positions: PositionDraft[]) => void;
  errors?: readonly PositionFieldError[];
  disabled?: boolean;
  /** 저장·취소·행 삭제 때 올라가며, 이미 떠난 해석 응답을 무효화한다. */
  resolverEpoch?: number;
  onResolverInvalidated?: () => void;
}) {
  const [names, setNames] = useState<Record<string, string>>({});
  const positionsRef = useRef(positions);
  const resolverEpochRef = useRef(resolverEpoch);
  positionsRef.current = positions;
  useEffect(() => { resolverEpochRef.current = resolverEpoch; }, [resolverEpoch]);
  useEffect(() => () => { resolverEpochRef.current += 1; }, []);

  function update(index: number, field: keyof PositionDraft, value: string) {
    onChange(positions.map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row));
  }

  function errorFor(index: number, field: string): PositionFieldError | undefined {
    return errors.find((item) => item.row === index && item.field === field);
  }

  function removeRow(index: number) {
    const id = positions[index]?._draftId;
    onResolverInvalidated?.();
    onChange(positions.filter((_, rowIndex) => rowIndex !== index));
    if (id) setNames((prev) => { const next = { ...prev }; delete next[id]; return next; });
  }

  /** 입력을 벗어날 때 한 번만 해석한다. 늦은 응답은 현재 행과 입력이 같을 때만 적용한다. */
  async function resolveRow(index: number, raw: string) {
    const text = raw.trim();
    const rowId = positionsRef.current[index]?._draftId;
    const requestEpoch = resolverEpochRef.current;
    if (!rowId) return;
    if (!text) {
      setNames((prev) => ({ ...prev, [rowId]: "" }));
      return;
    }
    try {
      const result = await getJson<CompanyResolution>(`/api/company/resolve?q=${encodeURIComponent(text)}&limit=1`);
      if (requestEpoch !== resolverEpochRef.current) return;
      const latest = positionsRef.current;
      const latestIndex = latest.findIndex((row) => row._draftId === rowId);
      const current = latest[latestIndex];
      if (latestIndex < 0 || !current || normalizedTicker(current.ticker) !== normalizedTicker(text)) return;
      if (result.status !== "confident" || !result.match) {
        setNames((prev) => ({ ...prev, [rowId]: "" }));
        return;
      }
      const match = result.match;
      setNames((prev) => ({ ...prev, [rowId]: match.name }));
      const patch: Partial<PositionDraft> = {};
      if (match.ticker && normalizedTicker(match.ticker) !== normalizedTicker(text)) patch.ticker = match.ticker;
      if (match.market && !current.market) patch.market = match.market;
      if (Object.keys(patch).length) onChange(latest.map((row, rowIndex) => rowIndex === latestIndex ? { ...row, ...patch } : row));
    } catch {
      if (requestEpoch === resolverEpochRef.current) setNames((prev) => ({ ...prev, [rowId]: "" }));
    }
  }

  return (
    <div className="portfolio-holdings-table-wrap portfolio-holdings-table-wrap--editor">
      <table className="portfolio-holdings-table portfolio-holdings-table--editor" aria-label="보유 종목 편집">
        <thead><tr><th>종목</th><th>수량</th><th>평균단가</th><th>시장</th><th><span className="sr-only">삭제</span></th></tr></thead>
        <tbody>{positions.map((row, index) => <tr key={row._draftId || index}>
          <td data-label="종목">{(() => { const issue = errorFor(index, "ticker"); const errorId = `holding-${index}-ticker-error`; return <><input aria-label={`${index + 1}번 종목`} disabled={disabled} aria-invalid={issue ? true : undefined} aria-describedby={issue ? errorId : undefined} value={row.ticker} onChange={(event) => update(index, "ticker", event.currentTarget.value.toUpperCase())} onBlur={(event) => void resolveRow(index, event.currentTarget.value)} placeholder="NVDA / 삼성전자" />{issue && <small id={errorId} className="portfolio-field-error" role="alert">{positionFieldErrorCopy(issue.code)}</small>}</>; })()}{row._draftId && names[row._draftId] && <small className="holdings-resolved">{names[row._draftId]}</small>}</td>
          <td data-label="수량">{(() => { const issue = errorFor(index, "quantity"); const errorId = `holding-${index}-quantity-error`; return <><input aria-label={`${row.ticker || index + 1} 수량`} disabled={disabled} aria-invalid={issue ? true : undefined} aria-describedby={issue ? errorId : undefined} value={row.quantity} onChange={(event) => update(index, "quantity", event.currentTarget.value)} inputMode="decimal" />{issue && <small id={errorId} className="portfolio-field-error" role="alert">{positionFieldErrorCopy(issue.code)}</small>}</>; })()}</td>
          <td data-label="평균단가">{(() => { const issue = errorFor(index, "averagePrice"); const errorId = `holding-${index}-average-price-error`; return <><input aria-label={`${row.ticker || index + 1} 평균단가`} disabled={disabled} aria-invalid={issue ? true : undefined} aria-describedby={issue ? errorId : undefined} value={row.averagePrice ?? ""} onChange={(event) => update(index, "averagePrice", event.currentTarget.value)} inputMode="decimal" />{issue && <small id={errorId} className="portfolio-field-error" role="alert">{positionFieldErrorCopy(issue.code)}</small>}</>; })()}</td>
          <td data-label="시장"><input aria-label={`${row.ticker || index + 1} 시장`} disabled={disabled} value={row.market || ""} onChange={(event) => update(index, "market", event.currentTarget.value.toUpperCase())} placeholder="US / KR / EUROPE / JP" /></td>
          <td data-label="삭제"><button type="button" className="btn btn--text btn--sm" disabled={disabled} onClick={() => removeRow(index)}>삭제</button></td>
        </tr>)}</tbody>
      </table>
      {!positions.length && <p className="cockpit-empty">보유 종목을 추가하세요. 이름으로 입력해도 종목 코드로 확인합니다.</p>}
    </div>
  );
}

/** 저장된 값만 보여 준다. 수량·평균단가는 API가 준 문자열을 가공하지 않는다. */
export function SavedHoldingsTable({ positions, baseCurrency = "USD" }: { positions: ReadonlyArray<PositionRow>; baseCurrency?: string }) {
  if (!positions.length) return <p className="portfolio-empty">저장된 보유 종목이 없습니다.</p>;
  return <div className="portfolio-holdings-table-wrap">
    <table className="portfolio-holdings-table portfolio-holdings-table--saved" aria-label="저장된 보유 종목">
      <thead><tr><th>종목</th><th>수량 · 평균단가</th><th>현재가</th><th>평가액 (USD)</th><th>평가손익 (USD)</th><th>비중</th></tr></thead>
      <tbody>{positions.map((row) => {
        const quoteUnavailable = row.quoteOk === false || Boolean(row.quoteError);
        return <tr key={row.id || `${row.market || ""}:${row.currency || ""}:${row.ticker}`}>
        <th scope="row" data-label="종목"><strong>{row.ticker}</strong>{row.name && <small>{row.name}</small>}</th>
        <td data-label="수량 · 평균단가"><span className="portfolio-exact-number">{row.quantity ?? "—"}</span><small>평균 {row.averagePrice ?? "—"} {row.currency || ""}</small></td>
        <td data-label="현재가"><span className="portfolio-number">{quoteUnavailable || row.currentPrice === null || row.currentPrice === undefined ? "—" : money(row.currentPrice, 2)}</span><small>{quoteUnavailable ? "시세 확인 불가" : row.currency || "현지 통화"}</small></td>
        <td className="portfolio-number" data-label="평가액 (USD)">{money(row.marketValueUsd)}<small>USD 환산</small></td>
        <td className="portfolio-number" data-label="평가손익 (USD)" data-sign={signOf(row.pnlUsd)}>{money(row.pnlUsd)}<small>{percent(row.pnlPct)}</small></td>
        <td className="portfolio-number" data-label="비중">{percent(row.weight)}<small>{baseCurrency} 기준</small></td>
      </tr>})}</tbody>
    </table>
  </div>;
}
