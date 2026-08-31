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
  readonly kind: "index" | "rss" | "setup" | "agent_bridge" | "agent_cli_install" | "briefing" | "company_analysis" | "topic_report" | "market_state_snapshot";
  readonly taskType: "index" | "rss" | "setup" | "companion" | "briefing" | "company_analysis" | "topic_report" | "personal_overlay" | "thesis_delta" | "market_memory_llm" | "market_state_snapshot" | "market_memory_update" | "quality_repair" | "investment_review";
  readonly labelCode: "index_rebuild" | "rss_import" | "setup" | "agent_chat" | "agent_cli_install" | "agent_task" | "briefing" | "company_analysis" | "topic_report" | "market_state";
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

export const WORK_LOG_ENTRY_KEYS = ["id", "jobId", "category", "kind", "taskType", "labelCode", "status", "progress", "messageCode", "createdAt", "startedAt", "updatedAt", "finishedAt", "errorCode", "generationMode", "adapter", "requestedMode", "mode", "attemptedEngine", "finalEngine", "fallbackReason", "artifactTypes", "artifactCount", "proposalId", "proposalStatus", "resultStatus"] as const;
const WORK_LOG_LIST_KEYS = ["schemaVersion", "storeRevision", "jobsStoreRevision", "retention", "total", "entries"] as const;
const RETENTION_KEYS = ["maxEntries", "maxDays"] as const;
const WORK_LOG_CATEGORIES = new Set(["companion", "task"]);
const WORK_LOG_KINDS = new Set(["index", "rss", "setup", "agent_bridge", "agent_cli_install", "briefing", "company_analysis", "topic_report", "market_state_snapshot"]);
const WORK_LOG_TASK_TYPES = new Set(["index", "rss", "setup", "companion", "briefing", "company_analysis", "topic_report", "personal_overlay", "thesis_delta", "market_memory_llm", "market_state_snapshot", "market_memory_update", "quality_repair", "investment_review"]);
const WORK_LOG_LABEL_CODES = new Set(["index_rebuild", "rss_import", "setup", "agent_chat", "agent_cli_install", "agent_task", "briefing", "company_analysis", "topic_report", "market_state"]);
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
    && nullableIn(value.resultStatus, WORK_LOG_RESULT_STATUSES);
}

export function parseWorkLogList(value: unknown): WorkLogList {
  if (!hasExactKeys(value, WORK_LOG_LIST_KEYS) || value.schemaVersion !== 1 || !Number.isInteger(value.storeRevision) || !Number.isInteger(value.jobsStoreRevision) || !Number.isInteger(value.total) || !Array.isArray(value.entries) || !value.entries.every(isWorkLogEntry) || !hasExactKeys(value.retention, RETENTION_KEYS) || value.retention.maxEntries !== 200 || value.retention.maxDays !== 30) {
    throw new Error("work_log_contract_invalid");
  }
  return value as WorkLogList;
}

export type ApiErrorPayload = Readonly<Record<string, unknown>>;

export class ApiRequestError extends Error {
  readonly name = "ApiRequestError";

  constructor(
    readonly path: string,
    readonly status: number,
    readonly code: string,
    readonly payload: ApiErrorPayload | null,
  ) {
    super(`${path} failed: ${status}${code ? ` (${code})` : ""}`);
  }
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

async function parseJson<T>(res: Response): Promise<T | null> {
  try {
    const payload: unknown = await res.json();
    return payload as T;
  } catch {
    return null;
  }
}

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  const payload = await parseJson<T>(res);
  if (!res.ok) {
    const record = isRecord(payload) ? payload : null;
    const rawCode = record?.error;
    const code = typeof rawCode === "string" ? rawCode : "request_failed";
    throw new ApiRequestError(path, res.status, code, record);
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

export type PromoteNoteToThesisResult = {
  ok: boolean;
  noteId: string;
  /** created = 빈자리를 채웠다 · updated = 명시적 갱신 · skipped_* = 아무것도 하지 않았다 */
  status: string;
  ticker: string;
};

export async function promoteNoteToThesis(
  noteId: string,
  options: JsonRequestOptions = {},
): Promise<PromoteNoteToThesisResult> {
  return postJson<PromoteNoteToThesisResult>(
    `/api/investment-notes/${encodeURIComponent(noteId)}/thesis`,
    {},
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
