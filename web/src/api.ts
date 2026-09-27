export type JobStatus =
  | "queued"
  | "running"
  | "cancel_requested"
  | "committing"
  | "done"
  | "cancelled"
  | "failed"
  | "failed_cancel"
  | "failed_commit"
  | "failed_restart"
  | "failed_commit_recovery";

export type HypothesisFreshness = "fresh" | "due" | "stale" | "unknown";
export type HypothesisCheckpointState = "open" | "due" | "checked" | "invalidated";
export type HypothesisCheckpoint = {
  readonly id: string;
  readonly label: string;
  readonly state: HypothesisCheckpointState;
  readonly dueAt: string | null;
  readonly checkedAt: string | null;
  readonly reasonCode: string;
  readonly evidenceRefs: readonly {
    readonly evidenceId: string;
    readonly source: string;
    readonly title: string;
  }[];
};
export type HypothesisReviewState = {
  readonly ticker: string;
  readonly lastReviewedAt: string | null;
  readonly nextReviewAt: string | null;
  readonly latestDeltaId: string | null;
  readonly freshness: HypothesisFreshness;
  readonly checkpoints: readonly HypothesisCheckpoint[];
  readonly revision: number;
  readonly updatedAt: string | null;
};
export type HypothesisIntelligencePayload = {
  readonly note: {
    readonly id: string;
    readonly ticker: string;
    readonly title: string;
    readonly linkedReports: readonly string[];
  } | null;
  readonly thesis: {
    readonly ticker: string;
    readonly company: string;
    readonly status: string;
    readonly reviewCycle: string;
    readonly conviction: string;
  } | null;
  readonly latestDelta: {
    readonly deltaId: string;
    readonly verdict: string;
    readonly generatedAt: string;
    readonly counterEvidenceCount: number;
    readonly contradictionCount: number;
    readonly uncertaintyCount: number;
  } | null;
  readonly reviewState: HypothesisReviewState;
  readonly checkpointCounts: Readonly<Record<HypothesisCheckpointState, number>>;
  readonly marketStateRef: Readonly<Record<string, unknown>>;
  readonly reasonCodes: readonly string[];
  readonly observedAt: string;
  readonly layer: "hypothesis";
  readonly reuseAsEvidence: false;
};
export type UpdateHypothesisCheckpointRequest = {
  readonly noteId: string;
  readonly checkpointId: string;
  readonly state: HypothesisCheckpointState;
  readonly expectedRevision: number;
};

export type InvestmentMarketDriver = {
  readonly stateId: string;
  readonly label: string;
  readonly momentum: "strengthening" | "stable" | "fading" | "turning" | "conflicted" | "unknown";
};

export type InvestmentDueCheckpoint = {
  readonly id: string;
  readonly label: string;
  readonly dueAt: string | null;
};

export type InvestmentCollectionLink = {
  readonly id: string;
  readonly name: string;
  readonly revision: number;
  readonly health: "active" | "stale" | "empty" | "noisy" | "unknown" | "unavailable";
  readonly matchSources: readonly ("saved_filter" | "external_result")[];
};

export type InvestmentTickerContext = {
  readonly ticker: string;
  readonly source: "portfolio" | "watchlist" | "both";
  readonly stance: "positive" | "watch" | "negative" | "neutral" | "unknown";
  readonly observedAt: string | null;
  readonly reasonCodes: readonly string[];
  readonly marketDrivers: readonly InvestmentMarketDriver[];
  readonly latestThesisVerdict: string;
  readonly dueCheckpoints: readonly InvestmentDueCheckpoint[];
  readonly linkedReports: readonly {
    readonly id: string;
    readonly title: string;
    readonly reportType: "briefing" | "analysis" | "topic" | "unknown";
  }[];
  readonly collections: readonly InvestmentCollectionLink[];
};

export type InvestmentContextSummary = {
  readonly observedAt: string;
  readonly counts: {
    readonly total: number;
    readonly portfolio: number;
    readonly watchlist: number;
    readonly both: number;
    readonly positive: number;
    readonly watch: number;
    readonly negative: number;
    readonly neutral: number;
    readonly unknown: number;
  };
  readonly watchContexts: readonly InvestmentTickerContext[];
};

export type InvestmentContextExplanationJob = {
  readonly id: string;
  readonly status: JobStatus;
  readonly message?: string;
  readonly error?: string;
  readonly result?: {
    readonly reply?: string | null;
    readonly noticeCode?: string | null;
  } | null;
};

export type ThesisReviewJob = {
  readonly id: string;
  readonly status: JobStatus;
  readonly message?: string;
  readonly error?: string;
};
export type ThesisReviewResult = ThesisReviewJob | {
  readonly ok: boolean;
  readonly status: string;
  readonly delta?: Readonly<Record<string, unknown>>;
};

export const MARKET_STATE_POLICIES = ["exclude", "include_current"] as const;
export type MarketStatePolicy = (typeof MARKET_STATE_POLICIES)[number];

export const EVIDENCE_MARKETS = ["US", "KR", "EUROPE", "JP", "GLOBAL", "UNKNOWN"] as const;
export type EvidenceMarket = (typeof EVIDENCE_MARKETS)[number];
export const PRODUCT_MARKETS = ["US", "KR", "EUROPE", "JP"] as const;
export type ProductMarket = (typeof PRODUCT_MARKETS)[number];
export const BRIEFING_REQUEST_SCOPES = ["us", "kr", "europe", "jp", "all"] as const;
export type BriefingRequestScope = (typeof BRIEFING_REQUEST_SCOPES)[number];
export const SAVED_MARKET_SCOPES = ["us", "kr", "europe", "jp", "all", "both"] as const;
export type SavedMarketScope = (typeof SAVED_MARKET_SCOPES)[number];

export const MARKET_STATE_SCOPES = ["AUTO", "GLOBAL", "US", "KR", "EUROPE", "JP"] as const;
export type MarketStateScope = (typeof MARKET_STATE_SCOPES)[number];

/** 시장 이름은 두 가지로 쓴다. 좁은 선택 컨트롤에서는 코드, 읽는 문장에서는 한글. */
export const MARKET_CODE_LABELS: Record<string, string> = {
  us: "US", kr: "KR", europe: "EU", jp: "JP",
  US: "US", KR: "KR", EUROPE: "EU", JP: "JP",
};
export const MARKET_KO_LABELS: Record<string, string> = {
  us: "미국", kr: "한국", europe: "유럽", jp: "일본",
  US: "미국", KR: "한국", EUROPE: "유럽", JP: "일본",
};

/** `auto`는 앱 설정(AI_AGENT_MODE)이 정한다. 리서치마다 고르는 값이 아니다. */
export const EXECUTION_MODES = ["auto", "direct", "cli"] as const;
export type ExecutionMode = (typeof EXECUTION_MODES)[number];

export const CLI_ADAPTERS = ["auto", "codex", "claude", "antigravity"] as const;
export type CliAdapter = (typeof CLI_ADAPTERS)[number];

export const FALLBACK_POLICY = "rules_on_engine_failure" as const;

export type CollectionRef = {
  readonly id: string;
  readonly revision: number;
};

export const SMART_COLLECTION_MARKETS = ["ALL", "US", "KR", "EUROPE", "JP", "GLOBAL", "UNKNOWN"] as const;
export type SmartCollectionMarket = (typeof SMART_COLLECTION_MARKETS)[number];

export type SmartCollectionFields = {
  readonly name: string;
  readonly query: string;
  readonly market: SmartCollectionMarket;
  readonly sources: readonly string[];
  readonly tickers: readonly string[];
  readonly tags: readonly string[];
};

export type SmartCollection = SmartCollectionFields & CollectionRef & {
  readonly createdAt: string;
  readonly updatedAt: string;
};

export type SmartCollectionListEnvelope = {
  readonly schemaVersion: 1;
  readonly storeRevision: number;
  readonly recovered: boolean;
  readonly total: number;
  readonly items: readonly SmartCollection[];
};

export type SmartCollectionMutationEnvelope = {
  readonly storeRevision: number;
  readonly collection: SmartCollection;
};

export type SmartCollectionProviderId = {
  readonly provider: "index" | "rss";
  readonly id: string;
};

export type SmartCollectionPreviewItem = {
  readonly id: string;
  readonly providerIds: readonly SmartCollectionProviderId[];
  readonly title: string;
  readonly url: string;
  readonly source: string;
  readonly markets: readonly string[];
  readonly tickers: readonly string[];
  readonly tags: readonly string[];
  readonly publishedAt: string;
  readonly score: number;
  readonly snippet: string;
  readonly usability: "indexed" | "unindexed_rss";
};

export type SmartCollectionPreview = {
  readonly collectionId: string;
  readonly revision: number;
  readonly total: number;
  readonly limit: number;
  readonly items: readonly SmartCollectionPreviewItem[];
};

export type UpdateSmartCollectionRequest = SmartCollectionFields & { readonly expectedRevision: number };
export type DeleteSmartCollectionRequest = { readonly expectedRevision: number };
export type PreviewSmartCollectionRequest = { readonly expectedRevision: number; readonly limit: number };
export type RefreshSmartCollectionRequest = { readonly expectedRevision: number };

export type SmartCollectionHealth = "active" | "stale" | "empty" | "noisy";

export type SmartCollectionProviderGenerations = {
  readonly index: string | null;
  readonly rss: string | null;
};

export type SmartCollectionLatestPreview = {
  readonly resolvedAt: string;
  readonly providerGenerations: SmartCollectionProviderGenerations;
  readonly inputWatermark: string | null;
  readonly eligibleCount: number;
  readonly resolvedCount: number;
  readonly executionCount: number;
  readonly unusableCount: number;
  readonly truncated: boolean;
};

export type SmartCollectionChangeCounts = {
  readonly added: number;
  readonly removed: number;
  readonly unchanged: number;
};

export type SmartCollectionWorkspaceEnvelope = {
  readonly collection: SmartCollection;
  readonly latestPreview: SmartCollectionLatestPreview | null;
  readonly health: SmartCollectionHealth;
  readonly healthReasonCodes: readonly string[];
  readonly lastRefresh: string | null;
  readonly changeCounts: SmartCollectionChangeCounts;
  readonly recentEvidence: readonly SmartCollectionPreviewItem[];
  readonly current: {
    readonly observedAt: string;
    readonly eligibleCount: number;
    readonly resolvedCount: number;
    readonly unusableCount: number;
    readonly truncated: boolean;
  };
};

export type SmartCollectionChangesEnvelope = {
  readonly collectionId: string;
  readonly revision: number;
  readonly observedAt: string;
  readonly health: SmartCollectionHealth;
  readonly reasonCodes: readonly string[];
  readonly counts: SmartCollectionChangeCounts & { readonly unusable: number };
  readonly addedItems: readonly SmartCollectionPreviewItem[];
  readonly removedIds: readonly string[];
  readonly unchangedIds: readonly string[];
  readonly truncated: boolean;
};

export type SmartCollectionChangeProjection = {
  readonly collectionId: string;
  readonly revision: number;
  readonly observedAt: string;
  readonly health: SmartCollectionHealth;
  readonly addedIds: readonly string[];
  readonly removedIds: readonly string[];
  readonly unchangedIds: readonly string[];
  readonly addedCount: number;
  readonly removedCount: number;
  readonly unchangedCount: number;
  readonly eligibleCount: number;
  readonly resolvedCount: number;
  readonly unusableCount: number;
  readonly truncated: boolean;
  readonly reasonCodes: readonly string[];
};

export type SmartCollectionRefreshEnvelope = {
  readonly collectionId: string;
  readonly revision: number;
  readonly refreshedAt: string;
  readonly latestPreview: SmartCollectionLatestPreview;
  readonly change: SmartCollectionChangeProjection;
  readonly recentEvidence: readonly SmartCollectionPreviewItem[];
};

/** `auto`는 설정된 엔진(API 키 또는 Agent CLI)이 계획을 쓴다. `rules`는 빠른 규칙 계획. */
export type PlannerEngine = "auto" | "rules";

export type PlanRequest = {
  readonly question: string;
  readonly userContext: string;
  readonly plannerEngine: PlannerEngine;
  readonly deepResearch: true;
  readonly customTickers: Readonly<Record<string, string>>;
  readonly marketStatePolicy: MarketStatePolicy;
  readonly marketStateScope: MarketStateScope;
  readonly collectionRef: CollectionRef | null;
};

export type AnalysisAxis = {
  readonly key: string;
  readonly label: string;
  readonly questions: readonly string[];
  readonly requiredData: readonly string[];
  readonly searchQueries: readonly string[];
};

export type DeepSubQuestion = {
  readonly id: string;
  readonly question: string;
  readonly axisKey: string;
  readonly round: 1 | 2;
  readonly searchQueries: readonly string[];
};

export type DeepResearchPlan = {
  readonly enabled: boolean;
  readonly maxRounds: 2;
  readonly subQuestions: readonly DeepSubQuestion[];
  readonly falsificationTriggers: readonly string[];
  readonly requiredOutputs: readonly string[];
};

export type PlannerMode = "rules" | "llm" | "preset" | "edited";

export type TopicPlan = {
  readonly topic: string;
  readonly topicLabel: string;
  readonly reportType: string;
  /** 이 계획을 무엇이 썼는가. 규칙 계획과 LLM 계획은 신뢰도가 다르다. */
  readonly plannerMode?: PlannerMode;
  readonly regions: readonly string[];
  readonly assetClasses: readonly string[];
  readonly timeHorizon: string;
  readonly userIntent: string;
  readonly researchQuestions: readonly string[];
  readonly analysisAxes: readonly AnalysisAxis[];
  readonly requiredMarketData: readonly string[];
  readonly requiredMacroData: readonly string[];
  readonly searchQueries: readonly string[];
  readonly memoryQueries: readonly string[];
  readonly candidateTickers: Readonly<Record<string, string>>;
  readonly expectedSections: readonly string[];
  readonly dataGapsLikely: readonly string[];
  readonly deepResearch: DeepResearchPlan;
};

export type CollectionDefinitionSnapshot = {
  readonly query: string;
  readonly market: string;
  readonly sources: readonly string[];
  readonly tickers: readonly string[];
  readonly tags: readonly string[];
};

export type ApprovedCollectionRef = CollectionRef & {
  readonly definitionHash: string;
  readonly definitionSnapshot: CollectionDefinitionSnapshot;
};

export type DegradedConfirmation = {
  readonly reasonCode: "no_index" | "zero_matches" | "filtered_empty";
  readonly resolutionFingerprint: string;
  readonly confirmed: true;
  readonly confirmedAt: string;
};

export type ApprovedRequest = {
  readonly schemaVersion: 1;
  readonly planRevision: 1;
  readonly asOfDate: string;
  readonly qualityMode: "diagnose_only";
  readonly question: string;
  readonly userContext: string;
  readonly contextLayer: "hypothesis";
  readonly deepResearch: boolean;
  readonly customTickers: Readonly<Record<string, string>>;
  readonly marketStatePolicy: MarketStatePolicy;
  readonly marketStateScope: MarketStateScope;
  readonly collectionRef: ApprovedCollectionRef | null;
  readonly topicPlan: TopicPlan;
  readonly degradedConfirmation: DegradedConfirmation | null;
  readonly planHash: string;
};

export type ApprovalGrant = {
  readonly id: string;
  readonly token: string;
  readonly expiresAt: string;
};

export type ApprovalReference = Pick<ApprovalGrant, "id" | "token">;

/** 승인 전 계획 수정. 서버가 이 항목만 반영하고 나머지는 계속 서버가 소유한다. */
export type AxisEdit = {
  readonly key: string;
  readonly label?: string;
  readonly questions?: readonly string[];
  readonly searchQueries?: readonly string[];
  readonly removed?: boolean;
};

export type PlanEdits = {
  readonly topicLabel?: string;
  readonly reportType?: string;
  readonly researchQuestions?: readonly string[];
  readonly searchQueries?: readonly string[];
  readonly axes?: readonly AxisEdit[];
};

/** 계획을 다시 쓰기. `instruction`이 있으면 지금 계획을 그 요청대로 고친다. */
export type ReplanRequest = {
  readonly approvedRequest: ApprovedRequest;
  readonly approval: ApprovalReference;
  readonly instruction: string;
};

export type RevisePlanRequest = {
  readonly approvedRequest: ApprovedRequest;
  readonly approval: ApprovalReference;
  readonly edits: PlanEdits;
};

export type ProviderGenerations = {
  readonly indexGeneration: string | null;
  readonly rssGeneration: string | null;
};

export type UnusableCandidate = {
  readonly candidateId: string;
  readonly reason: "unindexed_rss";
};

export type ResolutionSnapshot = {
  readonly schemaVersion: 1;
  readonly collectionId: string | null;
  readonly collectionRevision: number | null;
  readonly collectionDefinitionHash: string | null;
  readonly eligibleTotal: number | null;
  readonly candidateCap: number | null;
  readonly truncated: boolean;
  readonly resolvedCandidateIds: readonly string[];
  readonly executionUniverseIds: readonly string[];
  readonly unusableCandidates: readonly UnusableCandidate[];
  readonly selectedEvidenceIds: readonly string[];
  readonly providerGenerations: ProviderGenerations;
  readonly inputWatermark: string | null;
};

export type ZeroEvidence = {
  readonly required: boolean;
  readonly reasonCode: "no_index" | "zero_matches" | "filtered_empty" | null;
  readonly resolutionFingerprint: string | null;
};

export type ResearchPreview = {
  readonly resolution: ResolutionSnapshot;
  readonly resolvedAt: string;
  readonly zeroEvidence: ZeroEvidence;
};

export type PlanPreviewEnvelope = {
  readonly approvedRequest: ApprovedRequest;
  readonly approval: ApprovalGrant;
  readonly preview: ResearchPreview;
};

export type ExecutionRequest = {
  readonly mode: ExecutionMode;
  readonly adapter: CliAdapter;
  readonly fallbackPolicy: typeof FALLBACK_POLICY;
};

export type GenerateApprovedRequest = {
  readonly approvedRequest: ApprovedRequest;
  readonly approval: ApprovalReference;
  readonly execution: ExecutionRequest;
};

export type ConfirmDegradedRequest = {
  readonly approvedRequest: ApprovedRequest;
  readonly approval: ApprovalReference;
  readonly reasonCode: "no_index" | "zero_matches" | "filtered_empty";
  readonly resolutionFingerprint: string;
  readonly confirmed: true;
};

export type WorkLogFilter = "all" | "companion" | "task";
export type WorkLogProposalStatus = "pending" | "applying" | "applied" | "rejected" | "stale" | "conflict" | "failed_apply" | "unavailable";
export type WorkLogEntry = {
  readonly id: string;
  readonly jobId: string;
  readonly category: "companion" | "task";
  readonly kind: "macro_refresh" | "index" | "rss" | "setup" | "agent_bridge" | "agent_cli_install" | "briefing" | "company_analysis" | "topic_report" | "market_state_snapshot";
  readonly taskType: "macro_refresh" | "index" | "rss" | "setup" | "companion" | "briefing" | "company_analysis" | "topic_report" | "personal_overlay" | "thesis_delta" | "market_memory_llm" | "market_state_snapshot" | "market_memory_update" | "quality_repair" | "investment_review";
  readonly labelCode: "macro_refresh" | "index_rebuild" | "rss_import" | "setup" | "agent_chat" | "agent_cli_install" | "agent_task" | "briefing" | "company_analysis" | "topic_report" | "market_state";
  readonly status: JobStatus;
  readonly progress: number;
  readonly messageCode: JobStatus;
  readonly createdAt: string;
  readonly startedAt: string | null;
  readonly updatedAt: string;
  readonly finishedAt: string | null;
  readonly errorCode: "adapter_unavailable" | "adapter_failed" | "validation_failed" | "save_failed" | "cancel_failed" | "restart_interrupted" | "commit_recovery_failed" | "private_cleanup_failed" | "store_unavailable" | "internal_error" | null;
  readonly generationMode: "llm_api" | "llm_cli" | "rules" | "none";
  readonly adapter: "auto" | "codex" | "claude" | "antigravity" | "openai_api" | "gemini_api" | "claude_api" | "rules" | "none";
  readonly requestedMode: "direct" | "cli" | null;
  readonly mode: "collect" | "index" | "install" | "answer" | "generate" | "revise" | "fallback";
  readonly attemptedEngine: "api" | "cli" | "rules" | "none" | null;
  readonly finalEngine: "api" | "cli" | "rules" | "none" | null;
  readonly fallbackReason: "engine_unavailable" | "engine_failed" | "confirmed_zero_evidence" | null;
  readonly artifactTypes: readonly string[];
  readonly artifactCount: number;
  readonly proposalId: string | null;
  readonly proposalStatus: WorkLogProposalStatus | null;
  readonly resultStatus: "done" | "cancelled" | "failed" | null;
  // Agent Dock Stage A (2026-09-15): observed stage timings, numeric-only.
  readonly queueWaitMs: number | null;
  readonly contextMs: number | null;
  readonly cliMs: number | null;
  readonly postprocessMs: number | null;
  readonly totalMs: number | null;
};

export type WorkLogList = {
  readonly schemaVersion: 1;
  readonly storeRevision: number;
  readonly jobsStoreRevision: number;
  readonly retention: { readonly maxEntries: 200; readonly maxDays: 30 };
  readonly total: number;
  readonly entries: readonly WorkLogEntry[];
};
export type WorkLogClearPreview = { readonly previewToken: string; readonly scope: WorkLogFilter; readonly count: number; readonly jobsStoreRevision: number; readonly expiresAt: string };
export type WorkLogClearResponse = { readonly scope: WorkLogFilter; readonly hiddenCount: number; readonly jobsStoreRevision: number; readonly storeRevision: number };
export type WorkLogMigrationPreview = { readonly previewToken: string; readonly legacyJobs: number; readonly migratableJobs: number; readonly collisions: readonly { readonly legacyId: string; readonly reason: "id_collision" }[]; readonly jobsStoreRevision: number; readonly expiresAt: string };
export type WorkLogMigrationResponse = { readonly migratedJobs: number; readonly derivedVisibleEntries: number; readonly keptOriginal: boolean; readonly deletedOriginal: boolean; readonly jobsStoreRevision: number; readonly storeRevision: number };

export type AgentProposalRecord = {
  readonly schemaVersion: 2;
  readonly id: string;
  readonly reportKind: string;
  readonly reportId: string;
  readonly marketScope: "both" | "us" | "kr" | "none";
  readonly status: Exclude<WorkLogProposalStatus, "unavailable">;
  readonly summary: string | null;
  readonly diff: string | null;
  readonly revisedMarkdown: string | null;
  readonly userRequest: string | null;
};

export const WORK_LOG_ENTRY_KEYS = ["id", "jobId", "category", "kind", "taskType", "labelCode", "status", "progress", "messageCode", "createdAt", "startedAt", "updatedAt", "finishedAt", "errorCode", "generationMode", "adapter", "requestedMode", "mode", "attemptedEngine", "finalEngine", "fallbackReason", "artifactTypes", "artifactCount", "proposalId", "proposalStatus", "resultStatus", "queueWaitMs", "contextMs", "cliMs", "postprocessMs", "totalMs"] as const;
const WORK_LOG_LIST_KEYS = ["schemaVersion", "storeRevision", "jobsStoreRevision", "retention", "total", "entries"] as const;
const RETENTION_KEYS = ["maxEntries", "maxDays"] as const;
const WORK_LOG_CATEGORIES = new Set(["companion", "task"]);
const WORK_LOG_KINDS = new Set(["macro_refresh", "index", "rss", "setup", "agent_bridge", "agent_cli_install", "briefing", "company_analysis", "topic_report", "market_state_snapshot"]);
const WORK_LOG_TASK_TYPES = new Set(["macro_refresh", "index", "rss", "setup", "companion", "briefing", "company_analysis", "topic_report", "personal_overlay", "thesis_delta", "market_memory_llm", "market_state_snapshot", "market_memory_update", "quality_repair", "investment_review"]);
const WORK_LOG_LABEL_CODES = new Set(["macro_refresh", "index_rebuild", "rss_import", "setup", "agent_chat", "agent_cli_install", "agent_task", "briefing", "company_analysis", "topic_report", "market_state"]);
const WORK_LOG_STATUSES = new Set(["queued", "running", "cancel_requested", "committing", "done", "cancelled", "failed", "failed_cancel", "failed_commit", "failed_restart", "failed_commit_recovery"]);
const WORK_LOG_GENERATION_MODES = new Set(["llm_api", "llm_cli", "rules", "none"]);
const WORK_LOG_ADAPTERS = new Set(["auto", "codex", "claude", "antigravity", "openai_api", "gemini_api", "claude_api", "rules", "none"]);
const WORK_LOG_REQUESTED_MODES = new Set(["direct", "cli"]);
const WORK_LOG_MODES = new Set(["collect", "index", "install", "answer", "generate", "revise", "fallback"]);
const WORK_LOG_ENGINES = new Set(["api", "cli", "rules", "none"]);
const WORK_LOG_FALLBACK_REASONS = new Set(["engine_unavailable", "engine_failed", "confirmed_zero_evidence"]);
const WORK_LOG_ERROR_CODES = new Set(["adapter_unavailable", "adapter_failed", "validation_failed", "save_failed", "cancel_failed", "restart_interrupted", "commit_recovery_failed", "private_cleanup_failed", "store_unavailable", "internal_error"]);
const WORK_LOG_PROPOSAL_STATUSES = new Set(["pending", "applying", "applied", "rejected", "stale", "conflict", "failed_apply", "unavailable"]);
const WORK_LOG_RESULT_STATUSES = new Set(["done", "cancelled", "failed"]);
const UTC_Z = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/;

function hasExactKeys(value: unknown, keys: readonly string[]): value is Readonly<Record<string, unknown>> {
  if (!isRecord(value)) return false;
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function isWorkLogEntry(value: unknown): value is WorkLogEntry {
  if (!hasExactKeys(value, WORK_LOG_ENTRY_KEYS)) return false;
  const nullableIn = (item: unknown, values: ReadonlySet<string>) => item === null || values.has(item as string);
  const nullableUtc = (item: unknown) => item === null || (typeof item === "string" && UTC_Z.test(item));
  const nullableNonNegativeInt = (item: unknown) => item === null || (Number.isInteger(item) && (item as number) >= 0);
  return typeof value.id === "string" && /^wl_[0-9a-f]{24}$/.test(value.id) && typeof value.jobId === "string"
    && WORK_LOG_CATEGORIES.has(value.category as string) && WORK_LOG_KINDS.has(value.kind as string)
    && WORK_LOG_TASK_TYPES.has(value.taskType as string) && WORK_LOG_LABEL_CODES.has(value.labelCode as string)
    && WORK_LOG_STATUSES.has(value.status as string) && Number.isInteger(value.progress) && (value.progress as number) >= 0 && (value.progress as number) <= 100
    && WORK_LOG_STATUSES.has(value.messageCode as string) && typeof value.createdAt === "string" && UTC_Z.test(value.createdAt)
    && typeof value.updatedAt === "string" && UTC_Z.test(value.updatedAt) && nullableUtc(value.startedAt) && nullableUtc(value.finishedAt)
    && nullableIn(value.errorCode, WORK_LOG_ERROR_CODES) && WORK_LOG_GENERATION_MODES.has(value.generationMode as string)
    && WORK_LOG_ADAPTERS.has(value.adapter as string) && nullableIn(value.requestedMode, WORK_LOG_REQUESTED_MODES)
    && WORK_LOG_MODES.has(value.mode as string) && nullableIn(value.attemptedEngine, WORK_LOG_ENGINES) && nullableIn(value.finalEngine, WORK_LOG_ENGINES)
    && nullableIn(value.fallbackReason, WORK_LOG_FALLBACK_REASONS) && Array.isArray(value.artifactTypes)
    && value.artifactTypes.every((item) => typeof item === "string") && Number.isInteger(value.artifactCount) && (value.artifactCount as number) >= 0
    && (value.proposalId === null || typeof value.proposalId === "string") && nullableIn(value.proposalStatus, WORK_LOG_PROPOSAL_STATUSES)
    && nullableIn(value.resultStatus, WORK_LOG_RESULT_STATUSES)
    && nullableNonNegativeInt(value.queueWaitMs) && nullableNonNegativeInt(value.contextMs) && nullableNonNegativeInt(value.cliMs)
    && nullableNonNegativeInt(value.postprocessMs) && nullableNonNegativeInt(value.totalMs);
}

export function parseWorkLogList(value: unknown): WorkLogList {
  if (!hasExactKeys(value, WORK_LOG_LIST_KEYS) || value.schemaVersion !== 1 || !Number.isInteger(value.storeRevision) || !Number.isInteger(value.jobsStoreRevision) || !Number.isInteger(value.total) || !Array.isArray(value.entries) || !value.entries.every(isWorkLogEntry) || !hasExactKeys(value.retention, RETENTION_KEYS) || value.retention.maxEntries !== 200 || value.retention.maxDays !== 30) {
    throw new Error("work_log_contract_invalid");
  }
  return value as WorkLogList;
}

// 0.6 D3 — 안전한 진단 상세(features/common/diagnostics). jobId 또는 runId로 조회하며
// 본문/프롬프트/스택 원문은 절대 실리지 않는다(서버 schema v1의 closed allow-list).
export type DiagnosticSourceFrame = { readonly moduleCode: string; readonly functionCode: string; readonly line: number };
export type DiagnosticFailure = {
  readonly errorId: string;
  readonly stageId: string | null;
  readonly stageCode: string | null;
  readonly errorCode: string | null;
  readonly reasonCode: string;
  readonly exceptionCode: string;
  readonly frames: readonly DiagnosticSourceFrame[];
  readonly confirmation: "observed" | "inferred" | "unknown";
  readonly nextActionCode: string;
  readonly fingerprint: string;
};
export type DiagnosticEventRecord = {
  readonly seq: number;
  readonly eventId: string;
  readonly stageId: string;
  readonly stageCode: string;
  readonly eventCode: "start" | "end" | "failure" | "skip" | "fallback" | "resume";
  readonly producerEpoch: string;
  readonly at: string;
  readonly durationMs: number | null;
  readonly errorId: string | null;
  readonly count: number;
};
export type DiagnosticTerminalObservation = { readonly observedStatus: string; readonly observedAt: string; readonly processEpoch: string };
export type DiagnosticRecord = {
  readonly schemaVersion: 1;
  readonly runId: string;
  readonly jobId: string | null;
  readonly requestId: string | null;
  readonly parentRunId: string | null;
  readonly retryOfRunId: string | null;
  readonly processEpoch: string;
  readonly featureCode: string;
  readonly routeCode: string;
  readonly taskType: string | null;
  readonly authorityKind: "shared_job" | "automation" | "direct" | "recovery";
  readonly appVersion: string;
  readonly buildId: string | null;
  readonly os: string;
  readonly pythonVersion: string;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly finishedAt: string | null;
  readonly elapsedMs: number | null;
  readonly observedStatus: string;
  readonly attemptedEngine: "api" | "cli" | "rules" | "none" | null;
  readonly finalEngine: "api" | "cli" | "rules" | "none" | null;
  readonly adapter: WorkLogEntry["adapter"] | null;
  readonly fallbackReason: WorkLogEntry["fallbackReason"];
  readonly events: readonly DiagnosticEventRecord[];
  readonly errors: readonly DiagnosticFailure[];
  readonly firstFailure: DiagnosticFailure | null;
  readonly terminalFailure: DiagnosticFailure | null;
  readonly terminalObservation: DiagnosticTerminalObservation | null;
  readonly droppedEvents: number;
  readonly droppedErrors: number;
  readonly droppedIssues: number;
  readonly issueCodes: readonly string[];
  readonly requiredProducerCoverage: "complete" | "partial";
};
export type DiagnosticWarning = { readonly code: string; readonly runId: string };
export type DiagnosticDetail = {
  readonly version: 1;
  readonly runId: string | null;
  readonly diagnosticQuality: "complete" | "partial" | "unavailable" | "legacy_unavailable";
  readonly availabilityReason: "present" | "disabled" | "writer_conflict" | "quota_exceeded" | "read_failed" | "corrupt" | "unsupported_version" | "missing_unknown" | "legacy_no_detail" | "expired";
  readonly authorityState: "matched" | "changed" | "unavailable" | "not_applicable";
  readonly authorityStatus: string | null;
  readonly record: DiagnosticRecord | null;
  readonly warnings: readonly DiagnosticWarning[];
};

const DIAGNOSTIC_QUALITIES = new Set(["complete", "partial", "unavailable", "legacy_unavailable"]);
const DIAGNOSTIC_AVAILABILITY_REASONS = new Set(["present", "disabled", "writer_conflict", "quota_exceeded", "read_failed", "corrupt", "unsupported_version", "missing_unknown", "legacy_no_detail", "expired"]);
const DIAGNOSTIC_AUTHORITY_STATES = new Set(["matched", "changed", "unavailable", "not_applicable"]);
const DIAGNOSTIC_AUTHORITY_KINDS = new Set(["shared_job", "automation", "direct", "recovery"]);
const DIAGNOSTIC_PRODUCER_COVERAGE = new Set(["complete", "partial"]);
const DIAGNOSTIC_CONFIRMATIONS = new Set(["observed", "inferred", "unknown"]);
const DIAGNOSTIC_EVENT_CODES = new Set(["start", "end", "failure", "skip", "fallback", "resume"]);
const DIAGNOSTIC_RECORD_KEYS = ["schemaVersion", "runId", "jobId", "requestId", "parentRunId", "retryOfRunId", "processEpoch", "featureCode", "routeCode", "taskType", "authorityKind", "appVersion", "buildId", "os", "pythonVersion", "createdAt", "updatedAt", "finishedAt", "elapsedMs", "observedStatus", "attemptedEngine", "finalEngine", "adapter", "fallbackReason", "events", "errors", "firstFailure", "terminalFailure", "terminalObservation", "droppedEvents", "droppedErrors", "droppedIssues", "issueCodes", "requiredProducerCoverage"] as const;
const DIAGNOSTIC_FAILURE_KEYS = ["errorId", "stageId", "stageCode", "errorCode", "reasonCode", "exceptionCode", "frames", "confirmation", "nextActionCode", "fingerprint"] as const;
const DIAGNOSTIC_EVENT_KEYS = ["seq", "eventId", "stageId", "stageCode", "eventCode", "producerEpoch", "at", "durationMs", "errorId", "count"] as const;
const DIAGNOSTIC_FRAME_KEYS = ["moduleCode", "functionCode", "line"] as const;
const DIAGNOSTIC_TERMINAL_OBSERVATION_KEYS = ["observedStatus", "observedAt", "processEpoch"] as const;
const DIAGNOSTIC_WARNING_KEYS = ["code", "runId"] as const;
const DIAGNOSTIC_DETAIL_KEYS = ["version", "runId", "diagnosticQuality", "availabilityReason", "authorityState", "authorityStatus", "record", "warnings"] as const;

function isDiagnosticFrame(value: unknown): value is DiagnosticSourceFrame {
  return hasExactKeys(value, DIAGNOSTIC_FRAME_KEYS) && typeof value.moduleCode === "string" && typeof value.functionCode === "string" && Number.isInteger(value.line);
}

function isDiagnosticFailure(value: unknown): value is DiagnosticFailure {
  if (!hasExactKeys(value, DIAGNOSTIC_FAILURE_KEYS)) return false;
  const nullableString = (item: unknown) => item === null || typeof item === "string";
  return typeof value.errorId === "string" && nullableString(value.stageId) && nullableString(value.stageCode) && nullableString(value.errorCode)
    && typeof value.reasonCode === "string" && typeof value.exceptionCode === "string"
    && Array.isArray(value.frames) && value.frames.every(isDiagnosticFrame)
    && DIAGNOSTIC_CONFIRMATIONS.has(value.confirmation as string)
    && typeof value.nextActionCode === "string" && typeof value.fingerprint === "string";
}

function isDiagnosticEvent(value: unknown): value is DiagnosticEventRecord {
  if (!hasExactKeys(value, DIAGNOSTIC_EVENT_KEYS)) return false;
  return Number.isInteger(value.seq) && typeof value.eventId === "string" && typeof value.stageId === "string"
    && typeof value.stageCode === "string" && DIAGNOSTIC_EVENT_CODES.has(value.eventCode as string)
    && typeof value.producerEpoch === "string" && typeof value.at === "string"
    && (value.durationMs === null || Number.isInteger(value.durationMs))
    && (value.errorId === null || typeof value.errorId === "string") && Number.isInteger(value.count);
}

function isDiagnosticRecord(value: unknown): value is DiagnosticRecord {
  if (!hasExactKeys(value, DIAGNOSTIC_RECORD_KEYS)) return false;
  const nullableString = (item: unknown) => item === null || typeof item === "string";
  return value.schemaVersion === 1 && typeof value.runId === "string" && nullableString(value.jobId)
    && nullableString(value.requestId) && nullableString(value.parentRunId) && nullableString(value.retryOfRunId)
    && typeof value.processEpoch === "string" && typeof value.featureCode === "string" && typeof value.routeCode === "string"
    && nullableString(value.taskType) && DIAGNOSTIC_AUTHORITY_KINDS.has(value.authorityKind as string)
    && typeof value.appVersion === "string" && nullableString(value.buildId) && typeof value.os === "string"
    && typeof value.pythonVersion === "string" && typeof value.createdAt === "string" && typeof value.updatedAt === "string"
    && nullableString(value.finishedAt) && (value.elapsedMs === null || Number.isInteger(value.elapsedMs))
    && typeof value.observedStatus === "string" && nullableString(value.attemptedEngine) && nullableString(value.finalEngine)
    && nullableString(value.adapter) && nullableString(value.fallbackReason)
    && Array.isArray(value.events) && value.events.every(isDiagnosticEvent)
    && Array.isArray(value.errors) && value.errors.every(isDiagnosticFailure)
    && (value.firstFailure === null || isDiagnosticFailure(value.firstFailure))
    && (value.terminalFailure === null || isDiagnosticFailure(value.terminalFailure))
    && (value.terminalObservation === null || (hasExactKeys(value.terminalObservation, DIAGNOSTIC_TERMINAL_OBSERVATION_KEYS) && typeof value.terminalObservation.observedStatus === "string" && typeof value.terminalObservation.observedAt === "string" && typeof value.terminalObservation.processEpoch === "string"))
    && Number.isInteger(value.droppedEvents) && Number.isInteger(value.droppedErrors) && Number.isInteger(value.droppedIssues)
    && Array.isArray(value.issueCodes) && value.issueCodes.every((item) => typeof item === "string")
    && DIAGNOSTIC_PRODUCER_COVERAGE.has(value.requiredProducerCoverage as string);
}

export function parseDiagnosticDetail(value: unknown): DiagnosticDetail {
  if (
    !hasExactKeys(value, DIAGNOSTIC_DETAIL_KEYS) || value.version !== 1
    || !DIAGNOSTIC_QUALITIES.has(value.diagnosticQuality as string)
    || !DIAGNOSTIC_AVAILABILITY_REASONS.has(value.availabilityReason as string)
    || !DIAGNOSTIC_AUTHORITY_STATES.has(value.authorityState as string)
    || (value.runId !== null && typeof value.runId !== "string")
    || (value.authorityStatus !== null && typeof value.authorityStatus !== "string")
    || (value.record !== null && !isDiagnosticRecord(value.record))
    || !Array.isArray(value.warnings)
    || !value.warnings.every((item) => hasExactKeys(item, DIAGNOSTIC_WARNING_KEYS) && typeof item.code === "string" && typeof item.runId === "string")
  ) {
    throw new Error("diagnostic_detail_contract_invalid");
  }
  return value as DiagnosticDetail;
}

// 0.6 D3 다음 단계 — 공통 진단 목록(`GET /api/diagnostics/runs`). Work Log 26필드 목록과는
// 별도 계약이다: 실패/대체/기간으로 non-job(자동화·RSS·색인·direct) 실행까지 함께 찾는다.
export type DiagnosticOutcome = "failed" | "succeeded" | "cancelled" | "running" | "unknown";
export type DiagnosticListItem = {
  readonly runId: string;
  readonly createdAt: string;
  readonly finishedAt: string | null;
  readonly observedStatus: string;
  readonly observedOutcome: DiagnosticOutcome;
  /** 현재 권위와 일치가 확인된 결과만. matched가 아니면 null — observedOutcome과 다르다. */
  readonly outcome: DiagnosticOutcome | null;
  readonly featureCode: string;
  readonly routeCode: string;
  readonly authorityKind: "shared_job" | "automation" | "direct" | "recovery";
  readonly authorityState: "matched" | "changed" | "unavailable" | "not_applicable";
  readonly authorityStatus: string | null;
  readonly taskType: string | null;
  readonly jobId: string | null;
  /** 있으면 기존 Work Log 26필드 항목과 같은 실행이다 — 별도 카드로 세지 않는다. */
  readonly workLogId: string | null;
  readonly diagnosticQuality: "complete" | "partial";
  readonly adapter: string | null;
  readonly attemptedEngine: string | null;
  readonly finalEngine: string | null;
  readonly fallbackReason: string | null;
  /** null은 "대체 없었음 증명"이 아니라 "관측 안 됨"이다. */
  readonly fallbackObserved: boolean | null;
  readonly failureReasonCode: string | null;
  readonly failureStageCode: string | null;
};
export type DiagnosticListScan = { readonly entriesScanned: number; readonly runsScanned: number; readonly complete: boolean; readonly deadlineMs: number };
export type DiagnosticListError = { readonly code: string };
export type DiagnosticListResponse = {
  readonly version: 1;
  /** 이 페이지가 고정한 snapshot 기준 시각. "지금"이 아니라 이 목록을 만든 시각이다. */
  readonly snapshotAt: string;
  readonly items: readonly DiagnosticListItem[];
  readonly nextCursor: string | null;
  /** true면 전체 검사가 아직 끝나지 않았다 — 이 페이지에서는 nextCursor가 항상 null이다. */
  readonly truncated: boolean;
  readonly scan: DiagnosticListScan;
  readonly errors: readonly DiagnosticListError[];
};

export type DiagnosticListFilter = {
  readonly outcome?: "all" | DiagnosticOutcome;
  readonly fallback?: "all" | "observed";
  readonly from?: string;
  readonly to?: string;
  readonly limit?: number;
  readonly cursor?: string;
};

export function diagnosticListQuery(filter: DiagnosticListFilter): string {
  const params = new URLSearchParams({ version: "1" });
  if (filter.limit) params.set("limit", String(filter.limit));
  if (filter.outcome && filter.outcome !== "all") params.set("outcome", filter.outcome);
  if (filter.fallback && filter.fallback !== "all") params.set("fallback", filter.fallback);
  if (filter.from) params.set("from", filter.from);
  if (filter.to) params.set("to", filter.to);
  if (filter.cursor) params.set("cursor", filter.cursor);
  return `/api/diagnostics/runs?${params.toString()}`;
}

const DIAGNOSTIC_OUTCOMES = new Set(["failed", "succeeded", "cancelled", "running", "unknown"]);
const DIAGNOSTIC_LIST_ITEM_KEYS = ["runId", "createdAt", "finishedAt", "observedStatus", "observedOutcome", "outcome", "featureCode", "routeCode", "authorityKind", "authorityState", "authorityStatus", "taskType", "jobId", "workLogId", "diagnosticQuality", "adapter", "attemptedEngine", "finalEngine", "fallbackReason", "fallbackObserved", "failureReasonCode", "failureStageCode"] as const;
const DIAGNOSTIC_LIST_SCAN_KEYS = ["entriesScanned", "runsScanned", "complete", "deadlineMs"] as const;
const DIAGNOSTIC_LIST_KEYS = ["version", "snapshotAt", "items", "nextCursor", "truncated", "scan", "errors"] as const;
const DIAGNOSTIC_CODE_PATTERN = /^[a-z0-9][a-z0-9_.-]{0,79}$/;

function isDiagnosticCode(value: unknown): value is string {
  return typeof value === "string" && DIAGNOSTIC_CODE_PATTERN.test(value);
}

function isDiagnosticTimestamp(value: unknown): value is string {
  return typeof value === "string" && UTC_Z.test(value);
}

function isDiagnosticListItem(value: unknown): value is DiagnosticListItem {
  if (!hasExactKeys(value, DIAGNOSTIC_LIST_ITEM_KEYS)) return false;
  const nullableCode = (item: unknown) => item === null || isDiagnosticCode(item);
  const nullableOutcome = (item: unknown) => item === null || (typeof item === "string" && DIAGNOSTIC_OUTCOMES.has(item));
  return validateDiagnosticRunId(value.runId) !== null && isDiagnosticTimestamp(value.createdAt) && (value.finishedAt === null || isDiagnosticTimestamp(value.finishedAt))
    && isDiagnosticCode(value.observedStatus) && DIAGNOSTIC_OUTCOMES.has(value.observedOutcome as string) && nullableOutcome(value.outcome)
    && (value.outcome === null || value.authorityState === "matched")
    && isDiagnosticCode(value.featureCode) && isDiagnosticCode(value.routeCode)
    && DIAGNOSTIC_AUTHORITY_KINDS.has(value.authorityKind as string) && DIAGNOSTIC_AUTHORITY_STATES.has(value.authorityState as string)
    && nullableCode(value.authorityStatus) && nullableCode(value.taskType) && nullableCode(value.jobId) && nullableCode(value.workLogId)
    && DIAGNOSTIC_PRODUCER_COVERAGE.has(value.diagnosticQuality as string)
    && nullableCode(value.adapter) && nullableCode(value.attemptedEngine) && nullableCode(value.finalEngine) && nullableCode(value.fallbackReason)
    && (value.fallbackObserved === null || typeof value.fallbackObserved === "boolean")
    && nullableCode(value.failureReasonCode) && nullableCode(value.failureStageCode);
}

export function parseDiagnosticList(value: unknown): DiagnosticListResponse {
  if (
    !hasExactKeys(value, DIAGNOSTIC_LIST_KEYS) || value.version !== 1 || !isDiagnosticTimestamp(value.snapshotAt)
    || !Array.isArray(value.items) || !value.items.every(isDiagnosticListItem)
    || (value.nextCursor !== null && (typeof value.nextCursor !== "string" || value.nextCursor.length === 0 || value.nextCursor.length > 4096))
    || typeof value.truncated !== "boolean"
    || !hasExactKeys(value.scan, DIAGNOSTIC_LIST_SCAN_KEYS)
    || !Number.isInteger(value.scan.entriesScanned) || (value.scan.entriesScanned as number) < 0
    || !Number.isInteger(value.scan.runsScanned) || (value.scan.runsScanned as number) < 0
    || typeof value.scan.complete !== "boolean" || !Number.isInteger(value.scan.deadlineMs) || (value.scan.deadlineMs as number) < 0
    || value.truncated !== !value.scan.complete || (value.truncated && value.nextCursor !== null)
    || !Array.isArray(value.errors) || !value.errors.every((item) => hasExactKeys(item, ["code"]) && isDiagnosticCode(item.code))
  ) {
    throw new Error("diagnostic_list_contract_invalid");
  }
  return value as DiagnosticListResponse;
}

export type ApiErrorPayload = Readonly<Record<string, unknown>>;

export type TossImportAccount = {
  readonly label: string;
  readonly accountType: string;
  readonly selectable: boolean;
  readonly reason: string;
  readonly selectionId?: string;
};
export type TossImportAccounts = { readonly accounts: readonly TossImportAccount[]; readonly provider: "toss_open_api"; readonly openApiVersion: "1.2.14" };
export type TossImportIssue = { readonly positionKey: string | null; readonly issueCodes: readonly string[] };
export type TossImportBuckets = {
  readonly additions: readonly string[];
  readonly updates: readonly string[];
  readonly preservedManual: readonly string[];
  readonly unchanged: readonly string[];
  readonly conflicts: readonly TossImportIssue[];
  readonly unsupported: readonly TossImportIssue[];
};
export type TossImportDetail = {
  readonly positionKey: string;
  readonly action: "add" | "update" | "unchanged";
  readonly ticker: string;
  readonly currency: string;
  readonly before: { readonly quantity: string; readonly averagePrice: string } | null;
  readonly after: { readonly quantity: string; readonly averagePrice: string };
  readonly delta: { readonly quantity: string; readonly averagePrice: string };
};
export type TossImportPreview = { readonly previewId: string; readonly expectedRevision: number; readonly canConfirm: boolean; readonly status: "ready" | "empty"; readonly buckets: TossImportBuckets; readonly details: readonly TossImportDetail[]; readonly provider: "toss_open_api"; readonly openApiVersion: "1.2.14" };
export type TossImportConfirm<TPortfolio> = { readonly portfolio: TPortfolio; readonly metadataStatus: "ready" | "recovery_pending" | "recovered" | "stale"; readonly idempotent: boolean };

export class ApiRequestError extends Error {
  readonly name = "ApiRequestError";
  readonly requestId: string | null;
  readonly runId: string | null;

  constructor(
    readonly path: string,
    readonly status: number,
    readonly code: string,
    readonly payload: ApiErrorPayload | null,
    requestId: string | null = null,
    runId: string | null = null,
  ) {
    super(`${path} failed: ${status}${code ? ` (${code})` : ""}`);
    this.requestId = validateDiagnosticRequestId(requestId);
    this.runId = validateDiagnosticRunId(runId);
  }
}

/**
 * A response-less fetch failure is deliberately kept separate from HTTP
 * failures.  It must not be presented as proof that the server-side job
 * failed: there was no response to inspect.
 */
export class ApiTransportError extends Error {
  readonly name = "ApiTransportError";

  constructor() {
    super("서버 처리 결과를 확인할 수 없습니다.");
  }
}

/** The HTTP response arrived, but a successful body could not be read. */
export class ApiResponseReadError extends Error {
  readonly name = "ApiResponseReadError";

  constructor() {
    super("서버 처리 결과를 확인할 수 없습니다.");
  }
}

const DIAGNOSTIC_UUID_V4 = "[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}";
const DIAGNOSTIC_REQUEST_ID_PATTERN = new RegExp(`^req_${DIAGNOSTIC_UUID_V4}$`);
const DIAGNOSTIC_RUN_ID_PATTERN = new RegExp(`^run_${DIAGNOSTIC_UUID_V4}$`);

/** Header values are untrusted until they match the backend's exact ID schema. */
export function validateDiagnosticRequestId(value: unknown): string | null {
  return typeof value === "string" && value.length === 40 && DIAGNOSTIC_REQUEST_ID_PATTERN.test(value) ? value : null;
}

/** Header values are untrusted until they match the backend's exact ID schema. */
export function validateDiagnosticRunId(value: unknown): string | null {
  return typeof value === "string" && value.length === 40 && DIAGNOSTIC_RUN_ID_PATTERN.test(value) ? value : null;
}

export function isAbortError(error: unknown, signal?: AbortSignal | null): boolean {
  return Boolean(signal?.aborted || (error instanceof Error && error.name === "AbortError"));
}

export function isActiveJobStatus(status: JobStatus): boolean {
  return status === "queued" || status === "running" || status === "cancel_requested" || status === "committing";
}

export type JsonRequestOptions = {
  readonly signal?: AbortSignal;
};

function isRecord(value: unknown): value is ApiErrorPayload {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const RESPONSE_BODY_UNAVAILABLE = Symbol("response_body_unavailable");

async function parseJson<T>(res: Response, signal?: AbortSignal | null): Promise<T | null | typeof RESPONSE_BODY_UNAVAILABLE> {
  try {
    const payload: unknown = await res.json();
    return payload as T;
  } catch (error) {
    if (isAbortError(error, signal)) throw error;
    // Invalid JSON is still a usable non-JSON HTTP error response. Other
    // failures indicate that an otherwise successful response body vanished.
    if (!(error instanceof SyntaxError)) return RESPONSE_BODY_UNAVAILABLE;
    return null;
  }
}

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch (error) {
    // Keep the caller's abort semantics.  Other failures have no HTTP
    // response and therefore cannot be assigned a server status or run ID.
    if (isAbortError(error, init.signal)) throw error;
    throw new ApiTransportError();
  }
  const parsedPayload = await parseJson<T>(res, init.signal);
  if (parsedPayload === RESPONSE_BODY_UNAVAILABLE && res.ok) throw new ApiResponseReadError();
  const payload = parsedPayload === RESPONSE_BODY_UNAVAILABLE ? null : parsedPayload;
  if (!res.ok) {
    const record = isRecord(payload) ? payload : null;
    const detail = isRecord(record?.detail) ? record.detail : null;
    const rawCode = record?.error ?? detail?.code;
    const code = typeof rawCode === "string" ? rawCode : "request_failed";
    const headers = res.headers;
    throw new ApiRequestError(
      path,
      res.status,
      code,
      record,
      validateDiagnosticRequestId(headers?.get("X-Folio-Request-Id")),
      validateDiagnosticRunId(headers?.get("X-Folio-Run-Id")),
    );
  }
  if (payload === null) throw new Error(`${path} returned an empty response`);
  return payload;
}

export async function getJson<T>(path: string, options: JsonRequestOptions = {}): Promise<T> {
  return requestJson<T>(path, {
    headers: { "Content-Type": "application/json" },
    signal: options.signal,
  });
}

export async function postJson<T>(path: string, body: unknown, options: JsonRequestOptions = {}): Promise<T> {
  return requestJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options.signal,
  });
}

export async function getHypothesisIntelligence(
  noteId: string,
  options: JsonRequestOptions = {},
): Promise<HypothesisIntelligencePayload> {
  return getJson<HypothesisIntelligencePayload>(
    `/api/investment-notes/${encodeURIComponent(noteId)}/intelligence`,
    options,
  );
}

export async function updateHypothesisCheckpoint(
  ticker: string,
  body: UpdateHypothesisCheckpointRequest,
  options: JsonRequestOptions = {},
): Promise<HypothesisIntelligencePayload> {
  return postJson<HypothesisIntelligencePayload>(
    `/api/theses/${encodeURIComponent(ticker)}/review/checkpoints`,
    body,
    options,
  );
}

// --- 0.6 검증 루프 읽기 projection ------------------------------------------
// 화면은 저장된 판정을 읽기만 한다 — 판정·저장은 서버의 규칙 pass가 소유한다.

export type CheckpointEvidenceCopy = {
  date: string;
  title: string;
  /** 내러티브 근거 풀에만 있다. thesis 풀(문서)에는 role 분류가 없다. */
  role?: string;
};

export type TrackedCheckpointView = {
  id: string;
  item: string;
  direction: string;
  status: string;
  statusLabel: string;
  dueBy: string | null;
  keywords?: string[];
  tickers?: string[];
  lastVerdict: {
    verdict: string;
    verdictLabel: string;
    at: string;
    evidence: CheckpointEvidenceCopy[];
  } | null;
  historyCount?: number;
  history?: Array<{ at: string; from: string; to: string; verdict: string; verdictLabel: string }>;
};

export type NarrativeVerificationState = {
  stateId: string;
  stateKey: string;
  label: string;
  status: string;
  momentum: string;
  momentumLabel: string;
  evidenceCounts: { d7: number; d30: number; d90: number };
  lastEvidenceAt: string;
  lastConfirmedAt: string;
  lastChallengedAt: string;
  silence: { days: number | null; level: string; label: string; note: string };
  checkpoints: TrackedCheckpointView[];
  checkpointCounts: Record<string, number>;
  unverifiableCount: number;
  templates: string[];
  timeline: Array<{ at: string; kind: string; from: string; to: string; reason: string; evidenceCount: number }>;
};

export type NarrativeVerificationPayload = {
  asOf: string;
  states: NarrativeVerificationState[];
  summary: {
    stateCount: number;
    checkpointCount: number;
    confirmed: number;
    challenged: number;
    cooling: number;
    unverifiable: number;
  };
};

export type ThesisWorkspacePayload = {
  ticker: string;
  hasThesis: boolean;
  thesis: {
    ticker: string;
    company: string;
    coreThesis: string;
    keyAssumptions: string[];
    supportingSignals: string[];
    weakeningSignals: string[];
    falsificationTriggers: string[];
    keyMetrics: string[];
    linkedRegimes: string[];
    reviewCycle: string;
    conviction: string;
    status: string;
    lastReviewedAt: string;
    notePath: string;
  } | null;
  ownership: {
    source: string;
    appOwned: boolean;
    vaultNote: { title: string; relPath: string } | null;
    syncPaused: boolean;
    message: string;
  } | null;
  latestDelta: {
    deltaId: string;
    verdict: string;
    verdictLabel: string;
    generatedAt: string;
    period: string;
    summary: string;
    supportingEvidence: Array<{ title: string; source: string; date: string; reason: string }>;
    counterEvidence: Array<{ title: string; source: string; date: string; reason: string }>;
    contradictions: string[];
    uncertainties: string[];
  } | null;
  checkpoints: {
    structured: TrackedCheckpointView[];
    templates: string[];
    unverifiableCount: number;
    counts: Record<string, number>;
  };
  regimeAlerts: Array<{
    stateId: string;
    stateKey: string;
    label: string;
    status: string;
    momentum: string;
    reasons: Array<{ kind: string; detail: string }>;
  }>;
  deltaHistory: Array<{ deltaId: string; verdict: string; verdictLabel: string; generatedAt: string; summary: string }>;
  layer: string;
  reuseAsEvidence: boolean;
};

export type SaveThesisRequest = {
  ticker: string;
  company?: string;
  coreThesis?: string;
  keyAssumptions?: string[];
  falsificationTriggers?: string[];
  reviewCycle?: string;
  conviction?: string;
};

export async function saveThesis(
  body: SaveThesisRequest,
  options: JsonRequestOptions = {},
): Promise<{ ok: boolean; thesis: ThesisWorkspacePayload["thesis"] }> {
  return postJson("/api/theses", body, options);
}

export async function getNarrativeVerification(
  options: JsonRequestOptions = {},
): Promise<NarrativeVerificationPayload> {
  return getJson<NarrativeVerificationPayload>("/api/memory/verification", options);
}

export async function getThesisWorkspace(
  ticker: string,
  options: JsonRequestOptions = {},
): Promise<ThesisWorkspacePayload> {
  return getJson<ThesisWorkspacePayload>(`/api/theses/${encodeURIComponent(ticker)}/workspace`, options);
}

export type PromoteNoteToThesisResult = {
  ok: boolean;
  noteId: string;
  /** created = 빈자리를 채웠다 · updated = 명시적 갱신 · skipped_* = 아무것도 하지 않았다 */
  status: string;
  ticker: string;
};

export async function promoteNoteToThesis(
  noteId: string,
  overwrite = false,
  options: JsonRequestOptions = {},
): Promise<PromoteNoteToThesisResult> {
  return postJson<PromoteNoteToThesisResult>(
    `/api/investment-notes/${encodeURIComponent(noteId)}/thesis`,
    { overwrite },
    options,
  );
}

export async function runThesisReview(
  ticker: string,
  options: JsonRequestOptions = {},
): Promise<ThesisReviewResult> {
  return postJson<ThesisReviewResult>(
    `/api/theses/${encodeURIComponent(ticker)}/delta`,
    { period: "90d" },
    options,
  );
}

export async function putJson<T>(path: string, body: unknown, options: JsonRequestOptions = {}): Promise<T> {
  return requestJson<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options.signal,
  });
}

export async function deleteJson<T>(path: string, body: unknown, options: JsonRequestOptions = {}): Promise<T> {
  return requestJson<T>(path, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: options.signal,
  });
}
