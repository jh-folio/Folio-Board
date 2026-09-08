from __future__ import annotations

import importlib.util
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
QA_020 = ROOT / "scripts" / "qa_020.py"
SUPERVISOR = ROOT / "scripts" / "qa_server_supervisor.py"
FAULT_PROXY = ROOT / "scripts" / "qa_fault_proxy.py"
NOTE_THESIS_QA = ROOT / "scripts" / "qa_note_thesis_intelligence.py"
SMART_WORKSPACE_QA = ROOT / "scripts" / "qa_smart_collection_workspace.py"
INVESTMENT_CONTEXT_QA = ROOT / "scripts" / "qa_investment_context.py"

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
FULL = [*PRE_EXPOSURE, *POST_EXPOSURE]


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=10,
        check=False,
    )


def _load_qa_020():
    assert QA_020.is_file(), "TODO14_MISSING_QA_020"
    spec = importlib.util.spec_from_file_location("qa_020_contract_target", QA_020)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_script(path: Path, name: str):
    assert path.is_file()
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest(tmp_path: Path) -> tuple[Path, dict]:
    run_root = tmp_path / "attempt" / "task-16"
    run_root.mkdir(parents=True)
    marker = run_root / ".folio-qa-owned"
    marker.write_text(
        json.dumps({"attemptId": "attempt-contract", "state": "prepared"}),
        encoding="utf-8",
    )
    def server(number: int) -> dict:
        started = f"2099-07-22T00:00:0{number}Z"
        body = {
            "supervisorPid": 111,
            "supervisorCreateTime": "supervisor-create",
            "childPid": 200 + number,
            "childCreateTime": f"child-create-{number}",
            "restartCount": number,
            "port": 49152,
            "startedAt": started,
            "commandHash": "e" * 64,
            "state": "ready",
        }
        body["epochId"] = hashlib.sha256(
            "\0".join(
                map(
                    str,
                    (
                        body["supervisorPid"],
                        body["supervisorCreateTime"],
                        body["childPid"],
                        body["childCreateTime"],
                        body["restartCount"],
                        body["startedAt"],
                    ),
                )
            ).encode("utf-8")
        ).hexdigest()
        return body

    epoch_history = [server(number) for number in range(4)]
    health_expected = {
        "status": "ok",
        "version": "0.2.0",
        "commit": "b" * 40,
        "workspaceIdentity": "c" * 64,
    }
    restart_receipts = []
    for number in range(1, 4):
        old, new = epoch_history[number - 1], epoch_history[number]
        observed = {**health_expected, "pid": new["childPid"]}
        restart_receipts.append(
            {
                "oldEpochId": old["epochId"],
                "newEpochId": new["epochId"],
                "oldChild": {"pid": old["childPid"], "createTime": old["childCreateTime"]},
                "newChild": {"pid": new["childPid"], "createTime": new["childCreateTime"]},
                "triggeredAt": f"2099-07-22T00:00:0{number * 2 - 1}Z",
                "readyAt": f"2099-07-22T00:00:0{number * 2}Z",
                "healthHash": hashlib.sha256(
                    json.dumps(observed, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
            }
        )

    payload = {
        "schemaVersion": 1,
        "attemptId": "attempt-contract",
        "createdAt": "2099-07-22T00:00:00Z",
        "routeExposure": "hidden",
        "runRoot": str(run_root.resolve()),
        "ownershipMarker": str(marker.resolve()),
        "artifact": {
            "path": str((tmp_path / "FolioBoard-v0.2.0.zip").resolve()),
            "sha256": "a" * 64,
        },
        "build": {"version": "0.2.0", "commit": "b" * 40},
        "extractRoot": str((run_root / "packages" / "preExposure").resolve()),
        "workspaceIdentity": "c" * 64,
        "port": 49152,
        "baseUrl": "http://127.0.0.1:49152",
        "healthExpected": health_expected,
        "scenarioSet": "preExposure",
        "scenarioSets": {
            "preExposure": PRE_EXPOSURE,
            "postExposure": POST_EXPOSURE,
            "full": FULL,
        },
        "selectedScenarioIds": PRE_EXPOSURE,
        "restartScenarios": ["DR-H1", "WB-H1", "WL-H1"],
        "phases": [
            *[
                {
                    "phaseId": f"{scenario}:pre",
                    "scenario": scenario,
                    "action": "pre_restart",
                    "expectedEpochId": epoch_history[0]["epochId"],
                }
                for scenario in PRE_EXPOSURE
            ],
            *[
                {
                    "phaseId": f"{scenario}:post",
                    "scenario": scenario,
                    "action": "post_restart",
                    "expectedEpochId": epoch_history[index + 1]["epochId"],
                }
                for index, scenario in enumerate(["DR-H1", "WB-H1", "WL-H1"])
            ],
        ],
        "fixtures": {
            "reportId": "2026-07-22:qa-contract:fixture",
            "externalCanary": "EXTERNAL_EVIDENCE_CANARY",
            "hypothesisCanary": "HYPOTHESIS_ONLY_CANARY",
            "marketCanary": "MARKET_CONTEXT_CANARY",
            "privateCanaries": ["PROMPT_INJECTION_CANARY", "PRIVATE_CONTEXT_CANARY"],
        },
        "urls": {
            "health": "http://127.0.0.1:49152/api/health",
            "deepResearch": "http://127.0.0.1:49152/#/deep-research",
            "report": "http://127.0.0.1:49152/#/deep-research/2026-07-22%3Aqa-contract%3Afixture",
        },
        "selectors": {
            "question": "[data-qa=dr-question]",
            "preview": "[data-qa=dr-preview]",
            "plan": "[data-qa=dr-plan]",
            "continue": "[data-qa=dr-continue]",
            "report": "[data-qa=dr-report]",
        },
        "requiredEvidencePaths": [
            path
            for scenario in PRE_EXPOSURE
            for path in (
                [
                    f"{scenario}/{viewport}/{name}"
                    for viewport in ("1440", "768", "390")
                    for name in (
                        "screenshot.png", "screenshot.json", "console.json", "network.json",
                        "dom.json", "api-before.json", "api-after.json", "result.json",
                    )
                ]
                if scenario in {"DR-H1", "RP-H1", "NT-H1", "SC-H2", "IC-H1", "REL-H1"}
                else [f"{scenario}/result.json"]
            ) + ([f"{scenario}/post-restart-result.json"] if scenario in {"DR-H1", "WB-H1", "WL-H1"} else [])
        ],
        "epochHistory": epoch_history,
        "restartReceipts": restart_receipts,
    }
    path = run_root / "fixture-manifest.json"
    for relative in payload["requiredEvidencePaths"]:
        evidence_path = run_root / relative
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        parts = Path(relative).parts
        scenario = parts[0]
        viewport = parts[1] if len(parts) == 3 else None
        if evidence_path.suffix == ".png":
            evidence_path.write_bytes(b"contract-png")
            continue
        body = {
            "artifactSha256": "a" * 64,
            "buildCommit": "b" * 40,
            "capturedAt": "2099-07-22T00:00:00.500000Z",
            "baseUrl": "http://127.0.0.1:49152",
            "viewport": viewport,
            "scenario": scenario,
            "phaseId": f"{scenario}:pre",
            "serverEpochId": epoch_history[0]["epochId"],
            "childPid": epoch_history[0]["childPid"],
            "childCreateTime": epoch_history[0]["childCreateTime"],
            "restartCount": 0,
        }
        if evidence_path.name == "post-restart-result.json":
            restart_number = ["DR-H1", "WB-H1", "WL-H1"].index(scenario) + 1
            epoch = epoch_history[restart_number]
            body.update(
                {
                    "capturedAt": f"2099-07-22T00:00:0{restart_number * 2}.500000Z",
                    "phaseId": f"{scenario}:post",
                    "serverEpochId": epoch["epochId"],
                    "childPid": epoch["childPid"],
                    "childCreateTime": epoch["childCreateTime"],
                    "restartCount": restart_number,
                }
            )
        if evidence_path.name == "screenshot.json":
            body["pngSha256"] = hashlib.sha256(b"contract-png").hexdigest()
        if evidence_path.name in {"result.json", "post-restart-result.json"}:
            body.update(
                {
                    "passed": True,
                    "cancellation": "not_applicable",
                    "privateCanariesAbsent": True,
                }
            )
        evidence_path.write_text(json.dumps(body), encoding="utf-8")
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, payload


def _write_manifest(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _mutate_bundle(path: Path, payload: dict, mutation: str) -> None:
    run_root = Path(payload["runRoot"])
    if mutation == "hidden_doc":
        payload["selectedScenarioIds"] = [*PRE_EXPOSURE, "DOC-H1"]
    elif mutation == "incomplete_set":
        payload["selectedScenarioIds"] = PRE_EXPOSURE[:-1]
    elif mutation == "stale_bundle":
        payload["createdAt"] = "2020-01-01T00:00:00Z"
    elif mutation == "copied_epoch":
        post_phase = next(phase for phase in payload["phases"] if phase["action"] == "post_restart")
        post_phase["expectedEpochId"] = payload["epochHistory"][0]["epochId"]
    elif mutation == "reordered_epoch":
        payload["restartReceipts"] = [
            {"number": 2, "oldEpochId": "epoch-2", "newEpochId": "epoch-3"},
            {"number": 1, "oldEpochId": "epoch-1", "newEpochId": "epoch-2"},
        ]
    elif mutation == "png_mismatch":
        png = run_root / "DR-H1" / "1440" / "screenshot.png"
        png.parent.mkdir(exist_ok=True)
        png.write_bytes(b"not-the-sidecar-hash")
        sidecar = png.with_suffix(".json")
        sidecar.write_text(
            json.dumps({"pngSha256": hashlib.sha256(b"other-bytes").hexdigest()}),
            encoding="utf-8",
        )
    elif mutation == "private_canary":
        result = run_root / "CTX-F1" / "result.json"
        result.write_text(result.read_text(encoding="utf-8") + "PRIVATE_CONTEXT_CANARY", encoding="utf-8")
    elif mutation == "cancellation":
        result = run_root / "AG-H1" / "result.json"
        body = json.loads(result.read_text(encoding="utf-8"))
        body.pop("cancellation")
        result.write_text(json.dumps(body), encoding="utf-8")
    elif mutation == "unowned_root":
        Path(payload["ownershipMarker"]).unlink()
    elif mutation == "wrong_health":
        payload["healthObserved"] = {
            **payload["healthExpected"],
            "pid": 4444,
            "commit": "d" * 40,
        }
    elif mutation == "extra_health":
        payload["healthObserved"] = {
            **payload["healthExpected"],
            "pid": payload["epochHistory"][-1]["childPid"],
            "misleading": "ok",
        }
    elif mutation == "missing_post_coverage":
        for relative in payload["requiredEvidencePaths"]:
            if relative.endswith(".json"):
                evidence = run_root / relative
                body = json.loads(evidence.read_text(encoding="utf-8"))
                body["phaseId"] = f"{body['scenario']}:pre"
                body["serverEpochId"] = payload["epochHistory"][0]["epochId"]
                body["childPid"] = payload["epochHistory"][0]["childPid"]
                body["childCreateTime"] = payload["epochHistory"][0]["childCreateTime"]
                body["restartCount"] = 0
                body["capturedAt"] = "2099-07-22T00:00:00.500000Z"
                evidence.write_text(json.dumps(body), encoding="utf-8")
    else:  # pragma: no cover - protects the fixture itself
        raise AssertionError(mutation)
    _write_manifest(path, payload)


def test_prepare_help_exposes_manifest_only_contract() -> None:
    result = _run(QA_020, "prepare", "--help")

    assert result.returncode == 0, "TODO14_PREPARE_HELP_MISSING\n" + result.stderr
    for flag in ("--artifact", "--attempt-dir", "--scenario-set", "--manifest-only"):
        assert flag in result.stdout


def test_prepare_seeds_runtime_visible_strict_topic_report_and_wired_fixtures(tmp_path: Path) -> None:
    artifact = tmp_path / "FolioBoard-v0.2.0.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("FolioBoard/VERSION", "0.2.0\n")
        archive.writestr(
            "FolioBoard/BUILD.json",
            json.dumps(
                {
                    "version": "0.2.0",
                    "commit": "a" * 40,
                    "builtAt": "2026-07-22T00:00:00Z",
                }
            ),
        )
        archive.writestr("FolioBoard/app.py", "# fixture app\n")
    attempt = tmp_path / "attempt"
    result = _run(
        QA_020,
        "prepare",
        "--artifact",
        str(artifact),
        "--attempt-dir",
        str(attempt),
        "--scenario-set",
        "preExposure",
        "--manifest-only",
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((attempt / "fixture-manifest.json").read_text(encoding="utf-8"))
    extract_root = Path(manifest["extractRoot"])
    report_id = manifest["reportId"]
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,160}", report_id)
    saved = list((extract_root / "data" / "topic-reports").glob("*.json"))
    assert len(saved) == 1
    report = json.loads(saved[0].read_text(encoding="utf-8"))
    assert report["id"] == report_id
    assert report["saved"] is True
    assert report["reportType"] == "custom_research"
    assert report["topicPlan"]["reportType"] == "custom_research"
    assert report["executionProvenance"] == {
        "schemaVersion": 1,
        "approvalId": "qa-approval-1",
        "planHash": "d" * 64,
        "requestedMode": "direct",
        "attemptedEngine": "api",
        "finalEngine": "rules",
        "fallbackReason": "engine_failed",
        "adapter": "auto",
        "executedAt": "2026-07-22T12:00:00Z",
    }
    assert set(report["canonicalRevision"]) == {"number", "hash", "updatedAt", "lastOperationId"}
    from features.common.canonical_report_state import canonical_content_hash, revision

    assert report["canonicalRevision"]["hash"] == canonical_content_hash(report)
    assert revision(report) == (1, report["canonicalRevision"]["hash"])
    for key in (
        "markdown",
        "researchResolution",
        "executionProvenance",
        "evidenceItems",
        "sourceLedger",
        "marketStateResolution",
        "quality",
        "checkpoints",
        "personalOverlay",
        "canonicalRevision",
    ):
        assert key in report
    external_json = json.dumps(
        {"markdown": report["markdown"], "evidenceItems": report["evidenceItems"], "sourceLedger": report["sourceLedger"]}
    )
    assert "EXTERNAL_EVIDENCE_CANARY" in external_json
    assert "HYPOTHESIS_ONLY_CANARY" not in external_json
    assert "MARKET_CONTEXT_CANARY" not in external_json
    assert report["userContext"] == "HYPOTHESIS_ONLY_CANARY"
    assert report["marketStateResolution"]["ref"]["summary"] == "MARKET_CONTEXT_CANARY"
    identity = manifest["fixtureIdentity"]
    assert Path(identity["adapters"]["cli"]).is_file()
    assert manifest["runtimeEnvironment"]["FOLIO_AGENT_CODEX_COMMAND"] == manifest["scenarioFixtures"]["AG-H1"]["longRunningCli"]
    assert manifest["runtimeEnvironment"]["FOLIO_AGENT_CODEX_COMMAND"] != identity["adapters"]["cli"]
    assert Path(identity["externalEvidence"]["articlePath"]).is_file()
    assert Path(identity["externalEvidence"]["rssPath"]).is_file()
    assert Path(identity["missingIndex"]["path"]).exists() is False
    missing_root = Path(identity["missingIndex"]["root"])
    assert (missing_root / "app.py").is_file()
    assert (missing_root / "BUILD.json").is_file()
    assert Path(identity["missingIndex"]["manifestPath"]).is_file()
    variant_manifest = json.loads(Path(identity["missingIndex"]["manifestPath"]).read_text(encoding="utf-8"))
    assert manifest["launchMode"] == "app_main"
    assert variant_manifest["launchMode"] == "asgi_no_startup_index"
    assert len(manifest["auxiliaryPorts"]) == 1
    market_states = manifest["scenarioFixtures"]["MS-H1"]["states"]
    assert set(market_states) == {"current", "stale", "fallback", "empty"}
    for fixture in market_states.values():
        assert Path(fixture["marketDb"]).is_file()
    assert manifest["scenarioFixtures"]["GEN-F2"]["proxyUrl"] == (
        f"http://127.0.0.1:{manifest['proxyPort']}"
    )
    assert Path(manifest["scenarioFixtures"]["AG-H1"]["longRunningCli"]).is_file()
    assert manifest["scenarioFixtures"]["AG-H1"]["longRunningCli"] != identity["adapters"]["cli"]
    assert Path(manifest["scenarioFixtures"]["AG-H1"]["longRunningScript"]).is_file()
    assert Path(manifest["scenarioFixtures"]["AG-H1"]["loginScript"]).is_file()
    assert Path(manifest["scenarioFixtures"]["WB-H1"]["proposalsDir"]).parent == extract_root / "data"


def test_lifecycle_help_exposes_fail_closed_commands() -> None:
    result = _run(QA_020, "--help")

    assert result.returncode == 0, "TODO14_LIFECYCLE_CLI_MISSING\n" + result.stderr
    for command in (
        "prepare",
        "start",
        "restart",
        "stop",
        "cleanup",
        "verify-evidence",
        "proxy-start",
        "proxy-stop",
        "probe-fixtures",
        "probe-gen-f1",
    ):
        assert command in result.stdout


def test_proxy_stop_does_not_trust_stale_receipt_when_owned_proxy_is_live(tmp_path: Path, monkeypatch) -> None:
    module = _load_qa_020()
    state = {"pid": 4242, "port": 9876, "state": "ready"}
    process = {"pid": 4242, "createTime": "owned-create-time"}
    (tmp_path / "proxy.json").write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "proxy-process.json").write_text(json.dumps(process), encoding="utf-8")
    (tmp_path / "proxy-stop-receipt.json").write_text(
        json.dumps({"pid": 1111, "createTime": "old", "port": 9876, "portClosed": True}), encoding="utf-8"
    )
    stopped = {"value": False}
    monkeypatch.setattr(module, "_load_owned_manifest", lambda _path: ({"runRoot": str(tmp_path)}, tmp_path / "m.json"))
    monkeypatch.setattr(module, "_port_open", lambda _port: not stopped["value"])
    monkeypatch.setattr(
        module, "_terminate_pid", lambda pid, create: stopped.update(value=(pid, create) == (4242, "owned-create-time"))
    )
    args = type("Args", (), {"manifest": tmp_path / "m.json", "timeout": 0.1})()

    assert module.command_proxy_stop(args) == 0
    assert stopped["value"] is True
    receipt = json.loads((tmp_path / "proxy-stop-receipt.json").read_text(encoding="utf-8"))
    assert receipt["pid"] == 4242
    assert receipt["port"] == 9876
    assert receipt["portClosed"] is True


def test_cleanup_fails_closed_when_variant_port_is_still_open(tmp_path: Path, monkeypatch) -> None:
    module = _load_qa_020()
    payload = {"runRoot": str(tmp_path), "port": 8001, "proxyPort": 8002, "auxiliaryPorts": [8003]}
    monkeypatch.setattr(module, "_load_owned_manifest", lambda _path: (payload, tmp_path / "manifest.json"))
    monkeypatch.setattr(module, "_port_open", lambda port: port == 8003)
    args = type("Args", (), {"manifest": tmp_path / "manifest.json", "timeout": 0.1})()

    with pytest.raises(module.HarnessError, match="owned port remained open"):
        module.command_cleanup(args)
    assert tmp_path.exists()


def test_wait_process_gone_requires_supervisor_identity_to_disappear(monkeypatch) -> None:
    module = _load_qa_020()
    observed = iter(["owned-create-time", "owned-create-time", ProcessLookupError()])
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        module, "_process_create_time",
        lambda _pid: (_ for _ in ()).throw(value) if isinstance((value := next(observed)), Exception) else value,
    )

    assert module._wait_process_gone(4242, "owned-create-time", 1.0) is True
    monkeypatch.setattr(module, "_process_create_time", lambda _pid: "owned-create-time")
    assert module._wait_process_gone(4242, "owned-create-time", 0.0) is False


def test_exact_named_scenario_sets_are_public_contract() -> None:
    module = _load_qa_020()

    assert module.SCENARIO_SETS == {
        "preExposure": PRE_EXPOSURE,
        "postExposure": POST_EXPOSURE,
        "full": FULL,
    }


def test_stage_024_scenario_helpers_and_smoke_matrix_are_pinned() -> None:
    module = _load_qa_020()

    assert {"NT-H1", "SC-H2", "IC-H1"}.issubset(module.VIEWPORT_SCENARIOS)
    for script in (NOTE_THESIS_QA, SMART_WORKSPACE_QA, INVESTMENT_CONTEXT_QA):
        assert script.is_file(), f"TASK41_MISSING_HELPER:{script.name}"
        source = script.read_text(encoding="utf-8")
        assert "def run(source_root: Path, attempt_dir: Path) -> int:" in source
        assert "cleanup-receipt.json" in source
        assert "data/" not in source.split("Never read", maxsplit=1)[0]

    smoke = (ROOT / "docs" / "SMOKE_TESTS.md").read_text(encoding="utf-8")
    for phrase in (
        "Note and Thesis Intelligence",
        "Smart Collection workspace",
        "Investment Context",
        "1440 / 768 / 390",
        "synthetic fixture root",
        "Canonical hash",
        "recommendation",
    ):
        assert phrase in smoke, f"TASK41_SMOKE_MATRIX_MISSING:{phrase}"


def test_common_selectors_match_real_app_shell_classes() -> None:
    module = _load_qa_020()
    selectors = module._scenario_selectors(["GEN-F1"])["GEN-F1"]
    source = (ROOT / "web" / "src" / "app" / "AppShell.tsx").read_text(encoding="utf-8")

    assert selectors["root"] == ".react-shell"
    assert selectors["result"] == ".react-shell-main"
    assert 'className={`react-shell' in source
    assert 'className="react-shell-main"' in source


def test_full_generation_probe_receipt_requires_two_exact_independent_modes() -> None:
    module = _load_qa_020()
    receipt = {
        "direct": {"saved": False, "provenance": {
            "requestedMode": "direct", "attemptedEngine": "api", "finalEngine": "rules",
            "fallbackReason": "engine_failed",
        }},
        "cli": {"saved": False, "provenance": {
            "requestedMode": "cli", "attemptedEngine": "cli", "finalEngine": "rules",
            "fallbackReason": "engine_unavailable",
        }},
        "sameEvidence": True, "sameResolution": True, "orphanReport": False, "orphanJob": False,
    }
    module._validate_generation_probe(receipt)
    receipt["cli"]["provenance"]["attemptedEngine"] = "api"
    with pytest.raises(module.HarnessError, match="cli"):
        module._validate_generation_probe(receipt)


def test_workspace_identity_golden_vector_uses_normative_nul_formula(tmp_path: Path) -> None:
    module = _load_qa_020()
    extract_root = (tmp_path / "packages" / "preExposure" / "FolioBoard").resolve()
    expected = hashlib.sha256(
        f"attempt-golden\0{'a' * 64}\0{extract_root}".encode("utf-8")
    ).hexdigest()

    assert module._workspace_identity("attempt-golden", "a" * 64, extract_root) == expected


def test_server_epoch_golden_vector_uses_process_identity_and_started_at() -> None:
    module = _load_script(SUPERVISOR, "qa_server_supervisor_golden")
    expected = hashlib.sha256(
        "\0".join(
            ["101", "create-supervisor", "202", "create-child", "3", "2026-07-22T00:00:00Z"]
        ).encode("utf-8")
    ).hexdigest()

    assert module.compute_epoch_id(
        101,
        "create-supervisor",
        202,
        "create-child",
        3,
        "2026-07-22T00:00:00Z",
    ) == expected


@pytest.mark.parametrize(
    ("mutation", "expected_exit", "error_code"),
    [
        ("hidden_doc", 4, "DOC_H1_HIDDEN_PRE_EXPOSURE"),
        ("incomplete_set", 4, "SELECTED_SCENARIO_SET_INCOMPLETE"),
        ("stale_bundle", 4, "STALE_BUNDLE"),
        ("copied_epoch", 4, "EVIDENCE_EPOCH_MISMATCH"),
        ("reordered_epoch", 4, "RESTART_RECEIPT_ORDER_INVALID"),
        ("png_mismatch", 4, "PNG_SHA256_MISMATCH"),
        ("private_canary", 4, "PRIVATE_CANARY_EXPOSED"),
        ("cancellation", 4, "CANCELLATION_CONTRACT_MISSING"),
        ("unowned_root", 2, "UNOWNED_RUN_ROOT"),
        ("wrong_health", 3, "HEALTH_IDENTITY_MISMATCH"),
        ("extra_health", 3, "HEALTH_IDENTITY_SHAPE_MISMATCH"),
        ("missing_post_coverage", 4, "EVIDENCE_PHASE_COVERAGE_MISSING"),
    ],
)
def test_verify_evidence_rejects_adversarial_bundle(
    tmp_path: Path, mutation: str, expected_exit: int, error_code: str
) -> None:
    manifest, payload = _manifest(tmp_path)
    try:
        _mutate_bundle(manifest, payload, mutation)
        result = _run(
            QA_020,
            "verify-evidence",
            "--manifest",
            str(manifest),
            "--scenario-set",
            "preExposure",
        )
    finally:
        shutil.rmtree(tmp_path / "attempt", ignore_errors=True)

    assert result.returncode == expected_exit, (
        f"TODO14_{error_code}: expected assertion exit {expected_exit}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert error_code in result.stderr


def test_supervisor_and_fault_proxy_are_host_only_cli_tools() -> None:
    for script, required in (
        (SUPERVISOR, ("--manifest", "--readiness-timeout")),
        (FAULT_PROXY, ("--manifest", "--fault")),
    ):
        result = _run(script, "--help")
        assert result.returncode == 0, f"TODO14_MISSING_HOST_TOOL:{script.name}\n{result.stderr}"
        assert all(flag in result.stdout for flag in required)

    release = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    packaged = set(release["runtimeFiles"])
    assert not packaged.intersection(
        {"scripts/qa_020.py", "scripts/qa_server_supervisor.py", "scripts/qa_fault_proxy.py"}
    )
