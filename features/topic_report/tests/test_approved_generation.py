from __future__ import annotations

import hashlib
import io
import json
import urllib.error
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from features.llm_settings import client as llm_client
from features.topic_report import approved_generation as generation
from features.topic_report import approved_generation_support as generation_support
from features.topic_report.approved_generation import (
    ApprovedGenerationInput,
    EngineFailedError,
    EngineOutput,
    EngineUnavailableError,
)
from features.topic_report.approved_research import admit_research, prepare_market_state
from features.topic_report.approved_request import ApprovedRequestRuntime, ApprovedRequestService
from features.topic_report.approved_schema import PlanRequest
from features.topic_report.resolution_schema import (
    ProviderGenerations,
    ResearchPreview,
    ResolutionSnapshotV1,
    ZeroEvidence,
)
from features.market_memory.snapshot import save_market_state_snapshot


NOW = datetime(2026, 7, 16, 3, 4, 5, tzinfo=UTC)


def empty_resolution() -> ResolutionSnapshotV1:
    return ResolutionSnapshotV1(
        schemaVersion=1,
        collectionId=None,
        collectionRevision=None,
        collectionDefinitionHash=None,
        eligibleTotal=None,
        candidateCap=None,
        truncated=False,
        resolvedCandidateIds=[],
        executionUniverseIds=[],
        unusableCandidates=[],
        selectedEvidenceIds=[],
        providerGenerations=ProviderGenerations(indexGeneration="a" * 64, rssGeneration=None),
        inputWatermark="b" * 64,
    )


def approved_request(tmp_path: Path):
    runtime = ApprovedRequestRuntime(
        dataDir=tmp_path,
        clock=lambda: NOW,
        entropy=lambda size: bytes(range(size)),
        uuidFactory=lambda: UUID("12345678-1234-4567-9234-567812345678"),
        resolver=lambda _approved: empty_resolution(),
    )
    return ApprovedRequestService(runtime).plan(
        PlanRequest(
            question="AI 전력 수요와 전력기기 기업",
            userContext="private hypothesis",
            deepResearch=True,
            marketStatePolicy="exclude",
        )
    ).approvedRequest


def prepared_input(tmp_path: Path, mode: str) -> ApprovedGenerationInput:
    approved = approved_request(tmp_path)
    document = {
        "id": "doc-1",
        "title": "AI power demand",
        "source": "Reuters",
        "date": "2026-07-15",
        "url": "https://example.com/ai-power",
        "path": "research-inbox/rss/ai-power.md",
        "snippet": "Demand rises while grid constraints remain a counter risk.",
    }
    research = admit_research(
        approved,
        empty_resolution(),
        search_docs=lambda _queries, _limit, _allowed: [document],
        search_memories=lambda _keywords, _limit: [],
    )
    preview = ResearchPreview(
        resolution=research.resolution,
        resolvedAt="2026-07-16T03:04:05Z",
        zeroEvidence=ZeroEvidence(required=False, reasonCode=None, resolutionFingerprint=None),
    )
    return ApprovedGenerationInput(
        approved=approved,
        approvalId="apr_12345678-1234-4567-9234-567812345678",
        requestedMode=mode,
        adapter="codex" if mode == "cli" else "auto",
        preview=preview,
        research=research,
        marketState=prepare_market_state(tmp_path, approved, lambda: NOW),
    )


def fake_materials(approved, rows):
    return (
        generation._topic(approved),
        {"tickers": {}, "asOf": approved.asOfDate},
        {"ok": False},
    )


















def test_rules_and_cli_share_approved_structured_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generation, "_materials", fake_materials)
    monkeypatch.setattr(generation, "_read_prompt", lambda: "Approved prompt")
    monkeypatch.setattr(
        generation,
        "attempt_cli",
        lambda *_args, **_kwargs: EngineOutput("# CLI", "codex", "external_agent", "", ""),
    )

    direct = generation.build_approved_report(replace(prepared_input(tmp_path, "cli"), taskPolicy={"enabled": False}), job_id="job-direct", clock=lambda: NOW)
    cli = generation.build_approved_report(prepared_input(tmp_path, "cli"), job_id="job-cli", clock=lambda: NOW)

    shared = {
        "topicPlan",
        "evidencePackSummary",
        "evidenceItems",
        "sourceLedger",
        "researchResolution",
        "marketStateResolution",
        "deepResearch",
        "docCount",
    }
    assert set(direct.report) == set(cli.report)
    assert {key: direct.report[key] for key in shared} == {key: cli.report[key] for key in shared}
    assert direct.report["researchResolution"]["resolution"]["selectedEvidenceIds"] == ["doc-1"]
    assert direct.report["evidenceItems"][0]["documentId"] == "doc-1"
    assert direct.report["marketStateResolution"]["reason"] == "policy_excluded"
    assert direct.attemptedEngine == "none"
    assert cli.attemptedEngine == "cli"


def test_current_market_state_canary_never_changes_evidence_or_coverage_totals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given identical admitted evidence / When current state context is included / Then it stays outside evidence ledgers.
    base = prepared_input(tmp_path, "cli")
    save_market_state_snapshot(tmp_path / "market-memory.sqlite3", {
        "id": "mss_state_canary",
        "asOf": "2026-07-16T03:00:00Z",
        "headline": "STATE_CANARY_CONTEXT_ONLY",
        "oneLineSummary": "State context must not become evidence.",
        "marketRegime": "mixed",
        "actionPosture": "check",
        "keyDrivers": [{"title": "Driver", "summary": "Bounded", "sourceRefs": ["state:1"]}],
        "watchItems": ["Checkpoint"],
        "counterEvidence": ["Challenge"],
        "uncertainties": ["Unknown"],
        "sourceRefs": [{"id": "state:1", "title": "State source", "source": "Fixture"}],
        "confidence": 0.7,
        "inputWatermarks": {"GLOBAL": None, "US": None, "KR": None},
    })
    included_approved = base.approved.model_copy(update={"marketStatePolicy": "include_current"})
    included = ApprovedGenerationInput(
        approved=included_approved,
        approvalId=base.approvalId,
        requestedMode=base.requestedMode,
        adapter=base.adapter,
        preview=base.preview,
        research=base.research,
        marketState=prepare_market_state(tmp_path, included_approved, lambda: NOW),
    )
    monkeypatch.setattr(generation, "_materials", fake_materials)
    monkeypatch.setattr(generation, "_read_prompt", lambda: "Approved prompt")
    monkeypatch.setattr(
        generation,
        "attempt_cli",
        lambda _prompt, _context, **_kwargs: EngineOutput("# Same report", "openai_api", "openai", "fake", "r1"),
    )

    excluded_out = generation.build_approved_report(base, job_id="job-excluded", clock=lambda: NOW)
    included_out = generation.build_approved_report(included, job_id="job-included", clock=lambda: NOW)

    protected = ("evidenceItems", "sourceLedger", "evidencePackSummary", "docCount")
    digest = lambda report, key: hashlib.sha256(  # noqa: E731 - compact exact canary assertion.
        json.dumps(report[key], ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    assert {key: digest(excluded_out.report, key) for key in protected} == {
        key: digest(included_out.report, key) for key in protected
    }
    assert excluded_out.report["qualityPreflight"]["requiredInputs"] == included_out.report["qualityPreflight"]["requiredInputs"]
    assert excluded_out.report["qualityPreflight"]["requiredInputs"]["sourceCount"] == 1
    assert {
        key: value for key, value in excluded_out.report["quality"].items() if key != "generatedAt"
    } == {
        key: value for key, value in included_out.report["quality"].items() if key != "generatedAt"
    }
    assert included_out.report["marketStateResolution"]["injected"] is True
    assert included_out.report["marketStateResolution"]["ref"]["layer"] == "source-grounded"
    assert "STATE_CANARY_CONTEXT_ONLY" not in json.dumps(included_out.report["evidenceItems"])


def test_collection_admission_filters_universe_and_counts_normalized_url_once(tmp_path: Path) -> None:
    approved = approved_request(tmp_path)
    base = ResolutionSnapshotV1(
        schemaVersion=1,
        collectionId="sc_12345678-1234-4567-9234-567812345678",
        collectionRevision=1,
        collectionDefinitionHash="d" * 64,
        eligibleTotal=3,
        candidateCap=120,
        truncated=False,
        resolvedCandidateIds=["ev-1", "ev-2", "ev-off"],
        executionUniverseIds=["doc-1", "doc-duplicate"],
        unusableCandidates=[],
        selectedEvidenceIds=[],
        providerGenerations=ProviderGenerations(indexGeneration="a" * 64, rssGeneration="e" * 64),
        inputWatermark="b" * 64,
    )
    calls = []
    rows = [
        {
            "id": "doc-1",
            "title": "First",
            "url": "https://EXAMPLE.com/story?utm_source=rss",
            "path": "research-inbox/rss/first.md",
        },
        {
            "id": "doc-duplicate",
            "title": "Duplicate",
            "url": "https://example.com/story",
            "path": "research-inbox/rss/duplicate.md",
        },
        {
            "id": "doc-off-filter",
            "title": "Off filter",
            "url": "https://example.com/off-filter",
            "path": "research-inbox/rss/off.md",
        },
    ]

    def search(_queries, _limit, allowed):
        calls.append(set(allowed or set()))
        return rows

    research = admit_research(
        approved,
        base,
        search_docs=search,
        search_memories=lambda _keywords, _limit: [],
    )

    assert calls and all(call == {"doc-1", "doc-duplicate"} for call in calls)
    assert research.resolution.selectedEvidenceIds == ["doc-1"]
    assert [row["documentId"] for row in research.evidence_items] == ["doc-1"]
    assert research.evidencePack["totalDocs"] == 1
    assert sum(research.evidencePack["roleCounts"].values()) == 1


def test_cli_engine_failure_falls_back_within_same_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generation, "_materials", fake_materials)
    monkeypatch.setattr(generation, "_read_prompt", lambda: "Approved prompt")
    monkeypatch.setattr(
        generation,
        "attempt_cli",
        lambda _prompt, _context, **_kwargs: (_ for _ in ()).throw(EngineFailedError("cli")),
    )

    outcome = generation.build_approved_report(
        prepared_input(tmp_path, "cli"),
        job_id="job-fallback",
        clock=lambda: NOW,
    )

    assert outcome.attemptedEngine == "cli"
    assert outcome.finalEngine == "rules"
    assert outcome.fallbackReason == "engine_failed"
    assert outcome.adapter == "codex"
    assert outcome.mode == "fallback"
    assert outcome.report["executionProvenance"]["fallbackReason"] == "engine_failed"


def test_confirmed_zero_skips_all_external_engines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    approved = approved_request(tmp_path)
    research = admit_research(
        approved,
        empty_resolution(),
        search_docs=lambda _queries, _limit, _allowed: [],
        search_memories=lambda _keywords, _limit: [],
    )
    preview = ResearchPreview(
        resolution=research.resolution,
        resolvedAt="2026-07-16T03:04:05Z",
        zeroEvidence=ZeroEvidence(
            required=True,
            reasonCode="zero_matches",
            resolutionFingerprint="rf1_" + "c" * 64,
        ),
    )
    command = ApprovedGenerationInput(
        approved=approved,
        approvalId="apr_12345678-1234-4567-9234-567812345678",
        requestedMode="cli",
        adapter="codex",
        preview=preview,
        research=research,
        marketState=prepare_market_state(tmp_path, approved, lambda: NOW),
    )
    monkeypatch.setattr(generation, "attempt_cli", lambda *_args, **_kwargs: pytest.fail("cli invoked"))

    outcome = generation.build_approved_report(command, job_id="job-zero", clock=lambda: NOW)

    assert outcome.attemptedEngine == "none"
    assert outcome.finalEngine == "rules"
    assert outcome.fallbackReason == "confirmed_zero_evidence"
    assert outcome.generationMode == "rules"
    assert outcome.report["researchResolution"] == preview.model_dump(mode="json")


# ------------------------------------------- 초안 재시도 (draft guard)

def _deep_markdown(*, drop_tail: int = 0, filler: int = 8) -> str:
    from features.topic_report.report_contract import REPORT_HEAD_SECTIONS, REPORT_TAIL_SECTIONS

    body = "기대 심리가 지표에 반영되는 경로를 단계로 풀어 설명한 문장이다. " * filler
    tails = list(REPORT_TAIL_SECTIONS)[: len(REPORT_TAIL_SECTIONS) - drop_tail]
    names = [*REPORT_HEAD_SECTIONS, "분석축", *tails]
    return "\n\n".join(["# 제목", *(f"## {name}\n\n{body}" for name in names)])


def test_a_broken_draft_is_rewritten_once_instead_of_losing_the_whole_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 딥 실행에서 값비싼 것은 쓰기가 아니라 그 앞이다(근거 팩·웹 조회·축 브리프·논지).
    # 실측으로 마지막 쓰기 한 번이 어긋나 9분치 작업이 통째로 버려졌다.
    seen: list[str] = []

    def cli(_prompt, context, **_kwargs):
        seen.append(context)
        broken = len(seen) == 1
        return EngineOutput(
            markdown=_deep_markdown(drop_tail=2) if broken else _deep_markdown(filler=200),
            adapter="codex", provider="external_agent", model="", responseId="",
        )

    monkeypatch.setattr(generation, "_materials", fake_materials)
    monkeypatch.setattr(generation, "_read_prompt", lambda: "Approved prompt")
    monkeypatch.setattr(generation, "attempt_cli", cli)

    outcome = generation.build_approved_report(
        prepared_input(tmp_path, "cli"), job_id="job-draft-guard", clock=lambda: NOW,
    )

    guard = outcome.report["draftGuard"]
    assert "draft_sections_missing" in guard["problems"]
    assert guard["retried"] is True and guard["outcome"] == "retry_better"
    assert len(seen) == 2
    # 재시도 컨텍스트에만 교정 지시가 붙는다. 실패한 초안 자체는 돌려주지 않는다.
    assert "다시 작성 요청" not in seen[0]
    assert "고정 섹션이 빠졌습니다" in seen[1]
    assert "Source & Data Notes" in outcome.report["markdown"]


def test_a_healthy_draft_is_not_rewritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def cli(_prompt, _context, **_kwargs):
        calls["n"] += 1
        return EngineOutput(
            markdown=_deep_markdown(filler=200), adapter="codex",
            provider="external_agent", model="", responseId="",
        )

    monkeypatch.setattr(generation, "_materials", fake_materials)
    monkeypatch.setattr(generation, "_read_prompt", lambda: "Approved prompt")
    monkeypatch.setattr(generation, "attempt_cli", cli)

    outcome = generation.build_approved_report(
        prepared_input(tmp_path, "cli"), job_id="job-draft-ok", clock=lambda: NOW,
    )
    assert calls["n"] == 1
    assert outcome.report["draftGuard"] == {"problems": [], "retried": False, "outcome": ""}


def test_a_worse_retry_is_discarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 나쁜 초안이라도 없는 것보다 낫다.
    outputs = [_deep_markdown(drop_tail=1, filler=200), _deep_markdown(drop_tail=3)]

    def cli(_prompt, _context, **_kwargs):
        return EngineOutput(
            markdown=outputs.pop(0), adapter="codex",
            provider="external_agent", model="", responseId="",
        )

    monkeypatch.setattr(generation, "_materials", fake_materials)
    monkeypatch.setattr(generation, "_read_prompt", lambda: "Approved prompt")
    monkeypatch.setattr(generation, "attempt_cli", cli)

    outcome = generation.build_approved_report(
        prepared_input(tmp_path, "cli"), job_id="job-draft-worse", clock=lambda: NOW,
    )
    assert outcome.report["draftGuard"]["outcome"] in {"retry_worse", "retry_no_gain"}
    assert "반론과 리스크" in outcome.report["markdown"]
