import { FormEvent, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { getJson, postJson, type JobStatus } from "../api";
import { AgentMessageContent, AgentRunCard } from "./AgentMessageContent";
import { ThreadList, scopeChipLabel } from "./agentWorkspace/ThreadList";
import { useDockThreads } from "./agentWorkspace/useDockThreads";
import type { ScopedThreadRequest } from "./agentWorkspace/openScopedThread";
import { AgentPollTimeout, pollAgentJobBounded, releasePollController, replacePollController } from "./agentPolling";
import { actOnProposal, boundedProposalDiff, boundedProposalSummary, hydrateAgentProposalFromResult, notifyProposalLifecycle } from "./agentProposalLifecycle";
import type { ConsultationSearchMeta } from "./agentWorkspace/types";

type AgentResult = {
  reply?: string;
  notice?: string;
  proposalId?: string | null;
  // Agent Dock Stage C: lets the Dock fetch the exact reply message instead
  // of re-reading the whole thread.
  sessionId?: string;
  assistantMessageId?: string;
  // Agent Dock Stage D/E — only present via the single-message fetch, not the
  // job result itself (same reasoning as `reply`: bounded metadata belongs
  // with the answer, not the ephemeral job).
  search?: ConsultationSearchMeta;
};

type AgentProposal = {
  id: string;
  summary?: string;
  diff?: string;
  artifactKind?: string;
  artifactId?: string;
};

type AgentJob = {
  id: string;
  status: JobStatus;
  message?: string;
  error?: string;
  result?: AgentResult;
  // Agent Dock Stage A observation field — live phase within `running`.
  phaseCode?: "context" | "wait_engine" | "generate" | "postprocess" | "commit" | null;
};

type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  notice?: string;
  proposal?: AgentProposal | null;
  proposalStatus?: string;
  pending?: boolean;
  runState?: "pending" | "done" | "error" | "still-running";
  runTitle?: string;
  runMeta?: string;
  pendingHint?: string;
  jobId?: string;
  createdAt?: string;
  variant?: "welcome";
  search?: ConsultationSearchMeta;
};

type AgentModelChoice = {
  value: string;
  label: string;
};

type AgentAdapterSettings = {
  id: string;
  label?: string;
  model?: string;
  modelChoices?: AgentModelChoice[];
  // 노력 단계는 CLI마다, 같은 CLI 안에서도 모델마다 실제로 받는 값·이름이 다르다
  // (Codex는 low를 "Light"로 부르고 ultra까지, Claude는 "Low"로 부르고 대개
  // max까지). 서버(features/llm_settings/reasoning.py)가 계산한 값을 그대로
  // 쓴다 — 화면에서 다시 매핑을 지어내면 그 CLI가 실제로는 안 받는 값을 보낼 수
  // 있다.
  reasoningChoices?: AgentModelChoice[];
  reasoningByModel?: Record<string, AgentModelChoice[]>;
  // 브리지가 지원하지 않는 CLI(버전이 못 미치는 agy 등)는 고를 수 없어야 한다.
  bridgeSupported?: boolean;
  // Agent Dock Stage D — server-authoritative (bridge.py::adapter_supports_web_search()).
  supportsWebSearch?: boolean;
};

type AgentSettings = {
  provider?: string;
  selectedAdapter?: string;
  adapters?: AgentAdapterSettings[];
  message?: string;
};

type AgentPreflightCheck = {
  id: string;
  label: string;
  ok: boolean;
  severity?: "info" | "warning" | "error";
  message: string;
  detail?: string;
};

type AgentPreflight = {
  ok: boolean;
  adapter?: string;
  checks?: AgentPreflightCheck[];
};

type ReactAgentDockProps = {
  surface: string;
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
};

type AgentRequestDetail = Record<string, unknown> & {
  message?: string;
  prompt?: string;
  autoSubmit?: boolean;
};

const PROVIDERS = new Set(["codex", "claude", "antigravity"]);
const WELCOME_AGENT_MESSAGE: AgentMessage = {
  id: "welcome",
  role: "assistant",
  text: "현재 화면에 대해 물어보세요. 보고서 수정이나 발전 요청은 작업으로 전환해 처리합니다.",
  variant: "welcome",
  createdAt: new Date().toISOString(),
};

const CODEX_COLOR_LOGO = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="M19.503 0H4.496A4.496 4.496 0 000 4.496v15.007A4.496 4.496 0 004.496 24h15.007A4.496 4.496 0 0024 19.503V4.496A4.496 4.496 0 0019.503 0z" fill="#fff"></path><path d="M9.064 3.344a4.578 4.578 0 012.285-.312c1 .115 1.891.54 2.673 1.275.01.01.024.017.037.021a.09.09 0 00.043 0 4.55 4.55 0 013.046.275l.047.022.116.057a4.581 4.581 0 012.188 2.399c.209.51.313 1.041.315 1.595a4.24 4.24 0 01-.134 1.223.123.123 0 00.03.115c.594.607.988 1.33 1.183 2.17.289 1.425-.007 2.71-.887 3.854l-.136.166a4.548 4.548 0 01-2.201 1.388.123.123 0 00-.081.076c-.191.551-.383 1.023-.74 1.494-.9 1.187-2.222 1.846-3.711 1.838-1.187-.006-2.239-.44-3.157-1.302a.107.107 0 00-.105-.024c-.388.125-.78.143-1.204.138a4.441 4.441 0 01-1.945-.466 4.544 4.544 0 01-1.61-1.335c-.152-.202-.303-.392-.414-.617a5.81 5.81 0 01-.37-.961 4.582 4.582 0 01-.014-2.298.124.124 0 00.006-.056.085.085 0 00-.027-.048 4.467 4.467 0 01-1.034-1.651 3.896 3.896 0 01-.251-1.192 5.189 5.189 0 01.141-1.6c.337-1.112.982-1.985 1.933-2.618.212-.141.413-.251.601-.33.215-.089.43-.164.646-.227a.098.098 0 00.065-.066 4.51 4.51 0 01.829-1.615 4.535 4.535 0 011.837-1.388zm3.482 10.565a.637.637 0 000 1.272h3.636a.637.637 0 100-1.272h-3.636zM8.462 9.23a.637.637 0 00-1.106.631l1.272 2.224-1.266 2.136a.636.636 0 101.095.649l1.454-2.455a.636.636 0 00.005-.64L8.462 9.23z" fill="url(#folio-react-codex-gradient)"></path><defs><linearGradient gradientUnits="userSpaceOnUse" id="folio-react-codex-gradient" x1="12" x2="12" y1="3" y2="21"><stop stop-color="#B1A7FF"></stop><stop offset=".5" stop-color="#7A9DFF"></stop><stop offset="1" stop-color="#3941FF"></stop></linearGradient></defs></svg>`;
const CODEX_MONO_LOGO = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="M9.064 3.344a4.578 4.578 0 012.285-.312c1 .115 1.891.54 2.673 1.275.01.01.024.017.037.021a.09.09 0 00.043 0 4.55 4.55 0 013.046.275l.047.022.116.057a4.581 4.581 0 012.188 2.399c.209.51.313 1.041.315 1.595a4.24 4.24 0 01-.134 1.223.123.123 0 00.03.115c.594.607.988 1.33 1.183 2.17.289 1.425-.007 2.71-.887 3.854l-.136.166a4.548 4.548 0 01-2.201 1.388.123.123 0 00-.081.076c-.191.551-.383 1.023-.74 1.494-.9 1.187-2.222 1.846-3.711 1.838-1.187-.006-2.239-.44-3.157-1.302a.107.107 0 00-.105-.024c-.388.125-.78.143-1.204.138a4.441 4.441 0 01-1.945-.466 4.544 4.544 0 01-1.61-1.335c-.152-.202-.303-.392-.414-.617a5.81 5.81 0 01-.37-.961 4.582 4.582 0 01-.014-2.298.124.124 0 00.006-.056.085.085 0 00-.027-.048 4.467 4.467 0 01-1.034-1.651 3.896 3.896 0 01-.251-1.192 5.189 5.189 0 01.141-1.6c.337-1.112.982-1.985 1.933-2.618.212-.141.413-.251.601-.33.215-.089.43-.164.646-.227a.098.098 0 00.065-.066 4.51 4.51 0 01.829-1.615 4.535 4.535 0 011.837-1.388zm3.482 10.565a.637.637 0 000 1.272h3.636a.637.637 0 100-1.272h-3.636zM8.462 9.23a.637.637 0 00-1.106.631l1.272 2.224-1.266 2.136a.636.636 0 101.095.649l1.454-2.455a.636.636 0 00.005-.64L8.462 9.23z" fill="currentColor"/></svg>`;
const CLAUDE_LOGO_PATH = "M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z";
const CLAUDE_COLOR_LOGO = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="${CLAUDE_LOGO_PATH}" fill="#D97757" fill-rule="nonzero"></path></svg>`;
const CLAUDE_MONO_LOGO = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="${CLAUDE_LOGO_PATH}" fill="currentColor" fill-rule="nonzero"></path></svg>`;
const ANTIGRAVITY_LOGO_PATH = "M21.751 22.607c1.34 1.005 3.35.335 1.508-1.508C17.73 15.74 18.904 1 12.037 1 5.17 1 6.342 15.74.815 21.1c-2.01 2.009.167 2.511 1.507 1.506 5.192-3.517 4.857-9.714 9.715-9.714 4.857 0 4.522 6.197 9.714 9.715z";
const ANTIGRAVITY_COLOR_LOGO = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="${ANTIGRAVITY_LOGO_PATH}" fill="url(#folio-react-antigravity-gradient)"></path><defs><linearGradient id="folio-react-antigravity-gradient" x1="5" x2="19" y1="22" y2="2" gradientUnits="userSpaceOnUse"><stop stop-color="#3186FF"></stop><stop offset=".42" stop-color="#34A853"></stop><stop offset=".72" stop-color="#FBBC04"></stop><stop offset="1" stop-color="#EA4335"></stop></linearGradient></defs></svg>`;
const ANTIGRAVITY_MONO_LOGO = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="${ANTIGRAVITY_LOGO_PATH}" fill="currentColor"></path></svg>`;
const DEFAULT_AGENT_LOGO = `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M9 3c.4 3.9 3.1 6.6 7 7-3.9.4-6.6 3.1-7 7-.4-3.9-3.1-6.6-7-7 3.9-.4 6.6-3.1 7-7z"/><path d="M17.8 13c.25 2.4 1.85 4 4.2 4.25-2.35.25-3.95 1.85-4.2 4.25-.25-2.4-1.85-4-4.2-4.25 2.35-.25 3.95-1.85 4.2-4.25z" opacity=".7"/></svg>`;

const PROVIDER_META: Record<string, { label: string; color: string; logo: string; monoLogo: string }> = {
  codex: { label: "Codex", color: "#3941ff", logo: CODEX_COLOR_LOGO, monoLogo: CODEX_MONO_LOGO },
  claude: { label: "Claude", color: "#d97757", logo: CLAUDE_COLOR_LOGO, monoLogo: CLAUDE_MONO_LOGO },
  antigravity: { label: "Antigravity", color: "#3186ff", logo: ANTIGRAVITY_COLOR_LOGO, monoLogo: ANTIGRAVITY_MONO_LOGO },
  default: { label: "Folio Agent", color: "#c79a45", logo: DEFAULT_AGENT_LOGO, monoLogo: DEFAULT_AGENT_LOGO },
};

function messageId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function formatTime(value?: string) {
  const parsed = value ? new Date(value) : new Date();
  return parsed.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

// 어댑터·모델 정보가 아직 없을 때만 쓰는 자리표시자(설정을 못 불러왔을 때 등) —
// 실제 값은 항상 서버가 계산해 보내는 adapter별 reasoningChoices/reasoningByModel을
// 그대로 쓴다.
const FALLBACK_EFFORT_CHOICES: AgentModelChoice[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "max", label: "Max" },
];

/** 이 CLI(모델)가 실제로 받는 노력 단계 목록. `provider_default`(제공자 기본값)는
 *  여기서는 안 보여준다 — 도크는 항상 명시적인 단계 하나를 보낸다. */
function reasoningChoicesFor(adapter: AgentAdapterSettings | null, model: string): AgentModelChoice[] {
  const byModel = adapter?.reasoningByModel?.[model] || [];
  const source = byModel.length ? byModel : adapter?.reasoningChoices || [];
  const explicit = source.filter((choice) => choice?.value && choice.value !== "provider_default");
  const deduped = explicit.filter((choice, index, all) => all.findIndex((item) => item.value === choice.value) === index);
  return deduped.length ? deduped : FALLBACK_EFFORT_CHOICES;
}

function effortLabel(adapter: AgentAdapterSettings | null, model: string, value: string) {
  return reasoningChoicesFor(adapter, model).find((choice) => choice.value === value)?.label || value;
}

function elapsedSeconds(startedAt: number) {
  return `${Math.max(1, Math.round((Date.now() - startedAt) / 1000))}초`;
}

const PHASE_LABELS: Record<string, string> = {
  context: "대화 맥락을 조립하는 중",
  wait_engine: "다른 작업이 끝나길 기다리는 중",
  generate: "Agent가 응답을 생성하는 중",
  postprocess: "응답을 정리하는 중",
  commit: "답변을 저장하는 중",
};

/** 폴링 tick마다 실제 phase(Agent Dock Stage A가 관측)와 경과 시간을 보여준다.
 *  phase를 아직 모르면(예: 첫 tick 전) 호출부가 기존 고정 문구로 대신한다. */
function phaseHint(phaseCode: string | null | undefined, startedAt: number) {
  const label = phaseCode ? PHASE_LABELS[phaseCode] : "";
  return label ? `${label} · ${elapsedSeconds(startedAt)}` : "";
}

const MAX_SHOWN_SOURCE_REFS = 5;

/** Agent Dock Stage E — 실제로 검색을 썼을 때만 보이는 한 줄. 드롭다운·내부
 *  스크롤·다중 뷰를 만들지 않고, 최대 5개만 이름을 보여주고 나머지는 개수로
 *  요약한다(계획 §Stage E). */
function SearchSourcesLine({ search }: { search?: ConsultationSearchMeta }) {
  if (!search || search.toolUsed !== "yes" || !search.sourceRefs.length) return null;
  const shown = search.sourceRefs.slice(0, MAX_SHOWN_SOURCE_REFS);
  const remaining = search.sourceRefs.length - shown.length;
  return (
    <p className="react-agent-search-meta">
      {`웹 검색 · 출처 ${search.sourceRefs.length}개 — `}
      {shown.map((source, index) => (
        <span key={source.url}>
          {index > 0 && ", "}
          <a href={source.url} target="_blank" rel="noreferrer">{source.label || source.url}</a>
        </span>
      ))}
      {remaining > 0 && ` 외 ${remaining}개`}
    </p>
  );
}

const GLOBAL_AGENT_CONTEXT_FIELDS = [
  "surface",
  "viewId",
  "reportKind",
  "reportId",
  "marketScope",
  "selectedText",
  "visibleSection",
  "portfolioLinked",
] as const;

function safeGlobalContextPatch(context: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!context) return {};
  const patch: Record<string, unknown> = {};
  for (const field of GLOBAL_AGENT_CONTEXT_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(context, field)) patch[field] = context[field];
  }
  return patch;
}

function collectionIdentityPatch(context: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!context) return {};
  const hasId = Object.prototype.hasOwnProperty.call(context, "collectionId");
  const hasRevision = Object.prototype.hasOwnProperty.call(context, "collectionRevision");
  if (!hasId || !hasRevision) return {};
  const collectionId = context.collectionId;
  const collectionRevision = context.collectionRevision;
  if (collectionId === null && collectionRevision === null) return { collectionId: null, collectionRevision: null };
  if (
    typeof collectionId === "string"
    && collectionId.trim().length > 0
    && typeof collectionRevision === "number"
    && Number.isInteger(collectionRevision)
    && collectionRevision >= 1
  ) {
    return { collectionId, collectionRevision };
  }
  return {};
}

function withoutCollectionIdentity(context: Record<string, unknown>): Record<string, unknown> {
  const patch = { ...context };
  delete patch.collectionId;
  delete patch.collectionRevision;
  return patch;
}

export type DockContextState = {
  ownerSurface: string;
  patch: Record<string, unknown>;
};

export function resetDockContextForSurface(state: DockContextState, surface: string): DockContextState {
  if (state.ownerSurface === surface) return state;
  return { ownerSurface: surface, patch: {} };
}

export function patchDockContextForSurface(
  state: DockContextState,
  surface: string,
  contextPatch: Record<string, unknown>,
): DockContextState {
  const scoped = resetDockContextForSurface(state, surface);
  return {
    ownerSurface: surface,
    patch: { ...scoped.patch, ...contextPatch, surface: String(contextPatch.surface || surface) },
  };
}

export function buildAgentRequestContext(
  globalContext: Record<string, unknown> | undefined,
  state: DockContextState,
  surface: string,
  contextPatch: Record<string, unknown> = {},
): Record<string, unknown> {
  const scoped = resetDockContextForSurface(state, surface);
  return {
    ...safeGlobalContextPatch(globalContext),
    ...withoutCollectionIdentity(scoped.patch),
    ...withoutCollectionIdentity(contextPatch),
    ...collectionIdentityPatch(globalContext),
  };
}

function globalProvider(settings: AgentSettings | null) {
  return settings?.provider && PROVIDERS.has(settings.provider)
    ? settings.provider
    : settings?.selectedAdapter || "";
}

/** 이 대화가 실제로 쓸 어댑터.
 *
 *  `override`는 **이 대화에만** 적용된다 — 설정과 상단바가 소유한 전역 기본을 바꾸지
 *  않으므로, 도크에서 다른 CLI로 한 번 물어봐도 내일 아침 예약 브리핑은 그대로다.
 */
function selectedAdapter(settings: AgentSettings | null, override = ""): AgentAdapterSettings | null {
  const provider = override && PROVIDERS.has(override) ? override : globalProvider(settings);
  return settings?.adapters?.find((adapter) => adapter.id === provider) || null;
}

function providerMeta(settings: AgentSettings | null, override = "") {
  const provider = override && PROVIDERS.has(override) ? override : globalProvider(settings);
  return PROVIDER_META[provider] || PROVIDER_META.default;
}

function modelChoicesFor(adapter: AgentAdapterSettings | null) {
  return adapter?.modelChoices || [];
}

function preferredModel(adapter: AgentAdapterSettings | null) {
  const choices = modelChoicesFor(adapter);
  if (!choices.length) return "";
  return choices.some((choice) => choice.value === adapter?.model) ? String(adapter?.model || "") : choices[0].value;
}

export function ReactAgentDock({ surface, open, onOpen, onClose }: ReactAgentDockProps) {
  const [settings, setSettings] = useState<AgentSettings | null>(null);
  const [preflight, setPreflight] = useState<AgentPreflight | null>(null);
  const [messages, setMessages] = useState<AgentMessage[]>([WELCOME_AGENT_MESSAGE]);
  const [threadsOpen, setThreadsOpen] = useState(false);
  // 대화는 서버에 저장된다 — 브라우저를 닫아도, 기기를 바꿔도 남고 Agent가 다음
  // 세션에서 context로 읽는다. localStorage에만 있던 예전 구조에서는 불가능했다.
  const threads = useDockThreads(WELCOME_AGENT_MESSAGE);
  const scopeChip = scopeChipLabel(threads.scope || undefined);
  const [input, setInput] = useState("");
  const [model, setModel] = useState("");
  // 이 대화에만 쓰는 CLI. 비어 있으면 전역 기본(설정 탭·상단바)을 따른다. 새 대화는
  // 다시 빈 값에서 시작한다 — "이 대화에만"이 말 그대로여야 한다.
  const [providerOverride, setProviderOverride] = useState("");
  const [effort, setEffort] = useState("medium");
  // Agent Dock Stage E. Per-conversation like `providerOverride` — never
  // persisted to global settings (plan §5.3: 마이그레이션 기본값은 off,
  // 기존 대화의 네트워크 동작을 조용히 바꾸지 않는다). New chats start at "off".
  const [searchPolicy, setSearchPolicy] = useState<"off" | "auto" | "on">("off");
  const [runMenuOpen, setRunMenuOpen] = useState(false);
  const runMenuRef = useRef<HTMLDivElement | null>(null);
  const runTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const contextRef = useRef<DockContextState>({ ownerSurface: surface, patch: {} });
  const pollControllers = useRef(new Map<string, AbortController>());
  const scopedAutoSubmitInFlight = useRef(new Set<string>());

  useEffect(() => () => {
    for (const controller of pollControllers.current.values()) controller.abort();
    pollControllers.current.clear();
  }, []);

  // 상단바 메뉴와 같은 규칙 — 바깥을 누르거나 Escape면 닫고 포커스를 버튼으로 돌린다.
  useEffect(() => {
    if (!runMenuOpen) return undefined;
    const onPointerDown = (event: PointerEvent) => {
      if (!runMenuRef.current?.contains(event.target as Node)) setRunMenuOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setRunMenuOpen(false); runTriggerRef.current?.focus(); }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [runMenuOpen]);

  const applySettings = useCallback((payload: AgentSettings, keepCurrent = false, override = "") => {
    const adapter = selectedAdapter(payload, override);
    setSettings(payload);
    setModel((current) => {
      const preferred = preferredModel(adapter);
      if (keepCurrent && modelChoicesFor(adapter).some((choice) => choice.value === current)) return current;
      return preferred;
    });
  }, []);

  // CLI를 바꾸면 모델 목록이 통째로 달라진다. 이 대화의 모델을 새 CLI의 것으로 옮기고,
  // 전역 설정은 건드리지 않는다.
  const chooseProvider = useCallback((next: string) => {
    setProviderOverride(next);
    setModel(preferredModel(selectedAdapter(settings, next)));
  }, [settings]);

  const loadAgentSettings = useCallback(async (refresh = false) => {
    const payload = await getJson<AgentSettings>(`/api/agent-bridge/settings${refresh ? "?refresh=true" : ""}`);
    applySettings(payload, true);
    return payload;
  }, [applySettings]);

  const loadPreflight = useCallback(async (payload: AgentSettings | null) => {
    try {
      const provider = payload?.provider && PROVIDERS.has(payload.provider) ? payload.provider : "";
      const query = provider ? `?adapter=${encodeURIComponent(provider)}` : "";
      setPreflight(await getJson<AgentPreflight>(`/api/agent-bridge/preflight${query}`));
    } catch (err) {
      setPreflight({
        ok: false,
        checks: [{
          id: "preflight",
          label: "Agent Preflight",
          ok: false,
          severity: "error",
          message: err instanceof Error ? err.message : "Agent 준비 상태를 확인하지 못했습니다.",
        }],
      });
    }
  }, []);

  useEffect(() => {
    let alive = true;
    getJson<AgentSettings>("/api/agent-bridge/settings")
      .then((payload) => {
        if (!alive) return;
        applySettings(payload);
        void loadPreflight(payload);
      })
      .catch((err) => {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "Agent 설정을 불러오지 못했습니다.");
      });
    return () => {
      alive = false;
    };
  }, [applySettings, loadPreflight]);

  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [messages, open]);

  useEffect(() => {
    contextRef.current = resetDockContextForSurface(contextRef.current, surface);
  }, [surface]);

  useEffect(() => {
    const handleSettingsUpdate = (event: Event) => {
      const detail = (event as CustomEvent<AgentSettings | null>).detail;
      if (detail) {
        applySettings(detail);
        void loadPreflight(detail);
      } else {
        loadAgentSettings()
          .then((payload) => loadPreflight(payload))
          .catch((err) => setError(err instanceof Error ? err.message : "Agent 설정을 불러오지 못했습니다."));
      }
    };
    window.addEventListener("folio:agent-settings-updated", handleSettingsUpdate);
    return () => window.removeEventListener("folio:agent-settings-updated", handleSettingsUpdate);
  }, [applySettings, loadAgentSettings, loadPreflight]);

  const adapter = selectedAdapter(settings, providerOverride);
  const meta = providerMeta(settings, providerOverride);
  const globalId = globalProvider(settings);
  const overridden = Boolean(providerOverride) && providerOverride !== globalId;
  const modelChoices = modelChoicesFor(adapter);
  const effortChoices = reasoningChoicesFor(adapter, model);
  // 버튼에 적을 요약. 열지 않고도 무엇으로 도는지 읽혀야 접어 둔 값이 있다.
  const runSummary = [
    (adapter?.label || meta.label || "").replace(/\s*(Code\s*)?CLI$/i, ""),
    modelChoices.find((choice) => choice.value === model)?.label || model,
    effortLabel(adapter, model, effort),
  ].filter(Boolean).join(" · ");
  const accentStyle = useMemo(() => ({ "--react-agent-accent": meta.color } as CSSProperties), [meta.color]);
  const failedPreflightChecks = (preflight?.checks || []).filter((check) => !check.ok);

  // CLI나 모델을 바꾸면 그 조합이 지금 고른 노력 단계를 아예 안 받을 수 있다(예:
  // Antigravity는 max/ultra가 없고, Codex 일부 모델은 xhigh까지만 받는다). 그대로
  // 두면 다음 전송에서 CLI가 그 값을 거부한다 — 새 목록에 없으면 안전한 값으로 옮긴다.
  useEffect(() => {
    setEffort((current) => {
      if (effortChoices.some((choice) => choice.value === current)) return current;
      return effortChoices.find((choice) => choice.value === "medium")?.value || effortChoices[0]?.value || "medium";
    });
  }, [adapter?.id, model]);

  const submitAgentMessage = useCallback(async (
    rawText: string,
    contextPatch: Record<string, unknown> = {},
    explicitThreadId = "",
    lifecycle?: { onAccepted?: () => void; onRejected?: () => void },
  ) => {
    const text = rawText.trim();
    if (!text || busy) return false;

    contextRef.current = resetDockContextForSurface(contextRef.current, surface);
    const requestContext = buildAgentRequestContext(
      window.FolioAgent?.currentContext,
      contextRef.current,
      surface,
      contextPatch,
    );
    const assistantId = messageId();
    const startedAt = Date.now();
    const createdAt = new Date(startedAt).toISOString();
    const providerLabel = adapter?.label || meta.label;
    const modelLabel = model || adapter?.model || "model";
    setMessages((current) => [
      ...current,
      { id: messageId(), role: "user", text, createdAt },
      {
        id: assistantId,
        role: "assistant",
        text: "",
        pending: true,
        runState: "pending",
        runTitle: `${providerLabel} 세션 시작`,
        runMeta: `${modelLabel} · ${effortLabel(adapter, model, effort)} · on-request`,
        createdAt,
      },
    ]);
    setInput("");
    setBusy(true);
    setError("");

    let controller: AbortController | null = null;
    let accepted = false;
    try {
      // 대화는 스레드 경로로 보낸다. 서버가 user turn을 먼저 저장하므로 재시작 후에도
      // 질문이 남고, 다음 세션의 Agent가 이 대화를 context로 읽는다.
      const threadId =
        explicitThreadId
        || threads.threadId
        || (await threads.createThread({
          title: threads.pending?.title || text.slice(0, 40),
          scope: threads.pending?.scope,
        })).id;
      const submitted = await postJson<{ job: AgentJob }>(
        `/api/agent/threads/${encodeURIComponent(threadId)}/messages`,
        { message: text, operationId: messageId(), context: requestContext, options: { model, effort, adapter: providerOverride, searchPolicy } },
      );
      // The server has durably accepted both the user turn and its job at this
      // point.  Scoped actions must resolve now: Dock owns the longer-running
      // poll and its terminal presentation.
      accepted = true;
      lifecycle?.onAccepted?.();
      controller = new AbortController();
      replacePollController(pollControllers.current, assistantId, controller);
      const done = await pollAgentJobBounded(submitted.job, {
        signal: controller.signal,
        onUpdate: (current) => {
          const hint = phaseHint(current.phaseCode, startedAt);
          if (hint) setMessages((rows) => rows.map((row) => row.id === assistantId ? { ...row, pendingHint: hint } : row));
        },
      });
      releasePollController(pollControllers.current, assistantId, controller);
      // 답변 본문은 잡 결과가 아니라 스레드에서 읽는다 — 잡 결과는 Work Log에 저장되므로
      // transcript를 담지 않는다(0.4 상담 계약). 잡이 정확한 assistantMessageId를
      // 알려주면(Agent Dock Stage C) 그 메시지 하나만 읽고(검색 metadata도 함께,
      // Stage E), 없거나 실패하면 전체 스레드를 다시 읽는다(그 경로는 search가 없다).
      const raw = done.result || {};
      const fetched = raw.assistantMessageId ? await threads.getMessage(threadId, raw.assistantMessageId) : null;
      const reply = fetched?.content || await threads.latestReply(threadId);
      const result = { ...raw, reply, search: fetched?.search };
      const proposalHydration = await hydrateAgentProposalFromResult(result);
      threads.bumpList();
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                text: result.reply || done.message || "Agent가 응답을 반환하지 않았습니다.",
                notice: [result.notice, proposalHydration.notice].filter(Boolean).join(" "),
                proposal: proposalHydration.proposal,
                proposalStatus: proposalHydration.proposalStatus,
                search: result.search,
                pending: false,
                runState: "done",
                runTitle: `${providerLabel} 응답`,
                runMeta: `${modelLabel} · ${effortLabel(adapter, model, effort)} · ${elapsedSeconds(startedAt)}`,
              }
            : message,
        ),
      );
      return true;
    } catch (err) {
      if (controller) releasePollController(pollControllers.current, assistantId, controller);
      if (err instanceof AgentPollTimeout) {
        setMessages((current) => current.map((message) => message.id === assistantId ? {
          ...message,
          text: err.message,
          pending: false,
          runState: "still-running",
          runTitle: `${providerLabel} 계속 실행 중`,
          runMeta: `${modelLabel} · ${effortLabel(adapter, model, effort)} · ${elapsedSeconds(startedAt)}`,
          jobId: err.job.id,
        } : message));
        // The first message was accepted before polling began; only the
        // bounded wait elapsed, so the scoped action may acknowledge it.
        return true;
      }
      const messageText = err instanceof Error ? err.message : "Agent 요청에 실패했습니다.";
      if (!accepted) lifecycle?.onRejected?.();
      setError(messageText);
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                text: messageText,
                pending: false,
                runState: "error",
                runTitle: `${providerLabel} 오류`,
                runMeta: `${modelLabel} · ${effortLabel(adapter, model, effort)}`,
              }
            : message,
        ),
      );
      return false;
    } finally {
      setBusy(false);
    }
    // threads.threadId/pending은 useDockThreads가 렌더마다 새로 담는 스냅샷 값이라
    // 의존성에서 빠지면 낡은 threadId로 이전 대화에 질문이 저장된다 — `새 대화`·
    // `짚어보기`·대화 전환 직후의 첫 질문이 전부 직전 스레드로 갔다.
  }, [adapter, busy, effort, meta.label, model, searchPolicy, surface, threads.threadId, threads.pending, threads.createThread, threads.latestReply, threads.getMessage, threads.bumpList]);

  async function resumeAgentJob(messageIdValue: string, jobId: string) {
    const controller = new AbortController();
    const resumedAt = Date.now();
    replacePollController(pollControllers.current, messageIdValue, controller);
    setMessages((current) => current.map((message) => message.id === messageIdValue ? {
      ...message, pending: true, runState: "pending", runTitle: "Agent 상태 다시 확인 중",
    } : message));
    try {
      const current = await getJson<AgentJob>(`/api/jobs/${encodeURIComponent(jobId)}`, { signal: controller.signal });
      const done = await pollAgentJobBounded(current, {
        signal: controller.signal,
        onUpdate: (job) => {
          const hint = phaseHint(job.phaseCode, resumedAt);
          if (hint) setMessages((rows) => rows.map((row) => row.id === messageIdValue ? { ...row, pendingHint: hint } : row));
        },
      });
      // 제출 경로와 같은 계약이다 — 답변 본문은 잡 결과가 아니라 스레드에서 읽는다.
      // 잡이 정확한 assistantMessageId를 알려주면(Agent Dock Stage C) 그 메시지
      // 하나만(검색 metadata 포함, Stage E) 읽고, 없거나 실패하면 전체 스레드를
      // 다시 읽는다(그 경로는 search가 없다).
      const raw = done.result || {};
      const fetched = raw.assistantMessageId && threads.threadId
        ? await threads.getMessage(threads.threadId, raw.assistantMessageId)
        : null;
      const reply = fetched?.content || (threads.threadId ? await threads.latestReply(threads.threadId) : "");
      const result: AgentResult = { ...raw, reply, search: fetched?.search };
      const proposalHydration = await hydrateAgentProposalFromResult(result);
      threads.bumpList();
      setMessages((messages) => messages.map((message) => message.id === messageIdValue ? {
        ...message,
        text: result.reply || done.message || "Agent가 응답을 반환하지 않았습니다.",
        notice: [result.notice, proposalHydration.notice].filter(Boolean).join(" "),
        proposal: proposalHydration.proposal,
        proposalStatus: proposalHydration.proposalStatus,
        search: result.search,
        pending: false,
        runState: "done",
        runTitle: "Agent 응답",
        jobId: undefined,
      } : message));
    } catch (err) {
      if (err instanceof AgentPollTimeout) {
        setMessages((messages) => messages.map((message) => message.id === messageIdValue ? {
          ...message, text: err.message, pending: false, runState: "still-running", runTitle: "Agent 계속 실행 중", jobId: err.job.id,
        } : message));
      } else if (!(err instanceof DOMException && err.name === "AbortError")) {
        setMessages((messages) => messages.map((message) => message.id === messageIdValue ? {
          ...message, text: err instanceof Error ? err.message : "Agent 상태 확인에 실패했습니다.", pending: false, runState: "error", runTitle: "Agent 오류",
        } : message));
      }
    } finally {
      releasePollController(pollControllers.current, messageIdValue, controller);
    }
  }

  useEffect(() => {
    const handleAgentRequest = (event: Event) => {
      const detail = ((event as CustomEvent<AgentRequestDetail>).detail || {}) as AgentRequestDetail;
      const { message, prompt, autoSubmit, ...contextPatch } = detail;
      contextRef.current = patchDockContextForSurface(contextRef.current, surface, contextPatch);
      const text = String(message || prompt || "");
      if (!text) return;
      if (autoSubmit) {
        void submitAgentMessage(text, contextPatch);
      } else {
        setInput(text);
      }
    };
    window.addEventListener("folio:react-agent-request", handleAgentRequest);
    return () => window.removeEventListener("folio:react-agent-request", handleAgentRequest);
  }, [submitAgentMessage, surface]);

  // 워치리스트·포트폴리오에서 `짚어보기`를 누르면 주제가 붙은 대화를 새로 시작한다.
  // 예전에는 별도 상담 패널이 떠서 대화 목록이 둘로 갈렸다.
  useEffect(() => {
    async function handleScopedThread(event: Event) {
      const detail = (event as CustomEvent<ScopedThreadRequest>).detail || ({} as ScopedThreadRequest);
      if (!detail.scope) return;
      // auto-submit은 새 thread를 만든 뒤에야 busy가 된다. 서로 다른 상태 버튼을
      // 빠르게 누르면 key별 dedupe만으로는 두 번째 빈 thread가 남으므로, 생성 전부터
      // 전역으로 하나만 허용한다. openScopedThread는 뒤이어 dock을 열어 현재 작업은 보인다.
      if (detail.autoSubmit && detail.initialMessage && (busy || scopedAutoSubmitInFlight.current.size > 0)) {
        window.dispatchEvent(new CustomEvent("folio:agent-thread-ack", { detail: { requestId: detail.requestId, ok: false, error: "Agent가 다른 요청을 처리 중입니다. 잠시 후 다시 시도하세요." } }));
        return;
      }
      // 주제만 들고 있다가 첫 메시지에서 만든다. 여기서 만들면 사용자가 아무것도
      // 묻지 않고 화면을 떠났을 때 빈 대화가 목록에 남는다.
      threads.setThreadId("");
      threads.setPending({ title: detail.title, scope: detail.scope });
      setMessages([{ ...WELCOME_AGENT_MESSAGE, createdAt: new Date().toISOString() }]);
      setThreadsOpen(false);
      if (!detail.initialMessage) return;
      const autoSubmitKey = detail.autoSubmit ? "scoped-auto-submit" : "";
      if (autoSubmitKey) scopedAutoSubmitInFlight.current.add(autoSubmitKey);
      if (!detail.autoSubmit) {
        // 기존 `짚어보기`는 입력만 채우는 동작이다. Stage D 반박 action과 섞지 않는다.
        setInput(detail.initialMessage);
        window.dispatchEvent(new CustomEvent("folio:agent-thread-ack", { detail: { requestId: detail.requestId, ok: true } }));
        return;
      }
      try {
        // 상태 업데이트를 기다리지 않고 방금 만든 thread ID를 명시 전달한다. 그렇지 않으면
        // 첫 auto-submit이 이전 대화의 stale threadId에 저장될 수 있다.
        const created = await threads.createThread({ title: detail.title, scope: detail.scope });
        const releaseScopedAction = () => scopedAutoSubmitInFlight.current.delete(autoSubmitKey);
        const fail = async (reason: string) => {
          let actionError = reason;
          try {
            await threads.deleteEmptyThread(created.id);
            setMessages([{ ...WELCOME_AGENT_MESSAGE, createdAt: new Date().toISOString() }]);
          } catch {
            // The message POST may already have persisted the user's turn.
            // Keep that history and explicitly tell the action owner why it
            // was not cleaned up as an empty provisional thread.
            actionError = `${reason} 질문은 대화에 저장되어 보존했습니다.`;
          }
          window.dispatchEvent(new CustomEvent("folio:agent-thread-ack", { detail: { requestId: detail.requestId, ok: false, error: actionError } }));
          releaseScopedAction();
        };
        void submitAgentMessage(detail.initialMessage, {}, created.id, {
          onAccepted: () => {
            window.dispatchEvent(new CustomEvent("folio:agent-thread-ack", { detail: { requestId: detail.requestId, ok: true } }));
            releaseScopedAction();
          },
          onRejected: () => { void fail("Agent 첫 메시지 전송에 실패했습니다. 다시 시도하세요."); },
        });
        // The acknowledgement is emitted from onAccepted immediately after
        // durable message/job POST, while Dock polling keeps ownership of the
        // terminal response state.
      } catch (reason) {
        window.dispatchEvent(new CustomEvent("folio:agent-thread-ack", { detail: { requestId: detail.requestId, ok: false, error: reason instanceof Error ? reason.message : "Agent 요청에 실패했습니다." } }));
        scopedAutoSubmitInFlight.current.delete(autoSubmitKey);
      }
    }
    window.addEventListener("folio:open-agent-thread", handleScopedThread);
    return () => window.removeEventListener("folio:open-agent-thread", handleScopedThread);
  }, [busy, submitAgentMessage, threads]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitAgentMessage(input);
  }

  function startNewChat() {
    // 빈 대화는 저장하지 않는다. 첫 메시지를 보낼 때 만들어진다.
    setMessages([{ ...WELCOME_AGENT_MESSAGE, createdAt: new Date().toISOString() }]);
    setInput("");
    setError("");
    threads.setThreadId("");
    threads.setPending(null);
    setThreadsOpen(false);
  }

  async function openThread(id: string) {
    setError("");
    try {
      setMessages(await threads.openThread(id));
      setThreadsOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "대화를 불러오지 못했습니다.");
    }
  }

  function afterThreadDeleted(id: string) {
    // 지금 보고 있던 대화를 지웠으면 빈 화면으로 돌아간다.
    if (id !== threads.threadId) return;
    threads.setThreadId("");
    threads.setScope(null);
    setMessages([{ ...WELCOME_AGENT_MESSAGE, createdAt: new Date().toISOString() }]);
  }

  async function persistModel(nextModel: string) {
    setModel(nextModel);
    // 이 대화만 다른 CLI로 돌리는 중이면 전역 설정을 건드리지 않는다. 저장하면
    // "이 대화에만"이 거짓이 되고, 예약 브리핑의 모델까지 조용히 바뀐다.
    if (providerOverride || !adapter?.id || !nextModel) return;
    try {
      const models = Object.fromEntries((settings?.adapters || []).map((item) => [item.id, item.model || ""]));
      models[adapter.id] = nextModel;
      const payload = await postJson<AgentSettings>("/api/agent-bridge/settings", { provider: adapter.id, models });
      applySettings(payload, true);
      window.dispatchEvent(new CustomEvent("folio:agent-settings-updated", { detail: payload }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "모델 설정 저장에 실패했습니다.");
    }
  }

  async function handleProposalAction(messageIdValue: string, proposalId: string, action: "approve" | "reject") {
    try {
      const result = await actOnProposal(proposalId, action);
      setMessages((current) =>
        current.map((item) =>
          item.id === messageIdValue
            ? { ...item, proposalStatus: result.status }
            : item,
        ),
      );
      notifyProposalLifecycle(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "제안 처리에 실패했습니다.");
    }
  }

  if (!open) {
    return (
      <aside className="react-agent-dock is-closed" style={accentStyle} aria-label="AI Agent 닫힘">
        <button type="button" onClick={onOpen} aria-label="AI Agent 열기" data-tooltip="AI Agent 열기" data-tooltip-pos="left">
          <span className="react-agent-closed-dot" aria-hidden="true" />
          <span>AI</span>
        </button>
      </aside>
    );
  }

  return (
    <aside className="react-agent-dock" style={accentStyle} aria-label="AI Agent">
      <header className="react-agent-dock-header">
        <div className="react-agent-dock-title">
          <span className="react-agent-logo" aria-hidden="true">
            <span className="react-agent-logo-mark" dangerouslySetInnerHTML={{ __html: meta.logo }} />
          </span>
          <div>
            <p className="section-kicker">Agent</p>
            <h2>{adapter?.label || meta.label}</h2>
          </div>
        </div>
        {/* 도크는 384px이라 글자 버튼 셋이 175px을 가져가면 제목이 두 줄로 접힌다.
            셋 다 아이콘으로 줄이고 이름은 툴팁으로 남긴다 — 닫기가 이미 쓰던 방식이다. */}
        <div className="react-agent-header-actions">
          <button
            className="icon-btn" type="button"
            aria-label="대화 목록" aria-expanded={threadsOpen}
            data-tooltip="대화 목록" data-tooltip-pos="bottom"
            onClick={() => setThreadsOpen((value) => !value)}
          >
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" width="15" height="15">
              <path d="M3 4.5h10M3 8h10M3 11.5h6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
          <button
            className="icon-btn" type="button"
            aria-label="새 대화" data-tooltip="새 대화" data-tooltip-pos="bottom"
            onClick={startNewChat}
          >
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" width="15" height="15">
              <path d="M8 3.5v9M3.5 8h9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
            </svg>
          </button>
          <button className="icon-btn" type="button" aria-label="AI Agent 닫기" data-tooltip="닫기" data-tooltip-pos="left" onClick={onClose}>×</button>
        </div>
      </header>

      {/* 머리말과 본문 사이의 가변 요소는 한 칸에 묶는다. 도크 그리드는 세 칸
          (머리말/본문/입력)이라, 여기에 형제를 늘리면 본문용 유연 칸을 빼앗아
          대화가 아래로 밀리고 위가 빈다. */}
      <div className="react-agent-dock-chrome">
        {threadsOpen && (
          <ThreadList
            activeId={threads.threadId}
            refreshKey={threads.refreshKey}
            onSelect={(id) => void openThread(id)}
            onDeleted={afterThreadDeleted}
          />
        )}
        {scopeChip && <p className="react-agent-scope"><em className="chip">{scopeChip}</em> 대화</p>}
        {/* 상담 패널이 갖고 있던 계층 경계. 대화는 hypothesis라 근거로 승격되지 않는다. */}
        <p className="react-agent-layer-note">이 대화는 내 생각(가설)이며 보고서·Market Memory·근거 평가에 사용되지 않습니다.</p>
      </div>

      <div className="react-agent-dock-body" ref={bodyRef}>
        <div className="react-agent-watermark" aria-hidden="true" dangerouslySetInnerHTML={{ __html: meta.monoLogo }} />
        {failedPreflightChecks.length > 0 && (
          <div className="react-agent-preflight" role="status">
            <strong>Agent 준비 상태 확인 필요</strong>
            {failedPreflightChecks.slice(0, 3).map((check) => (
              <p key={check.id}>{check.message}</p>
            ))}
          </div>
        )}
        <div className="react-agent-messages">
          {messages.map((message) => (
            <article key={message.id} className={`react-agent-message ${message.role}${message.pending ? " pending" : ""}`}>
              {message.role === "assistant" && (
                <div className="react-agent-message-head">
                  <span className="react-agent-mini-logo" aria-hidden="true" dangerouslySetInnerHTML={{ __html: meta.logo }} />
                  <strong>{adapter?.label || meta.label}</strong>
                  <time>{formatTime(message.createdAt)}</time>
                </div>
              )}
              {message.runTitle && <AgentRunCard state={message.runState === "still-running" ? "pending" : message.runState} title={message.runTitle} meta={message.runMeta} pendingHint={message.pendingHint} />}
              {/* 매초 바뀌는 pendingHint를 그대로 live 처리하면 스크린리더에 소음이
                  된다 — done/error로 바뀌는 순간에만 문구가 채워지는 별도의 숨은
                  영역만 알린다. */}
              {message.runTitle && (
                <span className="sr-only" role="status" aria-live="polite">
                  {message.runState === "done" ? "답변을 받았습니다." : message.runState === "error" ? "오류가 발생했습니다." : ""}
                </span>
              )}
              {message.runState === "still-running" && message.jobId && (
                <div data-qa="agent-job-still-running">
                  <button type="button" data-qa="agent-job-resume" onClick={() => void resumeAgentJob(message.id, message.jobId!)}>상태 다시 확인</button>
                </div>
              )}
              {message.text && (
                <div className={message.variant === "welcome" ? "react-agent-welcome-card" : ""}>
                  <AgentMessageContent text={message.text} />
                </div>
              )}
              {message.notice && <p className="react-agent-notice" role="status">{message.notice}</p>}
              <SearchSourcesLine search={message.search} />
              {message.proposal && (
                <div className="agent-proposal">
                  <div className="agent-proposal-title">
                    <strong>{message.proposal.artifactKind || "proposal"}</strong>
                    {message.proposal.artifactId && <span>{message.proposal.artifactId}</span>}
                  </div>
                  {message.proposalStatus === "pending" && message.proposal.summary && <p data-qa="proposal-summary">{boundedProposalSummary(message.proposal.summary)}</p>}
                  {message.proposalStatus === "pending" && message.proposal.diff && (
                    <details className="agent-proposal-diff">
                      <summary>diff 보기</summary>
                      <pre data-qa="proposal-diff">{boundedProposalDiff(message.proposal.diff)}</pre>
                    </details>
                  )}
                  {message.proposalStatus === "pending" ? (
                    <div className="agent-actions">
                      <button type="button" data-qa="proposal-approve" onClick={() => handleProposalAction(message.id, message.proposal!.id, "approve")}>
                        승인
                      </button>
                      <button type="button" data-qa="proposal-reject" onClick={() => handleProposalAction(message.id, message.proposal!.id, "reject")}>
                        거절
                      </button>
                    </div>
                  ) : (
                    <p className="agent-proposal-status" data-qa={message.proposalStatus === "applied" ? "wb-happy-applied" : message.proposalStatus === "rejected" ? "wb-f1-terminal-rejected" : message.proposalStatus === "stale" ? "wb-f1-terminal-stale" : "proposal-terminal"}>상태: {message.proposalStatus}</p>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      </div>

      <form className="react-agent-form" onSubmit={handleSubmit}>
        <textarea
          data-qa="agent-input"
          value={input}
          onChange={(event) => setInput(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          rows={2}
          placeholder="현재 화면에 대해 물어보세요"
        />
        <div className="react-agent-form-toolbar">
          {/* 컨트롤 셋을 버튼 하나로 접는다. 도크는 384px이라 나란히 두면 두 줄이 되고,
              그 두 줄이 늘 접혀 있으면 폭이 모자란 것이지 안전장치가 아니다. 요약은
              버튼에 그대로 적어 열지 않고도 무엇으로 도는지 읽을 수 있게 한다. */}
          <div className="react-agent-tools" ref={runMenuRef}>
            <button
              type="button"
              className="react-agent-run-trigger"
              ref={runTriggerRef}
              aria-haspopup="dialog"
              aria-expanded={runMenuOpen}
              aria-label={`실행 설정: ${runSummary}`}
              title={runSummary}
              onClick={() => setRunMenuOpen((value) => !value)}
            >
              <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" width="14" height="14">
                <path d="M2.5 5h11M2.5 11h11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                <circle cx="6" cy="5" r="1.9" fill="currentColor" />
                <circle cx="10.5" cy="11" r="1.9" fill="currentColor" />
              </svg>
              <span>{runSummary}</span>
            </button>
            {runMenuOpen && (
              <div className="react-agent-run-menu" role="dialog" aria-label="실행 설정">
                <label>
                  <span>이 대화의 CLI</span>
                  <select
                    value={providerOverride || globalId}
                    onChange={(event) => chooseProvider(event.currentTarget.value === globalId ? "" : event.currentTarget.value)}
                  >
                    {(settings?.adapters || []).map((item) => (
                      <option key={item.id} value={item.id} disabled={item.bridgeSupported === false}>
                        {item.label || item.id}
                      </option>
                    ))}
                  </select>
                  <small>이 대화에만 적용됩니다. 전역 기본은 상단바와 설정에서 바꿉니다.</small>
                </label>
                <label>
                  <span>모델 버전</span>
                  <select value={model} onChange={(event) => persistModel(event.currentTarget.value)}>
                    {modelChoices.length ? modelChoices.map((choice) => (
                      <option key={choice.value} value={choice.value}>{choice.label}</option>
                    )) : <option value="">기본 버전</option>}
                  </select>
                </label>
                <label>
                  <span>노력 단계</span>
                  <select value={effort} onChange={(event) => setEffort(event.currentTarget.value)}>
                    {effortChoices.map((choice) => (
                      <option key={choice.value} value={choice.value}>{choice.label}</option>
                    ))}
                  </select>
                </label>
                <div className="react-agent-run-menu-row">
                  <span>웹 검색</span>
                  <div className="segment" role="group" aria-label="웹 검색">
                    <button type="button" aria-pressed={searchPolicy === "off"} onClick={() => setSearchPolicy("off")}>끔</button>
                    <button type="button" aria-pressed={searchPolicy === "auto"} disabled={adapter?.supportsWebSearch === false} onClick={() => setSearchPolicy("auto")}>자동</button>
                    <button type="button" aria-pressed={searchPolicy === "on"} disabled={adapter?.supportsWebSearch === false} onClick={() => setSearchPolicy("on")}>사용</button>
                  </div>
                  <small>{adapter?.supportsWebSearch === false ? "이 CLI는 웹 검색을 지원하지 않습니다." : "이 대화에만 적용됩니다."}</small>
                </div>
              </div>
            )}
          </div>
          <button className="btn btn--primary btn--sm" type="submit" data-qa="agent-submit" disabled={busy || !input.trim()}>{busy ? "작업 중" : "보내기"}</button>
        </div>
        {overridden && (
          // 전역과 다르면 그 사실을 말한다. 말하지 않으면 설정 탭이 A라고 하는데 대화는
          // B로 도는 상태가 되고, 어느 쪽이 진짜인지 알 수 없다.
          <p className="react-agent-scope-note">
            이 대화만 {adapter?.label || providerOverride}로 돕니다. 전역 기본은 그대로입니다.
          </p>
        )}
        {error && <p className="react-agent-error" role="alert">{error}</p>}
      </form>
    </aside>
  );
}
