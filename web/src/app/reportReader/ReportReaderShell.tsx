import { ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";
import { setReactAgentContextScope, type AgentContextPatch } from "../agentContext";
import { FolioNotePanel, type FolioNoteIdentity } from "./FolioNotePanel";
import type { PersonalOverlayPayload } from "../deepResearchPayload";

type ReportReaderShellProps = {
  eyebrow?: string;
  title: string;
  meta?: string;
  breadcrumb: ReactNode;
  actionSlot?: ReactNode;
  noteSlot?: ReactNode;
  noteIdentity?: FolioNoteIdentity;
  noteLinkedTitle?: string;
  noteOverlay?: PersonalOverlayPayload | null;
  agentContext?: AgentContextPatch;
  onClose?: () => void;
  children: ReactNode;
};

export function ReportReaderShell({
  eyebrow,
  title,
  meta,
  breadcrumb,
  actionSlot,
  noteSlot,
  noteIdentity,
  noteLinkedTitle,
  noteOverlay,
  agentContext,
  onClose,
  children,
}: ReportReaderShellProps) {
  const [mobileNoteOpen, setMobileNoteOpen] = useState(false);
  const [readingFocus, setReadingFocus] = useState(false);
  const readerRef = useRef<HTMLElement>(null);
  const noteTriggerRef = useRef<HTMLButtonElement>(null);
  const notePanelRef = useRef<HTMLElement>(null);
  const noteCloseRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const resolvedNoteSlot = noteSlot ?? (noteIdentity ? (
    <FolioNotePanel
      identity={noteIdentity}
      linkedTitle={noteLinkedTitle || title}
      overlay={noteOverlay || null}
    />
  ) : null);
  const agentContextKey = agentContext ? JSON.stringify(agentContext) : "";
  const stageClass = [
    "report-reader-stage",
    readingFocus ? "is-reading-focus" : "",
    !actionSlot && !resolvedNoteSlot ? "no-side" : "",
    !actionSlot ? "no-rail" : "",
    !resolvedNoteSlot ? "no-note" : "",
  ].filter(Boolean).join(" ");

  useEffect(() => {
    if (!agentContextKey || !agentContext) return;
    const viewId = String(agentContext.viewId || "");
    const scope = viewId === "topicrpt" ? "deep-research" : viewId;
    if (scope) setReactAgentContextScope(scope, agentContext);
  }, [agentContext, agentContextKey]);

  useEffect(() => {
    readerRef.current?.focus({ preventScroll: true });
  }, [title]);

  const closeMobileNote = useCallback(() => {
    setMobileNoteOpen(false);
    window.requestAnimationFrame(() => noteTriggerRef.current?.focus({ preventScroll: true }));
  }, []);

  useEffect(() => {
    if (!mobileNoteOpen) return;
    noteCloseRef.current?.focus({ preventScroll: true });
    const panel = notePanelRef.current;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeMobileNote();
        return;
      }
      if (event.key !== "Tab" || !panel) return;
      const controls = Array.from(panel.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'))
        .filter((item) => item.getClientRects().length > 0);
      if (!controls.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, [closeMobileNote, mobileNoteOpen]);

  useEffect(() => {
    const handleReaderEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || mobileNoteOpen || !onClose) return;
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest('[role="dialog"][aria-modal="true"]')) return;
      event.preventDefault();
      onClose();
    };
    document.addEventListener("keydown", handleReaderEscape);
    return () => document.removeEventListener("keydown", handleReaderEscape);
  }, [mobileNoteOpen, onClose]);

  return (
    <div className="report-reader-shell report-reader-inline" data-report-reader-shell>
      <div className="reader-breadcrumb report-reader-breadcrumb">{breadcrumb}</div>
      <div className={stageClass}>
        <section ref={readerRef} className="report-reader-dialog report-reader-main" aria-labelledby={titleId} tabIndex={-1}>
          <div className="report-reader-head">
            {(actionSlot || resolvedNoteSlot) && <button className="btn report-reading-focus" type="button" aria-pressed={readingFocus} onClick={() => setReadingFocus((value) => !value)}>{readingFocus ? "조작·노트 펼치기" : "읽기에 집중"}</button>}
            {onClose && (
              <button className="btn btn--icon icon-btn" type="button" onClick={onClose} aria-label="리더 닫기" data-qa="dr-report-close" data-tooltip="닫기" data-tooltip-pos="left">
                ×
              </button>
            )}
          </div>
          <div className="report-reader-body">
            <section className="report-hero react-report-hero">
              {eyebrow && <p className="report-kicker">{eyebrow}</p>}
              <h1 id={titleId}>{title}</h1>
              {meta && <p className="report-hero-meta">{meta}</p>}
            </section>
            <div className="headline react-report-card">{children}</div>
          </div>
        </section>
          {actionSlot && (
            <aside className="report-reader-rail" aria-label="보고서 조작 패널">
              {actionSlot}
            </aside>
          )}
        {resolvedNoteSlot && (
          <>
            <button
              ref={noteTriggerRef}
              className={mobileNoteOpen ? "report-note-grip is-open" : "report-note-grip"}
              type="button"
              aria-label="투자 노트 열기"
              aria-controls="report-reader-note-panel"
              aria-expanded={mobileNoteOpen}
              data-qa="reader-note-open"
              onClick={() => setMobileNoteOpen(true)}
            />
            <aside
              ref={notePanelRef}
              id="report-reader-note-panel"
              className={mobileNoteOpen ? "report-note-panel is-open" : "report-note-panel"}
              aria-label="투자 노트"
              role={mobileNoteOpen ? "dialog" : undefined}
              aria-modal={mobileNoteOpen ? true : undefined}
            >
              <div className="report-note-inner">
                <button
                  ref={noteCloseRef}
                  className="btn btn--icon report-note-mobile-close"
                  type="button"
                  aria-label="투자 노트 닫기"
                  data-qa="reader-note-close"
                  onClick={closeMobileNote}
                >
                  ×
                </button>
                {resolvedNoteSlot}
              </div>
            </aside>
          </>
        )}
      </div>
    </div>
  );
}
