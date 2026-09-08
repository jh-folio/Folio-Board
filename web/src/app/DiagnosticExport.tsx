import { useEffect, useRef, useState } from "react";
import { ApiRequestError } from "../api";
import { diagnosticExportPreview, type DiagnosticExportPreview } from "./diagnosticD4Api";

type DiagnosticExportProps = { readonly runId: string };

function errorCode(error: unknown) {
  if (error instanceof ApiRequestError) return error.code || `http_${error.status}`;
  if (error instanceof Error && /^[a-z0-9_.-]+$/.test(error.message)) return error.message;
  return "request_failed";
}

function formatBytes(value: number) {
  if (value < 1024) return `${value}B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)}KiB`;
  return `${(value / (1024 * 1024)).toFixed(2)}MiB`;
}

/** A preview is the only source for download. The browser creates the file locally. */
export function DiagnosticExport({ runId }: DiagnosticExportProps) {
  const [includeParent, setIncludeParent] = useState(false);
  const [includeChildren, setIncludeChildren] = useState(false);
  const [preview, setPreview] = useState<DiagnosticExportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [downloaded, setDownloaded] = useState(false);
  const openerRef = useRef<HTMLButtonElement | null>(null);
  const requestSequence = useRef(0);

  useEffect(() => {
    requestSequence.current += 1;
    setPreview(null);
    setDownloaded(false);
    setError("");
  }, [runId]);

  function changeOption(setter: (value: boolean) => void, value: boolean) {
    requestSequence.current += 1;
    setter(value);
    setPreview(null);
    setDownloaded(false);
  }

  async function previewExport(button: HTMLButtonElement) {
    if (busy) return;
    openerRef.current = button;
    const request = ++requestSequence.current;
    const requestedRunId = runId;
    const requestedParent = includeParent;
    const requestedChildren = includeChildren;
    setBusy(true);
    setError("");
    setDownloaded(false);
    try {
      const next = await diagnosticExportPreview(requestedRunId, requestedParent, requestedChildren);
      if (request === requestSequence.current && requestedRunId === runId && requestedParent === includeParent && requestedChildren === includeChildren) setPreview(next);
    } catch (err) {
      if (request !== requestSequence.current) return;
      setPreview(null);
      setError(errorCode(err));
    } finally {
      setBusy(false);
    }
  }

  function downloadPreview() {
    if (!preview) return;
    const text = JSON.stringify(preview.json);
    if (new TextEncoder().encode(text).byteLength > 1024 * 1024) {
      setError("export_too_large");
      return;
    }
    const blob = new Blob([text], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `diagnostics-${preview.selectedRunId}.json`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
    setDownloaded(true);
  }

  return (
    <details className="diag-export" data-qa="diag-export">
      <summary data-qa="diag-export-toggle">진단 정보 내보내기</summary>
      <div className="diag-export-body">
        <p className="diag-export-note">선택한 실행과 필요한 연결 실행만 안전한 필드로 묶습니다. 외부로 보내지 않고 이 브라우저에서만 다운로드합니다.</p>
        <div className="diag-export-options" role="group" aria-label="내보낼 실행 범위">
          <label><input type="checkbox" checked={includeParent} onChange={(event) => changeOption(setIncludeParent, event.currentTarget.checked)} /> 부모 실행 포함</label>
          <label><input type="checkbox" checked={includeChildren} onChange={(event) => changeOption(setIncludeChildren, event.currentTarget.checked)} /> 자식 실행 포함</label>
        </div>
        <p className="diag-export-limit">최대 20개 실행 · 1MiB · 원본 작업 파일·설정·대화·보고서·자료는 포함하지 않습니다.</p>
        <button type="button" className="btn" data-qa="diag-export-preview" disabled={busy} onClick={(event) => void previewExport(event.currentTarget)}>
          {busy ? "미리보는 중" : "내보내기 미리보기"}
        </button>
        {error && <p className="react-dashboard-error" data-qa="diag-export-error" data-error-code={error} role="alert">내보내기 미리보기에 실패했습니다. ({error}) 다시 시도하세요.</p>}
        {preview && (
          <div className="diag-export-preview surface surface--inset" data-qa="diag-export-preview-panel">
            <p className="diag-export-preview-title">미리보기</p>
            <p className="diag-export-summary" data-qa="diag-export-summary">{preview.summary}</p>
            <dl className="diag-export-facts">
              <dt>포함 실행</dt><dd>{preview.runCount}개</dd>
              <dt>파일 크기</dt><dd>{formatBytes(preview.byteCount)}</dd>
              <dt>범위</dt><dd>{preview.includeParent ? "부모 포함" : "선택 실행만"}{preview.includeChildren ? " · 자식 포함" : ""}</dd>
            </dl>
            <details className="diag-export-json">
              <summary>안전한 JSON 보기</summary>
              <pre data-qa="diag-export-json">{JSON.stringify(preview.json, null, 2)}</pre>
            </details>
            <div className="diag-export-actions">
              <button type="button" className="btn btn--primary" data-qa="diag-export-download" onClick={downloadPreview}>이 미리보기 다운로드</button>
              {downloaded && <span className="diag-export-downloaded" role="status">다운로드를 요청했습니다. 브라우저 저장 결과를 확인하세요.</span>}
            </div>
            <p className="diag-export-expiry">미리보기 내용만 다운로드할 수 있습니다. 서버에 다시 요청하지 않습니다.</p>
          </div>
        )}
      </div>
    </details>
  );
}
