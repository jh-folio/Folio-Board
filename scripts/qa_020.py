#!/usr/bin/env python3
"""Host-side Folio Board 0.2 QA evidence orchestrator.

This file is deliberately not part of the release package.  It only operates
inside a marker-owned attempt directory and never opens the repository's real
``data``, ``config`` or ``research-inbox`` roots.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Any


PRE_EXPOSURE = [
    "DR-H1",
    "PLAN-F1",
    "GEN-F1",
    "GEN-F2",
    "RP-H1",
    "AG-H1",
    "WB-H1",
    "WB-F1",
    "WL-H1",
    "COL-H1",
    "COL-F1",
    "MS-H1",
    "CTX-F1",
    "NT-H1",
    "SC-H2",
    "IC-H1",
    "REL-H1",
]
POST_EXPOSURE = ["DOC-H1"]
SCENARIO_SETS = {
    "preExposure": PRE_EXPOSURE,
    "postExposure": POST_EXPOSURE,
    "full": [*PRE_EXPOSURE, *POST_EXPOSURE],
}
RESTART_SCENARIOS = ["DR-H1", "WB-H1", "WL-H1"]
OWNERSHIP_MARKER = ".folio-qa-owned"
SCHEMA_VERSION = 1
REPORT_ID = "qa-contract-fixture-20260722"
INJECTED_CLOCK = "2026-07-22T12:00:00Z"
VIEWPORTS = ("1440", "768", "390")
CAPTURE_FILES = (
    "screenshot.png",
    "screenshot.json",
    "console.json",
    "network.json",
    "dom.json",
    "api-before.json",
    "api-after.json",
    "result.json",
)
VIEWPORT_SCENARIOS = {
    "DR-H1",
    "RP-H1",
    "NT-H1",
    "SC-H2",
    "IC-H1",
    "REL-H1",
    "DOC-H1",
}

EXIT_OK = 0
EXIT_OWNERSHIP = 2
EXIT_HEALTH = 3
EXIT_EVIDENCE = 4
EXIT_PROCESS = 5
EXIT_PROXY = 6

PRIVATE_CANARIES = ("PROMPT_INJECTION_CANARY", "PRIVATE_CONTEXT_CANARY")
HEALTH_KEYS = {"status", "pid", "version", "commit", "workspaceIdentity"}
ISO_MAX_AGE = dt.timedelta(days=7)


class HarnessError(Exception):
    def __init__(self, code: str, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def _fail(code: str, message: str, exit_code: int = EXIT_EVIDENCE) -> None:
    raise HarnessError(code, message, exit_code)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path, *, code: str = "MALFORMED_MANIFEST") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail(code, f"Cannot read JSON at {path}: {exc}")
    if not isinstance(value, dict):
        _fail(code, f"Expected a JSON object at {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the atomic sibling name short: packaged QA roots are intentionally
    # descriptive and can otherwise cross the legacy Windows MAX_PATH limit.
    temporary = path.with_name(f".q{uuid.uuid4().hex[:8]}")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    def serialize(item: Any) -> str:
        if item is None:
            return "null"
        if isinstance(item, bool):
            return "true" if item else "false"
        if isinstance(item, int):
            return str(item)
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("canonical JSON rejects non-finite numbers")
            if item == 0:
                return "0"
            magnitude, raw = abs(item), repr(item).lower()
            if 1e-6 <= magnitude < 1e21:
                fixed = format(Decimal(raw), "f")
                return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed
            if "e" not in raw:
                return raw
            mantissa, exponent_text = raw.split("e", maxsplit=1)
            exponent = int(exponent_text)
            return f"{mantissa.rstrip('0').rstrip('.')}{'e+' if exponent >= 0 else 'e-'}{abs(exponent)}"
        if isinstance(item, str):
            return json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        if isinstance(item, list):
            return "[" + ",".join(serialize(child) for child in item) + "]"
        if isinstance(item, dict):
            keys = sorted(item, key=lambda key: key.encode("utf-16be", errors="surrogatepass"))
            return "{" + ",".join(
                json.dumps(key, ensure_ascii=False, separators=(",", ":")) + ":" + serialize(item[key])
                for key in keys
            ) + "}"
        raise TypeError(f"unsupported canonical JSON value: {type(item).__name__}")

    return serialize(value).encode("utf-8")


def _canonical_content_hash(report: dict[str, Any]) -> str:
    excluded = {"canonicalRevision", "agentRevisions", "personalOverlay", "updatedAt", "jobCommit"}
    content = {key: value for key, value in report.items() if key not in excluded}
    return hashlib.sha256(_canonical_json_bytes(content)).hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_attempt_dir(path: Path) -> Path:
    resolved = path.resolve()
    forbidden_names = {"data", "config", "research-inbox", ".git"}
    if resolved.parent == resolved or resolved.name.lower() in forbidden_names:
        _fail("UNSAFE_ATTEMPT_ROOT", f"Unsafe attempt directory: {resolved}", EXIT_OWNERSHIP)
    return resolved


def _claim_attempt_dir(attempt_dir: Path) -> tuple[str, Path]:
    attempt_dir = _safe_attempt_dir(attempt_dir)
    marker = attempt_dir / OWNERSHIP_MARKER
    if attempt_dir.exists():
        if marker.is_file():
            owned = _read_json(marker, code="INVALID_OWNERSHIP_MARKER")
            attempt_id = str(owned.get("attemptId", ""))
            if not attempt_id:
                _fail("INVALID_OWNERSHIP_MARKER", "Ownership marker has no attemptId", EXIT_OWNERSHIP)
            return attempt_id, marker
        if any(attempt_dir.iterdir()):
            _fail("UNOWNED_RUN_ROOT", f"Attempt directory is non-empty and unowned: {attempt_dir}", EXIT_OWNERSHIP)
    else:
        attempt_dir.mkdir(parents=True)
    attempt_id = f"qa020-{uuid.uuid4().hex}"
    _write_json(marker, {"attemptId": attempt_id, "state": "prepared", "createdAt": _utc_now()})
    return attempt_id, marker


def _load_owned_manifest(path: Path) -> tuple[dict[str, Any], Path]:
    manifest_path = path.resolve()
    payload = _read_json(manifest_path)
    required = {
        "schemaVersion",
        "attemptId",
        "routeExposure",
        "runRoot",
        "ownershipMarker",
        "artifact",
        "build",
        "workspaceIdentity",
        "port",
        "baseUrl",
        "healthExpected",
        "scenarioSet",
        "scenarioSets",
        "selectedScenarioIds",
        "phases",
        "fixtures",
        "urls",
        "selectors",
        "requiredEvidencePaths",
    }
    missing = sorted(required - set(payload))
    if missing:
        _fail("INCOMPLETE_MANIFEST", f"Manifest is missing: {', '.join(missing)}")
    run_root = Path(str(payload["runRoot"])).resolve()
    marker = Path(str(payload["ownershipMarker"])).resolve()
    if marker != run_root / OWNERSHIP_MARKER or not marker.is_file():
        _fail("UNOWNED_RUN_ROOT", f"Missing ownership marker for {run_root}", EXIT_OWNERSHIP)
    owned = _read_json(marker, code="INVALID_OWNERSHIP_MARKER")
    if owned.get("attemptId") != payload.get("attemptId"):
        _fail("OWNERSHIP_ID_MISMATCH", "Ownership marker attemptId does not match", EXIT_OWNERSHIP)
    if not _is_relative_to(manifest_path, run_root):
        _fail("MANIFEST_OUTSIDE_RUN_ROOT", "Manifest is outside its owned run root", EXIT_OWNERSHIP)
    return payload, manifest_path


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        exclusive_address_use = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive_address_use is not None:
            listener.setsockopt(socket.SOL_SOCKET, exclusive_address_use, 1)
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _port_open(port: int, timeout: float = 0.2) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        return client.connect_ex(("127.0.0.1", port)) == 0


def _safe_extract(artifact: Path, destination: Path) -> Path:
    if not artifact.is_file() or not zipfile.is_zipfile(artifact):
        _fail("INVALID_ARTIFACT", f"Artifact is not a ZIP file: {artifact}")
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(artifact) as archive:
        for info in archive.infolist():
            member = Path(info.filename.replace("\\", "/"))
            target = (destination / member).resolve()
            if member.is_absolute() or ".." in member.parts or not _is_relative_to(target, destination.resolve()):
                _fail("UNSAFE_ARTIFACT_PATH", f"Unsafe ZIP member: {info.filename}")
        archive.extractall(destination)
    candidates = [path.parent for path in destination.rglob("BUILD.json") if path.is_file()]
    candidates = [path for path in candidates if (path / "VERSION").is_file()]
    if len(candidates) != 1:
        _fail("ARTIFACT_BUILD_ROOT_AMBIGUOUS", f"Expected one BUILD.json/VERSION root, found {len(candidates)}")
    return candidates[0].resolve()


def _read_build(extract_root: Path) -> dict[str, str]:
    build = _read_json(extract_root / "BUILD.json", code="INVALID_BUILD_METADATA")
    if set(build) != {"version", "commit", "builtAt"}:
        _fail("INVALID_BUILD_METADATA", "BUILD.json must contain exactly version, commit, and builtAt")
    version = str(build["version"])
    commit = str(build["commit"])
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        _fail("INVALID_BUILD_IDENTITY", "Artifact version or commit is invalid")
    if (extract_root / "VERSION").read_text(encoding="utf-8").strip() != version:
        _fail("BUILD_VERSION_MISMATCH", "BUILD.json version differs from VERSION")
    return {"version": version, "commit": commit, "builtAt": str(build["builtAt"])}


def _workspace_identity(attempt_id: str, artifact_sha256: str, extract_root: Path) -> str:
    material = f"{attempt_id}\0{artifact_sha256}\0{extract_root.resolve()}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _phases(selected: list[str]) -> list[dict[str, str]]:
    phases = [
        {"phaseId": f"{scenario}:pre", "scenario": scenario, "action": "pre_restart", "expectedEpochId": None}
        for scenario in selected
    ]
    restart_number = 1
    for scenario in RESTART_SCENARIOS:
        if scenario in selected:
            restart_number += 1
            phases.append(
                {
                    "phaseId": f"{scenario}:post",
                    "scenario": scenario,
                    "action": "post_restart",
                    "expectedEpochId": None,
                }
            )
    return phases


def _required_evidence_paths(selected: list[str]) -> list[str]:
    paths: list[str] = []
    for scenario in selected:
        if scenario in VIEWPORT_SCENARIOS:
            for viewport in VIEWPORTS:
                paths.extend(f"{scenario}/{viewport}/{name}" for name in CAPTURE_FILES)
        else:
            paths.append(f"{scenario}/result.json")
        if scenario in RESTART_SCENARIOS:
            paths.append(f"{scenario}/post-restart-result.json")
    return paths


def _scenario_selectors(selected: list[str]) -> dict[str, dict[str, str]]:
    common = {"root": ".react-shell", "result": ".react-shell-main"}
    selectors = {scenario: dict(common) for scenario in selected}
    if "DR-H1" in selectors:
        selectors["DR-H1"].update(
            {
                "question": "[data-qa=dr-question]",
                "preview": "[data-qa=dr-preview]",
                "plan": "[data-qa=dr-plan]",
                "continue": "[data-qa=dr-continue]",
                "report": "[data-qa=dr-report]",
            }
        )
    return selectors


def _seed_research_index(index_path: Path, article_path: Path, rss_path: Path) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(index_path) as connection:
        connection.executescript(
            """
            CREATE TABLE documents (
              doc_id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
              source TEXT NOT NULL, date TEXT NOT NULL, type TEXT NOT NULL, url TEXT NOT NULL,
              market_relevance REAL NOT NULL DEFAULT 0, metadata_json TEXT NOT NULL DEFAULT '{}',
              updated_at TEXT NOT NULL, content TEXT NOT NULL DEFAULT '', content_updated_at TEXT
            );
            CREATE TABLE chunks (
              chunk_id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, chunk_index INTEGER NOT NULL,
              text TEXT NOT NULL, embedding_json TEXT NOT NULL, UNIQUE(doc_id, chunk_index)
            );
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
              chunk_id UNINDEXED, doc_id UNINDEXED, title, source, text
            );
            CREATE TABLE file_manifest (
              path TEXT PRIMARY KEY, file_signature TEXT NOT NULL DEFAULT '',
              market_relevant INTEGER NOT NULL DEFAULT 0, doc_id TEXT NOT NULL DEFAULT '',
              modified_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE rss_feed_items (
              filename TEXT PRIMARY KEY, path TEXT NOT NULL, size INTEGER NOT NULL,
              mtime_ns INTEGER NOT NULL, title TEXT NOT NULL, timestamp TEXT NOT NULL,
              timestamp_sort TEXT NOT NULL, url TEXT NOT NULL, description TEXT NOT NULL,
              media TEXT NOT NULL, normalized_url TEXT NOT NULL DEFAULT '',
              collector TEXT NOT NULL DEFAULT '', source_type TEXT NOT NULL DEFAULT '',
              collection_status TEXT NOT NULL DEFAULT '', reliability_tier TEXT NOT NULL DEFAULT '',
              markets TEXT NOT NULL DEFAULT '', visible INTEGER NOT NULL, parsed_at TEXT NOT NULL
            );
            """
        )
        metadata = json.dumps(
            {"markets": ["US"], "tickers": ["QA"], "tags": ["qa-contract"], "collector": "manual"},
            separators=(",", ":"),
        )
        document_rows = [
            (
                "qa-external-article", str(article_path), "Synthetic external evidence", "QA Wire",
                "2026-07-22", "article", "https://example.invalid/qa-external", 1.0, metadata,
                INJECTED_CLOCK, "EXTERNAL_EVIDENCE_CANARY source-grounded market evidence.", INJECTED_CLOCK,
            ),
            (
                "qa-external-rss", str(rss_path), "Synthetic RSS evidence", "QA RSS",
                "2026-07-22", "rss", "https://example.invalid/qa-rss", 1.0, metadata,
                INJECTED_CLOCK, "EXTERNAL_EVIDENCE_CANARY RSS collection evidence.", INJECTED_CLOCK,
            ),
        ]
        connection.executemany(
            "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", document_rows
        )
        for number, row in enumerate(document_rows):
            chunk_id = f"qa-chunk-{number + 1}"
            connection.execute(
                "INSERT INTO chunks VALUES (?,?,?,?,?)",
                (chunk_id, row[0], 0, row[10], "[0.0,1.0]"),
            )
            connection.execute(
                "INSERT INTO chunks_fts VALUES (?,?,?,?,?)",
                (chunk_id, row[0], row[2], row[3], row[10]),
            )
        stat = rss_path.stat()
        connection.execute(
            "INSERT INTO rss_feed_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rss_path.name, str(rss_path), stat.st_size, stat.st_mtime_ns,
                "Synthetic RSS evidence", "2026-07-22 12:00:00", "2026-07-22T12:00:00Z",
                "https://example.invalid/qa-rss", "EXTERNAL_EVIDENCE_CANARY RSS collection evidence.",
                "QA RSS", "https://example.invalid/qa-rss", "rss", "news",
                "full_text", "1", '["US"]', 1, INJECTED_CLOCK,
            ),
        )


def _seed_runtime_fixtures(extract_root: Path, run_root: Path) -> dict[str, Any]:
    data_dir = extract_root / "data"
    reports_dir = data_dir / "topic-reports"
    articles_dir = extract_root / "research-inbox" / "articles"
    rss_dir = extract_root / "research-inbox" / "rss"
    for directory in (reports_dir, articles_dir, rss_dir):
        directory.mkdir(parents=True, exist_ok=True)

    article_path = articles_dir / "qa-external-evidence.md"
    rss_path = rss_dir / "2026-07-22 12-00-00 - QA RSS - Synthetic RSS evidence.md"
    article_path.write_text(
        "# Synthetic external evidence\n\nEXTERNAL_EVIDENCE_CANARY source-grounded market evidence.\n",
        encoding="utf-8",
    )
    rss_path.write_text(
        "---\ncollector: rss\nsource_type: news\nnormalized_url: https://example.invalid/qa-rss\n"
        "collection_status: full_text\nreliability_tier: 1\nmarkets: [US]\n---\n\n"
        "# Synthetic RSS evidence\n\nEXTERNAL_EVIDENCE_CANARY RSS collection evidence.\n",
        encoding="utf-8",
    )
    index_path = data_dir / "research-index.sqlite3"
    _seed_research_index(index_path, article_path, rss_path)
    _write_json(
        data_dir / "index.json",
        {"generatedAt": INJECTED_CLOCK, "count": 2, "incremental": True, "sqlite": str(index_path)},
    )

    canonical_hash = ""
    report = {
        "id": REPORT_ID,
        "saved": True,
        "filename": f"2026-07-22_qa_contract_{REPORT_ID}.json",
        "date": "2026-07-22",
        "generatedAt": INJECTED_CLOCK,
        "topicKey": "qa_contract",
        "reportType": "custom_research",
        "topicLabel": "QA Contract Research",
        "title": "QA Contract Research — 2026-07-22",
        "markdown": (
            "# QA Contract Research\n\n## 핵심 결론\n"
            "EXTERNAL_EVIDENCE_CANARY는 합성 외부 근거이며 투자 판단용 실제 데이터가 아닙니다.\n\n"
            "## 반대 근거와 불확실성\n합성 fixture이므로 실제 시장 일반화가 불가능합니다.\n\n"
            "## 참고자료\n- [Synthetic external evidence](https://example.invalid/qa-external)\n"
        ),
        "topicPlan": {
            "topic": "QA Contract Research", "reportType": "custom_research", "userIntent": "fixture verification",
            "researchQuestions": ["외부 근거와 가설 레이어가 분리되는가?"],
            "analysisAxes": [{"key": "layering", "label": "Layering", "questions": ["분리되는가?"]}],
            "searchQueries": ["QA synthetic evidence"], "expectedSections": ["핵심 결론", "반대 근거와 불확실성"],
            "dataGapsLikely": ["synthetic-only"],
            "deepResearch": {"falsificationTriggers": ["private canary enters evidence"]},
        },
        "evidencePackSummary": {
            "totalDocs": 2, "roleCounts": {"primary": 2},
            "axisCoverage": {"layering": {"label": "Layering", "count": 2, "level": "covered"}},
            "questionCoverage": {"q1": {"question": "분리되는가?", "count": 2, "level": "covered"}},
            "dataGaps": ["synthetic-only"], "memoryCount": 0,
        },
        "evidenceItems": [
            {
                "id": "qa-external-article", "documentId": "qa-external-article",
                "title": "Synthetic external evidence", "source": "QA Wire", "date": "2026-07-22",
                "role": "primary", "axis": "layering", "confidence": "high",
                "url": "https://example.invalid/qa-external", "artifactType": "topic_report", "artifactId": REPORT_ID,
            }
        ],
        "sourceLedger": [
            {
                "sourceId": "qa-source-1", "title": "Synthetic external evidence", "source": "QA Wire",
                "date": "2026-07-22", "evidenceRole": "primary", "reliability": "fixture",
                "usedInSections": ["핵심 결론"], "url": "https://example.invalid/qa-external",
                "artifactType": "topic_report", "artifactId": REPORT_ID, "path": str(article_path),
                "axisKey": "layering", "researchQuestionId": "q1", "researchRound": 1,
                "sourceLayer": "evidence",
            }
        ],
        "researchResolution": {
            "resolution": {
                "schemaVersion": 1, "collectionId": "sc_00000000-0000-4000-8000-000000000016",
                "collectionRevision": 1, "collectionDefinitionHash": "b" * 64,
                "eligibleTotal": 2, "candidateCap": 20,
                "resolvedCandidateIds": ["qa-external-article", "qa-external-rss"],
                "executionUniverseIds": ["qa-external-article"],
                "selectedEvidenceIds": ["qa-external-article"], "unusableCandidates": [],
                "truncated": False, "providerGenerations": {"indexGeneration": "qa-index-1", "rssGeneration": "qa-rss-1"},
                "inputWatermark": INJECTED_CLOCK,
            },
            "zeroEvidence": {"required": False, "reasonCode": "", "resolutionFingerprint": "c" * 64},
            "resolvedAt": INJECTED_CLOCK,
        },
        "executionProvenance": {
            "schemaVersion": 1, "approvalId": "qa-approval-1", "planHash": "d" * 64,
            "requestedMode": "direct", "attemptedEngine": "api", "finalEngine": "rules",
            "fallbackReason": "engine_failed", "adapter": "auto", "executedAt": INJECTED_CLOCK,
        },
        "marketStateResolution": {
            "policy": "include_current", "requestedScope": "US", "resolvedScope": "US",
            "injected": True, "reason": "current_injected",
            "ref": {
                "snapshotId": "mss_qa_fixture", "sourceKind": "snapshot", "scope": "US",
                "asOf": INJECTED_CLOCK, "status": "current", "freshnessReason": "within_window",
                "inputWatermark": INJECTED_CLOCK, "relevantEvidenceWatermark": INJECTED_CLOCK,
                "invalidWatermarkRows": 0, "resolvedAt": INJECTED_CLOCK, "layer": "source-grounded",
                "summary": "MARKET_CONTEXT_CANARY",
            },
        },
        "dataGaps": [{"id": "qa-gap-1", "severity": "info", "description": "Synthetic fixture only", "suggestedAction": "Use real evidence", "resolved": False, "artifactId": REPORT_ID}],
        "quality": {
            "score": 92, "grade": "A", "status": "pass", "warnings": ["synthetic fixture"],
            "suggestedFixes": [], "sourceGrounding": {"status": "pass"},
        },
        "qualityPreflight": {"status": "ready", "synthetic": True},
        "qualityGeneration": {"mode": "diagnose_only", "repairApplied": False, "warnings": []},
        "checkpoints": [{"id": "qa-checkpoint-1", "label": "Verify layer separation", "status": "open", "artifactId": REPORT_ID}],
        "marketTape": {"asOf": INJECTED_CLOCK, "status": "snapshot"},
        "generation": {"mode": "rules", "message": "Synthetic fixture", "generatedAt": INJECTED_CLOCK},
        "sources": [{"source": "QA Wire", "date": "2026-07-22", "title": "Synthetic external evidence", "url": "https://example.invalid/qa-external", "path": str(article_path)}],
        "docCount": 2,
        "memoryCount": 0,
        "userContext": "HYPOTHESIS_ONLY_CANARY",
        "canonicalRevision": {"number": 1, "hash": canonical_hash},
        "personalOverlay": {
            "markdown": "## Personal Overlay\n\nHYPOTHESIS_ONLY_CANARY는 가설이며 외부 근거가 아닙니다.",
            "stale": False, "staleReason": "", "canonicalRevision": {"number": 1, "hash": canonical_hash},
            "linkedNotes": [], "counterEvidence": ["Synthetic evidence cannot validate a real thesis"],
            "contradictions": [], "uncertainties": ["No real market data"], "personalQuestions": ["What real evidence is needed?"],
        },
    }
    canonical_hash = _canonical_content_hash(report)
    report["canonicalRevision"] = {
        "number": 1, "hash": canonical_hash, "updatedAt": INJECTED_CLOCK, "lastOperationId": None,
    }
    report["personalOverlay"]["canonicalRevision"] = {"number": 1, "hash": canonical_hash}
    report_path = reports_dir / report["filename"]
    _write_json(report_path, report)

    collection_path = data_dir / "smart-collections.json"
    collection = {
        "schemaVersion": 1, "storeRevision": 1, "updatedAt": INJECTED_CLOCK,
        "collections": [{
            "id": "sc_00000000-0000-4000-8000-000000000016", "revision": 1,
            "createdAt": INJECTED_CLOCK, "updatedAt": INJECTED_CLOCK,
            "name": "QA External Evidence", "query": "EXTERNAL_EVIDENCE_CANARY", "market": "US",
            "sources": ["qa wire", "qa rss"], "tickers": [], "tags": ["qa-contract"],
        }],
    }
    _write_json(collection_path, collection)

    adapters_dir = run_root / "fixtures" / "adapters"
    adapters_dir.mkdir(parents=True, exist_ok=True)
    direct_adapter = adapters_dir / "fake-direct-http-500.json"
    cli_adapter = adapters_dir / ("fake-cli-unavailable.cmd" if os.name == "nt" else "fake-cli-unavailable.sh")
    _write_json(direct_adapter, {"transport": "qa_fault_proxy", "fault": "http-500", "expectedRequests": 1})
    if os.name == "nt":
        cli_adapter.write_text("@echo off\r\nexit /b 127\r\n", encoding="utf-8")
    else:
        cli_adapter.write_text("#!/bin/sh\nexit 127\n", encoding="utf-8")
        cli_adapter.chmod(0o700)
    long_script = extract_root / "exec"
    login_script = extract_root / "login"
    if os.name == "nt":
        # The product deliberately invokes adapters with shell=False.  Batch
        # files therefore cannot be the cancellable child on Windows.  Python
        # executes this marker-owned `exec` file because it is the first
        # argument produced by the normal Codex adapter command.
        long_cli = adapters_dir / "python-long.exe"
        shutil.copy2(sys.executable, long_cli)
        long_script.write_text(
            "import time\ntime.sleep(30)\nprint('{\\\"status\\\":\\\"done\\\"}')\n",
            encoding="utf-8",
        )
        login_script.write_text("print('authenticated')\n", encoding="utf-8")
    else:
        long_cli = adapters_dir / "fake-cli-long-running.sh"
        long_cli.write_text(
            "#!/bin/sh\n[ \"$1\" = \"--version\" ] && { echo 'qa-long-cli 1.0'; exit 0; }\n"
            "[ \"$1\" = \"login\" ] && exit 0\nsleep 30\nprintf '%s\\n' '{\"status\":\"done\"}'\n",
            encoding="utf-8",
        )
        long_cli.chmod(0o700)
        long_script = long_cli
        login_script.write_text("authenticated\n", encoding="utf-8")
    clock_path = run_root / "fixtures" / "injected-clock.json"
    _write_json(clock_path, {"now": INJECTED_CLOCK, "marketStateRef": report["marketStateResolution"]["ref"]})
    market_states = _seed_market_state_fixtures(run_root / "fixtures" / "market-state")

    # GEN-F1 is a real extracted-package variant, not an empty stand-in.  Copy
    # after normal fixtures are installed, then remove only the copied index.
    missing_root = run_root / "packages" / "g1"
    shutil.copytree(extract_root, missing_root)
    missing_index = missing_root / "data" / "research-index.sqlite3"
    missing_index.unlink()
    missing_manifest = run_root / "gen-f1-manifest.json"

    return {
        "reportPath": str(report_path),
        "articlePath": str(article_path),
        "rssPath": str(rss_path),
        "indexPath": str(index_path),
        "collectionPath": str(collection_path),
        "directAdapter": str(direct_adapter),
        "cliAdapter": str(cli_adapter),
        "longCliAdapter": str(long_cli),
        "longCliScript": str(long_script),
        "loginCliScript": str(login_script),
        "clockPath": str(clock_path),
        "marketStates": market_states,
        "missingIndexRoot": str(missing_root),
        "missingIndexPath": str(missing_index),
        "missingManifestPath": str(missing_manifest),
    }


def _seed_market_state_fixtures(root: Path) -> dict[str, dict[str, str]]:
    fixtures: dict[str, dict[str, str]] = {}
    snapshots = {
        "current": ("mss_qa_current", "2026-07-22T11:00:00Z"),
        "stale": ("mss_qa_stale", "2026-07-18T00:00:00Z"),
    }
    for name, (snapshot_id, as_of) in snapshots.items():
        directory = root / name
        directory.mkdir(parents=True, exist_ok=True)
        market_db = directory / "market.sqlite3"
        with sqlite3.connect(market_db) as connection:
            connection.execute("CREATE TABLE market_state_snapshots (payload_json TEXT, status TEXT, as_of TEXT)")
            payload = {"id": snapshot_id, "asOf": as_of, "inputWatermarks": {"US": None}}
            connection.execute(
                "INSERT INTO market_state_snapshots VALUES (?, 'active', ?)",
                (json.dumps(payload, separators=(",", ":")), as_of),
            )
        fixtures[name] = {"marketDb": str(market_db), "researchDb": str(directory / "research.sqlite3")}

    fallback_dir = root / "fallback"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    fallback_db = fallback_dir / "market.sqlite3"
    with sqlite3.connect(fallback_db) as connection:
        connection.execute("CREATE TABLE market_narrative_states (status TEXT, updated_at TEXT)")
        connection.execute("INSERT INTO market_narrative_states VALUES ('active','2026-07-22T10:00:00Z')")
    fixtures["fallback"] = {
        "marketDb": str(fallback_db), "researchDb": str(fallback_dir / "research.sqlite3")
    }

    empty_dir = root / "empty"
    empty_dir.mkdir(parents=True, exist_ok=True)
    empty_db = empty_dir / "market.sqlite3"
    with sqlite3.connect(empty_db):
        pass
    fixtures["empty"] = {"marketDb": str(empty_db), "researchDb": str(empty_dir / "research.sqlite3")}
    return fixtures


def command_prepare(args: argparse.Namespace) -> int:
    artifact = args.artifact.resolve()
    run_root = _safe_attempt_dir(args.attempt_dir)
    attempt_id, marker = _claim_attempt_dir(run_root)
    selected = list(SCENARIO_SETS[args.scenario_set])
    if args.route_exposure == "hidden" and "DOC-H1" in selected:
        _fail("DOC_H1_HIDDEN_PRE_EXPOSURE", "DOC-H1 requires an exposed-route fixture")

    packages = run_root / "packages"
    extraction = packages / args.scenario_set
    if extraction.exists():
        _fail("ATTEMPT_ALREADY_PREPARED", f"Extraction root already exists: {extraction}", EXIT_OWNERSHIP)
    artifact_sha256 = _sha256(artifact) if artifact.is_file() else _fail("INVALID_ARTIFACT", str(artifact))
    extract_root = _safe_extract(artifact, extraction)
    build = _read_build(extract_root)
    workspace_identity = _workspace_identity(attempt_id, str(artifact_sha256), extract_root)
    port = _reserve_port()
    proxy_port = _reserve_port()
    while proxy_port == port:
        proxy_port = _reserve_port()
    base_url = f"http://127.0.0.1:{port}"
    report_url_id = urllib.parse.quote(REPORT_ID, safe="")

    fixture_dir = run_root / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    seeded = _seed_runtime_fixtures(extract_root, run_root)
    sentinel = extract_root / "data" / "manual-pack-sentinel.bin"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_bytes(b"FOLIO-QA-MANUAL-PACK-SENTINEL\n")
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "attemptId": attempt_id,
        "createdAt": _utc_now(),
        "routeExposure": args.route_exposure,
        "runRoot": str(run_root),
        "ownershipMarker": str(marker),
        "artifact": {"path": str(artifact), "sha256": artifact_sha256},
        "artifactSha256": artifact_sha256,
        "build": build,
        "buildCommit": build["commit"],
        "extractRoot": str(extract_root),
        "workspaceIdentity": workspace_identity,
        "port": port,
        "proxyPort": proxy_port,
        "baseUrl": base_url,
        "healthExpected": {
            "status": "ok",
            "version": build["version"],
            "commit": build["commit"],
            "workspaceIdentity": workspace_identity,
        },
        "scenarioSet": args.scenario_set,
        "scenarioSets": SCENARIO_SETS,
        "selectedScenarioIds": selected,
        "restartScenarios": [item for item in RESTART_SCENARIOS if item in selected],
        "phases": _phases(selected),
        "fixtures": {
            "reportId": REPORT_ID,
            "externalCanary": "EXTERNAL_EVIDENCE_CANARY",
            "hypothesisCanary": "HYPOTHESIS_ONLY_CANARY",
            "marketCanary": "MARKET_CONTEXT_CANARY",
            "privateCanaries": list(PRIVATE_CANARIES),
        },
        "reportId": REPORT_ID,
        "fixtureIdentity": {
            "manualPackSentinel": {"path": str(sentinel), "sha256": _sha256(sentinel)},
            "savedReport": {"path": seeded["reportPath"], "id": REPORT_ID},
            "missingIndex": {
                "root": seeded["missingIndexRoot"], "path": seeded["missingIndexPath"],
                "manifestPath": seeded["missingManifestPath"], "expectedExists": False
            },
            "externalEvidence": {
                "articlePath": seeded["articlePath"], "rssPath": seeded["rssPath"],
                "indexPath": seeded["indexPath"], "collectionPath": seeded["collectionPath"],
            },
            "adapters": {"direct": seeded["directAdapter"], "cli": seeded["cliAdapter"]},
            "injectedClock": {"path": seeded["clockPath"], "value": INJECTED_CLOCK},
        },
        "runtimeEnvironment": {
            "AGENT_CLI_PROVIDER": "codex",
            "FOLIO_AGENT_CODEX_COMMAND": seeded["longCliAdapter"],
        },
        "scenarioFixtures": {
            "GEN-F1": {
                "root": seeded["missingIndexRoot"], "missingIndex": seeded["missingIndexPath"],
                "manifest": seeded["missingManifestPath"],
            },
            "GEN-F2": {
                "directFault": seeded["directAdapter"], "cliExecutable": seeded["cliAdapter"],
                "proxyUrl": f"http://127.0.0.1:{proxy_port}",
            },
            "AG-H1": {
                "longRunningCli": seeded["longCliAdapter"], "longRunningScript": seeded["longCliScript"],
                "loginScript": seeded["loginCliScript"],
            },
            "WB-H1": {"proposalsDir": str(extract_root / "data" / "agent-proposals")},
            "MS-H1": {"clock": seeded["clockPath"], "states": seeded["marketStates"]},
            "DR-H1": {"index": seeded["indexPath"], "article": seeded["articlePath"]},
            "COL-H1": {"collection": seeded["collectionPath"], "rss": seeded["rssPath"]},
            "NT-H1": {
                "helper": "scripts/qa_note_thesis_intelligence.py",
                "syntheticOnly": True,
            },
            "SC-H2": {
                "helper": "scripts/qa_smart_collection_workspace.py",
                "syntheticOnly": True,
            },
            "IC-H1": {
                "helper": "scripts/qa_investment_context.py",
                "syntheticOnly": True,
            },
        },
        "urls": {
            "health": f"{base_url}/api/health",
            "root": f"{base_url}/",
            "deepResearch": f"{base_url}/#/deep-research",
            "report": f"{base_url}/#/deep-research/{report_url_id}",
            "home": f"{base_url}/#/home",
            "docs": f"{base_url}/#/docs",
        },
        "selectors": _scenario_selectors(selected),
        "requiredEvidencePaths": _required_evidence_paths(selected),
        "processesStarted": False,
        "launchMode": "app_main",
    }
    manifest_path = run_root / "fixture-manifest.json"
    _write_json(manifest_path, manifest)
    variant = json.loads(json.dumps(manifest))
    variant_root = Path(seeded["missingIndexRoot"])
    variant_port = _reserve_port()
    while variant_port in {port, proxy_port}:
        variant_port = _reserve_port()
    variant_identity = _workspace_identity(attempt_id, str(artifact_sha256), variant_root)
    manifest["auxiliaryPorts"] = [variant_port]
    variant_base = f"http://127.0.0.1:{variant_port}"
    variant.update(
        {
            "extractRoot": str(variant_root),
            "workspaceIdentity": variant_identity,
            "port": variant_port,
            "baseUrl": variant_base,
            "healthExpected": {
                "status": "ok", "version": build["version"], "commit": build["commit"],
                "workspaceIdentity": variant_identity,
            },
            "urls": {
                "health": f"{variant_base}/api/health",
                "root": f"{variant_base}/",
                "deepResearch": f"{variant_base}/#/deep-research",
                "report": f"{variant_base}/#/deep-research/{report_url_id}",
                "home": f"{variant_base}/#/home",
                "docs": f"{variant_base}/#/docs",
            },
            "processesStarted": False,
            "launchMode": "asgi_no_startup_index",
        }
    )
    variant["auxiliaryPorts"] = [port]
    _write_json(manifest_path, manifest)
    _write_json(Path(seeded["missingManifestPath"]), variant)
    print(str(manifest_path))
    if not args.manifest_only:
        args.manifest = manifest_path
        return command_start(args)
    return EXIT_OK


def _health(url: str, timeout: float = 2.0) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except (OSError, urllib.error.URLError, UnicodeError) as exc:
        _fail("HEALTH_UNREACHABLE", f"Health endpoint failed: {exc}", EXIT_HEALTH)
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        _fail("HEALTH_MALFORMED", f"Health response is not JSON: {exc}", EXIT_HEALTH)
    if not isinstance(value, dict):
        _fail("HEALTH_MALFORMED", "Health response is not an object", EXIT_HEALTH)
    return value


def _http_json(url: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        _fail("HTTP_JSON_INVALID", f"{url}: {error}")
    if not isinstance(value, dict):
        _fail("HTTP_JSON_INVALID", f"{url}: response is not an object")
    return status, value


def command_probe_gen_f1(args: argparse.Namespace) -> int:
    payload, _ = _load_owned_manifest(args.manifest)
    if payload.get("launchMode") != "asgi_no_startup_index":
        _fail("GEN_F1_LAUNCH_MODE_INVALID", "GEN-F1 must use the normal ASGI deployment seam")
    index_path = Path(payload["extractRoot"]) / "data" / "research-index.sqlite3"
    if index_path.exists():
        _fail("GEN_F1_INDEX_PRESENT", "GEN-F1 index exists before the first request")
    base = str(payload["baseUrl"])
    plan_status, envelope = _http_json(
        f"{base}/api/topic-reports/plan", method="POST", body={"question": "QA missing index"}
    )
    zero = ((envelope.get("preview") or {}).get("zeroEvidence") or {})
    resolution = ((envelope.get("preview") or {}).get("resolution") or {})
    generations = resolution.get("providerGenerations") or {}
    if plan_status != 200 or zero.get("reasonCode") != "no_index" or generations.get("indexGeneration") is not None:
        _fail("GEN_F1_NOT_NO_INDEX", f"Unexpected first preview: {envelope}")
    if index_path.exists():
        _fail("GEN_F1_INDEX_RECREATED", "First plan request recreated the absent index")
    execution = {
        "approvedRequest": envelope["approvedRequest"],
        "approval": {"id": envelope["approval"]["id"], "token": envelope["approval"]["token"]},
        "execution": {"mode": "direct", "adapter": "auto", "fallbackPolicy": "rules_on_engine_failure"},
    }
    unconfirmed_status, unconfirmed = _http_json(f"{base}/api/topic-reports", method="POST", body=execution)
    unconfirmed_zero = ((unconfirmed.get("preview") or {}).get("zeroEvidence") or {})
    if (
        unconfirmed_status != 409 or unconfirmed.get("error") != "evidence_confirmation_required"
        or unconfirmed_zero.get("resolutionFingerprint") != zero.get("resolutionFingerprint")
    ):
        _fail("GEN_F1_CONFIRMATION_GATE_FAILED", f"Unexpected unconfirmed response: {unconfirmed}")
    confirm_status, replacement = _http_json(
        f"{base}/api/topic-reports/confirm-degraded", method="POST",
        body={
            "approvedRequest": envelope["approvedRequest"],
            "approval": {"id": envelope["approval"]["id"], "token": envelope["approval"]["token"]},
            "reasonCode": "no_index", "resolutionFingerprint": zero["resolutionFingerprint"], "confirmed": True,
        },
    )
    replacement_zero = ((replacement.get("preview") or {}).get("zeroEvidence") or {})
    if confirm_status != 200 or replacement_zero.get("reasonCode") != "no_index":
        _fail("GEN_F1_CONFIRM_FAILED", f"Unexpected confirmation: {replacement}")
    reports_dir = Path(payload["extractRoot"]) / "data" / "topic-reports"
    before_reports = {path.resolve() for path in reports_dir.glob("*.json")}
    confirmed_execution = {
        "approvedRequest": replacement["approvedRequest"],
        "approval": {"id": replacement["approval"]["id"], "token": replacement["approval"]["token"]},
        "execution": execution["execution"],
    }
    generate_status, generated = _http_json(f"{base}/api/topic-reports", method="POST", body=confirmed_execution)
    if generate_status != 202 or not isinstance(generated.get("job"), dict):
        _fail("GEN_F1_GENERATE_FAILED", f"Unexpected generation response: {generated}")
    job_id = str(generated["job"].get("id") or "")
    deadline = time.monotonic() + args.timeout
    job: dict[str, Any] = generated["job"]
    while time.monotonic() < deadline and job.get("status") not in {"done", "failed", "cancelled"}:
        time.sleep(0.1)
        status, job = _http_json(f"{base}/api/jobs/{urllib.parse.quote(job_id, safe='')}")
        if status != 200:
            _fail("GEN_F1_JOB_READ_FAILED", job_id)
    expected_job = ("done", "none", "rules", "confirmed_zero_evidence")
    observed_job = tuple(job.get(key) for key in ("status", "attemptedEngine", "finalEngine", "fallbackReason"))
    if observed_job != expected_job:
        _fail("GEN_F1_RULES_FALLBACK_FAILED", f"Unexpected job: {job}")
    after_reports = {path.resolve() for path in reports_dir.glob("*.json")}
    created = sorted(after_reports - before_reports)
    if len(created) != 1:
        _fail("GEN_F1_REPORT_PERSIST_FAILED", f"Expected one report, found {len(created)}")
    report = _read_json(created[0], code="GEN_F1_REPORT_INVALID")
    report_zero = ((report.get("researchResolution") or {}).get("zeroEvidence") or {})
    provenance = report.get("executionProvenance") or {}
    if (
        report_zero.get("reasonCode") != "no_index" or report.get("evidenceItems") != []
        or tuple(provenance.get(key) for key in ("attemptedEngine", "finalEngine", "fallbackReason"))
        != ("none", "rules", "confirmed_zero_evidence")
    ):
        _fail("GEN_F1_REPORT_CONTRACT_FAILED", f"Unexpected report: {created[0]}")
    receipt = {
        "probedAt": _utc_now(), "indexAbsentBefore": True, "indexAbsentAfterPlan": not index_path.exists(),
        "plan": {"status": plan_status, "zeroEvidence": zero, "providerGenerations": generations},
        "unconfirmed": {"status": unconfirmed_status, "error": unconfirmed.get("error"), "zeroEvidence": unconfirmed_zero},
        "confirmed": {"status": confirm_status, "zeroEvidence": replacement_zero},
        "job": job, "reportPath": str(created[0]), "reportProvenance": provenance,
    }
    output = Path(payload["runRoot"]) / "gen-f1-probe.json"
    _write_json(output, receipt)
    print(str(output))
    return EXIT_OK


def _assert_health(payload: dict[str, Any], observed: dict[str, Any], child_pid: int | None = None) -> None:
    if set(observed) != HEALTH_KEYS:
        _fail(
            "HEALTH_IDENTITY_SHAPE_MISMATCH",
            "Health response must contain exactly status, pid, version, commit, and workspaceIdentity",
            EXIT_HEALTH,
        )
    expected = payload["healthExpected"]
    for key in ("status", "version", "commit", "workspaceIdentity"):
        if observed.get(key) != expected.get(key):
            _fail("HEALTH_IDENTITY_MISMATCH", f"Health {key} does not match manifest", EXIT_HEALTH)
    if child_pid is not None and observed.get("pid") != child_pid:
        _fail("HEALTH_PID_MISMATCH", "Health pid is not the owned child pid", EXIT_HEALTH)


def _health_hash(observed: dict[str, Any]) -> str:
    encoded = json.dumps(observed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _epoch_id(
    supervisor_pid: int,
    supervisor_create_time: str | int,
    child_pid: int,
    child_create_time: str | int,
    restart_count: int,
    started_at: str,
) -> str:
    material = "\0".join(
        map(str, (supervisor_pid, supervisor_create_time, child_pid, child_create_time, restart_count, started_at))
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _detached_flags() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
    return {"start_new_session": True}


def command_start(args: argparse.Namespace) -> int:
    payload, manifest_path = _load_owned_manifest(args.manifest)
    port = int(payload["port"])
    if _port_open(port):
        _fail("PORT_ALREADY_IN_USE", f"Port {port} is already open", EXIT_PROCESS)
    run_root = Path(payload["runRoot"])
    state_path = run_root / "server.json"
    if state_path.is_file():
        stale = _read_json(state_path, code="SUPERVISOR_STATE_INVALID")
        if stale.get("state") not in {"stopped", "failed"}:
            _fail("SUPERVISOR_ALREADY_ACTIVE", "Owned supervisor state is not terminal", EXIT_PROCESS)
        _write_json(run_root / "server.previous.json", stale)
        state_path.unlink()
        for name in ("supervisor-control.json", "supervisor-response.json"):
            (run_root / name).unlink(missing_ok=True)
    supervisor = Path(__file__).with_name("qa_server_supervisor.py")
    log_path = Path(payload["runRoot"]) / "supervisor-launch.log"
    with log_path.open("ab") as log:
        subprocess.Popen(
            [sys.executable, str(supervisor), "--manifest", str(manifest_path), "--readiness-timeout", str(args.readiness_timeout)],
            cwd=Path(payload["runRoot"]),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            **_detached_flags(),
        )
    deadline = time.monotonic() + args.readiness_timeout + 2
    state: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        if state_path.is_file():
            state = _read_json(state_path, code="SUPERVISOR_STATE_INVALID")
            if state.get("state") in {"ready", "failed", "stopped"}:
                break
        time.sleep(0.1)
    if not state or state.get("state") != "ready":
        _fail("SUPERVISOR_START_FAILED", f"Supervisor did not become ready: {state}", EXIT_PROCESS)
    observed = _health(payload["urls"]["health"])
    _assert_health(payload, observed, int(state["childPid"]))
    payload["healthObserved"] = observed
    payload["processesStarted"] = True
    payload["serverEpochId"] = state["epochId"]
    payload["epochHistory"] = [state]
    for phase in payload["phases"]:
        if phase["action"] == "pre_restart":
            phase["expectedEpochId"] = state["epochId"]
    _write_json(manifest_path, payload)
    print(json.dumps(state, sort_keys=True))
    return EXIT_OK


def _request_supervisor(
    payload: dict[str, Any], action: str, timeout: float, *, scenario: str | None = None
) -> dict[str, Any]:
    run_root = Path(payload["runRoot"])
    state_path = run_root / "server.json"
    response_path = run_root / "supervisor-response.json"
    if not state_path.is_file():
        _fail("SUPERVISOR_NOT_RUNNING", "Supervisor state is missing", EXIT_PROCESS)
    before = _read_json(state_path, code="SUPERVISOR_STATE_INVALID")
    request_id = uuid.uuid4().hex
    request = {"requestId": request_id, "action": action, "createdAt": _utc_now()}
    if scenario is not None:
        request["scenario"] = scenario
    _write_json(run_root / "supervisor-control.json", request)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state_path.is_file():
            current = _read_json(state_path, code="SUPERVISOR_STATE_INVALID")
            if response_path.is_file():
                response = _read_json(response_path, code="SUPERVISOR_RESPONSE_INVALID")
                if response.get("requestId") == request_id:
                    return current
            if action == "stop" and current.get("state") == "stopped":
                return current
            if action == "restart" and int(current.get("restartCount", 0)) > int(before.get("restartCount", 0)):
                return current
        time.sleep(0.1)
    _fail("SUPERVISOR_REQUEST_TIMEOUT", f"Supervisor did not complete {action}", EXIT_PROCESS)


def command_restart(args: argparse.Namespace) -> int:
    payload, manifest_path = _load_owned_manifest(args.manifest)
    run_root = Path(payload["runRoot"])
    before = _read_json(run_root / "server.json", code="SUPERVISOR_STATE_INVALID")
    if args.scenario not in payload.get("restartScenarios", []):
        _fail("RESTART_SCENARIO_NOT_ALLOWED", args.scenario, EXIT_PROCESS)
    completed = len(payload.get("restartReceipts", []))
    if completed >= len(payload["restartScenarios"]) or payload["restartScenarios"][completed] != args.scenario:
        _fail("RESTART_SCENARIO_ORDER_INVALID", args.scenario, EXIT_PROCESS)
    state = _request_supervisor(payload, "restart", args.timeout, scenario=args.scenario)
    receipt_number = int(state["restartCount"])
    receipt_path = run_root / f"restart-{receipt_number}-receipt.json"
    receipt = _read_json(receipt_path, code="RESTART_RECEIPT_MISSING")
    receipts = list(payload.get("restartReceipts", []))
    receipts.append(receipt)
    payload["restartReceipts"] = receipts
    payload["serverEpochId"] = state["epochId"]
    payload.setdefault("epochHistory", []).append(state)
    matching = [
        phase for phase in payload["phases"]
        if phase["scenario"] == args.scenario and phase["action"] == "post_restart"
    ]
    if len(matching) != 1 or matching[0].get("expectedEpochId") is not None:
        _fail("RESTART_PHASE_ALREADY_BOUND", args.scenario, EXIT_PROCESS)
    if receipt.get("oldEpochId") != before.get("epochId") or receipt.get("newEpochId") != state.get("epochId"):
        _fail("RESTART_RECEIPT_IDENTITY_MISMATCH", args.scenario, EXIT_PROCESS)
    matching[0]["expectedEpochId"] = state["epochId"]
    observed = _health(payload["urls"]["health"])
    _assert_health(payload, observed, int(state["childPid"]))
    payload["healthObserved"] = observed
    _write_json(manifest_path, payload)
    print(json.dumps(receipt, sort_keys=True))
    return EXIT_OK


def command_stop(args: argparse.Namespace) -> int:
    payload, manifest_path = _load_owned_manifest(args.manifest)
    state_path = Path(payload["runRoot"]) / "server.json"
    if state_path.is_file():
        state = _read_json(state_path, code="SUPERVISOR_STATE_INVALID")
        if state.get("state") != "stopped":
            state = _request_supervisor(payload, "stop", args.timeout)
            print(json.dumps(state, sort_keys=True))
        supervisor_pid = int(state.get("supervisorPid", 0))
        supervisor_create_time = str(state.get("supervisorCreateTime", ""))
        if not _wait_process_gone(supervisor_pid, supervisor_create_time, args.timeout):
            _fail("SUPERVISOR_STOP_TIMEOUT", "Supervisor remained alive after stopped state", EXIT_PROCESS)
        _write_json(
            Path(payload["runRoot"]) / "server-stop-receipt.json",
            {
                "supervisorPid": supervisor_pid, "supervisorCreateTime": supervisor_create_time,
                "supervisorExited": True, "stoppedAt": _utc_now(),
            },
        )
    payload["processesStarted"] = False
    _write_json(manifest_path, payload)
    return EXIT_OK


def _wait_process_gone(pid: int, expected_create_time: str, timeout: float) -> bool:
    if pid <= 0 or not expected_create_time:
        return True
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            if _process_create_time(pid) != expected_create_time:
                return True
        except (OSError, ProcessLookupError):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def _process_create_time(pid: int) -> str:
    if os.name == "nt":
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            raise ProcessLookupError(pid)
        creation, exit_time, kernel, user = (wintypes.FILETIME() for _ in range(4))
        try:
            if not kernel32.GetProcessTimes(
                handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel), ctypes.byref(user)
            ):
                raise OSError(ctypes.get_last_error(), "GetProcessTimes")
            return str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
        finally:
            kernel32.CloseHandle(handle)
    return Path(f"/proc/{pid}/stat").read_text(encoding="ascii").rsplit(")", 1)[1].split()[19]


def _terminate_pid(pid: int, expected_create_time: str) -> None:
    if pid <= 0:
        return
    try:
        if _process_create_time(pid) != expected_create_time:
            _fail("PROXY_PID_IDENTITY_MISMATCH", "Refusing to kill a reused proxy PID", EXIT_PROXY)
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10, check=False)
        else:
            os.killpg(pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        pass


def command_proxy_start(args: argparse.Namespace) -> int:
    payload, manifest_path = _load_owned_manifest(args.manifest)
    run_root = Path(payload["runRoot"])
    state_path = run_root / "proxy.json"
    receipt_path = run_root / "proxy-stop-receipt.json"
    if receipt_path.is_file():
        receipt = _read_json(receipt_path, code="PROXY_STOP_RECEIPT_INVALID")
        try:
            old_alive = _process_create_time(int(receipt.get("pid", 0))) == str(receipt.get("createTime", ""))
        except (OSError, ProcessLookupError):
            old_alive = False
        if old_alive or _port_open(int(receipt.get("port", 0))):
            _fail("PROXY_STOP_RECEIPT_NOT_TERMINAL", "Prior proxy receipt is not terminal", EXIT_PROXY)
        receipt_path.unlink()
    if state_path.is_file():
        old = _read_json(state_path, code="PROXY_STATE_INVALID")
        if _port_open(int(old.get("port", 0))):
            _fail("PROXY_ALREADY_RUNNING", "Fault proxy is already running", EXIT_PROXY)
    proxy = Path(__file__).with_name("qa_fault_proxy.py")
    log_path = Path(payload["runRoot"]) / "fault-proxy.log"
    with log_path.open("ab") as log:
        subprocess.Popen(
            [sys.executable, str(proxy), "--manifest", str(manifest_path), "--fault", args.fault],
            cwd=Path(payload["runRoot"]), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            close_fds=True, **_detached_flags(),
        )
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if state_path.is_file():
            state = _read_json(state_path, code="PROXY_STATE_INVALID")
            if state.get("state") == "ready" and _port_open(int(state["port"])):
                print(json.dumps(state, sort_keys=True))
                return EXIT_OK
        time.sleep(0.1)
    _fail("PROXY_START_FAILED", "Fault proxy did not become ready", EXIT_PROXY)


def command_proxy_stop(args: argparse.Namespace) -> int:
    payload, _ = _load_owned_manifest(args.manifest)
    state_path = Path(payload["runRoot"]) / "proxy.json"
    receipt_path = Path(payload["runRoot"]) / "proxy-stop-receipt.json"
    if receipt_path.is_file():
        receipt = _read_json(receipt_path, code="PROXY_STOP_RECEIPT_INVALID")
        receipt_pid = int(receipt.get("pid", 0))
        receipt_port = int(receipt.get("port", 0))
        try:
            receipt_pid_alive = _process_create_time(receipt_pid) == str(receipt.get("createTime", ""))
        except (OSError, ProcessLookupError):
            receipt_pid_alive = False
        if not receipt_pid_alive and not _port_open(receipt_port):
            return EXIT_OK
    if state_path.is_file():
        state = _read_json(state_path, code="PROXY_STATE_INVALID")
        process = _read_json(Path(payload["runRoot"]) / "proxy-process.json", code="PROXY_PROCESS_INVALID")
        _terminate_pid(int(state.get("pid", 0)), str(process.get("createTime", "")))
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline and _port_open(int(state.get("port", 0))):
            time.sleep(0.1)
        if _port_open(int(state.get("port", 0))):
            _fail("PROXY_STOP_FAILED", "Fault proxy port remained open", EXIT_PROXY)
        _write_json(
            receipt_path,
            {
                "pid": state["pid"], "createTime": process["createTime"], "port": state["port"],
                "stoppedAt": _utc_now(), "portClosed": True,
            },
        )
    return EXIT_OK


def _validate_scenario_contract(payload: dict[str, Any], requested: str) -> None:
    if payload.get("scenarioSets") != SCENARIO_SETS:
        _fail("SCENARIO_SET_CONTRACT_MISMATCH", "Manifest scenario sets are not exact")
    if requested not in SCENARIO_SETS or payload.get("scenarioSet") != requested:
        _fail("SCENARIO_SET_MISMATCH", "Requested scenario set differs from manifest")
    selected = payload.get("selectedScenarioIds")
    if selected != SCENARIO_SETS[requested]:
        if payload.get("routeExposure") == "hidden" and isinstance(selected, list) and "DOC-H1" in selected:
            _fail("DOC_H1_HIDDEN_PRE_EXPOSURE", "Hidden-route evidence includes DOC-H1")
        _fail("SELECTED_SCENARIO_SET_INCOMPLETE", "Selected scenarios are not the exact named set")
    if payload.get("routeExposure") == "hidden" and "DOC-H1" in selected:
        _fail("DOC_H1_HIDDEN_PRE_EXPOSURE", "DOC-H1 cannot run before route exposure")


def _validate_freshness(payload: dict[str, Any]) -> None:
    try:
        created = dt.datetime.fromisoformat(str(payload["createdAt"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        _fail("MALFORMED_CREATED_AT", "createdAt is not a UTC instant")
    now = dt.datetime.now(dt.timezone.utc)
    if created.tzinfo is None:
        _fail("MALFORMED_CREATED_AT", "createdAt lacks timezone")
    if now - created.astimezone(dt.timezone.utc) > ISO_MAX_AGE:
        _fail("STALE_BUNDLE", "Evidence bundle is older than seven days")


def _validate_epochs(payload: dict[str, Any]) -> dict[str, str]:
    phases = payload.get("phases")
    if not isinstance(phases, list):
        _fail("MALFORMED_PHASES", "phases must be a list")
    phase_epochs: dict[str, str] = {}
    for phase in phases:
        if not isinstance(phase, dict) or not all(key in phase for key in ("phaseId", "scenario", "action", "expectedEpochId")):
            _fail("MALFORMED_PHASE", "A phase is incomplete")
        phase_id = str(phase["phaseId"])
        if phase_id in phase_epochs:
            _fail("DUPLICATE_PHASE_ID", phase_id)
        epoch = str(phase["expectedEpochId"])
        phase_epochs[phase_id] = epoch
        if not re.fullmatch(r"[0-9a-f]{64}", epoch):
            _fail("EVIDENCE_EPOCH_MISMATCH", "Phase epoch is not a bound SHA-256 identity")
    history = payload.get("epochHistory")
    if not isinstance(history, list) or not history:
        _fail("EPOCH_HISTORY_MISSING", "Manifest lacks actual server epoch history")
    exact_server_keys = {
        "supervisorPid", "supervisorCreateTime", "childPid", "childCreateTime", "restartCount",
        "epochId", "port", "startedAt", "commandHash", "state",
    }
    for number, server in enumerate(history):
        if not isinstance(server, dict) or set(server) != exact_server_keys or server.get("restartCount") != number:
            _fail("SERVER_IDENTITY_INVALID", "server.json history is incomplete or reordered")
        computed = _epoch_id(
            server["supervisorPid"], server["supervisorCreateTime"], server["childPid"],
            server["childCreateTime"], server["restartCount"], server["startedAt"],
        )
        if server.get("epochId") != computed:
            _fail("EVIDENCE_EPOCH_MISMATCH", "Server epoch hash does not match process identity")
        if number and (
            server["supervisorPid"] != history[0]["supervisorPid"]
            or server["supervisorCreateTime"] != history[0]["supervisorCreateTime"]
            or (server["childPid"], server["childCreateTime"])
            == (history[number - 1]["childPid"], history[number - 1]["childCreateTime"])
        ):
            _fail("EVIDENCE_EPOCH_MISMATCH", "Restart did not preserve supervisor and replace child identity")
    pre_epochs = [phase_epochs[phase["phaseId"]] for phase in phases if phase["action"] == "pre_restart"]
    if any(epoch != history[0]["epochId"] for epoch in pre_epochs):
        _fail("EVIDENCE_EPOCH_MISMATCH", "Pre-restart phases are not bound to the initial epoch")
    post_phases = [phase for phase in phases if phase["action"] == "post_restart"]
    for number, phase in enumerate(post_phases, 1):
        if number >= len(history) or phase["expectedEpochId"] != history[number]["epochId"]:
            _fail("EVIDENCE_EPOCH_MISMATCH", "Post-restart phase is copied or reordered")
    receipts = payload.get("restartReceipts", [])
    if not isinstance(receipts, list):
        _fail("RESTART_RECEIPTS_MALFORMED", "restartReceipts must be a list")
    if len(receipts) != len(history) - 1:
        _fail("RESTART_RECEIPT_ORDER_INVALID", "Restart receipt count differs from epoch history")
    receipt_keys = {"oldEpochId", "newEpochId", "oldChild", "newChild", "triggeredAt", "readyAt", "healthHash"}
    for expected_number, receipt in enumerate(receipts, 1):
        if not isinstance(receipt, dict) or set(receipt) != receipt_keys:
            _fail("RESTART_RECEIPT_ORDER_INVALID", "Restart receipts are missing, copied, or reordered")
        old, new = history[expected_number - 1], history[expected_number]
        if receipt.get("oldEpochId") != old["epochId"] or receipt.get("newEpochId") != new["epochId"]:
            _fail("EVIDENCE_EPOCH_MISMATCH", "Restart receipt epoch chain is invalid")
        if receipt.get("oldChild") != {"pid": old["childPid"], "createTime": old["childCreateTime"]}:
            _fail("EVIDENCE_EPOCH_MISMATCH", "Restart old child identity is invalid")
        if receipt.get("newChild") != {"pid": new["childPid"], "createTime": new["childCreateTime"]}:
            _fail("EVIDENCE_EPOCH_MISMATCH", "Restart new child identity is invalid")
        try:
            triggered = dt.datetime.fromisoformat(str(receipt["triggeredAt"]).replace("Z", "+00:00"))
            ready = dt.datetime.fromisoformat(str(receipt["readyAt"]).replace("Z", "+00:00"))
        except ValueError:
            _fail("RESTART_RECEIPT_TIME_INVALID", "Restart receipt timestamp is invalid")
        if triggered > ready:
            _fail("RESTART_RECEIPT_TIME_INVALID", "Restart readiness predates trigger")
        expected_health = {**payload["healthExpected"], "pid": new["childPid"]}
        if receipt.get("healthHash") != _health_hash(expected_health):
            _fail("RESTART_RECEIPT_HEALTH_MISMATCH", "Restart receipt health hash is invalid")
    return phase_epochs


def _validate_evidence_files(payload: dict[str, Any], phase_epochs: dict[str, str]) -> None:
    run_root = Path(payload["runRoot"]).resolve()
    paths = payload.get("requiredEvidencePaths")
    if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
        _fail("REQUIRED_EVIDENCE_PATHS_MALFORMED", "requiredEvidencePaths must be strings")
    if paths != _required_evidence_paths(payload["selectedScenarioIds"]):
        _fail("REQUIRED_EVIDENCE_PATHS_INCOMPLETE", "Evidence paths are not the exact selected scenario ledger")
    history_by_epoch = {item["epochId"]: item for item in payload["epochHistory"]}
    receipt_by_new_epoch = {item["newEpochId"]: item for item in payload.get("restartReceipts", [])}
    next_trigger: dict[str, str] = {
        item["oldEpochId"]: item["triggeredAt"] for item in payload.get("restartReceipts", [])
    }
    json_identity = {
        "artifactSha256", "buildCommit", "capturedAt", "baseUrl", "viewport", "scenario",
        "phaseId", "serverEpochId", "childPid", "childCreateTime", "restartCount",
    }
    phase_coverage = {phase_id: 0 for phase_id in phase_epochs}
    for relative in paths:
        path = (run_root / relative).resolve()
        if not _is_relative_to(path, run_root) or not path.is_file():
            _fail("REQUIRED_EVIDENCE_MISSING", f"Missing or unsafe evidence path: {relative}")
        if path.suffix.lower() == ".png":
            sidecar = path.with_suffix(".json")
            if not sidecar.is_file():
                _fail("PNG_SIDECAR_MISSING", str(sidecar))
            metadata = _read_json(sidecar, code="PNG_SIDECAR_MALFORMED")
            if metadata.get("pngSha256") != _sha256(path):
                _fail("PNG_SHA256_MISMATCH", str(path))
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(canary in text for canary in PRIVATE_CANARIES):
            _fail("PRIVATE_CANARY_EXPOSED", f"Private canary found in {relative}")
        if path.suffix.lower() == ".json":
            evidence = _read_json(path, code="EVIDENCE_JSON_MALFORMED")
            if not json_identity.issubset(evidence):
                _fail("EVIDENCE_IDENTITY_MISSING", relative)
            epoch = str(evidence["serverEpochId"])
            if phase_epochs.get(str(evidence["phaseId"])) != epoch or evidence["scenario"] != relative.split("/", 1)[0]:
                _fail("EVIDENCE_EPOCH_MISMATCH", relative)
            phase_coverage[str(evidence["phaseId"])] += 1
            server = history_by_epoch.get(epoch)
            if server is None or (
                evidence["childPid"] != server["childPid"]
                or evidence["childCreateTime"] != server["childCreateTime"]
                or evidence["restartCount"] != server["restartCount"]
            ):
                _fail("EVIDENCE_EPOCH_MISMATCH", relative)
            try:
                captured = dt.datetime.fromisoformat(str(evidence["capturedAt"]).replace("Z", "+00:00"))
                lower_text = receipt_by_new_epoch.get(epoch, {}).get("readyAt", server["startedAt"])
                lower = dt.datetime.fromisoformat(str(lower_text).replace("Z", "+00:00"))
                upper_text = next_trigger.get(epoch)
                upper = dt.datetime.fromisoformat(str(upper_text).replace("Z", "+00:00")) if upper_text else None
            except ValueError:
                _fail("EVIDENCE_CAPTURE_TIME_INVALID", relative)
            if captured < lower or (upper is not None and captured >= upper):
                _fail("EVIDENCE_CAPTURE_TIME_INVALID", relative)
    uncovered = [phase_id for phase_id, count in phase_coverage.items() if count == 0]
    if uncovered:
        _fail("EVIDENCE_PHASE_COVERAGE_MISSING", ", ".join(uncovered))
    for relative in [item for item in paths if item.endswith("/result.json")]:
        result_path = run_root / relative
        result = _read_json(result_path, code="RESULT_JSON_MALFORMED")
        scenario = relative.split("/", 1)[0]
        if result.get("scenario") != scenario or result.get("passed") is not True:
            _fail("SCENARIO_RESULT_INVALID", scenario)
        if "cancellation" not in result:
            _fail("CANCELLATION_CONTRACT_MISSING", scenario)
        phase_id = str(result.get("phaseId", ""))
        if phase_id not in phase_epochs or result.get("serverEpochId") != phase_epochs[phase_id]:
            _fail("EVIDENCE_EPOCH_MISMATCH", scenario)
        if result.get("privateCanariesAbsent") is not True:
            _fail("PRIVATE_CANARY_ASSERTION_MISSING", scenario)


def command_verify(args: argparse.Namespace) -> int:
    payload, _ = _load_owned_manifest(args.manifest)
    _validate_scenario_contract(payload, args.scenario_set)
    _validate_freshness(payload)
    phase_epochs = _validate_epochs(payload)
    if "healthObserved" in payload:
        _assert_health(payload, payload["healthObserved"])
    _validate_evidence_files(payload, phase_epochs)
    print("QA020_EVIDENCE_VERIFIED")
    return EXIT_OK


def _package_probe(extract_root: Path, source: str, arguments: list[str], environment: dict[str, str]) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-c", source, *arguments],
        cwd=extract_root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    if completed.returncode != 0:
        _fail(
            "FIXTURE_PROBE_FAILED",
            f"Packaged probe exited {completed.returncode}: {(completed.stderr or completed.stdout)[-500:]}",
        )
    try:
        value = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        _fail("FIXTURE_PROBE_MALFORMED", f"Packaged probe returned malformed JSON: {exc}")
    if not isinstance(value, dict):
        _fail("FIXTURE_PROBE_MALFORMED", "Packaged probe did not return an object")
    return value


def _validate_generation_probe(generation: dict[str, Any]) -> None:
    expected_provenance = {
        "direct": ("direct", "api", "rules", "engine_failed"),
        "cli": ("cli", "cli", "rules", "engine_unavailable"),
    }
    for mode, expected in expected_provenance.items():
        provenance = generation.get(mode, {}).get("provenance", {})
        observed = tuple(provenance.get(key) for key in (
            "requestedMode", "attemptedEngine", "finalEngine", "fallbackReason"
        ))
        if observed != expected or generation.get(mode, {}).get("saved") is not False:
            _fail("FULL_GENERATION_PROVENANCE_FAILED", f"{mode}: {observed}")
    if generation.get("sameEvidence") is not True or generation.get("sameResolution") is not True:
        _fail("FULL_GENERATION_INPUT_DRIFT", "Direct and CLI did not use identical approved evidence")
    if generation.get("orphanReport") is not False or generation.get("orphanJob") is not False:
        _fail("FULL_GENERATION_ORPHAN", f"Unexpected persistence: {generation}")


def command_probe_fixtures(args: argparse.Namespace) -> int:
    payload, _ = _load_owned_manifest(args.manifest)
    extract_root = Path(payload["extractRoot"])
    environment = os.environ.copy()
    environment.update({str(key): str(value) for key, value in payload["runtimeEnvironment"].items()})

    cli_source = (
        "import json; from features.agent_mode.bridge import _probe_adapter; "
        "print(json.dumps(_probe_adapter('codex'), ensure_ascii=False))"
    )
    unavailable_environment = environment.copy()
    unavailable_environment["FOLIO_AGENT_CODEX_COMMAND"] = str(
        payload["scenarioFixtures"]["GEN-F2"]["cliExecutable"]
    )
    cli = _package_probe(extract_root, cli_source, [], unavailable_environment)
    if cli.get("installed") is not False or cli.get("available") is not False:
        _fail("CLI_UNAVAILABLE_SEAM_FAILED", "Configured marker CLI was not genuinely unavailable")

    states = payload["scenarioFixtures"]["MS-H1"]["states"]
    market_source = """
import json, sys
from datetime import datetime
from pathlib import Path
from features.market_memory.market_state_ref import MarketStateRefQuery, resolve_market_state_ref
fixtures = json.loads(sys.argv[1]); now = datetime.fromisoformat(sys.argv[2].replace('Z', '+00:00'))
out = {}
for name, paths in fixtures.items():
    out[name] = resolve_market_state_ref(MarketStateRefQuery(
        market_db_path=Path(paths['marketDb']), research_db_path=Path(paths['researchDb']),
        scope='US', now=now,
    ))
print(json.dumps(out, ensure_ascii=False))
"""
    market = _package_probe(extract_root, market_source, [json.dumps(states), INJECTED_CLOCK], environment)
    observed_states = {name: value.get("status") for name, value in market.items()}
    if observed_states != {"current": "current", "stale": "stale", "fallback": "fallback", "empty": "empty"}:
        _fail("MARKET_STATE_TRUTH_TABLE_FAILED", f"Unexpected statuses: {observed_states}")

    proxy_url = str(payload["scenarioFixtures"]["GEN-F2"]["proxyUrl"])
    direct_environment = environment.copy()
    direct_environment.update(
        {
            "OPENAI_API_KEY": "qa-synthetic-not-a-secret",
            "LLM_PROVIDER": "openai",
            "AI_AGENT_ENABLED": "1",
            "USE_LLM_ANALYSIS": "1",
            "LLM_TIMEOUT_SECONDS": "5",
            "HTTPS_PROXY": proxy_url,
            "https_proxy": proxy_url,
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
    )
    generation_source = """
import hashlib, json, os, sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID
from features.agent_mode.bridge import invalidate_bridge_status
from features.topic_report import approved_generation as generation
from features.topic_report.approved_generation import ApprovedGenerationInput, build_approved_report
from features.topic_report.approved_research import admit_research, prepare_market_state
from features.topic_report.approved_request import ApprovedRequestRuntime, ApprovedRequestService
from features.topic_report.approved_schema import PlanRequest
from features.topic_report.resolution_schema import ProviderGenerations, ResearchPreview, ResolutionSnapshotV1, ZeroEvidence

NOW = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)
root = Path(sys.argv[1]); root.mkdir(parents=True, exist_ok=True); unavailable = sys.argv[2]
def empty_resolution():
    return ResolutionSnapshotV1(
        schemaVersion=1, collectionId=None, collectionRevision=None, collectionDefinitionHash=None,
        eligibleTotal=None, candidateCap=None, truncated=False, resolvedCandidateIds=[],
        executionUniverseIds=[], unusableCandidates=[], selectedEvidenceIds=[],
        providerGenerations=ProviderGenerations(indexGeneration='a' * 64, rssGeneration=None),
        inputWatermark='b' * 64,
    )
runtime = ApprovedRequestRuntime(
    dataDir=root, clock=lambda: NOW, entropy=lambda size: bytes(range(size)),
    uuidFactory=lambda: UUID('12345678-1234-4567-9234-567812345678'),
    resolver=lambda _approved: empty_resolution(),
)
approved = ApprovedRequestService(runtime).plan(PlanRequest(
    question='QA synthetic evidence layer separation', userContext='HYPOTHESIS_ONLY_CANARY',
    deepResearch=True, marketStatePolicy='exclude',
)).approvedRequest
document = {
    'id':'qa-external-article', 'title':'Synthetic external evidence', 'source':'QA Wire',
    'date':'2026-07-22', 'url':'https://example.invalid/qa-external',
    'path':'research-inbox/articles/qa-external-evidence.md',
    'snippet':'EXTERNAL_EVIDENCE_CANARY with counter-risk uncertainty.',
}
research = admit_research(approved, empty_resolution(),
    search_docs=lambda _queries, _limit, _allowed: [document],
    search_memories=lambda _keywords, _limit: [])
preview = ResearchPreview(
    resolution=research.resolution, resolvedAt='2026-07-22T12:00:00Z',
    zeroEvidence=ZeroEvidence(required=False, reasonCode=None, resolutionFingerprint=None),
)
market = prepare_market_state(root, approved, lambda: NOW)
generation._materials = lambda request, rows: (
    generation._topic(request), {'tickers':{}, 'asOf':request.asOfDate}, {'ok':False}
)
def command(mode, approval):
    return ApprovedGenerationInput(
        approved=approved, approvalId=approval, requestedMode=mode,
        adapter='codex' if mode == 'cli' else 'auto', preview=preview, research=research, marketState=market,
    )
reports_before = sorted(str(path) for path in Path('data/topic-reports').glob('*.json'))
jobs_before = hashlib.sha256(Path('data/jobs-v2.json').read_bytes()).hexdigest() if Path('data/jobs-v2.json').is_file() else None
direct = build_approved_report(command('direct', 'apr_00000000-0000-4000-8000-000000000021'), job_id=None, clock=lambda: NOW)
os.environ['FOLIO_AGENT_CODEX_COMMAND'] = unavailable
invalidate_bridge_status()
packs_before = set(Path('data/agent-packs/topic_report').glob('*.json'))
cli = build_approved_report(command('cli', 'apr_00000000-0000-4000-8000-000000000022'), job_id=None, clock=lambda: NOW)
for path in set(Path('data/agent-packs/topic_report').glob('*.json')) - packs_before:
    path.unlink()
reports_after = sorted(str(path) for path in Path('data/topic-reports').glob('*.json'))
jobs_after = hashlib.sha256(Path('data/jobs-v2.json').read_bytes()).hexdigest() if Path('data/jobs-v2.json').is_file() else None
def result(outcome):
    return {'provenance':outcome.report['executionProvenance'], 'evidenceItems':outcome.report['evidenceItems'],
            'researchResolution':outcome.report['researchResolution'], 'saved':outcome.report['saved']}
print(json.dumps({'direct':result(direct), 'cli':result(cli),
                  'sameEvidence':direct.report['evidenceItems'] == cli.report['evidenceItems'],
                  'sameResolution':direct.report['researchResolution'] == cli.report['researchResolution'],
                  'orphanReport':reports_before != reports_after, 'orphanJob':jobs_before != jobs_after}))
"""
    generation = _package_probe(
        extract_root, generation_source,
        [str(Path(payload["runRoot"]) / "fixtures" / "approved-generation"), str(payload["scenarioFixtures"]["GEN-F2"]["cliExecutable"])],
        direct_environment,
    )
    _validate_generation_probe(generation)
    direct = {"failed": True, "statusCode": 500, "cause": "EngineFailedError"}

    proposal_source = """
import json
from pathlib import Path
from features.agent_mode.chat import create_revision_proposal, get_proposal
from features.common.canonical_report_state import revision
report_id = __import__('sys').argv[1]
report_path, current = next(
    (path, value) for path in Path('data/topic-reports').glob('*.json')
    for value in [json.loads(path.read_text(encoding='utf-8'))] if value.get('id') == report_id
)
seed_revision = revision(current)
if seed_revision is None or seed_revision[0] != 1:
    raise RuntimeError('seeded canonical revision is invalid')
markdown = current['markdown']
out = {}
for key, suffix in (
    ('happyApprove', 'QA_WB_H1_APPROVE_CANDIDATE'),
    ('rejectReplay', 'QA_WB_F1_REJECT_CANDIDATE'),
    ('staleConflict', 'QA_WB_F1_STALE_CANDIDATE'),
):
    created = create_revision_proposal(
        kind='topic_report', report_id=report_id, market_scope='', message='QA ' + key,
        summary='Marker-owned canonical revision proposal: ' + key,
        revised_markdown=markdown + '\\n\\n' + suffix, current_markdown=markdown,
        adapter='qa-fixture', model='qa-fixture',
    )
    stored = get_proposal(created['id'])
    out[key] = {'id': created['id'], 'status': stored['status'], 'reportId': stored['reportId']}
print(json.dumps(out))
"""
    proposal = _package_probe(extract_root, proposal_source, [REPORT_ID], environment)
    if set(proposal) != {"happyApprove", "rejectReplay", "staleConflict"} or any(
        item.get("status") != "pending" or item.get("reportId") != REPORT_ID for item in proposal.values()
    ):
        _fail("PROPOSAL_CREATE_SEAM_FAILED", f"Unexpected proposal result: {proposal}")

    long_environment = environment.copy()
    long_environment["FOLIO_AGENT_CODEX_COMMAND"] = str(
        payload["scenarioFixtures"]["AG-H1"]["longRunningCli"]
    )
    cancellation_source = """
import json, os, time
from features.agent_mode import bridge
from features.common.jobs import FUTURES, get_job, submit_job

def worker(*, progress=None, job_id='', adapter=''):
    selected = {'id': 'codex', 'executable': os.environ['FOLIO_AGENT_CODEX_COMMAND']}
    return {'generationMode': 'llm_cli', 'adapter': 'codex', 'mode': 'answer',
            'output': bridge._invoke_agent_cli(selected, 'wait', 25, job_id)}

job = submit_job('agent_bridge', 'QA cancellable adapter', worker, pass_job_id=True,
                 dedicated_thread=True, adapter='codex')
job_id = job['id']
deadline = time.time() + 8
while time.time() < deadline:
    with bridge._PROCESS_LOCK:
        proc = bridge._RUNNING_PROCESSES.get(job_id)
    if proc is not None and (get_job(job_id) or {}).get('status') == 'running':
        break
    time.sleep(0.05)
else:
    raise RuntimeError('long-running adapter never registered')
cancel = bridge.cancel_agent_task(job_id)
deadline = time.time() + 8
observed = get_job(job_id)
while time.time() < deadline and observed.get('status') != 'cancelled':
    time.sleep(0.05); observed = get_job(job_id)
future = FUTURES.get(job_id)
if hasattr(future, 'join'):
    future.join(timeout=1)
with bridge._PROCESS_LOCK:
    registered = job_id in bridge._RUNNING_PROCESSES
print(json.dumps({'id': job_id, 'cancelAccepted': cancel.get('cancelled'), 'status': observed.get('status'),
                  'registryCleared': not registered, 'childExited': proc.poll() is not None}))
"""
    cancellation = _package_probe(extract_root, cancellation_source, [], long_environment)
    if cancellation.get("cancelAccepted") is not True or cancellation.get("status") != "cancelled" or (
        cancellation.get("registryCleared") is not True or cancellation.get("childExited") is not True
    ):
        _fail("LONG_TASK_CANCELLATION_FAILED", f"Unexpected cancellation result: {cancellation}")

    missing = payload["fixtureIdentity"]["missingIndex"]
    variant_root = Path(missing["root"])
    gen_f1 = {
        "appPresent": (variant_root / "app.py").is_file(),
        "buildPresent": (variant_root / "BUILD.json").is_file(),
        "indexAbsent": not Path(missing["path"]).exists(),
        "manifest": missing["manifestPath"],
    }
    if gen_f1 != {**gen_f1, "appPresent": True, "buildPresent": True, "indexAbsent": True}:
        _fail("GEN_F1_VARIANT_INVALID", f"Missing-index package variant is invalid: {gen_f1}")

    receipt = {
        "probedAt": _utc_now(), "extractRoot": str(extract_root), "direct": direct, "cli": cli,
        "generation": generation, "marketState": market, "proposal": proposal,
        "cancellation": cancellation, "genF1": gen_f1,
    }
    output = Path(args.output).resolve() if args.output else Path(payload["runRoot"]) / "fixture-probe.json"
    if not _is_relative_to(output, Path(payload["runRoot"]).resolve()):
        _fail("PROBE_OUTPUT_OUTSIDE_RUN_ROOT", "Fixture probe output must remain marker-owned", EXIT_OWNERSHIP)
    _write_json(output, receipt)
    print(str(output))
    return EXIT_OK


def command_cleanup(args: argparse.Namespace) -> int:
    payload, _ = _load_owned_manifest(args.manifest)
    run_root = Path(payload["runRoot"]).resolve()
    try:
        if (run_root / "proxy.json").is_file():
            command_proxy_stop(args)
        if (run_root / "server.json").is_file():
            command_stop(args)
    finally:
        ports = [
            int(payload.get("port", 0)), int(payload.get("proxyPort", 0)),
            *(int(port) for port in payload.get("auxiliaryPorts", [])),
        ]
        if any(port and _port_open(port) for port in ports):
            _fail("CLEANUP_PORT_STILL_OPEN", "An owned port remained open", EXIT_PROCESS)
        shutil.rmtree(run_root)
    print(f"Removed owned attempt root: {run_root}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare, supervise, fault, and verify Folio Board QA-020 evidence.")
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="Extract a synthetic release artifact and emit fixture-manifest.json.")
    prepare.add_argument("--artifact", required=True, type=Path)
    prepare.add_argument("--attempt-dir", required=True, type=Path)
    prepare.add_argument("--scenario-set", required=True, choices=tuple(SCENARIO_SETS))
    prepare.add_argument("--route-exposure", choices=("hidden", "exposed"), default="hidden")
    prepare.add_argument("--manifest-only", action="store_true", help="Prepare fixtures without starting processes.")
    prepare.add_argument("--readiness-timeout", type=float, default=30.0)
    prepare.set_defaults(handler=command_prepare)

    for name, handler in (("start", command_start), ("restart", command_restart), ("stop", command_stop)):
        sub = commands.add_parser(name, help=f"{name.title()} the marker-owned packaged server.")
        sub.add_argument("--manifest", required=True, type=Path)
        if name == "start":
            sub.add_argument("--readiness-timeout", type=float, default=30.0)
        else:
            sub.add_argument("--timeout", type=float, default=30.0)
        if name == "restart":
            sub.add_argument("--scenario", required=True, choices=tuple(RESTART_SCENARIOS))
        sub.set_defaults(handler=handler)

    cleanup = commands.add_parser("cleanup", help="Stop owned process trees and remove the marker-owned attempt root.")
    cleanup.add_argument("--manifest", required=True, type=Path)
    cleanup.add_argument("--timeout", type=float, default=30.0)
    cleanup.set_defaults(handler=command_cleanup)

    verify = commands.add_parser("verify-evidence", help="Fail closed on malformed, stale, copied, or private evidence.")
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--scenario-set", required=True, choices=tuple(SCENARIO_SETS))
    verify.set_defaults(handler=command_verify)

    proxy_start = commands.add_parser("proxy-start", help="Start the host-only deterministic fault proxy.")
    proxy_start.add_argument("--manifest", required=True, type=Path)
    proxy_start.add_argument("--fault", required=True, choices=("disconnect", "timeout", "http-500", "passthrough"))
    proxy_start.add_argument("--timeout", type=float, default=10.0)
    proxy_start.set_defaults(handler=command_proxy_start)

    proxy_stop = commands.add_parser("proxy-stop", help="Stop the marker-owned fault proxy tree.")
    proxy_stop.add_argument("--manifest", required=True, type=Path)
    proxy_stop.add_argument("--timeout", type=float, default=10.0)
    proxy_stop.set_defaults(handler=command_proxy_stop)

    probe = commands.add_parser("probe-fixtures", help="Execute normal packaged seams against marker fixtures.")
    probe.add_argument("--manifest", required=True, type=Path)
    probe.add_argument("--output", type=Path)
    probe.set_defaults(handler=command_probe_fixtures)

    gen_f1_probe = commands.add_parser("probe-gen-f1", help="Exercise the absent-index packaged HTTP flow.")
    gen_f1_probe.add_argument("--manifest", required=True, type=Path)
    gen_f1_probe.add_argument("--timeout", type=float, default=30.0)
    gen_f1_probe.set_defaults(handler=command_probe_gen_f1)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.handler(args))
    except HarnessError as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("INTERRUPTED: operation cancelled", file=sys.stderr)
        return EXIT_PROCESS


if __name__ == "__main__":
    raise SystemExit(main())
