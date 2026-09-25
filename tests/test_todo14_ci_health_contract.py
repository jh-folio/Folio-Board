from __future__ import annotations

import json
import os
import re
from pathlib import Path

import app as folio_app
from scripts.verify_release import verify_release


ROOT = Path(__file__).resolve().parents[1]
HEALTH_KEYS = {"status", "pid", "version", "commit", "workspaceIdentity"}
QA_HELPERS = ("scripts/qa_server_supervisor.py", "scripts/qa_fault_proxy.py")


def test_api_health_is_exact_minimal_private_identity() -> None:
    matching_routes = [route for route in folio_app.fastapi_app.routes if getattr(route, "path", None) == "/api/health"]
    assert len(matching_routes) == 1
    route = matching_routes[0]
    assert route.methods == {"GET"}
    payload = route.endpoint()
    assert set(payload) == HEALTH_KEYS
    assert payload["status"] == "ok"
    assert payload["pid"] == os.getpid()
    assert re.fullmatch(r"\d+\.\d+\.\d+", payload["version"])
    assert re.fullmatch(r"[0-9a-f]{40}", payload["commit"])
    assert re.fullmatch(r"[0-9a-f]{64}", payload["workspaceIdentity"])

    serialized = json.dumps(payload, sort_keys=True).lower()
    for forbidden in ("api_key", "secret", "token", "data/", "research-inbox", str(ROOT).lower()):
        assert forbidden not in serialized


def test_ci_build_fails_on_tracked_and_untracked_react_bundle_drift() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    build_at = workflow.index("npm run build")
    tail = workflow[build_at:]

    assert re.search(r"git\s+diff\s+--exit-code\s+--\s+(?:\.\./)?public/react/?", tail)
    assert re.search(r"git\s+status\s+--porcelain(?:=v?\d+)?[^\n]*public/react/?", tail)
    assert "timeout-minutes:" in workflow[workflow.index("web:") :]


def test_qa_identity_and_epoch_rejection_hooks_are_present() -> None:
    orchestrator = ROOT / "scripts" / "qa_020.py"
    supervisor = ROOT / "scripts" / "qa_server_supervisor.py"

    assert orchestrator.is_file()
    assert supervisor.is_file()
    source = orchestrator.read_text(encoding="utf-8") + supervisor.read_text(encoding="utf-8")
    for contract_field in (
        "artifactSha256",
        "buildCommit",
        "workspaceIdentity",
        "serverEpochId",
        "childPid",
        "childCreateTime",
        "restartCount",
    ):
        assert contract_field in source
    for rejection_axis in ("workspace", "commit", "epoch", "pid"):
        assert re.search(rf"(?:reject|mismatch|wrong|stale)[^\n]{{0,100}}{rejection_axis}|{rejection_axis}[^\n]{{0,100}}(?:reject|mismatch|wrong|stale)", source, re.IGNORECASE)


def test_qa_helpers_are_explicitly_unpackageable(tmp_path: Path) -> None:
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    packaged_inputs = set(manifest["runtimeFiles"]) | set(manifest["runtimeDirectories"])
    assert "scripts" not in packaged_inputs
    assert not (set(QA_HELPERS) & packaged_inputs)

    package = tmp_path / "FolioBoard-test"
    package.mkdir()
    (package / "VERSION").write_text("0.2.0\n", encoding="utf-8")
    (package / "BUILD.json").write_text(
        json.dumps({"version": "0.2.0", "commit": "a" * 40, "builtAt": "2026-07-22T00:00:00Z"}),
        encoding="utf-8",
    )
    (package / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for rel in manifest["runtimeFiles"]:
        path = package / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    for rel in manifest["runtimeDirectories"] + manifest["emptyDirectories"]:
        (package / rel).mkdir(parents=True, exist_ok=True)
    leaked = package / QA_HELPERS[0]
    leaked.parent.mkdir(parents=True, exist_ok=True)
    leaked.write_text("# must never ship\n", encoding="utf-8")

    issues = verify_release(
        package,
        package / "release-manifest.json",
        run_gitleaks=False,
        expected_commit="a" * 40,
    )
    assert any("qa_server_supervisor.py" in issue for issue in issues)


def test_qa_harness_is_attempt_owned_and_never_opens_real_user_roots() -> None:
    helper_paths = [ROOT / "scripts" / "qa_020.py", *(ROOT / rel for rel in QA_HELPERS)]
    assert all(path.is_file() for path in helper_paths)
    helper_source = "\n".join(path.read_text(encoding="utf-8") for path in helper_paths)
    assert ".folio-qa-owned" in helper_source
    assert "attemptDir" in helper_source or "attempt_dir" in helper_source
    assert not re.search(r"ROOT\s*/\s*[\"'](?:data|research-inbox)[\"']", helper_source)


def test_product_has_no_qa_switch() -> None:
    product_files = [ROOT / "app.py", ROOT / "public" / "app.js"]
    product_files.extend(path for path in (ROOT / "features").rglob("*.py") if "tests" not in path.parts)
    product_files.extend(
        path for path in (ROOT / "web" / "src").rglob("*") if path.suffix in {".ts", ".tsx", ".js", ".jsx"}
    )
    product_source = [file.read_text(encoding="utf-8", errors="replace") for file in product_files]
    joined = "\n".join(product_source)
    assert not re.search(r"FOLIO_QA|QA_FAULT|qa[_-]?mode|/__qa|/api/qa", joined, re.IGNORECASE)
