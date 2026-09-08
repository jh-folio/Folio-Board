import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiRequestError, getJson, postJson, type TossImportAccounts, type TossImportConfirm, type TossImportDetail, type TossImportPreview } from "../../api";
import type { PositionDraft } from "./HoldingsTable";

type Portfolio = { revision: number; positions: PositionDraft[]; cash?: Array<{ currency: string; amount: number }>; updatedAt?: string };

export function importStatusCopy(code: string): string {
  const copy: Record<string, string> = {
    selection_expired: "계좌 선택 시간이 만료되었습니다. 계좌 목록을 다시 불러오세요.",
    preview_expired: "미리보기 시간이 만료되었습니다. 다시 확인하세요.",
    portfolio_revision_conflict: "Portfolio가 변경되었습니다. 최신 상태를 확인한 뒤 다시 미리보기하세요.",
    preview_stale: "보유 내역 또는 Portfolio가 바뀌었습니다. 새 미리보기가 필요합니다.",
    blocking_items: "지원하지 않거나 충돌한 항목이 있어 저장하지 않았습니다.",
    empty_holdings: "가져올 보유 종목이 없습니다. Portfolio는 변경되지 않았습니다.",
    unsupported_account_type: "이 계좌 유형은 가져오기를 지원하지 않습니다.",
    recovery_pending: "이전 가져오기 메타데이터를 복구 중입니다. 수동 Portfolio는 계속 사용할 수 있습니다.",
    metadata_unavailable: "가져오기 메타데이터를 확인할 수 없습니다. 잠시 후 다시 시도하세요.",
    provider_contract_invalid: "Toss Open API 응답 형식을 확인할 수 없습니다. 수동 Portfolio 입력은 계속 사용할 수 있습니다.",
    provider_unavailable: "Toss Open API를 사용할 수 없습니다. 수동 Portfolio 입력은 계속 사용할 수 있습니다.",
    disabled: "Toss Open API가 설정되어 있지 않습니다. 수동 Portfolio 입력은 계속 사용할 수 있습니다.",
    credentials_missing: "Toss Open API 자격 증명이 설정되어 있지 않습니다. 수동 Portfolio 입력은 계속 사용할 수 있습니다.",
    draft_unsaved: "직접 편집한 Portfolio가 저장되지 않았습니다. 먼저 저장하거나 편집을 취소하세요.",
  };
  return copy[code] || "가져오기를 완료하지 못했습니다. 수동 Portfolio 입력은 계속 사용할 수 있습니다.";
}

export function importIssueCopy(code: string): string {
  const copy: Record<string, string> = {
    duplicate_existing_ticker: "기존 Portfolio에 같은 종목 코드가 둘 이상 있습니다",
    duplicate_existing_position: "기존 Portfolio에 같은 포지션이 둘 이상 있습니다",
    duplicate_incoming_ticker: "증권사 응답에 같은 종목 코드가 둘 이상 있습니다",
    market_currency_conflict: "기존 종목의 시장 또는 통화가 다릅니다",
    missing_required_field: "가져오기에 필요한 종목 정보가 없습니다",
    unsupported_market_or_currency: "지원하지 않는 시장 또는 통화입니다",
    invalid_quantity: "수량이 올바르지 않습니다",
    invalid_average_purchase_price: "평균단가가 올바르지 않습니다",
    precision_unsupported: "정확하게 저장할 수 없는 수량 또는 평균단가입니다",
  };
  return copy[code] || "확인할 수 없는 가져오기 항목입니다";
}

export function isBlockingPreview(preview: TossImportPreview | null): boolean {
  return !preview || !preview.canConfirm || preview.buckets.conflicts.length > 0 || preview.buckets.unsupported.length > 0;
}

export function draftAllowsImport(dirty: boolean): boolean {
  return !dirty;
}

const TERMINAL_PREVIEW_CODES = new Set([
  "preview_stale",
  "portfolio_revision_conflict",
  "preview_expired",
  "blocking_items",
  "empty_holdings",
  "idempotency_conflict",
  "fingerprint_collision_or_corruption",
]);

function bucketLabel(label: string, rows: readonly string[]): ReactNode {
  return rows.length ? <li key={label}><strong>{label}</strong> {rows.join(", ")}</li> : null;
}

function previewValue(detail: TossImportDetail, field: "quantity" | "averagePrice"): ReactNode {
  const before = detail.before?.[field] ?? "없음";
  const label = field === "quantity" ? "수량" : "평균단가";
  return <li key={field} aria-label={`${detail.ticker} ${label}: 이전 ${before}, 이후 ${detail.after[field]}, 변경 ${detail.delta[field]}`}>
    <span>{label}</span>
    <span className="toss-holdings-import__detail-value"><small>이전</small><span>{before}</span></span>
    <span className="toss-holdings-import__detail-value"><small>이후</small><span>{detail.after[field]}</span></span>
    <span className="toss-holdings-import__detail-value"><small>변경</small><span>{detail.delta[field]}</span></span>
  </li>;
}

function detailActionCopy(action: TossImportDetail["action"]): string {
  return action === "add" ? "추가" : action === "update" ? "갱신" : "변경 없음";
}

function issueKey(bucket: "conflict" | "unsupported", positionKey: string | null, issueCodes: readonly string[], index: number): string {
  return `${bucket}:${positionKey || "none"}:${issueCodes.join("|")}:${index}`;
}

export function TossHoldingsImport({ portfolio, dirty, onCommitted, onBusyChange, externalBusy = false }: { portfolio: Portfolio | null; dirty: boolean; onCommitted: (portfolio: Portfolio) => void; onBusyChange?: (busy: boolean) => void; /** 상위 저장 중에는 계좌·미리보기·확정을 함께 잠근다. */ externalBusy?: boolean }) {
  const [accounts, setAccounts] = useState<TossImportAccounts | null>(null);
  const [selectionId, setSelectionId] = useState("");
  const [preview, setPreview] = useState<TossImportPreview | null>(null);
  const [busy, setBusy] = useState<"accounts" | "preview" | "confirm" | "">("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const statusRef = useRef<HTMLParagraphElement>(null);
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const authorityReady = portfolio !== null;
  const controlsLocked = busy !== "" || externalBusy;
  useEffect(() => { onBusyChange?.(busy !== ""); }, [busy, onBusyChange]);

  function blockDirtyDraft(): boolean {
    if (draftAllowsImport(dirtyRef.current)) return false;
    setPreview(null); setSelectionId(""); setError(importStatusCopy("draft_unsaved"));
    window.setTimeout(() => statusRef.current?.focus(), 0);
    return true;
  }

  function reportError(reason: unknown) {
    const code = reason instanceof ApiRequestError ? reason.code : "provider_unavailable";
    setError(importStatusCopy(code));
    window.setTimeout(() => statusRef.current?.focus(), 0);
  }

  async function loadAccounts() {
    if (externalBusy) return;
    if (blockDirtyDraft()) return;
    setBusy("accounts"); setError(""); setNotice(""); setPreview(null); setSelectionId("");
    try {
      const payload = await getJson<TossImportAccounts>("/api/portfolio/toss/accounts");
      if (blockDirtyDraft()) return;
      setAccounts(payload);
      setNotice(payload.accounts.length ? "가져올 계좌를 선택하세요. 확인 전에는 Portfolio가 바뀌지 않습니다." : "가져올 수 있는 계좌가 없습니다.");
    } catch (reason) { reportError(reason); } finally { setBusy(""); }
  }

  async function createPreview() {
    if (externalBusy) return;
    if (blockDirtyDraft()) return;
    if (!selectionId) { setError("가져올 계좌를 먼저 선택하세요."); return; }
    setBusy("preview"); setError(""); setNotice(""); setPreview(null);
    try {
      const payload = await postJson<TossImportPreview>("/api/portfolio/toss/preview", { selectionId });
      if (blockDirtyDraft()) return;
      setPreview(payload);
      setNotice(payload.canConfirm ? "미리보기를 확인한 뒤 가져오기를 확정하세요." : (payload.status === "empty" ? "가져올 보유 종목이 없습니다. Portfolio는 변경되지 않습니다." : "충돌 또는 미지원 항목이 있어 Portfolio는 변경되지 않습니다."));
    } catch (reason) { reportError(reason); } finally { setBusy(""); }
  }

  async function confirm() {
    if (externalBusy) return;
    if (blockDirtyDraft()) return;
    if (!preview || !portfolio || isBlockingPreview(preview)) return;
    setBusy("confirm"); setError("");
    try {
      const payload = await postJson<TossImportConfirm<Portfolio>>("/api/portfolio/toss/confirm", { previewId: preview.previewId, expectedRevision: preview.expectedRevision });
      if (blockDirtyDraft()) return;
      onCommitted(payload.portfolio);
      setNotice(payload.metadataStatus === "recovery_pending" ? importStatusCopy("recovery_pending") : (payload.idempotent ? "이미 반영된 가져오기입니다." : "보유 내역을 반영했습니다."));
      setPreview(null); setSelectionId("");
    } catch (reason) {
      // These replies prove that this opaque preview can no longer authorize a
      // write. Remove its confirm control immediately; account selection stays
      // available so the user can explicitly request a fresh preview.
      if (reason instanceof ApiRequestError && TERMINAL_PREVIEW_CODES.has(reason.code)) setPreview(null);
      reportError(reason);
    } finally { setBusy(""); }
  }

  return (
    <section className="surface surface--group toss-holdings-import" aria-labelledby="toss-import-title">
      <div className="toss-holdings-import__head"><div><span>TOSS OPEN API</span><h3 id="toss-import-title">보유 내역 가져오기</h3></div><span className="chip status-chip" data-tone="muted">미리보기 후 확인</span></div>
      <p>선택한 증권 계좌 한 개의 보유 종목만 추가 또는 갱신합니다. 현금과 직접 입력한 종목은 유지됩니다.</p>
      <div className="portfolio-actions">
        <button type="button" className="btn" onClick={() => void loadAccounts()} disabled={controlsLocked || !authorityReady}>{busy === "accounts" ? "계좌 확인 중" : "Toss 계좌 불러오기"}</button>
      </div>
      {!authorityReady && <p className="react-reader-status" role="status" aria-live="polite">Portfolio 기준을 불러오는 중입니다. 계좌 가져오기는 준비되면 사용할 수 있습니다.</p>}
      {accounts && <div className="toss-holdings-import__accounts" role="list" aria-label="Toss 계좌 선택">
        {accounts.accounts.map((account) => (
          <div key={account.selectionId || `${account.label}-${account.accountType}`} role="listitem"><button type="button" className="btn toss-import-account" aria-pressed={selectionId === account.selectionId} disabled={!account.selectable || controlsLocked} onClick={() => { setSelectionId(account.selectionId || ""); setPreview(null); setError(""); }}>
            <span>{account.label}</span><small>{account.selectable ? "증권 계좌" : "지원하지 않음"}</small>
          </button></div>
        ))}
      </div>}
      {selectionId && <div className="portfolio-actions"><button type="button" className="btn" onClick={() => void createPreview()} disabled={controlsLocked}>{busy === "preview" ? "미리보기 생성 중" : "미리보기"}</button></div>}
      {preview && <div className="surface surface--inset toss-holdings-import__preview">
        <h4>변경 미리보기</h4>
        {preview.details.length > 0 && <div className="toss-holdings-import__details" aria-label="포지션별 변경 상세">
          {preview.details.map((detail) => <div key={detail.positionKey} className="toss-holdings-import__detail">
            <div><strong>{detail.ticker}</strong><span className="chip status-chip" data-tone="muted">{detailActionCopy(detail.action)}</span><small>{detail.currency}</small></div>
            <ul>{previewValue(detail, "quantity")}{previewValue(detail, "averagePrice")}</ul>
          </div>)}
        </div>}
        <ul>
          {bucketLabel("추가", preview.buckets.additions)}
          {bucketLabel("갱신", preview.buckets.updates)}
          {bucketLabel("직접 입력 유지", preview.buckets.preservedManual)}
          {bucketLabel("변경 없음", preview.buckets.unchanged)}
          {preview.buckets.conflicts.map((issue, index) => <li key={issueKey("conflict", issue.positionKey, issue.issueCodes, index)}><strong>충돌</strong> {issue.positionKey || "알 수 없는 종목"} · {issue.issueCodes.map(importIssueCopy).join(", ")}</li>)}
          {preview.buckets.unsupported.map((issue, index) => <li key={issueKey("unsupported", issue.positionKey, issue.issueCodes, index)}><strong>지원하지 않음</strong> {issue.positionKey || "알 수 없는 종목"} · {issue.issueCodes.map(importIssueCopy).join(", ")}</li>)}
        </ul>
        <button type="button" className="btn btn--primary" onClick={() => void confirm()} disabled={controlsLocked || isBlockingPreview(preview) || !portfolio}>{busy === "confirm" ? "반영 중" : "가져오기 확정"}</button>
      </div>}
      {busy && <p className="react-reader-status" role="status" aria-live="polite">{busy === "accounts" ? "계좌를 확인하고 있습니다." : busy === "preview" ? "미리보기를 만들고 있습니다." : "가져오기를 반영하고 있습니다."}</p>}
      {(notice || error) && <p ref={statusRef} className={error ? "react-dashboard-error" : "react-reader-status"} role={error ? "alert" : "status"} aria-live="polite" tabIndex={-1}>{error || notice}</p>}
    </section>
  );
}
