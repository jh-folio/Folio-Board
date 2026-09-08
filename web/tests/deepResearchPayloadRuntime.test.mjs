import { readFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
let parserPromise;
async function loadParser() {
  if (parserPromise) return parserPromise;
  parserPromise = (async () => {
    const sourcePath = new URL("../src/app/deepResearchPayload.ts", import.meta.url);
    const tempRoot = await mkdtemp(join(tmpdir(), "folio-dr-parser-"));
    const tscPath = new URL("../node_modules/typescript/bin/tsc", import.meta.url);
    try {
      await execFileAsync(process.execPath, [fileURLToPath(tscPath), fileURLToPath(sourcePath), "--ignoreConfig", "--target", "ES2022", "--module", "ES2022", "--outDir", tempRoot, "--skipLibCheck"]);
      const output = await readFile(join(tempRoot, "deepResearchPayload.js"), "utf8");
      return import("data:text/javascript;base64," + Buffer.from(output).toString("base64"));
    } finally {
      await rm(tempRoot, { recursive: true, force: true });
    }
  })();
  return parserPromise;
}

const fixture = {
  id: "rp-h1-runtime",
  topicKey: "custom",
  topicLabel: "AI 전력 수요",
  markdown: "# AI 전력 수요\n\n외부 근거 기반 결론",
  userContext: true,
  topicPlan: {
    topic: "AI 전력 수요", reportType: "industry_theme", userIntent: "반증 조건 확인",
    researchQuestions: ["수요가 수주에 반영되는가?"],
    analysisAxes: [{ key: "demand", label: "전력 수요", questions: ["얼마나 증가하는가?"], requiredData: ["수주"], searchQueries: ["power demand"] }],
    searchQueries: ["AI power demand"], expectedSections: ["Executive Summary"], dataGapsLikely: ["수주 시점"],
    deepResearch: { enabled: true, maxRounds: 2, subQuestions: [], falsificationTriggers: ["가이던스가 반대로 나온다"], requiredOutputs: ["counter_arguments"] },
  },
  evidencePackSummary: {
    totalDocs: 1, roleCounts: { supporting: 1 },
    axisCoverage: { demand: { label: "전력 수요", count: 1, level: "low" } },
    questionCoverage: { dq_01: { question: "수요가 수주에 반영되는가?", count: 1, level: "low" } }, dataGaps: ["수주 시점"], memoryCount: 0,
  },
  evidenceItems: [{ id: "ev-1", title: "External", source: "Reuters", role: "supporting", axis: "demand", confidence: "high", url: "https://example.com/evidence" }],
  sourceLedger: [{ sourceId: "src-1", artifactType: "topic_report", artifactId: "rp-h1-runtime", title: "External", source: "Reuters", path: "research-inbox/rss/a.md", evidenceRole: "supporting", axisKey: "demand", reliability: "high", researchQuestionId: "dq_01", researchRound: 1, usedInSections: ["Executive Summary"], url: "javascript:alert(1)" }],
  dataGaps: [{ id: "gap-1", severity: "high", description: "수주 시점 부족", suggestedAction: "공식자료 보강", resolved: false }],
  quality: { score: 62, grade: "C", status: "warn", warnings: ["반대 근거 부족"], suggestedFixes: ["반대 근거 보강"] },
  researchResolution: { resolution: { schemaVersion: 1, collectionId: "sc-1", collectionRevision: 3, collectionDefinitionHash: "def-hash", eligibleTotal: 2, candidateCap: 120, resolvedCandidateIds: ["candidate-1"], executionUniverseIds: ["doc-1"], selectedEvidenceIds: ["doc-1"], unusableCandidates: [{ candidateId: "rss-1", reason: "unindexed_rss" }], truncated: false, providerGenerations: { indexGeneration: "index-1", rssGeneration: "rss-1" }, inputWatermark: "watermark-1" }, resolvedAt: "2026-07-16T03:04:05Z", zeroEvidence: { required: false, reasonCode: null, resolutionFingerprint: "fingerprint-1" } },
  marketStateResolution: { policy: "include_current", requestedScope: "AUTO", resolvedScope: "US", injected: true, reason: "current_injected", ref: { snapshotId: "mss-1", sourceKind: "snapshot", scope: "US", asOf: "2026-07-16T02:00:00Z", status: "current", freshnessReason: "within_window", inputWatermark: "2026-07-16T01:00:00Z", relevantEvidenceWatermark: "2026-07-16T01:00:00Z", invalidWatermarkRows: 0, resolvedAt: "2026-07-16T03:04:05Z", layer: "source-grounded" } },
  qualityPreflight: { requiredInputs: { sourceCount: 1 } },
  executionProvenance: { schemaVersion: 1, approvalId: "apr-1", planHash: "plan-hash", requestedMode: "direct", attemptedEngine: "api", finalEngine: "api", fallbackReason: null, adapter: "openai_api", executedAt: "2026-07-16T03:04:05Z" },
  checkpoints: [{ id: "cp-1", label: "수주 확인" }],
  marketTape: { asOf: "2026-07-16", symbols: ["PWR"] },
  canonicalRevision: { number: 2, hash: "22" },
  personalOverlay: { markdown: "사용자 가설", stale: false, staleReason: "canonical_revision_changed", canonicalRevision: { number: 1, hash: "11" }, linkedNotes: [{ title: "전력 thesis" }], counterEvidence: ["반대 자료"], contradictions: [], uncertainties: ["시점"], personalQuestions: ["재확인"] },
};

test("typed Topic report parser preserves every provenance layer and sanitizes links", async () => {
  const { parseTopicReportPayload } = await loadParser();
  const report = parseTopicReportPayload(fixture);
  assert.equal(report.id, fixture.id);
  assert.equal(report.evidenceItems.length, 1);
  assert.equal(report.sourceLedger.length, 1);
  assert.equal(report.dataGaps.length, 1);
  assert.equal(report.userContext, true);
  assert.equal(report.sourceLedger[0].url, "");
  assert.equal(report.contractWarnings.length, 0);
  assert.equal(report.personalOverlay.stale, true);
  assert.equal(report.sourceLedger[0].artifactType, "topic_report");
  assert.equal(report.sourceLedger[0].researchRound, 1);
  assert.equal(report.researchTraceSummary.usedSourceCount, 1);
  assert.equal(report.researchTraceSummary.latestSourceDate, "");
  assert.equal(report.researchTraceSummary.unresolvedDataGapCount, 1);
  assert.equal(report.researchResolution.collectionDefinitionHash, "def-hash");
  assert.deepEqual(report.researchResolution.resolvedCandidateIds, ["candidate-1"]);
  assert.deepEqual(report.researchResolution.executionUniverseIds, ["doc-1"]);
  assert.equal(report.researchResolution.providerGenerations.indexGeneration, "index-1");
  assert.equal(report.researchResolution.inputWatermark, "watermark-1");
  assert.equal(report.researchResolution.resolutionFingerprint, "fingerprint-1");
  assert.equal(report.marketStateResolution.ref.snapshotId, "mss-1");
  assert.equal(report.qualityPreflight.requiredInputs.sourceCount, 1);
  assert.equal(report.executionProvenance.approvalId, "apr-1");
  assert.equal(report.checkpoints.length, 1);
  assert.deepEqual(report.marketTape.symbols, ["PWR"]);
});

test("hypothesis-shaped ledger rows are rejected and malformed Market State warns", async () => {
  const { parseTopicReportPayload } = await loadParser();
  const hypothesis = { ...fixture.sourceLedger[0], sourceId: "note-1", artifactType: "", type: "user_note", evidenceRole: "hypothesis", source_layer: "hypothesis" };
  const selfReference = { ...fixture.sourceLedger[0], sourceId: "folio-1", generated_by: "folio_os", source_layer: "primary_processed" };
  const exportedSelfReference = { ...fixture.sourceLedger[0], sourceId: "folio-export-1", generated_by: "Folio OS" };
  // 2026-09 리네이밍 이후 새로 내보낸 노트는 이 값들을 쓴다 — 신·구 표시명 모두
  // 자기참조로 걸러져야 한다(dual-read, plan §4.3). 이름이 바뀌었다고 새로 내보낸
  // 자기 노트가 source ledger에 evidence로 남으면 원칙 5(자기참조 금지) 위반이다.
  const newMarkerSelfReference = { ...fixture.sourceLedger[0], sourceId: "folio-board-1", generated_by: "folio_board", source_layer: "primary_processed" };
  const newMarkerExportedSelfReference = { ...fixture.sourceLedger[0], sourceId: "folio-board-export-1", generated_by: "Folio Board" };
  const unrelatedPublisher = { ...fixture.sourceLedger[0], sourceId: "publisher-1", generated_by: "Folio Observer" };
  const report = parseTopicReportPayload({ ...fixture, sourceLedger: [fixture.sourceLedger[0], hypothesis, selfReference, exportedSelfReference, newMarkerSelfReference, newMarkerExportedSelfReference, unrelatedPublisher], marketStateResolution: { injected: true, ref: {} } });
  assert.equal(report.sourceLedger.length, 2);
  assert.equal(report.sourceLedger[0].artifactType, "topic_report");
  assert.equal(report.sourceLedger[1].sourceId, "publisher-1");
  assert.equal(report.marketStateResolution, undefined);
  assert.ok(report.contractWarnings.includes("sourceLedger_rows_invalid"));
  assert.ok(report.contractWarnings.includes("marketStateResolution_invalid"));
});

test("optional malformed provenance fields fail safe to empty sections", async () => {
  const { parseTopicReportPayload } = await loadParser();
  for (const bad of [null, {}, "bad", 7]) {
    const report = parseTopicReportPayload({ ...fixture, evidenceItems: bad, sourceLedger: bad, dataGaps: bad, quality: bad, researchResolution: bad, personalOverlay: bad });
    assert.deepEqual(report.evidenceItems, []);
    assert.deepEqual(report.sourceLedger, []);
    assert.deepEqual(report.dataGaps, []);
    assert.ok(report.contractWarnings.length >= 5);
  }
});

test("required report identity and canonical Markdown are rejected at runtime", async () => {
  const { parseTopicReportPayload } = await loadParser();
  for (const payload of [null, [], {}, { id: "x", markdown: 3 }, { id: "", markdown: "# x" }]) {
    assert.throws(() => parseTopicReportPayload(payload), /topic_report_contract_invalid/);
  }
});

test("malformed rows are discarded without throwing", async () => {
  const { parseTopicReportPayload, parseTopicReportSummaries } = await loadParser();
  const report = parseTopicReportPayload({ ...fixture, evidenceItems: [null, 1, fixture.evidenceItems[0]], sourceLedger: ["bad"], dataGaps: [{ nope: true }] });
  assert.equal(report.evidenceItems.length, 1);
  assert.equal(report.sourceLedger.length, 0);
  assert.equal(report.dataGaps.length, 0);
  assert.ok(report.contractWarnings.length >= 3);
  assert.deepEqual(parseTopicReportSummaries([null, 1, { id: "summary-1", topicLabel: "valid" }, { id: "", topicLabel: "invalid" }]), [{
    id: "summary-1", topicKey: "", topicLabel: "valid", date: "", generatedAt: "", mode: "", saved: false,
    engine: "", engineDetail: "",
  }]);
  assert.deepEqual(parseTopicReportSummaries({}), []);
});

test("nested Collection hashes round-trip and remain distinct from report details", async () => {
  const { deepResearchCollectionHash, parseDeepResearchLocation } = await loadParser();
  const collectionId = "sc_12345678-1234-4234-9234-123456789abc";
  assert.equal(deepResearchCollectionHash(collectionId), `#/deep-research/collections/${collectionId}`);
  assert.deepEqual(parseDeepResearchLocation(`#/deep-research/collections/${collectionId}`), {
    kind: "collection",
    id: collectionId,
    malformed: false,
  });
  assert.deepEqual(parseDeepResearchLocation("#/deep-research/report-1"), {
    kind: "report",
    id: "report-1",
    malformed: false,
  });
  assert.deepEqual(parseDeepResearchLocation("#/deep-research"), {
    kind: "list",
    id: "",
    malformed: false,
  });
});

test("malformed nested Collection hashes fail closed", async () => {
  const { parseDeepResearchLocation } = await loadParser();
  assert.deepEqual(parseDeepResearchLocation("#/deep-research/collections/%E0%A4%A"), {
    kind: "collection",
    id: "",
    malformed: true,
  });
  assert.deepEqual(parseDeepResearchLocation("#/deep-research/collections/not-a-collection"), {
    kind: "collection",
    id: "",
    malformed: true,
  });
});
