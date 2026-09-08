import { useEffect, useState } from "react";
import { ApiRequestError } from "../api";
import {
  DIAGNOSTIC_RETENTION_DAYS,
  diagnosticRetentionConfirm,
  diagnosticRetentionPreview,
  diagnosticRetentionSettingsConfirm,
  diagnosticRetentionSettingsPreview,
  diagnosticRetentionStatus,
  type DiagnosticRetentionDays,
  type DiagnosticRetentionPreview,
  type DiagnosticRetentionSettingsPreview,
  type DiagnosticRetentionStatus,
} from "./diagnosticD4Api";

function errorCode(error: unknown) {
  if (error instanceof ApiRequestError) return error.code || `http_${error.status}`;
  if (error instanceof Error && /^[a-z0-9_.-]+$/.test(error.message)) return error.message;
  return "request_failed";
}

function displayTime(value: string | null | undefined) {
  if (!value) return "없음";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "시간 확인 불가" : new Intl.DateTimeFormat("ko-KR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function formatBytes(value: number) {
  if (value < 1024) return `${value}B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)}KiB`;
  return `${(value / (1024 * 1024)).toFixed(2)}MiB`;
}

const DAYS_LABELS: Record<number, string> = { 7: "7일", 30: "30일", 90: "90일", 180: "180일", 365: "365일" };
const EXCLUDED_LABELS: Record<string, string> = { running: "실행 중", unknown: "상태 미확인", recovery: "복구 중", privateBlocked: "보호된 기록", authorityChanged: "상태 변경", corrupt: "손상", deleteFailed: "삭제 실패", other: "기타" };

export function DiagnosticRetention() {
  const [status, setStatus] = useState<DiagnosticRetentionStatus | null>(null);
  const [days, setDays] = useState<DiagnosticRetentionDays>(30);
  const [autoDelete, setAutoDelete] = useState(false);
  const [deletePreview, setDeletePreview] = useState<DiagnosticRetentionPreview | null>(null);
  const [settingsPreview, setSettingsPreview] = useState<DiagnosticRetentionSettingsPreview | null>(null);
  const [busy, setBusy] = useState<"load" | "delete-preview" | "delete-confirm" | "settings-preview" | "settings-confirm" | "">("load");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function load() {
    setDeletePreview(null);
    setSettingsPreview(null);
    setBusy("load");
    setError("");
    try {
      const next = await diagnosticRetentionStatus();
      setStatus(next);
      setDays(next.settings.retentionDays);
      setAutoDelete(next.settings.autoDelete);
    } catch (err) {
      setError(errorCode(err));
    } finally { setBusy(""); }
  }

  useEffect(() => { void load(); }, []);

  async function previewDelete() {
    setBusy("delete-preview"); setError(""); setNotice(""); setDeletePreview(null); setSettingsPreview(null);
    try { setDeletePreview(await diagnosticRetentionPreview(days)); }
    catch (err) { setError(errorCode(err)); }
    finally { setBusy(""); }
  }

  async function confirmDelete() {
    if (!deletePreview || busy || deletePreview.status !== "ready") return;
    setBusy("delete-confirm"); setError("");
    try {
      const result = await diagnosticRetentionConfirm(deletePreview.previewToken);
      const skipped = Object.entries(result.skippedCounts || {}).filter(([, count]) => count > 0).map(([key, count]) => `${EXCLUDED_LABELS[key] || "기타"} ${count}건`).join(" · ");
      setNotice(`진단 상세 ${result.deletedCount}건(${formatBytes(result.deletedBytes)})을 ${result.status === "partial" ? "일부 정리했습니다" : "정리했습니다"}.${skipped ? ` 제외된 항목: ${skipped}.` : ""} 작업 요약은 유지되고 진단 상세만 정리했습니다.`);
      setDeletePreview(null); setSettingsPreview(null);
      await load();
    } catch (err) { setError(errorCode(err)); setDeletePreview(null); setBusy(""); }
  }

  async function previewSettings() {
    setBusy("settings-preview"); setError(""); setNotice(""); setSettingsPreview(null); setDeletePreview(null);
    try { setSettingsPreview(await diagnosticRetentionSettingsPreview(days, autoDelete)); }
    catch (err) { setError(errorCode(err)); }
    finally { setBusy(""); }
  }

  async function confirmSettings() {
    if (!settingsPreview || busy || settingsPreview.status !== "ready") return;
    setBusy("settings-confirm"); setError("");
    try {
      const result = await diagnosticRetentionSettingsConfirm(settingsPreview.previewToken);
      setDays(result.retentionDays); setAutoDelete(result.autoDelete);
      setSettingsPreview(null); setDeletePreview(null);
      setNotice(result.autoDelete ? "보존 설정을 저장했습니다. 자동 삭제는 다음 대상부터 적용됩니다." : "보존 설정을 저장했습니다. 자동 삭제는 꺼져 있습니다.");
      await load();
    } catch (err) { setError(errorCode(err)); setSettingsPreview(null); setBusy(""); }
  }

  const unavailable = status && !status.status.available;
  return (
    <section className="settings-panel input-panel diagnostic-retention" data-qa="diagnostic-retention">
      <div className="input-panel-header">
        <div><h3>진단 보존 관리</h3><p>진단 상세의 보관 기간과 사용량을 확인합니다. 자동 삭제는 기본으로 꺼져 있으며, 미리보기와 확인 후에만 적용됩니다.</p></div>
        <button type="button" className="btn" data-qa="diagnostic-retention-refresh" disabled={busy !== ""} onClick={() => void load()}>상태 새로고침</button>
      </div>
      {busy === "load" && <p role="status">상태를 불러오는 중입니다.</p>}
      {error && <p className="react-dashboard-error" data-qa="diagnostic-retention-error" data-error-code={error} role="alert">진단 보존 상태를 확인하지 못했습니다. ({error}) 다시 시도하세요.</p>}
      {status && (
        <>
          <div className="diagnostic-retention-usage surface surface--group" data-qa="diagnostic-retention-usage">
            <div><span>사용량</span><strong>{formatBytes(status.usage.bytesUsed)}</strong></div>
            <div><span>실행 파일</span><strong>{status.usage.runFiles} / {status.limits.maxRunFiles}</strong></div>
            <div><span>기록 항목</span><strong>{status.usage.entries}</strong></div>
            <div><span>상한</span><strong>{formatBytes(status.limits.maxBytes)}</strong></div>
          </div>
          {unavailable && <p className="react-dashboard-warning" data-qa="diagnostic-retention-unavailable">진단 저장소를 현재 사용할 수 없어 보존 작업을 진행할 수 없습니다.</p>}
          <div className="diagnostic-retention-settings surface surface--group">
            <div className="diagnostic-retention-setting-row">
              <label className="field"><span>보관 기간</span><select value={days} onChange={(event) => { setDays(Number(event.currentTarget.value) as DiagnosticRetentionDays); setSettingsPreview(null); setDeletePreview(null); }} disabled={Boolean(unavailable) || busy !== ""}>{DIAGNOSTIC_RETENTION_DAYS.map((value) => <option value={value} key={value}>{DAYS_LABELS[value]}</option>)}</select></label>
              <label className="diagnostic-retention-checkbox"><input type="checkbox" checked={autoDelete} onChange={(event) => { setAutoDelete(event.currentTarget.checked); setSettingsPreview(null); }} disabled={Boolean(unavailable) || busy !== ""} /> 기간이 지난 진단을 자동 삭제</label>
            </div>
            <p className="settings-hint">현재 {DAYS_LABELS[status.settings.retentionDays]} · 자동 삭제 {status.settings.autoDelete ? "켜짐" : "꺼짐"}. 실행 중 기록과 기존 사용자 자료는 대상에서 제외됩니다.</p>
            <button type="button" className="btn" data-qa="diagnostic-retention-settings-preview" disabled={Boolean(unavailable) || busy !== ""} onClick={() => void previewSettings()}>설정 변경 미리보기</button>
            {settingsPreview && <SettingsPreview preview={settingsPreview} busy={busy !== ""} onConfirm={() => void confirmSettings()} onCancel={() => setSettingsPreview(null)} />}
          </div>
          <div className="diagnostic-retention-delete surface surface--group">
            <p className="diagnostic-retention-subhead">기존 상세 정리</p>
            <p className="settings-hint">정리할 실행 수와 범위를 먼저 확인합니다. 이 동작은 진단 파일만 대상으로 하며, 확인 전에는 삭제하지 않습니다. 작업 요약은 유지됩니다.</p>
            <button type="button" className="btn btn--danger" data-qa="diagnostic-retention-preview" disabled={Boolean(unavailable) || busy !== ""} onClick={() => void previewDelete()}>삭제 대상 미리보기</button>
            {deletePreview && <DeletePreview preview={deletePreview} busy={busy !== ""} onConfirm={() => void confirmDelete()} onCancel={() => setDeletePreview(null)} />}
          </div>
        </>
      )}
      {notice && <p className="react-dashboard-warning" data-qa="diagnostic-retention-notice" role="status">{notice}</p>}
    </section>
  );
}

function SettingsPreview({ preview, busy, onConfirm, onCancel }: { preview: DiagnosticRetentionSettingsPreview; busy: boolean; onConfirm: () => void; onCancel: () => void }) {
  const ready = preview.status === "ready";
  return <div className="diagnostic-retention-preview surface surface--inset" data-qa="diagnostic-retention-settings-preview-panel"><strong>설정 변경 미리보기</strong><p>{DAYS_LABELS[preview.retentionDays]} · 자동 삭제 {preview.autoDelete ? "켜짐" : "꺼짐"} · {preview.changed ? "변경됨" : "변경 없음"}</p><p className="settings-hint">{displayTime(preview.expiresAt)}까지 확인할 수 있습니다.{ready ? "" : " 현재 저장할 수 없는 상태입니다."}</p><div className="diagnostic-retention-actions"><button type="button" className="btn btn--primary" data-qa="diagnostic-retention-settings-confirm" disabled={busy || !ready} onClick={onConfirm}>이 설정 저장</button><button type="button" className="btn btn--text" data-qa="diagnostic-retention-settings-cancel" disabled={busy} onClick={onCancel}>취소</button></div></div>;
}

function DeletePreview({ preview, busy, onConfirm, onCancel }: { preview: DiagnosticRetentionPreview; busy: boolean; onConfirm: () => void; onCancel: () => void }) {
  const excluded = Object.entries(preview.excludedCounts).filter(([, count]) => count > 0).map(([key, count]) => `${EXCLUDED_LABELS[key] || "기타"} ${count}건`).join(" · ") || "없음";
  const ready = preview.status === "ready";
  return <div className="diagnostic-retention-preview surface surface--inset" data-qa="diagnostic-retention-preview-panel"><strong>삭제 대상 미리보기</strong><p>{preview.eligibleCount}건 · {formatBytes(preview.eligibleBytes)} · {displayTime(preview.oldestCreatedAt)} ~ {displayTime(preview.newestCreatedAt)}</p><p className="settings-hint">제외: {excluded}</p><p className="settings-hint">{displayTime(preview.expiresAt)}까지 유효합니다. 실행 중 기록과 권한이 확인되지 않은 기록은 삭제하지 않습니다.{ready ? "" : " 현재 삭제할 수 없는 상태입니다."}</p><div className="diagnostic-retention-actions"><button type="button" className="btn btn--primary btn--danger" data-qa="diagnostic-retention-confirm" disabled={busy || !ready || preview.eligibleCount === 0} onClick={onConfirm}>이 대상 삭제 확인</button><button type="button" className="btn btn--text" data-qa="diagnostic-retention-cancel" disabled={busy} onClick={onCancel}>취소</button></div></div>;
}
