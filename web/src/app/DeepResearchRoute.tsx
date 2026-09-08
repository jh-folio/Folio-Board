import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useContentRevision } from "./useContentRevision";
import { engineNote, groupMeta, listDate } from "./savedListFormat";
import {
  ApiRequestError,
  deleteJson,
  isAbortError,
  FALLBACK_POLICY,
  getJson,
  isActiveJobStatus,
  postJson,
  type ApprovalReference,
  type CollectionRef,
  type ConfirmDegradedRequest,
  type ExecutionRequest,
  type GenerateApprovedRequest,
  type JobStatus,
  type InvestmentTickerContext,
  type MarketStatePolicy,
  type MarketStateScope,
  type PlanPreviewEnvelope,
  type PlannerEngine,
  type PlanRequest,
  type ReplanRequest,
} from "../api";
import { openReactAgentDock, patchReactAgentContextScope, setReactAgentContextScope } from "./agentContext";
import { PROPOSAL_LIFECYCLE_EVENT, proposalTargetsContext, type ProposalLifecycleResult } from "./agentProposalLifecycle";
import { stableNoteKey } from "./reportReader/FolioNotePanel";
import { ReaderActionButton, ReaderActionGroup } from "./reportReader/ReaderActions";
import { ReportBody } from "./reportReader/ReportBody";
import { ReportReaderShell } from "./reportReader/ReportReaderShell";
import { PersonalOverlayView } from "./reportReader/PersonalOverlayView";
import { RouteHero } from "./RouteHero";
import { captureReportError, isResponseLessError, ReportErrorDiagnostic, reportErrorMessage, type CapturedReportError } from "./reportErrorDiagnostic";
import { marketStateContextProjection, readMarketStateRef } from "./marketStateContext";
import {
  deepResearchCollectionHash,
  deepResearchReportHash,
  parseDeepResearchLocation,
  parsePersonalOverlayPayload,
  parseTopicReportPayload,
  parseTopicReportSummaries,
  plannerModeLabel,
  reportTypeLabel,
  type MarketStateResolutionPayload,
  type TopicReport,
  type TopicReportSummary,
} from "./deepResearchPayload";
import { SmartCollectionsPanel, SmartCollectionWorkspace } from "./SmartCollectionWorkspace";
import { InvestmentContextCard } from "./InvestmentContextCard";
import { clearDeepResearchJobId, persistDeepResearchJobId, readDeepResearchJobId, recoverDeepResearchJob } from "./deepResearchJobResume";

/** 계획을 누가 쓰는가. 둘 중 하나이므로 세그먼트로 고른다. */
const PLANNER_ENGINES: ReadonlyArray<{ value: PlannerEngine; label: string; hint: string }> = [
  { value: "auto", label: "AI", hint: "설정한 엔진이 이 질문에 맞는 축과 검색어를 씁니다. 40초쯤 걸립니다." },
  { value: "rules", label: "규칙", hint: "보고서 유형의 기본 축으로 즉시 만듭니다." },
];

type DeepResearchPhase =
  | "readiness"
  | "draft"
  | "plan-loading"
  | "plan-review"
  | "generation"
  | "report"
  | "recoverable-error";

type ErrorKind = "validation" | "readiness" | "plan" | "degraded" | "generation" | "report";

type AgentJob = {
  readonly id: string;
  readonly kind?: string;
  readonly status: JobStatus;
  readonly message?: string;
  readonly error?: string;
  readonly errorCode?: string;
  readonly result?: { readonly reportId?: string; readonly artifactId?: string };
};

type JobEnvelope = { readonly job: AgentJob };

type ExportResult = {
  notionUrl?: string;
  title?: string;
  filename?: string;
  topic?: string;
};

type OverlayResult = {
  personalOverlay?: { markdown?: string } | null;
};

function EmptyProvenance({ children = "저장된 구조화 정보가 없습니다." }: { readonly children?: string }) {
  return <p className="topicrpt-provenance-empty">{children}</p>;
}

function DeepResearchProvenance({ report }: { readonly report: TopicReport }) {
  const plan = report.topicPlan;
  const coverage = report.evidencePackSummary;
  const resolution = report.researchResolution;
  const overlay = parsePersonalOverlayPayload(report.personalOverlay, report.canonicalRevision);
  const userContext = typeof report.userContext === "string" ? report.userContext.trim() : report.userContext ? "생성 요청에 사용자 컨텍스트가 포함되었습니다." : "";
  return (
    <section className="topicrpt-provenance" aria-labelledby="dr-provenance-heading">
      <div className="topicrpt-provenance-heading">
        <p className="section-kicker">사용한 자료와 생성 과정</p>
        <h2 id="dr-provenance-heading">리서치 근거 추적</h2>
        <p>본문에서 실제 사용한 근거와 남은 자료 공백만 간단히 요약합니다.</p>
      </div>
      {report.researchTraceSummary ? (
        <dl className="topicrpt-trace-summary" data-qa="dr-trace-summary">
          <div><dt>사용 근거</dt><dd>{report.researchTraceSummary.usedSourceCount}건</dd></div>
          <div><dt>최신 근거</dt><dd>{report.researchTraceSummary.latestSourceDate || "날짜 미상"}</dd></div>
          <div><dt>반대·도전 근거</dt><dd>{report.researchTraceSummary.challengingSourceCount}건</dd></div>
          <div><dt>남은 자료 공백</dt><dd>{report.researchTraceSummary.unresolvedDataGapCount}건</dd></div>
          {report.researchTraceSummary.cautionReasons.length > 0 && <div className="topicrpt-trace-caution"><dt>주의</dt><dd>{report.researchTraceSummary.cautionReasons.join(" · ")}</dd></div>}
        </dl>
      ) : <EmptyProvenance>요약 추적 정보가 없는 이전 보고서입니다.</EmptyProvenance>}
      {report.contractWarnings.length > 0 && (
        <div className="topicrpt-contract-warning" role="status">
          일부 구조화 필드가 올바르지 않아 안전한 빈 상태로 표시했습니다.
        </div>
      )}
      <details className="topicrpt-trace-details">
        <summary>전체 근거 추적 보기</summary>
        <div className="topicrpt-provenance-grid">
        <section className="topicrpt-provenance-panel" data-qa="dr-approved-plan" aria-labelledby="dr-approved-plan-heading">
          <h3 id="dr-approved-plan-heading">승인된 계획</h3>
          {plan ? (
            <>
              <dl className="topicrpt-provenance-facts">
                <div><dt>주제</dt><dd>{plan.topic || "미기록"}</dd></div>
                <div><dt>보고서 유형</dt><dd>{plan.reportType ? reportTypeLabel(plan.reportType) : "미기록"}</dd></div>
                <div><dt>사용자 의도</dt><dd>{plan.userIntent || "미기록"}</dd></div>
              </dl>
              <h4>리서치 질문</h4>{renderList(plan.researchQuestions)}
              <h4>반증 조건</h4>{renderList(plan.falsificationTriggers)}
            </>
          ) : <EmptyProvenance />}
        </section>

        <section className="topicrpt-provenance-panel" data-qa="dr-evidence-coverage" aria-labelledby="dr-evidence-coverage-heading">
          <h3 id="dr-evidence-coverage-heading">근거 커버리지</h3>
          {coverage ? (
            <>
              <dl className="topicrpt-provenance-facts">
                <div><dt>외부 문서</dt><dd>{coverage.totalDocs}건</dd></div>
                <div><dt>메모리 참조</dt><dd>{coverage.memoryCount}건</dd></div>
              </dl>
              {Object.keys(coverage.roleCounts).length > 0 && <><h4>근거 역할</h4><ul className="topicrpt-provenance-list">{Object.entries(coverage.roleCounts).map(([role, count]) => <li key={role}><strong>{role}</strong><span>{count}건</span></li>)}</ul></>}
              {Object.keys(coverage.axisCoverage).length ? (
                <ul className="topicrpt-provenance-list">
                  {Object.entries(coverage.axisCoverage).map(([key, row]) => <li key={key}><strong>{row.label || key}</strong><span>{row.count}건 · {row.level || "수준 미상"}</span></li>)}
                </ul>
              ) : <EmptyProvenance>분석 축별 커버리지가 없습니다.</EmptyProvenance>}
              {Object.keys(coverage.questionCoverage).length > 0 && <details><summary>리서치 질문 커버리지</summary><ul className="topicrpt-provenance-list">{Object.entries(coverage.questionCoverage).map(([key, row]) => <li key={key}><strong>{row.question || key}</strong><span>{row.count}건 · {row.level || "수준 미상"}</span></li>)}</ul></details>}
              {report.evidenceItems.length > 0 && (
                <details>
                  <summary>선별된 근거 {report.evidenceItems.length}건</summary>
                  <ul className="topicrpt-provenance-list">{report.evidenceItems.map((item) => <li key={item.id}><strong>{item.title}</strong><span>{[item.source, item.role, item.confidence].filter(Boolean).join(" · ")}</span></li>)}</ul>
                </details>
              )}
            </>
          ) : <EmptyProvenance />}
        </section>

        <section className="topicrpt-provenance-panel topicrpt-provenance-wide" data-qa="dr-source-ledger" aria-labelledby="dr-source-ledger-heading">
          <h3 id="dr-source-ledger-heading">외부 근거 원장</h3>
          <p className="topicrpt-layer-note">이 목록만 보고서의 권위 있는 외부 출처 원장입니다.</p>
          {report.sourceLedger.length ? (
            <ol className="topicrpt-source-ledger">
              {report.sourceLedger.map((source) => (
                <li key={source.sourceId}>
                  <div><strong>{source.title || "제목 미상"}</strong><span>{[source.source, source.date, source.evidenceRole, source.reliability, source.artifactType].filter(Boolean).join(" · ")}</span></div>
                  {source.usedInSections.length > 0 && <small>사용 섹션: {source.usedInSections.join(", ")}</small>}
                  {(source.axisKey || source.researchQuestionId || source.researchRound !== null) && <small>추적: {[source.axisKey, source.researchQuestionId, source.researchRound === null ? "" : `round ${source.researchRound}`].filter(Boolean).join(" · ")}</small>}
                  {source.url && <a href={source.url} target="_blank" rel="noopener noreferrer">원문 열기</a>}
                </li>
              ))}
            </ol>
          ) : <EmptyProvenance>확인 가능한 외부 근거 원장이 없습니다.</EmptyProvenance>}
        </section>

        <section className="topicrpt-provenance-panel" data-qa="dr-data-gaps" aria-labelledby="dr-data-gaps-heading">
          <h3 id="dr-data-gaps-heading">자료 공백</h3>
          {report.dataGaps.length ? (
            <ul className="topicrpt-provenance-list">{report.dataGaps.map((gap) => <li key={gap.id} data-severity={gap.severity}><strong>{gap.description}</strong><span>{gap.resolved ? "해결됨" : gap.suggestedAction || "추가 확인 필요"}</span></li>)}</ul>
          ) : <EmptyProvenance>기록된 자료 공백이 없습니다.</EmptyProvenance>}
        </section>

        <section className="topicrpt-provenance-panel" data-qa="dr-quality" aria-labelledby="dr-quality-heading">
          <h3 id="dr-quality-heading">검토 시 주의할 점</h3>
          {report.quality ? (
            <>
              <h4>경고</h4>{renderList(report.quality.warnings, "경고 없음")}
              <h4>보완 제안</h4>{renderList(report.quality.suggestedFixes, "제안 없음")}
            </>
          ) : <EmptyProvenance />}
        </section>

        <section className="topicrpt-provenance-panel topicrpt-provenance-wide" data-qa="dr-collection-resolution" aria-labelledby="dr-collection-resolution-heading">
          <h3 id="dr-collection-resolution-heading">자료 모음 실행 기록</h3>
          {resolution ? (
            <>
              <dl className="topicrpt-provenance-facts topicrpt-provenance-facts-wide">
                <div><dt>자료 모음</dt><dd>{resolution.collectionId || "직접 범위"}</dd></div>
                <div><dt>버전</dt><dd>{resolution.collectionRevision ?? "—"}</dd></div>
                <div><dt>후보</dt><dd>{resolution.eligibleTotal ?? "—"}건</dd></div>
                <div><dt>선택 근거</dt><dd>{resolution.selectedEvidenceIds.length}건</dd></div>
                <div><dt>후보 상한</dt><dd>{resolution.candidateCap ?? "—"}</dd></div>
                <div><dt>해결 / 실행</dt><dd>{resolution.resolvedCandidateIds.length} / {resolution.executionUniverseIds.length}건</dd></div>
              </dl>
              <details><summary>재현성 세부 정보</summary><dl className="topicrpt-provenance-facts topicrpt-provenance-facts-wide"><div><dt>Definition hash</dt><dd>{resolution.collectionDefinitionHash || "—"}</dd></div><div><dt>Input watermark</dt><dd>{resolution.inputWatermark || "—"}</dd></div><div><dt>Index generation</dt><dd>{resolution.providerGenerations.indexGeneration || "—"}</dd></div><div><dt>RSS generation</dt><dd>{resolution.providerGenerations.rssGeneration || "—"}</dd></div><div><dt>Fingerprint</dt><dd>{resolution.resolutionFingerprint || "—"}</dd></div><div><dt>Resolved at</dt><dd>{resolution.resolvedAt || "—"}</dd></div></dl></details>
              {resolution.unusableCandidates.length > 0 && <p className="topicrpt-layer-note">사용 제외 {resolution.unusableCandidates.length}건 · {resolution.unusableCandidates.map((row) => row.reason).join(", ")}</p>}
              {resolution.zeroEvidenceRequired && <p className="topicrpt-contract-warning">근거 부족 확인: {resolution.zeroEvidenceReason || "사유 미기록"}</p>}
            </>
          ) : <EmptyProvenance />}
        </section>

        <aside className="topicrpt-hypothesis-panel" data-qa="dr-user-context-hypothesis" aria-labelledby="dr-user-context-heading">
          <p className="section-kicker">내 생각·가설 · 근거 아님</p>
          <h3 id="dr-user-context-heading">사용자 컨텍스트</h3>
          <p>{userContext || "이 보고서에는 사용자 컨텍스트가 기록되지 않았습니다."}</p>
        </aside>

        <aside className="topicrpt-hypothesis-panel topicrpt-provenance-wide" data-qa="dr-overlay-hypothesis" aria-labelledby="dr-overlay-heading">
          <p className="section-kicker">내 투자 관점과 비교 · 가설</p>
          <h3 id="dr-overlay-heading">개인 해석</h3>
          <PersonalOverlayView overlay={overlay} staleQa="dr-overlay-stale" />
        </aside>
        </div>
      </details>
    </section>
  );
}

export function MarketStateReportContext({ resolution }: { resolution?: MarketStateResolutionPayload }) {
  if (!resolution) return null;
  const ref = readMarketStateRef(resolution);
  const reason = typeof resolution.reason === "string" ? resolution.reason : "";
  const injected = resolution.injected === true;
  const status = ref?.status || (reason === "policy_excluded" ? "excluded" : "unknown");
  const statusCopy = status === "current" && injected
    ? "생성 시점의 현재 상태를 별도 시장 배경으로 포함했습니다."
    : status === "stale" ? "최신성이 만료되어 보고서 판단에는 주입하지 않았습니다."
      : status === "fallback" ? "참고용 대체 상태이며 현재 투자 자세로 사용하지 않았습니다."
        : status === "empty" ? "사용 가능한 시장 상태가 없어 보고서 판단에 포함하지 않았습니다."
          : status === "excluded" ? "요청 정책에 따라 시장 상태를 제외했습니다."
            : "시장 상태 참조를 확인할 수 없습니다.";
  return (
    <aside className={`topicrpt-market-state-context state-${status}`} data-qa="dr-market-state-context" data-status={status} aria-label="별도 시장 상태 배경">
      <div><span>시장 상태 · 근거 기반 배경</span><strong>{status}</strong></div>
      <p>{statusCopy}</p>
      {ref ? <dl><div><dt>기준 시각</dt><dd>{ref.asOf || "없음"}</dd></div><div><dt>최신성</dt><dd>{ref.freshnessReason}</dd></div><div><dt>출처</dt><dd>{ref.sourceKind}</dd></div><div><dt>범위</dt><dd>{ref.scope}</dd></div></dl> : null}
      <small>이 컨텍스트는 외부 근거 목록·인용·가설에 포함되지 않습니다.</small>
    </aside>
  );
}

// 저장 보고서 호환용 topicKey. 0.5 기준 딥 리서치는 질문 중심 하나뿐이라
// 사용자가 고를 프리셋이 없다(선택지 하나짜리 컨트롤은 두지 않는다).
const DEFAULT_TOPIC_KEY = "custom";
// 사용자가 직접 던진 질문 묶음. 프리셋 주제와 구분해 부른다.
const PRESET_LABELS: Record<string, string> = { custom: "직접 질문" };
const JOB_STATUS_VALUES = [
  "queued",
  "running",
  "cancel_requested",
  "committing",
  "done",
  "cancelled",
  "failed",
  "failed_cancel",
  "failed_commit",
  "failed_restart",
  "failed_commit_recovery",
] as const;

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Request cancelled", "AbortError"));
      return;
    }
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    const abort = () => {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      reject(new DOMException("Request cancelled", "AbortError"));
    };
    signal.addEventListener("abort", abort, { once: true });
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isJobStatus(value: unknown): value is JobStatus {
  return typeof value === "string" && JOB_STATUS_VALUES.includes(value as (typeof JOB_STATUS_VALUES)[number]);
}

function isAgentJob(value: unknown): value is AgentJob {
  if (!isRecord(value)) return false;
  return typeof value.id === "string" && isJobStatus(value.status);
}

function isJobEnvelope(value: unknown): value is JobEnvelope {
  if (!isRecord(value)) return false;
  return isAgentJob(value.job);
}

class JobTerminalError extends Error {
  readonly name = "JobTerminalError";

  constructor(readonly job: AgentJob) {
    super(job.message || job.error || `딥 리서치 작업이 ${job.status} 상태로 종료되었습니다.`);
  }
}

async function pollJob(job: AgentJob, signal: AbortSignal): Promise<AgentJob> {
  let current = job;
  while (isActiveJobStatus(current.status)) {
    await sleep(1000, signal);
    current = await getJson<AgentJob>(`/api/jobs/${encodeURIComponent(current.id)}`, { signal });
  }
  if (current.status !== "done") throw new JobTerminalError(current);
  return current;
}

function splitReportTitle(markdown = "", fallback = "딥 리서치") {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const firstContentIndex = lines.findIndex((line) => line.trim());
  if (firstContentIndex < 0) return { title: fallback, body: "" };
  const titleMatch = lines[firstContentIndex].trim().match(/^#\s+(.+)$/);
  if (!titleMatch) return { title: fallback, body: markdown };
  return { title: titleMatch[1], body: lines.slice(firstContentIndex + 1).join("\n").trim() };
}

function reportLabel(report: TopicReport | TopicReportSummary) {
  return report.topicLabel || report.topicKey || "딥 리서치";
}

/** 목록 그룹의 이름. 내부 키(`custom`, `exchange_rate`)를 그대로 보여주지 않는다. */
function presetLabel(report: TopicReport | TopicReportSummary) {
  const key = String(report.topicKey || "").trim();
  if (PRESET_LABELS[key]) return PRESET_LABELS[key];
  // custom이 아닌 프리셋은 저장된 주제 이름이 사람이 읽는 유일한 단서다.
  const label = String((report as TopicReportSummary).topicLabel || "").trim();
  if (label) return label;
  return key ? key.replace(/_/g, " ") : "기타";
}

function displayDate(value?: string) {
  return listDate(value) || "날짜 미상";
}

function displayMonth(value?: string) {
  if (!value) return "월 미상";
  const parsed = new Date(value);
  if (!Number.isNaN(parsed.getTime())) {
    return `${parsed.getFullYear()}.${String(parsed.getMonth() + 1).padStart(2, "0")}`;
  }
  const match = String(value).match(/^(\d{4})[-.](\d{1,2})/);
  return match ? `${match[1]}.${String(match[2]).padStart(2, "0")}` : "월 미상";
}

function normalizeText(value?: string) {
  return String(value || "").trim().toLowerCase();
}

/** 저장 목록을 훑는 기준. 기업분석과 같은 세 가지다. */
type SavedViewMode = "recent" | "topic" | "month";
const RECENT_RESEARCH_LIMIT = 8;

function setTopicHash(reportId?: string) {
  window.location.hash = reportId ? deepResearchReportHash(reportId) : "#/deep-research";
}

function isDeepResearchHash() {
  return window.location.hash.replace(/^#\/?/, "").split("/")[0] === "deep-research";
}

function errorCode(error: unknown): string {
  if (error instanceof ApiRequestError) return error.code;
  if (error instanceof JobTerminalError) return error.job.errorCode || error.job.status;
  if (error instanceof Error) return error.name;
  return "request_failed";
}

function errorCopy(kind: ErrorKind, error: unknown): string {
  const code = errorCode(error);
  if (kind === "validation") return "투자 질문을 1~500자로 입력하세요.";
  // 질문이 아니라 **플래너가 쓴 계획**이 계약을 어긴 경우다. 입력을 고치라고 안내하면
  // 사용자는 멀쩡한 질문을 계속 고쳐 쓰게 된다.
  if (code === "plan_invalid") return "AI가 쓴 실행 계획이 형식을 벗어나 저장하지 못했습니다. 다시 시도하거나 빠른 계획으로 만들어 보세요.";
  if (code === "evidence_confirmation_required" || code === "resolution_changed") return "자료 상태가 계획 미리보기와 달라졌습니다. 최신 계획을 다시 미리보고 확인하세요.";
  if (code === "no_index" || code === "index_unavailable") return "연구 인덱스를 아직 읽을 수 없습니다. RSS 자료를 수집하고 인덱스를 만든 뒤 다시 시도하세요.";
  if (code === "rss_unavailable") return "RSS 자료를 읽을 수 없습니다. RSS 수집 상태를 확인한 뒤 다시 시도하세요.";
  if (code === "cli_unavailable") return "선택한 CLI 어댑터를 사용할 수 없습니다. 자동 어댑터를 선택하거나 설정을 확인하세요.";
  // 계획을 고치면 앞선 승인은 무효가 된다. 화면이 옛 승인을 들고 있으면 여기로 온다.
  if (code === "approval_superseded" || code === "approval_expired" || code === "approval_mismatch") {
    return "이 계획의 승인이 더 이상 유효하지 않습니다. 계획을 다시 미리보고 진행하세요.";
  }
  if (kind === "degraded") return "근거가 없는 규칙 기반 보고서를 실행하려면 근거 부족 확인이 필요합니다.";
  if (kind === "generation") return reportErrorMessage(error, "생성 작업에 실패했습니다.");
  if (kind === "report") return "저장된 리서치를 열지 못했습니다. 목록으로 돌아가 다시 시도하세요.";
  if (error instanceof Error && error.message) return error.message;
  return "요청을 처리하지 못했습니다. 입력을 확인하고 다시 시도하세요.";
}

function reportActionErrorCopy(error: unknown, fallback: string): string {
  return isResponseLessError(error) ? reportErrorMessage(error, fallback) : errorCopy("report", error);
}

function approvalReference(envelope: PlanPreviewEnvelope): ApprovalReference {
  return { id: envelope.approval.id, token: envelope.approval.token };
}

function renderList(items: readonly string[], empty = "없음") {
  if (!items.length) return <span className="topicrpt-empty-value">{empty}</span>;
  return <ul className="topicrpt-inline-list">{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}

/** 계획을 말로 고친다.
 *
 *  칸을 하나씩 편집하게 했더니 축 다섯 개에 텍스트 영역이 열한 개였다. 사람이
 *  계획을 고칠 때 하는 말은 "밸류에이션 축은 빼고 공급 쪽을 자세히"에 가깝지,
 *  각 칸을 다시 타자하는 것이 아니다. 요청을 그대로 엔진에 넘긴다.
 */
const REVISION_EXAMPLES = [
  "축 하나를 빼고 공급 쪽을 자세히 봐줘",
  "검색어에 영어 키워드를 더해줘",
  "한국 기업 중심으로 좁혀줘",
];

function PlanRevisionBox({
  busy,
  onSubmit,
  onCancel,
}: {
  readonly busy: boolean;
  readonly onSubmit: (instruction: string) => void;
  readonly onCancel: () => void;
}) {
  const [instruction, setInstruction] = useState("");
  const ready = instruction.trim().length > 0;

  return (
    <div className="topicrpt-plan-revision" data-qa="dr-plan-revision">
      <p className="topicrpt-plan-revision-head">
        <strong>어떻게 고칠까요?</strong>
        <span>요청한 부분만 바꾸고 나머지는 그대로 둡니다. 고친 계획으로 승인이 다시 발급됩니다.</span>
      </p>
      <label className="field">
        <span className="sr-only">수정 요청</span>
        <textarea
          rows={3}
          value={instruction}
          maxLength={1000}
          disabled={busy}
          placeholder="예: 밸류에이션 축은 빼고 공급 쪽을 자세히 봐줘"
          onChange={(event) => setInstruction(event.currentTarget.value)}
        />
      </label>
      <div className="topicrpt-plan-revision-examples">
        {REVISION_EXAMPLES.map((example) => (
          <button className="chip" type="button" key={example} disabled={busy} onClick={() => setInstruction(example)}>
            {example}
          </button>
        ))}
      </div>
      <div className="topicrpt-plan-revision-actions">
        <button className="btn btn--text" type="button" onClick={onCancel} disabled={busy}>취소</button>
        <button
          className="btn btn--primary"
          type="button"
          data-qa="dr-plan-revision-submit"
          disabled={busy || !ready}
          onClick={() => onSubmit(instruction.trim())}
        >
          {busy ? "고치는 중" : "이대로 고치기"}
        </button>
      </div>
    </div>
  );
}

function PlanReview({
  envelope,
  onContinue,
  onEdit,
  degradedConfirming,
  onConfirmDegraded,
  onCancelDegraded,
  editing,
  revising,
  replanning,
  onReplan,
  onEditPlan,
  onRevise,
  onCancelEdit,
}: {
  readonly envelope: PlanPreviewEnvelope;
  readonly onContinue: () => void;
  readonly onEdit: () => void;
  readonly degradedConfirming: boolean;
  readonly onConfirmDegraded: () => void;
  readonly onCancelDegraded: () => void;
  readonly editing: boolean;
  readonly revising: boolean;
  readonly replanning: boolean;
  readonly onReplan: () => void;
  readonly onEditPlan: () => void;
  readonly onRevise: (instruction: string) => void;
  readonly onCancelEdit: () => void;
}) {
  const { approvedRequest, preview } = envelope;
  const plan = approvedRequest.topicPlan;
  const zeroEvidence = preview.zeroEvidence;
  const reason = zeroEvidence.reasonCode;
  return (
    <section className="input-panel topicrpt-plan-panel" data-qa="dr-plan" aria-labelledby="dr-plan-heading">
      <div className="input-panel-header">
        <span className="section-kicker">조사 계획 확인</span>
        <h2 id="dr-plan-heading">실행 전에 리서치 계획을 확인하세요</h2>
        <p>계획의 범위와 자료 상태를 확인한 뒤에만 생성 작업을 시작합니다. 이 계획은 승인한 요청의 일부로 기록됩니다.</p>
        <p className="topicrpt-plan-origin">
          <span className="chip">{plannerModeLabel(plan.plannerMode)}</span>
          {!editing && (
            <>
              <button className="btn" type="button" data-qa="dr-plan-edit" onClick={onEditPlan} disabled={replanning || revising}>계획 고치기</button>
              <button className="btn" type="button" data-qa="dr-plan-replan" onClick={onReplan} disabled={replanning || revising}>
                {replanning ? "다시 쓰는 중" : "처음부터 다시"}
              </button>
            </>
          )}
        </p>
      </div>
      {editing && <PlanRevisionBox busy={revising} onSubmit={onRevise} onCancel={onCancelEdit} />}
      {!editing && <div className="topicrpt-plan-grid">
        <div className="topicrpt-plan-card">
          <span className="topicrpt-plan-label">보고서 유형</span>
          <strong>{reportTypeLabel(plan.reportType)}</strong>
          <span className="topicrpt-plan-label">분석 축</span>
          {plan.analysisAxes.length ? (
            <ul className="topicrpt-axis-list">
              {plan.analysisAxes.map((axis) => (
                <li key={axis.key}>
                  <strong>{axis.label}</strong>
                  {renderList(axis.questions)}
                </li>
              ))}
            </ul>
          ) : <span className="topicrpt-empty-value">분석 축 없음</span>}
        </div>
        <div className="topicrpt-plan-card">
          <span className="topicrpt-plan-label">검색 질의</span>
          {renderList(plan.searchQueries)}
          <span className="topicrpt-plan-label">심층 범위</span>
          <p>최대 {plan.deepResearch.maxRounds}라운드 · 하위 질문 {plan.deepResearch.subQuestions.length}개</p>
          <span className="topicrpt-plan-label">예상 공백</span>
          {renderList(plan.dataGapsLikely)}
        </div>
        <div className="topicrpt-plan-card">
          <span className="topicrpt-plan-label">저장한 자료 모음</span>
          {approvedRequest.collectionRef ? (
            <p>저장한 자료 모음 사용 · {approvedRequest.collectionRef.id} · 버전 {approvedRequest.collectionRef.revision}<br />후보 {preview.resolution.eligibleTotal ?? 0}건 · 선택 {preview.resolution.selectedEvidenceIds.length}건<br /><small>자료 모음은 근거 자체가 아니며, 일치하는 자료를 실행 시점에 다시 확인합니다.</small></p>
          ) : <p>저장한 자료 모음 없이 전체 허용 자료에서 확인합니다.</p>}
          {zeroEvidence.required && (
            <p className="topicrpt-zero-evidence" data-qa={`dr-readiness-${reason === "no_index" ? "no-index" : reason || "zero-evidence"}`} data-reason-code={reason || undefined}>
              {reason === "no_index" ? "인덱스 없음" : reason === "filtered_empty" ? "필터 결과 없음" : "일치 자료 없음"} · 실행 전 확인 필요
            </p>
          )}
          <span className="topicrpt-plan-label">시장 상태 배경</span>
          <p>{approvedRequest.marketStatePolicy === "exclude" ? "제외" : "현재 상태 포함"} · 범위 {approvedRequest.marketStateScope === "AUTO" ? "자동" : approvedRequest.marketStateScope}<br /><small>실행 시 상태, 기준 시각, 최신성, 출처를 별도 배경으로 기록합니다.</small></p>
        </div>
      </div>}
      {zeroEvidence.required && reason && zeroEvidence.resolutionFingerprint && (
        <div className="topicrpt-degraded-panel" data-qa={`dr-degraded-${reason === "no_index" ? "no-index" : reason}`} data-reason-code={reason} role="alert">
          <strong>근거 부족 상태를 확인해야 합니다</strong>
          <p>현재 선택된 외부 근거가 0건입니다. 확인하면 규칙 기반 결과로 진행하며, 보고서에 근거 공백과 반대 근거를 표시합니다.</p>
          {degradedConfirming ? (
            <div className="topicrpt-degraded-actions">
              <button className="btn btn--primary" type="button" data-qa="dr-degraded-confirm" onClick={onConfirmDegraded}>근거 부족을 확인하고 계속</button>
              <button className="btn" type="button" onClick={onCancelDegraded}>취소</button>
            </div>
          ) : <p>계속하기를 누르면 확인 단계가 열립니다.</p>}
        </div>
      )}
      <div className="topicrpt-action-row">
<button className="btn" type="button" onClick={onEdit}>질문 수정</button>
        <button className={degradedConfirming ? "btn" : "btn btn--primary"} type="button" data-qa="dr-continue" onClick={onContinue}>
          {zeroEvidence.required ? "계속하기" : "이 계획으로 생성"}
        </button>
      </div>
    </section>
  );
}

export function DeepResearchRoute() {
  const contentRevision = useContentRevision("topicReport");
  const [reports, setReports] = useState<TopicReportSummary[]>([]);
  const [selected, setSelected] = useState<TopicReport | null>(null);
  const initialLocation = useMemo(() => parseDeepResearchLocation(window.location.hash), []);
  const [detailId, setDetailId] = useState(initialLocation.kind === "report" ? initialLocation.id : "");
  const [collectionDetailId, setCollectionDetailId] = useState(initialLocation.kind === "collection" ? initialLocation.id : "");
  const [malformedRoute, setMalformedRoute] = useState(initialLocation.malformed);
  const [question, setQuestion] = useState("");
  const [userContext, setUserContext] = useState("");
  const [marketStatePolicy, setMarketStatePolicy] = useState<MarketStatePolicy>("include_current");
  const [marketStateScope, setMarketStateScope] = useState<MarketStateScope>("AUTO");
  const [selectedCollectionRef, setSelectedCollectionRef] = useState<CollectionRef | null>(null);
  const [collectionBusy, setCollectionBusy] = useState(false);
  const [phase, setPhase] = useState<DeepResearchPhase>("readiness");
  const [planEnvelope, setPlanEnvelope] = useState<PlanPreviewEnvelope | null>(null);
  const [degradedConfirming, setDegradedConfirming] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [generationError, setGenerationError] = useState<CapturedReportError | null>(null);
  const generationOperationId = useRef(0);
  const generationErrorRef = useRef<CapturedReportError | null>(null);
  generationErrorRef.current = generationError;
  const [reportListError, setReportListError] = useState("");
  const [reportListErrorDiagnostic, setReportListErrorDiagnostic] = useState<CapturedReportError | null>(null);
  const [readErrorDiagnostic, setReadErrorDiagnostic] = useState<CapturedReportError | null>(null);
  const [actionErrorMessage, setActionErrorMessage] = useState("");
  const [actionErrorDiagnostic, setActionErrorDiagnostic] = useState<CapturedReportError | null>(null);
  const [errorKind, setErrorKind] = useState<ErrorKind | null>(null);
  const [errorReason, setErrorReason] = useState("");
  const [readinessKind, setReadinessKind] = useState<"no-index" | "rss" | "api" | null>(null);
  const [status, setStatus] = useState("");
  const [actionBusy, setActionBusy] = useState("");
  const [proposalReloadKey, setProposalReloadKey] = useState(0);
  // 엔진을 설정해 둔 사용자는 그 순간부터 Agent 사용을 허락한 것으로 본다.
  // 빠른 계획이 필요한 때를 위해 고를 수는 있게 둔다.
  const [plannerEngine, setPlannerEngine] = useState<PlannerEngine>("auto");
  const [planEditing, setPlanEditing] = useState(false);
  const [planRevising, setPlanRevising] = useState(false);
  const [planReplanning, setPlanReplanning] = useState(false);
  const [reportQuery, setReportQuery] = useState("");
  const [reportView, setReportView] = useState<SavedViewMode>("recent");
  const requestId = useRef(0);
  const requestController = useRef<AbortController | null>(null);
  const listRequestId = useRef(0);
  const listController = useRef<AbortController | null>(null);
  const actionRequestId = useRef(0);
  const actionController = useRef<AbortController | null>(null);
  const phaseRef = useRef<DeepResearchPhase>(phase);
  phaseRef.current = phase;
  const listHeadingRef = useRef<HTMLHeadingElement>(null);
  const openingReportId = useRef("");
  const restoreFocusPending = useRef(false);

  const clearGenerationDiagnostic = useCallback(() => {
    setGenerationError(null);
  }, []);

  const beginGenerationDiagnostic = useCallback(() => {
    generationOperationId.current += 1;
    clearGenerationDiagnostic();
    return generationOperationId.current;
  }, [clearGenerationDiagnostic]);

  const invalidateGenerationDiagnostic = useCallback(() => {
    generationOperationId.current += 1;
    clearGenerationDiagnostic();
  }, [clearGenerationDiagnostic]);

  const topicKey = DEFAULT_TOPIC_KEY;
  const customLabel = question;
  const deepResearch = true;

  const beginRequest = useCallback(() => {
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    requestId.current += 1;
    invalidateGenerationDiagnostic();
    return { id: requestId.current, signal: controller.signal };
  }, [invalidateGenerationDiagnostic]);

  const isCurrentRequest = useCallback((id: number) => id === requestId.current, []);

  function beginReportAction() {
    actionController.current?.abort();
    const id = ++actionRequestId.current;
    const controller = new AbortController();
    actionController.current = controller;
    setActionErrorMessage("");
    setActionErrorDiagnostic(null);
    return { id, controller };
  }

  function isCurrentReportAction(id: number, controller: AbortController) {
    return id === actionRequestId.current && actionController.current === controller && !controller.signal.aborted;
  }

  function invalidateReportAction() {
    actionRequestId.current += 1;
    actionController.current?.abort();
    actionController.current = null;
    setActionErrorMessage("");
    setActionErrorDiagnostic(null);
    setActionBusy("");
  }

  const loadReports = useCallback(async () => {
    const sequence = ++listRequestId.current;
    listController.current?.abort();
    const controller = new AbortController();
    listController.current = controller;
    setLoading(true);
    setReportListError("");
    setReportListErrorDiagnostic(null);
    try {
      const payload = await getJson<unknown>("/api/topic-reports", { signal: controller.signal });
      if (controller.signal.aborted || sequence !== listRequestId.current) return;
      setReports(parseTopicReportSummaries(payload));
      setReadinessKind(null);
      setPhase((current) => current === "readiness" ? "draft" : current);
      setReactAgentContextScope("deep-research", { surface: "topic_report", viewId: "topicrpt", reportKind: "", reportId: "", collectionId: null, collectionRevision: null });
    } catch (err) {
      if (isAbortError(err, controller.signal) || sequence !== listRequestId.current) return;
      const message = errorCopy("readiness", err);
      setReportListError(message);
      setReportListErrorDiagnostic(captureReportError(err, sequence));
      const code = errorCode(err);
      if (!generationErrorRef.current && phaseRef.current === "readiness") {
        setError(message);
        setErrorKind("readiness");
        setErrorReason(code);
        setReadinessKind(code === "no_index" || code === "index_unavailable" ? "no-index" : code === "rss_unavailable" ? "rss" : "api");
        setPhase("recoverable-error");
      }
    } finally {
      if (sequence === listRequestId.current) {
        listController.current = null;
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadReports();
    return () => {
      listRequestId.current += 1;
      listController.current?.abort();
      listController.current = null;
    };
  // 생성·수집이 어디서 일어나든 목록이 따라온다(자동화, 다른 탭, Agent 도크 포함).
  }, [loadReports, contentRevision]);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    const operationId = beginGenerationDiagnostic();
    void (async () => {
      const recovery = await recoverDeepResearchJob((id) => getJson<AgentJob>(`/api/jobs/${encodeURIComponent(id)}`, { signal: controller.signal }));
      if (!current || recovery.kind === "none") return;
      if (recovery.kind === "unavailable") {
        setStatus("이전에 시작한 딥 리서치 작업이 있습니다. 서버 연결이 돌아오면 다시 확인합니다.");
        return;
      }
      if (recovery.kind === "invalid") {
        setError("저장된 딥 리서치 작업 정보를 확인할 수 없어 안전하게 제거했습니다.");
        return;
      }
      setPhase("generation");
      setStatus(recovery.kind === "active" ? "이전에 시작한 딥 리서치 작업에 다시 연결했습니다." : "완료된 딥 리서치 결과를 불러오는 중입니다.");
      try {
        const done = recovery.kind === "active" ? await pollJob(recovery.job as AgentJob, controller.signal) : recovery.job as AgentJob;
        if (!current) return;
        // 복구 폴링 중에 사용자가 새 딥 리서치를 시작했으면(새 id가 저장돼 있으면)
        // 여기서 지우거나 화면을 갈아치우지 않는다 — 새 실행의 재개 열쇠를 지우고
        // 그 화면 위에 옛 결과를 덮어쓰는 경합이 있었다.
        {
          const persisted = readDeepResearchJobId();
          if (persisted !== null && persisted !== recovery.job.id) return;
        }
        if (done.status !== "done") throw new JobTerminalError(done);
        clearDeepResearchJobId();
        const reportId = done.result?.reportId || done.result?.artifactId || "";
        if (!reportId) throw new Error("완료된 보고서 ID를 확인하지 못했습니다.");
        const report = parseTopicReportPayload(await getJson<unknown>(`/api/topic-reports/${encodeURIComponent(reportId)}?includePersonal=true`, { signal: controller.signal }));
        if (!current) return;
        setReports((rows) => [report, ...rows.filter((row) => row.id !== report.id)]);
        setSelected(report);
        setPhase("report");
        setStatus("딥 리서치를 생성하고 자동 저장했습니다.");
        setTopicHash(report.id);
      } catch (err) {
        if (!current || isAbortError(err, controller.signal) || operationId !== generationOperationId.current) return;
        if (err instanceof JobTerminalError) clearDeepResearchJobId();
        setGenerationError(captureReportError(err, operationId));
        setError(errorCopy("generation", err));
        setErrorKind("generation");
        setPhase("recoverable-error");
        setStatus("");
      }
    })();
    return () => { current = false; controller.abort(); };
  }, [beginGenerationDiagnostic]);

  useEffect(() => {
    const ownedCollectionIdentity = {
      collectionId: selectedCollectionRef?.id || null,
      collectionRevision: selectedCollectionRef?.revision || null,
    };
    patchReactAgentContextScope("deep-research", ownedCollectionIdentity);
    return () => {
      const current = window.FolioAgent?.currentContext;
      if (
        current?.collectionId === ownedCollectionIdentity.collectionId
        && current.collectionRevision === ownedCollectionIdentity.collectionRevision
      ) {
        patchReactAgentContextScope("deep-research", { collectionId: null, collectionRevision: null });
      }
    };
  }, [selectedCollectionRef]);

  useEffect(() => {
    const handleHashChange = () => {
      if (!isDeepResearchHash()) return;
      const route = parseDeepResearchLocation(window.location.hash);
      if (route.malformed || route.kind === "report" || route.kind === "collection") invalidateGenerationDiagnostic();
      setMalformedRoute(route.malformed);
      setDetailId(route.kind === "report" ? route.id : "");
      setCollectionDetailId(route.kind === "collection" ? route.id : "");
      if (route.malformed) {
        setSelected(null);
        setError(route.kind === "collection"
          ? "컬렉션 주소 형식이 올바르지 않습니다. 목록으로 돌아가 다시 여세요."
          : "보고서 주소 형식이 올바르지 않습니다. 목록으로 돌아가 다시 여세요.");
        setErrorKind("report");
        setErrorReason(route.kind === "collection" ? "malformed_collection_id" : "malformed_report_id");
        setPhase("recoverable-error");
      }
    };
    window.addEventListener("hashchange", handleHashChange);
    handleHashChange();
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, [invalidateGenerationDiagnostic]);

  const returnToReportList = useCallback(() => {
    restoreFocusPending.current = true;
    invalidateGenerationDiagnostic();
    invalidateReportAction();
    setReadErrorDiagnostic(null);
    setSelected(null);
    setMalformedRoute(false);
    setError("");
    setErrorKind(null);
    setErrorReason("");
    setTopicHash();
  }, [invalidateGenerationDiagnostic]);

  useEffect(() => {
    if (detailId || malformedRoute || !restoreFocusPending.current) return;
    restoreFocusPending.current = false;
    window.requestAnimationFrame(() => {
      const reportId = openingReportId.current.replace(/["\\]/g, "");
      const opener = reportId ? document.querySelector<HTMLElement>("[data-report-id=\"" + reportId + "\"]") : null;
      (opener || listHeadingRef.current)?.focus({ preventScroll: true });
    });
  }, [detailId, malformedRoute, phase]);

  useEffect(() => {
    const handleProposalLifecycle = (event: Event) => {
      const result = (event as CustomEvent<ProposalLifecycleResult>).detail;
      if (proposalTargetsContext(result, window.FolioAgent?.currentContext)) {
        setProposalReloadKey((value) => value + 1);
      }
    };
    window.addEventListener(PROPOSAL_LIFECYCLE_EVENT, handleProposalLifecycle);
    return () => window.removeEventListener(PROPOSAL_LIFECYCLE_EVENT, handleProposalLifecycle);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    if (detailId || malformedRoute || collectionDetailId) invalidateGenerationDiagnostic();
    invalidateReportAction();
    requestController.current?.abort();
    const detailRequest = requestId.current + 1;
    requestId.current = detailRequest;
    async function loadDetail(reportId: string) {
      setLoading(true);
      setReadErrorDiagnostic(null);
      setError("");
      setErrorKind(null);
      setErrorReason("");
      try {
        const payload = await getJson<unknown>(`/api/topic-reports/${encodeURIComponent(reportId)}?includePersonal=true`, { signal: controller.signal });
        if (controller.signal.aborted || requestId.current !== detailRequest) return;
        const report = parseTopicReportPayload(payload);
        setSelected(report);
        setPhase("report");
        setReactAgentContextScope("deep-research", { surface: "topic_report_reader", viewId: "topicrpt", reportKind: "topic_report", reportId: report.id || reportId, collectionId: selectedCollectionRef?.id || null, collectionRevision: selectedCollectionRef?.revision || null });
      } catch (err) {
        if (isAbortError(err, controller.signal)) return;
        if (controller.signal.aborted || requestId.current !== detailRequest) return;
        clearGenerationDiagnostic();
        setReadErrorDiagnostic(captureReportError(err, detailRequest));
        setSelected(null);
        setError(errorCopy("report", err));
        setErrorKind("report");
        setErrorReason(errorCode(err));
        setPhase("recoverable-error");
      } finally {
        if (!controller.signal.aborted && requestId.current === detailRequest) setLoading(false);
      }
    }
    if (detailId && !malformedRoute) {
      void loadDetail(detailId);
    } else if (!malformedRoute && !collectionDetailId) {
      setReadErrorDiagnostic(null);
      setSelected(null);
      setPhase((current) => current === "report" ? "draft" : current);
      setReactAgentContextScope("deep-research", { surface: "topic_report", viewId: "topicrpt", reportKind: "", reportId: "", collectionId: selectedCollectionRef?.id || null, collectionRevision: selectedCollectionRef?.revision || null });
      setLoading(false);
    }
    return () => controller.abort();
  }, [clearGenerationDiagnostic, collectionDetailId, detailId, invalidateGenerationDiagnostic, malformedRoute, proposalReloadKey]);

  const handlePreview = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedQuestion = question.normalize("NFKC").trim();
    if (!normalizedQuestion || normalizedQuestion.length > 500) {
      invalidateGenerationDiagnostic();
      setError(errorCopy("validation", new Error("question_invalid")));
      setErrorKind("validation");
      setErrorReason("question_invalid");
      setPhase("recoverable-error");
      return;
    }
    const request = beginRequest();
    setPhase("plan-loading");
    setPlanEnvelope(null);
    setDegradedConfirming(false);
    setError("");
    setErrorKind(null);
    setErrorReason("");
    setStatus(plannerEngine === "rules"
      ? "질문을 실행 계획으로 바꾸는 중입니다."
      : "AI가 리서치 계획을 쓰는 중입니다. 30초 이상 걸릴 수 있습니다.");
    const body: PlanRequest = {
      question: normalizedQuestion,
      userContext: userContext.normalize("NFKC").trim(),
      plannerEngine,
      deepResearch: true,
      customTickers: {},
      marketStatePolicy,
      marketStateScope,
      collectionRef: selectedCollectionRef,
    };
    try {
      const envelope = await postJson<PlanPreviewEnvelope>("/api/topic-reports/plan", body, { signal: request.signal });
      if (!isCurrentRequest(request.id)) return;
      setPlanEnvelope(envelope);
      setPhase("plan-review");
      setStatus("실행 계획을 확인하세요.");
    } catch (err) {
      if (isAbortError(err, request.signal)) return;
      if (!isCurrentRequest(request.id)) return;
      setError(errorCopy("plan", err));
      setErrorKind("plan");
      setErrorReason(errorCode(err));
      setReadinessKind(errorCode(err) === "no_index" || errorCode(err) === "index_unavailable" ? "no-index" : errorCode(err) === "rss_unavailable" ? "rss" : null);
      setPhase("recoverable-error");
      setStatus("");
    }
  };

  const executeEnvelope = async (envelope: PlanPreviewEnvelope) => {
    const request = beginRequest();
    const operationId = generationOperationId.current;
    setPhase("generation");
    setError("");
    setErrorKind(null);
    setErrorReason("");
    setStatus("승인된 계획으로 리서치를 생성하는 중입니다.");
    const execution: ExecutionRequest = {
      // 실행 경로는 앱 설정이 정한다. 리서치마다 고를 값이 아니다.
      mode: "auto",
      adapter: "auto",
      fallbackPolicy: FALLBACK_POLICY,
    };
    const body: GenerateApprovedRequest = {
      approvedRequest: envelope.approvedRequest,
      approval: approvalReference(envelope),
      execution,
    };
    try {
      const response = await postJson<JobEnvelope>("/api/topic-reports", body, { signal: request.signal });
      const job = isJobEnvelope(response) ? response.job : isAgentJob(response) ? response : null;
      if (!job) throw new Error("생성 작업 ID를 확인하지 못했습니다.");
      persistDeepResearchJobId(job.id);
      const done = await pollJob(job, request.signal);
      if (!isCurrentRequest(request.id)) return;
      const reportId = done.result?.reportId || done.result?.artifactId || "";
      if (!reportId) throw new Error("생성된 보고서 ID를 확인하지 못했습니다.");
      clearDeepResearchJobId();
      const report = parseTopicReportPayload(await getJson<unknown>(`/api/topic-reports/${encodeURIComponent(reportId)}?includePersonal=true`, { signal: request.signal }));
      if (!isCurrentRequest(request.id)) return;
      setReports((current) => [report, ...current.filter((item) => item.id !== report.id)]);
      setSelected(report);
      setPhase("report");
      setStatus("딥 리서치를 생성하고 자동 저장했습니다.");
      setTopicHash(report.id);
      setReactAgentContextScope("deep-research", { surface: "topic_report_reader", viewId: "topicrpt", reportKind: "topic_report", reportId: report.id || "", collectionId: selectedCollectionRef?.id || null, collectionRevision: selectedCollectionRef?.revision || null });
    } catch (err) {
      if (isAbortError(err, request.signal)) return;
      if (!isCurrentRequest(request.id)) return;
      if (err instanceof JobTerminalError) clearDeepResearchJobId();
      const degraded = err instanceof ApiRequestError && (err.code === "evidence_confirmation_required" || err.code === "resolution_changed");
      if (operationId !== generationOperationId.current) return;
      if (!degraded) setGenerationError(captureReportError(err, operationId));
      setError(errorCopy("generation", err));
      setErrorKind(degraded ? "degraded" : "generation");
      setErrorReason(errorCode(err));
      setPhase("recoverable-error");
      setStatus("");
    }
  };

  const handleContinue = () => {
    if (!planEnvelope) return;
    if (planEnvelope.preview.zeroEvidence.required) {
      if (!planEnvelope.preview.zeroEvidence.reasonCode || !planEnvelope.preview.zeroEvidence.resolutionFingerprint) {
        invalidateGenerationDiagnostic();
        setError("근거 부족 확인 정보가 없어 실행을 중단했습니다. 계획을 다시 미리보세요.");
        setErrorKind("degraded");
        setErrorReason("invalid_zero_evidence");
        setPhase("recoverable-error");
        return;
      }
      setDegradedConfirming(true);
      setStatus("근거 부족 확인을 검토하세요.");
      return;
    }
    void executeEnvelope(planEnvelope);
  };

  const runReplan = async (instruction: string) => {
    if (!planEnvelope) return;
    const request = beginRequest();
    const editing = instruction.length > 0;
    if (editing) setPlanRevising(true); else setPlanReplanning(true);
    setError("");
    setErrorKind(null);
    setErrorReason("");
    setStatus(editing
      ? "요청하신 대로 계획을 고치는 중입니다. 30초 이상 걸릴 수 있습니다."
      : "AI가 리서치 계획을 다시 쓰는 중입니다. 30초 이상 걸릴 수 있습니다.");
    const body: ReplanRequest = {
      approvedRequest: planEnvelope.approvedRequest,
      approval: approvalReference(planEnvelope),
      instruction,
    };
    try {
      const replacement = await postJson<PlanPreviewEnvelope>("/api/topic-reports/plan/replan", body, { signal: request.signal });
      if (!isCurrentRequest(request.id)) return;
      setPlanEnvelope(replacement);
      setPlanEditing(false);
      setDegradedConfirming(false);
      // 엔진이 없거나 실패하면 규칙 계획이 그대로 온다. 그 사실을 숨기지 않는다.
      setStatus(replacement.approvedRequest.topicPlan.plannerMode === "llm"
        ? (editing ? "요청하신 대로 계획을 고쳤습니다." : "AI가 계획을 다시 썼습니다.")
        : "AI 엔진을 쓸 수 없어 계획을 그대로 두었습니다.");
    } catch (err) {
      if (isAbortError(err, request.signal)) return;
      if (!isCurrentRequest(request.id)) return;
      setError(errorCopy("plan", err));
      setErrorKind("plan");
      setErrorReason(errorCode(err));
      // 이 줄이 없어 실패가 통째로 조용했다. 오류 상자는 `recoverable-error`에서만 뜬다.
      setPhase("recoverable-error");
      setStatus("");
    } finally {
      if (isCurrentRequest(request.id)) {
        setPlanReplanning(false);
        setPlanRevising(false);
      }
    }
  };

  const revisePlan = async (instruction: string) => {
    await runReplan(instruction);
  };

  const confirmDegraded = async () => {
    if (!planEnvelope) return;
    const zeroEvidence = planEnvelope.preview.zeroEvidence;
    if (!zeroEvidence.required || !zeroEvidence.reasonCode || !zeroEvidence.resolutionFingerprint) return;
    const request = beginRequest();
    setError("");
    setErrorKind(null);
    setErrorReason("");
    setStatus("근거 부족 확인을 저장하는 중입니다.");
    const body: ConfirmDegradedRequest = {
      approvedRequest: planEnvelope.approvedRequest,
      approval: approvalReference(planEnvelope),
      reasonCode: zeroEvidence.reasonCode,
      resolutionFingerprint: zeroEvidence.resolutionFingerprint,
      confirmed: true,
    };
    try {
      const replacement = await postJson<PlanPreviewEnvelope>("/api/topic-reports/confirm-degraded", body, { signal: request.signal });
      if (!isCurrentRequest(request.id)) return;
      setPlanEnvelope(replacement);
      setDegradedConfirming(false);
      await executeEnvelope(replacement);
    } catch (err) {
      if (isAbortError(err, request.signal)) return;
      if (!isCurrentRequest(request.id)) return;
      setError(errorCopy("degraded", err));
      setErrorKind("degraded");
      setErrorReason(errorCode(err));
      setPhase("recoverable-error");
      setStatus("");
    }
  };

  async function deleteReport(report: TopicReportSummary) {
    if (!report.id || !window.confirm(`${reportLabel(report)} 보고서를 삭제할까요?`)) return;
    const action = beginReportAction();
    setActionBusy(`delete-${report.id}`);
    invalidateGenerationDiagnostic();
    setError("");
    try {
      const result = await deleteJson<{ readonly deleted?: boolean }>(
        `/api/topic-reports/${encodeURIComponent(report.id)}`,
        {},
        { signal: action.controller.signal },
      );
      if (!result || result.deleted !== true) throw new Error("딥 리서치 삭제 결과를 확인하지 못했습니다.");
      if (!isCurrentReportAction(action.id, action.controller)) return;
      if (selected?.id === report.id) setTopicHash();
      setReports((current) => current.filter((item) => item.id !== report.id));
      setStatus("저장된 딥 리서치를 삭제했습니다.");
    } catch (err) {
      if (!isCurrentReportAction(action.id, action.controller) || isAbortError(err, action.controller.signal)) return;
      // A transport/body-read loss has no server execution to inspect. Keep the
      // action message neutral and do not create a diagnostic/retry affordance.
      setActionErrorDiagnostic(isResponseLessError(err) ? null : captureReportError(err, action.id));
      setActionErrorMessage(reportActionErrorCopy(err, "보고서 삭제에 실패했습니다."));
    } finally {
      if (isCurrentReportAction(action.id, action.controller)) {
        actionController.current = null;
        setActionBusy("");
      }
    }
  }

  async function exportTopicReport(target: "notion" | "obsidian") {
    if (!selected) return;
    const action = beginReportAction();
    setActionBusy(target);
    setStatus(target === "notion" ? "Notion으로 내보내는 중..." : "Obsidian으로 내보내는 중...");
    try {
      const result = target === "notion"
        ? await postJson<ExportResult>("/api/export-notion/topic-report", selected, { signal: action.controller.signal })
        : await postJson<ExportResult>("/api/export-obsidian/topic-report", selected, { signal: action.controller.signal });
      if (!isCurrentReportAction(action.id, action.controller)) return;
      setStatus(target === "notion"
        ? `Notion으로 내보냈습니다${result.title ? `: ${result.title}` : ""}`
        : `Obsidian으로 내보냈습니다${result.topic || result.filename ? `: ${result.topic || result.filename}` : ""}`);
    } catch (err) {
      if (!isCurrentReportAction(action.id, action.controller) || isAbortError(err, action.controller.signal)) return;
      setActionErrorDiagnostic(captureReportError(err, action.id));
      const message = reportErrorMessage(err, "내보내기에 실패했습니다.");
      setActionErrorMessage(message);
      setStatus(message);
    } finally {
      if (isCurrentReportAction(action.id, action.controller)) {
        actionController.current = null;
        setActionBusy("");
      }
    }
  }

  async function generatePersonalOverlay() {
    if (!selected?.id) return;
    setActionBusy("overlay");
    setStatus("내 노트와 연결하는 중...");
    try {
      const response = await postJson<OverlayResult | AgentJob>(`/api/topic-reports/${encodeURIComponent(selected.id)}/personal-overlay`, {});
      if (isAgentJob(response)) await pollJob(response, new AbortController().signal);
      const updated = parseTopicReportPayload(await getJson<unknown>(`/api/topic-reports/${encodeURIComponent(selected.id)}?includePersonal=true`));
      setSelected(updated);
      setStatus("내 노트와 연결했습니다.");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "내 노트 연결에 실패했습니다.");
    } finally {
      setActionBusy("");
    }
  }

  const filteredReports = useMemo(() => {
    const query = normalizeText(reportQuery);
    if (!query) return reports;
    return reports.filter((report) => normalizeText([
      reportLabel(report),
      presetLabel(report),
      report.topicKey,
      report.engine,
      report.engineDetail,
      displayDate(report.generatedAt || report.date),
    ].filter(Boolean).join(" ")).includes(query));
  }, [reportQuery, reports]);

  const groupedReports = useMemo(() => {
    const at = (report: TopicReportSummary) => String(report.generatedAt || report.date || "");
    const sorted = [...filteredReports].sort((a, b) => at(b).localeCompare(at(a)));
    if (reportView === "recent") {
      if (!sorted.length) return [];
      return [{ key: `최근 리서치 ${Math.min(sorted.length, RECENT_RESEARCH_LIMIT)}건`, rows: sorted.slice(0, RECENT_RESEARCH_LIMIT) }];
    }
    const groups = new Map<string, TopicReportSummary[]>();
    for (const report of sorted) {
      const key = reportView === "month" ? displayMonth(report.generatedAt || report.date) : presetLabel(report);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)?.push(report);
    }
    return Array.from(groups.entries())
      .map(([key, rows]) => ({ key, rows }))
      .sort((a, b) => at(b.rows[0]).localeCompare(at(a.rows[0])));
  }, [filteredReports, reportView]);

  const readerContent = splitReportTitle(selected?.markdown || "", selected ? reportLabel(selected) : "딥 리서치");
  const selectedMarketStateContext = marketStateContextProjection(selected?.marketStateResolution);

  const referenceInvestmentContext = useCallback((context: InvestmentTickerContext) => {
    const source = context.source === "both"
      ? "포트폴리오·워치리스트"
      : context.source === "portfolio"
        ? "포트폴리오"
        : "워치리스트";
    const reference = `개인 맥락(hypothesis): ${context.ticker} · ${source}`;
    setUserContext((current) => {
      const lines = current.split("\n").map((line) => line.trim()).filter(Boolean);
      if (lines.includes(reference)) return current;
      return [...lines, reference].join("\n").slice(0, 4000);
    });
  }, []);

  if (collectionDetailId && !malformedRoute) {
    return (
      <div className="react-deep-research-route" data-deep-research-route>
        <SmartCollectionWorkspace
          collectionId={collectionDetailId}
          onBack={() => setTopicHash()}
          onStartResearch={(ref) => {
            setSelectedCollectionRef(ref);
            setTopicHash();
          }}
        />
      </div>
    );
  }

  if (detailId && !selected && !(phase === "recoverable-error" && errorKind === "report")) {
    return (
      <div className="react-deep-research-route" data-deep-research-route>
        <section className="topicrpt-report-state" data-qa="dr-report-loading" role="status" aria-live="polite" aria-busy="true">
          <p className="section-kicker">DEEP RESEARCH</p>
          <h1 tabIndex={-1}>저장된 리서치를 여는 중입니다</h1>
          <p>보고서 본문과 함께 사용한 자료 목록을 불러오는 중입니다.</p>
        </section>
      </div>
    );
  }

  if ((detailId || malformedRoute) && !selected && (malformedRoute || (phase === "recoverable-error" && errorKind === "report"))) {
    const notFound = errorReason === "topic_report_not_found" || errorReason === "not_found";
    return (
      <div className="react-deep-research-route" data-deep-research-route>
        <section
          className="topicrpt-report-state is-error"
          data-qa={notFound ? "dr-report-not-found" : "dr-report-error"}
          role="alert"
          aria-live="assertive"
        >
          <p className="section-kicker">DEEP RESEARCH</p>
          <h1>{notFound ? "저장된 리서치를 찾을 수 없습니다" : "리서치를 열 수 없습니다"}</h1>
          <p data-qa={notFound ? "dr-not-found" : undefined}>{error || "보고서 주소나 저장 데이터를 확인한 뒤 목록에서 다시 여세요."}</p>
          {readErrorDiagnostic && <ReportErrorDiagnostic diagnostic={readErrorDiagnostic} />}
          <button className="btn" type="button" data-qa="dr-report-return" onClick={returnToReportList}>딥 리서치 목록으로 돌아가기</button>
        </section>
      </div>
    );
  }

  if (selected && phase === "report") {
    return (
      <div className="react-deep-research-route" data-deep-research-route data-qa="dr-report">
        {error && <p className="react-dashboard-error" data-qa="dr-error-report">{error}</p>}
        {readErrorDiagnostic && <ReportErrorDiagnostic diagnostic={readErrorDiagnostic} />}
        {(selected.mode === "fallback" || selected.generation?.mode === "rules") && <p className="react-dashboard-warning" data-qa="dr-degraded-rules" role="status">근거 부족을 확인한 규칙 기반 보고서입니다. 자료 공백과 반대 근거를 함께 확인하세요.</p>}
        <ReportReaderShell
          eyebrow={`DEEP RESEARCH${selected.date ? ` · ${selected.date}` : ""}`}
          title={readerContent.title}
          meta={`${reportLabel(selected)} · 뉴스 ${selected.docCount || 0}건 · 내러티브 ${selected.memoryCount || 0}건`}
          agentContext={{ surface: "topic_report_reader", viewId: "topicrpt", reportKind: "topic_report", reportId: selected.id || "", topic: reportLabel(selected), marketState: selectedMarketStateContext }}
          breadcrumb={(
            <>
              <button type="button" data-qa="dr-report-return" onClick={returnToReportList}>딥 리서치</button>
              <span>{readerContent.title}</span>
            </>
          )}
          onClose={returnToReportList}
          actionSlot={(
            <>
              <ReaderActionGroup title="AI">
                <ReaderActionButton icon="agent" onClick={() => openReactAgentDock({ surface: "topic_report_reader", reportKind: "topic_report", reportId: selected.id || "", topic: reportLabel(selected), message: `${readerContent.title}의 핵심 결론, 반대 근거, 더 발전시킬 분석 방향을 정리해줘.`, autoSubmit: true })}>Agent에게 묻기</ReaderActionButton>
              </ReaderActionGroup>
              <ReaderActionGroup title="노트">
                <ReaderActionButton icon="link" data-qa="dr-overlay-generate" disabled={actionBusy === "overlay" || !selected.id} onClick={generatePersonalOverlay}>{actionBusy === "overlay" ? "연결 중" : "내 노트와 연결"}</ReaderActionButton>
              </ReaderActionGroup>
              <ReaderActionGroup title="내보내기">
                <ReaderActionButton icon="notion" disabled={actionBusy === "notion"} onClick={() => exportTopicReport("notion")}>{actionBusy === "notion" ? "내보내는 중" : "Notion으로 내보내기"}</ReaderActionButton>
                <ReaderActionButton icon="obsidian" disabled={actionBusy === "obsidian"} onClick={() => exportTopicReport("obsidian")}>{actionBusy === "obsidian" ? "내보내는 중" : "Obsidian으로 내보내기"}</ReaderActionButton>
              </ReaderActionGroup>
              {selected.generation?.message && <p className="react-reader-status">{selected.generation.message}</p>}
              {status && <p className="react-reader-status">{status}</p>}
              {actionErrorMessage && <p className="react-reader-status react-dashboard-error">{actionErrorMessage}</p>}
              {actionErrorDiagnostic && <ReportErrorDiagnostic diagnostic={actionErrorDiagnostic} />}
            </>
          )}
          noteIdentity={{ id: stableNoteKey("topic", reportLabel(selected)), noteType: "topic_review", title: reportLabel(selected) ? `${reportLabel(selected)} 리서치 노트` : "딥 리서치 노트", topic: reportLabel(selected), label: reportLabel(selected), reportKind: "topic_report", reportId: reportLabel(selected), linkedReports: [readerContent.title].filter(Boolean) }}
          noteLinkedTitle={readerContent.title}
          noteOverlay={parsePersonalOverlayPayload(selected.personalOverlay, selected.canonicalRevision)}
        >
          <MarketStateReportContext resolution={selected.marketStateResolution} />
          <ReportBody markdown={readerContent.body || selected.markdown || ""} />
          <DeepResearchProvenance report={selected} />
        </ReportReaderShell>
      </div>
    );
  }

  const isBusy = phase === "plan-loading" || phase === "generation" || loading || collectionBusy;
  const showError = phase === "recoverable-error" && error;
  const generationOutcomeUnknown = Boolean(showError && errorKind === "generation" && generationError?.responseLess);
  return (
    <div className="react-deep-research-route" data-deep-research-route>
      <RouteHero
        eyebrow="Deep Research"
        title="딥 리서치"
        description="투자 질문을 실행 계획으로 정리해 확인한 뒤, 정해진 자료 범위 안에서 근거를 구분한 보고서를 생성합니다."
        actions={<button className="btn" type="button" onClick={() => void loadReports()} disabled={loading}>{loading ? "불러오는 중" : "새로고침"}</button>}
      />

      {phase === "readiness" && <p className="react-dashboard-warning" data-qa="dr-readiness-loading" role="status">저장된 리서치와 자료 상태를 확인하는 중입니다.</p>}
      {readinessKind && phase === "recoverable-error" && <p className="react-dashboard-error" data-qa={`dr-readiness-${readinessKind}`}>{error}</p>}
      {reportListError && !(readinessKind && phase === "recoverable-error") && <p className="react-dashboard-error" data-qa="dr-report-list-error" role="alert">{reportListError}</p>}
      {reportListErrorDiagnostic && <ReportErrorDiagnostic diagnostic={reportListErrorDiagnostic} />}
      {!selected && actionErrorMessage && <p className="react-dashboard-error" data-qa="dr-report-action-error" role="alert">{actionErrorMessage}</p>}
      {!selected && actionErrorDiagnostic && <ReportErrorDiagnostic diagnostic={actionErrorDiagnostic} />}
      {showError && <div className="react-dashboard-error topicrpt-recoverable-error" data-qa={`dr-error-${errorKind || "request"}`} role="alert"><strong>{generationOutcomeUnknown ? "서버 상태를 확인하세요" : "다시 시도할 수 있습니다"}</strong><span data-qa={`dr-error-${(errorReason || "request").replace(/_/g, "-")}`} data-error-code={errorReason || "request"}>{error}</span>{errorKind === "generation" && generationError && <ReportErrorDiagnostic diagnostic={generationError} />}<p>{generationOutcomeUnknown ? "응답이 없어 생성 결과를 확인하지 못했습니다. 현재 저장 상태를 확인한 뒤 필요할 때 직접 실행하세요." : "입력한 질문과 컨텍스트, 마지막 계획은 유지됩니다."}</p><button className="btn" type="button" onClick={() => { invalidateGenerationDiagnostic(); setError(""); setErrorKind(null); setErrorReason(""); setPhase(planEnvelope ? "plan-review" : "draft"); }}>돌아가서 수정</button></div>}

      {phase !== "plan-review" && phase !== "generation" && (
        <form className="input-panel topicrpt-form" onSubmit={handlePreview} noValidate>
          <div className="input-panel-header">
            <span className="section-kicker">투자 질문</span>
            <h2>무엇을 투자 판단으로 확인하고 싶나요?</h2>
            <p>질문은 1~500자로 입력하세요. 추가로 적는 조건은 내 생각(가설)로만 전달되며 외부 근거로 쓰이지 않습니다.</p>
          </div>
          <label className="field topicrpt-question-field">
            <span>투자 질문</span>
            <textarea data-qa="dr-question" value={question} onChange={(event) => setQuestion(event.currentTarget.value)} maxLength={500} rows={4} placeholder="예: 미국 전력 수요 증가가 12개월 내 반도체 공급망과 관련 기업에 어떤 영향을 줄까?" required aria-describedby="dr-question-help" />
            <small id="dr-question-help">{question.length}/500</small>
          </label>
          <details className="topicrpt-advanced" data-qa="dr-advanced" open={Boolean(userContext.trim() || selectedCollectionRef)}>
            <summary>분석 조건 추가 <em>(선택)</em></summary>
            <label className="field topicrpt-context-field">
              <span>추가 조건</span>
              <textarea data-qa="dr-context" value={userContext} onChange={(event) => setUserContext(event.currentTarget.value)} maxLength={4000} rows={4} placeholder="예: 보유 종목, 관심 지역, 확인할 기간 등. 이 내용은 내 생각(가설)로 표시됩니다." />
            </label>
            <InvestmentContextCard mode="deep-research" onReference={referenceInvestmentContext} />
            <SmartCollectionsPanel
              selectedRef={selectedCollectionRef}
              onSelectedRef={setSelectedCollectionRef}
              onBusyChange={setCollectionBusy}
              onOpenDetail={(collectionId) => { window.location.hash = deepResearchCollectionHash(collectionId); }}
              disabled={phase === "plan-loading" || loading}
            />
            <div className="topicrpt-policy-row">
              <label className="field topicrpt-policy-field">
                <span>시장 상태 배경</span>
                <select value={marketStatePolicy} onChange={(event) => setMarketStatePolicy(event.currentTarget.value as MarketStatePolicy)}>
                  <option value="include_current">현재 상태 포함</option>
                  <option value="exclude">제외</option>
                </select>
              </label>
              <label className="field topicrpt-policy-field">
                <span>시장 상태 범위</span>
                <select value={marketStateScope} onChange={(event) => setMarketStateScope(event.currentTarget.value as MarketStateScope)}>
                  <option value="AUTO">자동</option>
                  <option value="GLOBAL">글로벌</option>
                  <option value="US">미국</option>
                  <option value="KR">한국</option>
                </select>
              </label>
            </div>
          </details>
          <div className="topicrpt-action-row">
            <span className="topicrpt-policy-note">심층 조사 · 최대 2라운드</span>
            {/* 한 줄 안에서 고르는 자리라 라벨을 위가 아니라 옆에 둔다. 위에 두면
                이 칸만 다른 것들보다 20px 높아져 줄이 어긋난다. */}
            <div className="topicrpt-planner-choice">
              <span id="dr-planner-engine-label">계획 작성</span>
              <div className="segment" data-qa="dr-planner-engine" role="group" aria-labelledby="dr-planner-engine-label">
                {PLANNER_ENGINES.map((option) => (
                  <button
                    type="button"
                    key={option.value}
                    aria-pressed={plannerEngine === option.value}
                    disabled={isBusy}
                    data-tooltip={option.hint}
                    onClick={() => setPlannerEngine(option.value)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
            <button className="btn btn--primary" type="submit" data-qa="dr-preview" disabled={isBusy}>
              {phase === "plan-loading" ? (plannerEngine === "rules" ? "계획 준비 중" : "AI가 계획을 쓰는 중") : "계획 미리보기"}
            </button>
          </div>
          <input type="hidden" value={customLabel} data-legacy-topic={topicKey} readOnly aria-hidden="true" />
          <input type="hidden" value={deepResearch ? "true" : "false"} readOnly aria-hidden="true" />
        </form>
      )}

      {phase === "plan-review" && planEnvelope && (
        <PlanReview
          envelope={planEnvelope}
          onContinue={handleContinue}
          onEdit={() => { setPhase("draft"); setPlanEditing(false); setStatus(""); }}
          editing={planEditing}
          revising={planRevising}
          replanning={planReplanning}
          onReplan={() => void runReplan("")}
          onEditPlan={() => setPlanEditing(true)}
          onRevise={(instruction) => void revisePlan(instruction)}
          onCancelEdit={() => setPlanEditing(false)}
          degradedConfirming={degradedConfirming}
          onConfirmDegraded={() => void confirmDegraded()}
          onCancelDegraded={() => setDegradedConfirming(false)}
        />
      )}

      {phase === "generation" && <section className="input-panel topicrpt-generation-panel" data-qa="dr-generation" aria-live="polite"><span className="section-kicker">생성 중</span><h2>승인한 계획을 실행하는 중입니다</h2><p data-qa="dr-generation-status">{status || "작업 상태를 확인하는 중입니다."}</p></section>}

      {status && phase !== "generation" && phase !== "report" && <p className="react-dashboard-warning" data-qa="dr-status" role="status">{status}</p>}

      {/* 저장 목록은 브리핑·기업분석과 같은 서식을 쓴다. 화면마다 제목·건수 표시가
          달라 보이면 같은 종류의 목록이라는 것이 읽히지 않는다. */}
      <section className="find-bar" aria-label="저장된 리서치 검색">
        <input
          className="find-bar__search"
          type="search"
          value={reportQuery}
          onChange={(event) => setReportQuery(event.currentTarget.value)}
          placeholder="주제·질문·모델 검색"
          aria-label="저장된 리서치 검색"
        />
        <label className="find-bar__field">
          <span>보기</span>
          <select
            aria-label="저장된 리서치 보기 방식"
            value={reportView}
            onChange={(event) => setReportView(event.currentTarget.value as SavedViewMode)}
          >
            <option value="recent">최근</option>
            <option value="topic">주제별</option>
            <option value="month">월별</option>
          </select>
        </label>
        <button
          className="btn btn--text find-bar__reset"
          type="button"
          onClick={() => { setReportQuery(""); setReportView("recent"); }}
        >
          초기화
        </button>
      </section>

      <section className="react-analysis-feed" aria-label="저장된 리서치">
        <div className="react-section-heading">
          <div>
            <p className="section-kicker">Saved Research</p>
            <h2 ref={listHeadingRef} tabIndex={-1}>저장된 리서치</h2>
          </div>
          <span aria-live="polite">{`${filteredReports.length}건${reportQuery ? " · 검색 결과" : ""}`}</span>
        </div>
        {groupedReports.length ? groupedReports.map((group) => (
          <section className="report-feed-group" key={group.key}>
            <div className="report-feed-group-head"><span className="report-feed-group-name">{group.key}</span><span className="report-feed-group-meta">{groupMeta(group.rows.length, group.rows[0]?.generatedAt || group.rows[0]?.date)}</span></div>
            <div className="report-feed-group-cards">
              {group.rows.map((report) => {
                const deleting = actionBusy === `delete-${report.id}`;
                return (
                  <div className="report-feed-card-wrap" key={report.id || `${reportLabel(report)}-${report.date}`}>
                    <button className="report-feed-card is-topic" type="button" data-report-id={report.id} onClick={() => { if (report.id) { openingReportId.current = report.id; setTopicHash(report.id); } }}><span className="report-feed-card-meta">{(report.engine || report.mode) && <span className="report-feed-badge">{report.engine || String(report.mode).toUpperCase()}{engineNote(report.engine, report.engineDetail) && <em>{engineNote(report.engine, report.engineDetail)}</em>}</span>}</span><strong>{reportLabel(report)}</strong><span className="report-feed-card-foot">생성일 {displayDate(report.date || report.generatedAt)}</span></button>
                    <button type="button" className="btn btn--icon report-feed-card-delete" disabled={deleting} onClick={() => void deleteReport(report)} aria-label={`${reportLabel(report)} 삭제`} data-tooltip="삭제" data-tooltip-pos="bottom"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2.5 4h11M6 4V2.5h4V4M5 4l.5 9h5L11 4" /></svg></button>
                  </div>
                );
              })}
            </div>
          </section>
        )) : <div className="report-feed-empty" data-qa="dr-report-list-empty">{reportQuery ? "검색 결과가 없습니다." : "저장된 딥 리서치가 없습니다. 질문을 입력해 실행 계획을 미리보세요."}</div>}
      </section>
    </div>
  );
}
