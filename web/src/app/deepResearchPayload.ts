type UnknownRecord = Record<string, unknown>;

export type TopicPlanPayload = {
  readonly topic: string;
  readonly reportType: string;
  readonly userIntent: string;
  readonly researchQuestions: readonly string[];
  readonly analysisAxes: readonly { readonly key: string; readonly label: string; readonly questions: readonly string[] }[];
  readonly searchQueries: readonly string[];
  readonly expectedSections: readonly string[];
  readonly dataGapsLikely: readonly string[];
  readonly falsificationTriggers: readonly string[];
};

export type EvidenceCoveragePayload = {
  readonly totalDocs: number;
  readonly roleCounts: Readonly<Record<string, number>>;
  readonly axisCoverage: Readonly<Record<string, { readonly label: string; readonly count: number; readonly level: string }>>;
  readonly questionCoverage: Readonly<Record<string, { readonly question: string; readonly count: number; readonly level: string }>>;
  readonly dataGaps: readonly string[];
  readonly memoryCount: number;
};

export type EvidenceItemPayload = {
  readonly id: string;
  readonly title: string;
  readonly source: string;
  readonly date: string;
  readonly role: string;
  readonly axis: string;
  readonly confidence: string;
  readonly url: string;
};

export type SourceLedgerItemPayload = {
  readonly sourceId: string;
  readonly title: string;
  readonly source: string;
  readonly date: string;
  readonly evidenceRole: string;
  readonly reliability: string;
  readonly usedInSections: readonly string[];
  readonly url: string;
  readonly artifactType: string;
  readonly artifactId: string;
  readonly path: string;
  readonly axisKey: string;
  readonly researchQuestionId: string;
  readonly researchRound: number | null;
};

export type DataGapPayload = {
  readonly id: string;
  readonly severity: string;
  readonly description: string;
  readonly suggestedAction: string;
  readonly resolved: boolean;
};

export type QualityPayload = {
  readonly score: number | null;
  readonly grade: string;
  readonly status: string;
  readonly warnings: readonly string[];
  readonly suggestedFixes: readonly string[];
};

export type ResearchResolutionPayload = {
  readonly schemaVersion: number | null;
  readonly collectionId: string;
  readonly collectionRevision: number | null;
  readonly collectionDefinitionHash: string;
  readonly eligibleTotal: number | null;
  readonly candidateCap: number | null;
  readonly resolvedCandidateIds: readonly string[];
  readonly executionUniverseIds: readonly string[];
  readonly selectedEvidenceIds: readonly string[];
  readonly unusableCandidates: readonly { readonly candidateId: string; readonly reason: string }[];
  readonly truncated: boolean;
  readonly resolvedAt: string;
  readonly zeroEvidenceRequired: boolean;
  readonly zeroEvidenceReason: string;
  readonly resolutionFingerprint: string;
  readonly providerGenerations: { readonly indexGeneration: string | null; readonly rssGeneration: string | null };
  readonly inputWatermark: string | null;
};

export type MarketStateRefPayload = {
  readonly snapshotId: string | null; readonly sourceKind: string; readonly scope: string; readonly asOf: string | null;
  readonly status: string; readonly freshnessReason: string; readonly inputWatermark: string | null;
  readonly relevantEvidenceWatermark: string | null; readonly invalidWatermarkRows: number;
  readonly resolvedAt: string; readonly layer: "source-grounded";
};
export type MarketStateResolutionPayload = {
  readonly policy: string; readonly requestedScope: string; readonly resolvedScope: string;
  readonly injected: boolean; readonly reason: string; readonly ref?: MarketStateRefPayload;
};
export type ExecutionProvenancePayload = {
  readonly schemaVersion: number | null; readonly approvalId: string; readonly planHash: string;
  readonly requestedMode: string; readonly attemptedEngine: string; readonly finalEngine: string;
  readonly fallbackReason: string | null; readonly adapter: string; readonly executedAt: string;
};

export type RevisionPayload = { readonly number: number | null; readonly hash: string };

export type DeepResearchLocation =
  | { readonly kind: "list"; readonly id: ""; readonly malformed: false }
  | { readonly kind: "report"; readonly id: string; readonly malformed: boolean }
  | { readonly kind: "collection"; readonly id: string; readonly malformed: boolean };

const COLLECTION_ROUTE_ID = /^sc_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export function deepResearchCollectionHash(collectionId: string): string {
  return `#/deep-research/collections/${encodeURIComponent(collectionId)}`;
}

export function deepResearchReportHash(reportId: string): string {
  return `#/deep-research/${encodeURIComponent(reportId)}`;
}

export function parseDeepResearchLocation(hash: string): DeepResearchLocation {
  const route = hash.replace(/^#\/?/, "");
  if (route === "deep-research" || route === "deep-research/") {
    return { kind: "list", id: "", malformed: false };
  }
  const collection = route.match(/^deep-research\/collections\/(.+)$/);
  if (collection) {
    try {
      const id = decodeURIComponent(collection[1]);
      return COLLECTION_ROUTE_ID.test(id)
        ? { kind: "collection", id, malformed: false }
        : { kind: "collection", id: "", malformed: true };
    } catch {
      return { kind: "collection", id: "", malformed: true };
    }
  }
  const report = route.match(/^deep-research\/(.+)$/);
  if (!report) return { kind: "list", id: "", malformed: false };
  try {
    const id = decodeURIComponent(report[1]);
    return id
      ? { kind: "report", id, malformed: false }
      : { kind: "report", id: "", malformed: true };
  } catch {
    return { kind: "report", id: "", malformed: true };
  }
}

export type PersonalOverlayPayload = {
  readonly markdown: string;
  readonly stale: boolean;
  readonly staleReason: string;
  readonly canonicalRevision: RevisionPayload | null;
  readonly linkedNotes: readonly { readonly title: string; readonly type: string; readonly ticker: string }[];
  readonly counterEvidence: readonly string[];
  readonly contradictions: readonly string[];
  readonly uncertainties: readonly string[];
  readonly personalQuestions: readonly string[];
  readonly revisionState: "current" | "stale" | "legacy_unknown";
};

export type TopicReport = {
  readonly id: string;
  readonly topicKey: string;
  readonly topicLabel: string;
  readonly date: string;
  readonly generatedAt: string;
  readonly mode: string;
  readonly saved: boolean;
  readonly markdown: string;
  readonly docCount: number;
  readonly memoryCount: number;
  readonly userContext: string | boolean;
  readonly generation: { readonly message: string; readonly mode: string; readonly generatedAt: string } | null;
  readonly sources: readonly { readonly source: string; readonly date: string; readonly title: string; readonly url: string; readonly path: string }[];
  readonly personalOverlay: PersonalOverlayPayload | null;
  readonly topicPlan: TopicPlanPayload | null;
  readonly evidencePackSummary: EvidenceCoveragePayload | null;
  readonly evidenceItems: readonly EvidenceItemPayload[];
  readonly sourceLedger: readonly SourceLedgerItemPayload[];
  readonly dataGaps: readonly DataGapPayload[];
  readonly quality: QualityPayload | null;
  readonly researchTraceSummary: {
    readonly usedSourceCount: number;
    readonly latestSourceDate: string;
    readonly challengingSourceCount: number;
    readonly unresolvedDataGapCount: number;
    readonly cautionReasons: readonly string[];
  } | null;
  readonly researchResolution: ResearchResolutionPayload | null;
  readonly marketStateResolution: MarketStateResolutionPayload | undefined;
  readonly qualityPreflight: UnknownRecord | null;
  readonly executionProvenance: ExecutionProvenancePayload | null;
  readonly checkpoints: readonly UnknownRecord[];
  readonly marketTape: UnknownRecord | null;
  readonly canonicalRevision: RevisionPayload | null;
  readonly contractWarnings: readonly string[];
};

export type TopicReportSummary =
  Pick<TopicReport, "id" | "topicKey" | "topicLabel" | "date" | "generatedAt" | "mode" | "saved">
  // 어느 모델이 썼는지. 목록 배지가 "LLM"만 적으면 보고서를 구분할 수 없다.
  & { engine?: string; engineDetail?: string };

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function safeExternalUrl(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "";
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
  } catch {
    return "";
  }
}

function normalizedMarker(value: unknown): string {
  return stringValue(value).trim().toLowerCase().replace(/[\s_-]+/g, "");
}

function revision(value: unknown): RevisionPayload | null {
  if (!isRecord(value)) return null;
  const number = numberValue(value.number);
  const hash = stringValue(value.hash);
  return number !== null || hash ? { number, hash } : null;
}

function recordNumbers(value: unknown): Record<string, number> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(Object.entries(value).filter((entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1])));
}

function coverageRows(value: unknown, question = false): Record<string, { label: string; question: string; count: number; level: string }> {
  if (!isRecord(value)) return {};
  const rows: Record<string, { label: string; question: string; count: number; level: string }> = {};
  for (const [key, row] of Object.entries(value)) {
    if (!isRecord(row)) continue;
    rows[key] = { label: stringValue(row.label), question: question ? stringValue(row.question) : "", count: numberValue(row.count) ?? 0, level: stringValue(row.level) };
  }
  return rows;
}

function parseTopicPlan(value: unknown): TopicPlanPayload | null {
  if (!isRecord(value)) return null;
  const deep = isRecord(value.deepResearch) ? value.deepResearch : {};
  const axes = Array.isArray(value.analysisAxes) ? value.analysisAxes.filter(isRecord).map((row) => ({
    key: stringValue(row.key), label: stringValue(row.label), questions: strings(row.questions),
  })).filter((row) => row.key || row.label) : [];
  return {
    topic: stringValue(value.topic), reportType: stringValue(value.reportType), userIntent: stringValue(value.userIntent),
    researchQuestions: strings(value.researchQuestions), analysisAxes: axes, searchQueries: strings(value.searchQueries),
    expectedSections: strings(value.expectedSections), dataGapsLikely: strings(value.dataGapsLikely),
    falsificationTriggers: strings(deep.falsificationTriggers),
  };
}

function parseCoverage(value: unknown): EvidenceCoveragePayload | null {
  if (!isRecord(value)) return null;
  const axes = coverageRows(value.axisCoverage);
  const questions = coverageRows(value.questionCoverage, true);
  return {
    totalDocs: numberValue(value.totalDocs) ?? 0, roleCounts: recordNumbers(value.roleCounts),
    axisCoverage: Object.fromEntries(Object.entries(axes).map(([key, row]) => [key, { label: row.label, count: row.count, level: row.level }])),
    questionCoverage: Object.fromEntries(Object.entries(questions).map(([key, row]) => [key, { question: row.question, count: row.count, level: row.level }])),
    dataGaps: strings(value.dataGaps), memoryCount: numberValue(value.memoryCount) ?? 0,
  };
}

function parseEvidence(value: unknown): EvidenceItemPayload[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((row) => ({
    id: stringValue(row.id), title: stringValue(row.title), source: stringValue(row.source), date: stringValue(row.date),
    role: stringValue(row.role), axis: stringValue(row.axis), confidence: stringValue(row.confidence), url: safeExternalUrl(row.url),
  })).filter((row) => Boolean(row.id && (row.title || row.source)));
}

function parseLedger(value: unknown): SourceLedgerItemPayload[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).filter((row) => {
    const artifactType = stringValue(row.artifactType).toLowerCase();
    const rowType = stringValue(row.type).toLowerCase();
    const evidenceRole = stringValue(row.evidenceRole).toLowerCase();
    const sourceLayer = stringValue(row.sourceLayer ?? row.source_layer).toLowerCase();
    const generatedBy = normalizedMarker(row.generatedBy ?? row.generated_by);
    return artifactType !== "user_note" && rowType !== "user_note" && evidenceRole !== "hypothesis"
      && sourceLayer !== "hypothesis" && sourceLayer !== "primary_processed" && generatedBy !== "folioos";
  }).map((row) => ({
    sourceId: stringValue(row.sourceId), title: stringValue(row.title), source: stringValue(row.source), date: stringValue(row.date),
    evidenceRole: stringValue(row.evidenceRole), reliability: stringValue(row.reliability), usedInSections: strings(row.usedInSections),
    url: safeExternalUrl(row.url), artifactType: stringValue(row.artifactType), artifactId: stringValue(row.artifactId),
    path: stringValue(row.path), axisKey: stringValue(row.axisKey), researchQuestionId: stringValue(row.researchQuestionId),
    researchRound: numberValue(row.researchRound),
  })).filter((row) => Boolean(row.sourceId && (row.title || row.source)));
}

function parseGaps(value: unknown): DataGapPayload[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((row) => ({
    id: stringValue(row.id), severity: stringValue(row.severity), description: stringValue(row.description),
    suggestedAction: stringValue(row.suggestedAction), resolved: row.resolved === true,
  })).filter((row) => Boolean(row.id && row.description));
}

function parseQuality(value: unknown): QualityPayload | null {
  if (!isRecord(value)) return null;
  if (!["score", "grade", "status", "warnings", "suggestedFixes"].some((key) => key in value)) return null;
  return {
    score: numberValue(value.score), grade: stringValue(value.grade), status: stringValue(value.status),
    warnings: strings(value.warnings), suggestedFixes: strings(value.suggestedFixes),
  };
}

function parseResearchTrace(value: unknown): TopicReport["researchTraceSummary"] {
  if (!isRecord(value)) return null;
  return {
    usedSourceCount: numberValue(value.usedSourceCount) ?? 0,
    latestSourceDate: stringValue(value.latestSourceDate),
    challengingSourceCount: numberValue(value.challengingSourceCount) ?? 0,
    unresolvedDataGapCount: numberValue(value.unresolvedDataGapCount) ?? 0,
    cautionReasons: strings(value.cautionReasons).slice(0, 2),
  };
}

function deriveResearchTrace(sourceLedger: readonly SourceLedgerItemPayload[], dataGaps: readonly DataGapPayload[]): TopicReport["researchTraceSummary"] {
  if (!sourceLedger.length && !dataGaps.length) return null;
  const used = sourceLedger.filter((row) => row.usedInSections.length > 0);
  // 숨은 출처 태그는 딥 모드 계약이다. 태그가 하나도 없는 보고서(일반·과거 보고서)에
  // 요약을 만들면 근거 수십 건을 쓴 보고서가 "사용 근거 0건"으로 표시된다 — 그런
  // 보고서는 요약 없음(empty state)이 정답이다.
  if (!used.length) return null;
  const dates = used.map((row) => row.date.slice(0, 10)).filter(Boolean).sort();
  const unresolved = dataGaps.filter((row) => !row.resolved);
  return {
    usedSourceCount: used.length,
    latestSourceDate: dates.length ? dates[dates.length - 1] : "",
    challengingSourceCount: used.filter((row) => row.evidenceRole === "challenging").length,
    unresolvedDataGapCount: unresolved.length,
    cautionReasons: unresolved.map((row) => row.description).filter(Boolean).slice(0, 2),
  };
}

function parseResolution(value: unknown): ResearchResolutionPayload | null {
  if (!isRecord(value) || !isRecord(value.resolution)) return null;
  const row = value.resolution;
  const zero = isRecord(value.zeroEvidence) ? value.zeroEvidence : {};
  const providers = isRecord(row.providerGenerations) ? row.providerGenerations : {};
  const unusable = Array.isArray(row.unusableCandidates) ? row.unusableCandidates.filter(isRecord).map((item) => ({
    candidateId: stringValue(item.candidateId), reason: stringValue(item.reason),
  })).filter((item) => item.candidateId) : [];
  return {
    schemaVersion: numberValue(row.schemaVersion), collectionId: stringValue(row.collectionId), collectionRevision: numberValue(row.collectionRevision),
    collectionDefinitionHash: stringValue(row.collectionDefinitionHash), eligibleTotal: numberValue(row.eligibleTotal), candidateCap: numberValue(row.candidateCap),
    resolvedCandidateIds: strings(row.resolvedCandidateIds), executionUniverseIds: strings(row.executionUniverseIds), selectedEvidenceIds: strings(row.selectedEvidenceIds),
    unusableCandidates: unusable, truncated: row.truncated === true, resolvedAt: stringValue(value.resolvedAt),
    zeroEvidenceRequired: zero.required === true, zeroEvidenceReason: stringValue(zero.reasonCode), resolutionFingerprint: stringValue(zero.resolutionFingerprint),
    providerGenerations: { indexGeneration: typeof providers.indexGeneration === "string" ? providers.indexGeneration : null, rssGeneration: typeof providers.rssGeneration === "string" ? providers.rssGeneration : null },
    inputWatermark: typeof row.inputWatermark === "string" ? row.inputWatermark : null,
  };
}

function nullableString(value: unknown): string | null | undefined {
  return value === null ? null : typeof value === "string" ? value : undefined;
}

function parseMarketState(value: unknown): MarketStateResolutionPayload | undefined {
  if (!isRecord(value) || typeof value.reason !== "string" || typeof value.injected !== "boolean") return undefined;
  const base = { policy: stringValue(value.policy), requestedScope: stringValue(value.requestedScope), resolvedScope: stringValue(value.resolvedScope), injected: value.injected, reason: value.reason };
  if (!isRecord(value.ref)) return value.injected ? undefined : base;
  const ref = value.ref;
  const snapshotId = nullableString(ref.snapshotId), asOf = nullableString(ref.asOf), inputWatermark = nullableString(ref.inputWatermark), relevantEvidenceWatermark = nullableString(ref.relevantEvidenceWatermark);
  if (snapshotId === undefined || asOf === undefined || inputWatermark === undefined || relevantEvidenceWatermark === undefined
    || typeof ref.sourceKind !== "string" || typeof ref.scope !== "string" || typeof ref.status !== "string"
    || typeof ref.freshnessReason !== "string" || typeof ref.invalidWatermarkRows !== "number" || !Number.isFinite(ref.invalidWatermarkRows)
    || typeof ref.resolvedAt !== "string" || ref.layer !== "source-grounded") return undefined;
  return { ...base, ref: { snapshotId, sourceKind: ref.sourceKind, scope: ref.scope, asOf, status: ref.status, freshnessReason: ref.freshnessReason, inputWatermark, relevantEvidenceWatermark, invalidWatermarkRows: ref.invalidWatermarkRows, resolvedAt: ref.resolvedAt, layer: "source-grounded" } };
}

function parseExecution(value: unknown): ExecutionProvenancePayload | null {
  if (!isRecord(value) || typeof value.approvalId !== "string" || typeof value.executedAt !== "string") return null;
  return { schemaVersion: numberValue(value.schemaVersion), approvalId: value.approvalId, planHash: stringValue(value.planHash), requestedMode: stringValue(value.requestedMode), attemptedEngine: stringValue(value.attemptedEngine), finalEngine: stringValue(value.finalEngine), fallbackReason: value.fallbackReason === null ? null : stringValue(value.fallbackReason), adapter: stringValue(value.adapter), executedAt: value.executedAt };
}

export function parsePersonalOverlayPayload(value: unknown, canonicalValue: unknown): PersonalOverlayPayload | null {
  if (!isRecord(value)) return null;
  const canonical = revision(canonicalValue);
  if (!["markdown", "stale", "staleReason", "canonicalRevision", "linkedNotes", "counterEvidence", "contradictions", "uncertainties", "personalQuestions"].some((key) => key in value)) return null;
  const overlayRevision = revision(value.canonicalRevision);
  const mismatch = Boolean(canonical && overlayRevision && (
    (canonical.number !== null && overlayRevision.number !== null && canonical.number !== overlayRevision.number)
    || (canonical.hash && overlayRevision.hash && canonical.hash !== overlayRevision.hash)
  ));
  const notes = Array.isArray(value.linkedNotes) ? value.linkedNotes.filter(isRecord).map((row) => ({
    title: stringValue(row.title), type: stringValue(row.type), ticker: stringValue(row.ticker),
  })).filter((row) => row.title) : [];
  const stale = value.stale === true || value.staleReason === "canonical_revision_changed" || mismatch;
  return {
    markdown: stringValue(value.markdown),
    stale,
    staleReason: stringValue(value.staleReason), canonicalRevision: overlayRevision, linkedNotes: notes,
    counterEvidence: strings(value.counterEvidence), contradictions: strings(value.contradictions),
    uncertainties: strings(value.uncertainties), personalQuestions: strings(value.personalQuestions),
    revisionState: stale ? "stale" : overlayRevision && canonical ? "current" : "legacy_unknown",
  };
}

function malformedOptional(value: UnknownRecord, key: string, expected: "array" | "record"): boolean {
  if (!(key in value) || value[key] === undefined) return false;
  return expected === "array" ? !Array.isArray(value[key]) : !isRecord(value[key]);
}

export function parseTopicReportPayload(value: unknown): TopicReport {
  if (!isRecord(value) || typeof value.id !== "string" || !value.id.trim() || typeof value.markdown !== "string") {
    throw new Error("topic_report_contract_invalid");
  }
  const warnings: string[] = [];
  for (const key of ["evidenceItems", "sourceLedger", "dataGaps", "checkpoints"] as const) {
    if (malformedOptional(value, key, "array")) warnings.push(key + "_invalid");
  }
  for (const key of ["topicPlan", "evidencePackSummary", "quality", "researchTraceSummary", "researchResolution", "personalOverlay", "qualityPreflight", "executionProvenance", "marketTape", "marketStateResolution"] as const) {
    if (malformedOptional(value, key, "record")) warnings.push(key + "_invalid");
  }
  const evidenceItems = parseEvidence(value.evidenceItems);
  const sourceLedger = parseLedger(value.sourceLedger);
  const dataGaps = parseGaps(value.dataGaps);
  const topicPlan = parseTopicPlan(value.topicPlan);
  const evidencePackSummary = parseCoverage(value.evidencePackSummary);
  const quality = parseQuality(value.quality);
  const researchTraceSummary = parseResearchTrace(value.researchTraceSummary) ?? deriveResearchTrace(sourceLedger, dataGaps);
  const researchResolution = parseResolution(value.researchResolution);
  const marketStateResolution = parseMarketState(value.marketStateResolution);
  const executionProvenance = parseExecution(value.executionProvenance);
  if (Array.isArray(value.evidenceItems) && evidenceItems.length < value.evidenceItems.length) warnings.push("evidenceItems_rows_invalid");
  if (Array.isArray(value.sourceLedger) && sourceLedger.length < value.sourceLedger.length) warnings.push("sourceLedger_rows_invalid");
  if (Array.isArray(value.dataGaps) && dataGaps.length < value.dataGaps.length) warnings.push("dataGaps_rows_invalid");
  if (value.marketStateResolution !== undefined && !marketStateResolution && !warnings.includes("marketStateResolution_invalid")) warnings.push("marketStateResolution_invalid");
  if (value.executionProvenance !== undefined && !executionProvenance && !warnings.includes("executionProvenance_invalid")) warnings.push("executionProvenance_invalid");
  const canonicalRevision = revision(value.canonicalRevision);
  const personalOverlay = parsePersonalOverlayPayload(value.personalOverlay, canonicalRevision);
  for (const [key, parsed] of [
    ["topicPlan", topicPlan], ["evidencePackSummary", evidencePackSummary], ["quality", quality],
    ["researchResolution", researchResolution], ["personalOverlay", personalOverlay],
  ] as const) {
    if (key in value && value[key] !== undefined && parsed === null && !warnings.includes(key + "_invalid")) warnings.push(key + "_invalid");
  }
  const generation = isRecord(value.generation) ? {
    message: stringValue(value.generation.message), mode: stringValue(value.generation.mode), generatedAt: stringValue(value.generation.generatedAt),
  } : null;
  const sources = Array.isArray(value.sources) ? value.sources.filter(isRecord).map((row) => ({
    source: stringValue(row.source), date: stringValue(row.date), title: stringValue(row.title),
    url: safeExternalUrl(row.url), path: stringValue(row.path),
  })).filter((row) => row.title || row.source || row.url || row.path) : [];
  return {
    id: value.id, topicKey: stringValue(value.topicKey), topicLabel: stringValue(value.topicLabel),
    date: stringValue(value.date), generatedAt: stringValue(value.generatedAt), mode: stringValue(value.mode),
    saved: value.saved === true, markdown: value.markdown, docCount: numberValue(value.docCount) ?? 0,
    memoryCount: numberValue(value.memoryCount) ?? 0,
    userContext: typeof value.userContext === "string" || typeof value.userContext === "boolean" ? value.userContext : false,
    generation, sources, topicPlan, evidencePackSummary,
    evidenceItems, sourceLedger, dataGaps, quality, researchTraceSummary,
    researchResolution,
    marketStateResolution,
    qualityPreflight: isRecord(value.qualityPreflight) ? value.qualityPreflight : null,
    executionProvenance,
    checkpoints: Array.isArray(value.checkpoints) ? value.checkpoints.filter(isRecord) : [],
    marketTape: isRecord(value.marketTape) ? value.marketTape : null,
    canonicalRevision, personalOverlay,
    contractWarnings: warnings,
  };
}

export function parseTopicReportSummaries(value: unknown): TopicReportSummary[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((row) => ({
    id: stringValue(row.id), topicKey: stringValue(row.topicKey), topicLabel: stringValue(row.topicLabel),
    date: stringValue(row.date), generatedAt: stringValue(row.generatedAt), mode: stringValue(row.mode), saved: row.saved === true,
    engine: stringValue(row.engine), engineDetail: stringValue(row.engineDetail),
  })).filter((row) => Boolean(row.id));
}

/** 보고서 유형의 한국어 이름. 서버 `topic_schema.REPORT_TYPE_LABELS`와 같은 표다.
 *  화면에 `industry_theme`을 그대로 내보내면 사용자는 그것이 무엇인지 알 수 없다. */
export const REPORT_TYPE_LABELS: Record<string, string> = {
  macro_analysis: "거시 분석",
  cross_asset_analysis: "크로스에셋 분석",
  industry_theme: "산업 테마",
  supply_chain_theme: "공급망 테마",
  policy_regulation: "정책·규제",
  geopolitical_risk: "지정학 리스크",
  earnings_theme: "실적 테마",
  factor_style: "팩터·스타일",
  company_basket: "기업군 비교",
  country_market: "국가 시장",
  portfolio_implication: "포트폴리오 영향",
  custom_research: "자유 리서치",
};

export function reportTypeLabel(value?: string): string {
  const key = String(value || "");
  return REPORT_TYPE_LABELS[key] || key || "유형 미상";
}

/** 계획을 무엇이 썼는지. 규칙 계획과 LLM 계획은 신뢰도가 다르고, 사용자가 고친
 *  계획은 또 다르다. 어느 쪽인지 모르면 계획을 얼마나 믿을지 정할 수 없다. */
export function plannerModeLabel(value?: string): string {
  switch (value) {
    case "llm":
      return "LLM이 작성";
    case "edited":
      return "직접 수정함";
    case "preset":
      return "저장된 주제";
    default:
      return "규칙으로 작성";
  }
}
