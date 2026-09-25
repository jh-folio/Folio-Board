import { useRef, useState } from "react";
import type { AgentWorkspaceController } from "./useAgentWorkspace";

export function AgentComposer({ workspace }: { workspace: AgentWorkspaceController }) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  return (
    <form className="agent-home-prompt" onSubmit={workspace.handleSubmit}>
      <div className="agent-home-prompt-shell">
        <textarea
          value={workspace.input}
          onChange={(event) => workspace.setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder="오늘 어떤 투자 리서치를 도와드릴까요?"
          rows={3}
        />
        <div className="agent-home-toolbar">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            hidden
            onChange={(event) => {
              workspace.handleFiles(event.currentTarget.files).finally(() => {
                if (fileInputRef.current) fileInputRef.current.value = "";
              });
            }}
          />
          <div className="agent-home-toolbar-left">
            <button
              type="button"
              className="btn btn--icon agent-home-icon-btn"
              onClick={() => fileInputRef.current?.click()}
              aria-label="파일 첨부"
              data-tooltip="파일 첨부"
            >
              +
            </button>
            <span className="agent-home-provider">{workspace.adapter?.label || workspace.adapter?.id || "Folio Board"}</span>
          </div>
          <div className="agent-home-toolbar-right">
            <button
              type="button"
              className="agent-home-icon-btn agent-home-advanced-toggle"
              aria-expanded={showAdvanced}
              onClick={() => setShowAdvanced((current) => !current)}
            >
              상세 설정
            </button>
            {showAdvanced && (
              <>
                <select aria-label="모델" value={workspace.model} onChange={(event) => workspace.persistModel(event.target.value)}>
                  {workspace.modelChoices.length > 0 ? workspace.modelChoices.map((choice) => (
                    <option key={choice.value} value={choice.value}>{choice.label}</option>
                  )) : <option value="">모델 목록 없음</option>}
                </select>
                <select aria-label="노력 단계" value={workspace.effort} onChange={(event) => workspace.setEffort(event.target.value)}>
                  {workspace.effortChoices.map((choice) => (
                    <option key={choice.value} value={choice.value}>{choice.label}</option>
                  ))}
                </select>
              </>
            )}
            <button
              className="btn btn--icon btn--primary agent-home-send"
              type="submit"
              disabled={workspace.busy || !workspace.input.trim()}
              aria-label="전송"
              data-tooltip="전송"
            >
              {workspace.busy ? "..." : "↑"}
            </button>
          </div>
        </div>
      </div>
      {workspace.settingsMessage && <p className="agent-home-notice">{workspace.settingsMessage}</p>}
      {workspace.attachments.length > 0 && (
        <div className="agent-home-attachments">
          {workspace.attachments.map((item) => (
            <span key={item.name}>
              {item.name}
              {/* 이미지는 본문 텍스트가 없어 예전에는 첨부해도 아무 일이 없었다.
                  CLI가 파일을 직접 읽는다는 것과, 못 읽는 경우를 여기서 알린다. */}
              {item.imageData ? <em className="agent-attachment-note">이미지 · Agent가 직접 읽음</em> : null}
              {!item.imageData && !item.content ? <em className="agent-attachment-note">본문 미포함</em> : null}
              <button
                type="button"
                className="btn btn--icon"
                aria-label={`${item.name} 첨부 제거`}
                onClick={() => workspace.setAttachments((current) => current.filter((candidate) => candidate.name !== item.name))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      {workspace.quickStatus && <p className="agent-home-notice">{workspace.quickStatus}</p>}
      {workspace.error && <p className="agent-home-error">{workspace.error}</p>}
    </form>
  );
}

