import { useEffect, useRef, useState } from "react";
import { postJson } from "../../api";
import { errorCopy } from "./copy";
import { slotLabels, type Slot } from "./types";

type Impact = { token: string; policy: string; notice: string; linkedJournalCount: number; affected: Array<{ journalId: string; slots: Slot[] }> };
export function useSourceDelete() {
  const [target, setTarget] = useState<{ kind: string; id: string; label: string } | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const dialog = useRef<HTMLDialogElement>(null); const restore = useRef<HTMLElement | null>(null);
  const resolve = useRef<((value: { confirmationToken: string; operationId: string } | null) => void) | null>(null);
  const generation = useRef(0); const origin = useRef("");
  const pending = useRef<AbortController | null>(null); const policyRequest = useRef<AbortController | null>(null);
  const detach = useRef<(() => void) | null>(null);
  function stop() {
    ++generation.current; pending.current?.abort(); policyRequest.current?.abort();
    pending.current = null; policyRequest.current = null; detach.current?.(); detach.current = null;
  }
  function close(confirm = false) {
    const result = confirm && impact ? { confirmationToken: impact.token, operationId: crypto.randomUUID().replace(/-/g, "") } : null;
    stop(); resolve.current?.(result); resolve.current = null;
    dialog.current?.close(); setTarget(null); setImpact(null); setBusy(false);
    if (origin.current === window.location.hash) restore.current?.focus();
  }
  useEffect(() => { if (target) dialog.current?.showModal(); }, [target]);
  useEffect(() => {
    const moved = () => { if (origin.current !== window.location.hash) close(); };
    window.addEventListener("hashchange", moved);
    return () => { window.removeEventListener("hashchange", moved); stop(); resolve.current?.(null); resolve.current = null; };
  }, []);
  async function requestDelete(kind: string, id: string, label: string, signal?: AbortSignal) {
    close(); origin.current = window.location.hash;
    if (signal?.aborted) return null;
    const request = generation.current; const controller = new AbortController(); pending.current = controller;
    const cancelled = () => { if (request === generation.current) close(); };
    signal?.addEventListener("abort", cancelled, { once: true });
    detach.current = () => signal?.removeEventListener("abort", cancelled);
    const isCurrent = () => request === generation.current && !controller.signal.aborted && origin.current === window.location.hash;
    if (id.startsWith("recovery-")) {
      const result = isCurrent() && window.confirm(`${label} 보고서를 삭제할까요?`) ? {} : null;
      stop(); return result;
    }
    let preview: Impact;
    try { preview = await postJson<Impact>("/api/investment-cases/source-delete-preview", { kind, id }, { signal: controller.signal }); }
    catch (reason) { if (!isCurrent()) return null; stop(); throw reason; }
    if (!isCurrent()) return null;
    if (!preview.linkedJournalCount) {
      const result = window.confirm(`${label} 보고서를 삭제할까요?`) ? {} : null;
      stop(); return result;
    }
    restore.current = document.activeElement as HTMLElement;
    setTarget({ kind, id, label }); setImpact(preview); setError("");
    return new Promise<{ confirmationToken: string; operationId: string } | null>(done => { resolve.current = done; });
  }
  async function policy(value: string) {
    if (!target || busy) return;
    const request = generation.current; const controller = new AbortController();
    policyRequest.current?.abort(); policyRequest.current = controller;
    setBusy(true); setError(""); setImpact(null);
    const isCurrent = () => request === generation.current && !controller.signal.aborted && origin.current === window.location.hash;
    try {
      const result = await postJson<Impact>("/api/investment-cases/source-delete-preview", { kind: target.kind, id: target.id, policy: value }, { signal: controller.signal });
      if (isCurrent()) setImpact(result);
    } catch (reason) { if (isCurrent()) setError(errorCopy(reason)); }
    finally { if (isCurrent()) setBusy(false); }
  }
  const node = target && <dialog ref={dialog} className="surface case-delete-dialog" aria-labelledby="case-delete-title" onCancel={event => { event.preventDefault(); close(); }}>
    <h3 id="case-delete-title">보고서와 연결된 보존 기록 확인</h3><p>{target.label}</p><p>이 원자료를 보존한 개인 기록 {impact?.linkedJournalCount ?? "확인 중"}건이 있습니다.</p>
    <label className="field">보존본문 처리<select value={impact?.policy || "purge"} disabled={busy} onChange={event => void policy(event.target.value)}><option value="purge">연결 보존본문도 함께 삭제 (기본)</option><option value="preserve">개인 기록의 보존본문 유지</option></select></label>
    {error && <p role="alert">{error}</p>}<p>{impact?.notice}</p>{impact && <p>영향받는 항목: {[...new Set(impact.affected.flatMap(row => row.slots))].map(slot => slotLabels[slot]).join(", ")}</p>}
    <p>기존 백업에 남은 내용은 자동으로 지우지 않습니다.</p><div className="case-actions"><button className="btn btn--primary btn--danger" disabled={busy || !impact} onClick={() => close(true)}>{impact?.policy === "preserve" ? "보존본 유지 확인 후 원본 삭제" : "원본과 연결 보존본문 삭제"}</button><button className="btn btn--text" onClick={() => close()}>취소</button></div>
  </dialog>;
  return { requestDelete, node };
}
