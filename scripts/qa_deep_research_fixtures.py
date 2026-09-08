#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run qa_deep_research_fixtures.py
# 3. Or make executable and run:
#      chmod +x qa_deep_research_fixtures.py && ./qa_deep_research_fixtures.py
# ──────────────────

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import textwrap
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from dataclasses import dataclass
from pathlib import Path

JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class Fixture:
    workspace: Path
    data: Path
    inbox: Path
    adapters: Path
    marker: Path
    protected: dict[str, str]


@dataclass(frozen=True, slots=True)
class FakeApi:
    server: ThreadingHTTPServer
    thread: Thread
    modePath: Path
    requests: list[dict[str, JsonValue]]
    url: str


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_tree(source_root: Path, workspace: Path) -> None:
    ignored = shutil.ignore_patterns(
        ".git",
        ".omo",
        ".pytest_cache",
        "__pycache__",
        "node_modules",
        ".env",
        "data",
        "research-inbox",
    )
    shutil.copytree(source_root, workspace, ignore=ignored)


def _init_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
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
            text TEXT NOT NULL, embedding_json TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE chunks_fts USING fts5(chunk_id UNINDEXED, doc_id UNINDEXED, title, source, text);
        CREATE TABLE file_manifest (
            path TEXT PRIMARY KEY, file_signature TEXT NOT NULL, market_relevant INTEGER NOT NULL,
            doc_id TEXT NOT NULL, modified_at TEXT NOT NULL
        );
        CREATE TABLE rss_feed_items (
            filename TEXT PRIMARY KEY, path TEXT NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
            title TEXT NOT NULL, timestamp TEXT NOT NULL, timestamp_sort TEXT NOT NULL, url TEXT NOT NULL,
            description TEXT NOT NULL, media TEXT NOT NULL, normalized_url TEXT NOT NULL DEFAULT '',
            collector TEXT NOT NULL DEFAULT '', source_type TEXT NOT NULL DEFAULT '', collection_status TEXT NOT NULL DEFAULT '',
            reliability_tier TEXT NOT NULL DEFAULT '', markets TEXT NOT NULL DEFAULT '', visible INTEGER NOT NULL,
            parsed_at TEXT NOT NULL
        );
        """
    )
    return connection


def _insert_document(connection: sqlite3.Connection, number: int, *, allowed: bool, duplicate: bool = False) -> None:
    doc_id = "doc-allowed" if allowed else f"doc-off-{number:03d}"
    url = "https://qa.example/allowed" if allowed or duplicate else f"https://qa.example/off/{number:03d}"
    ticker = "QAE" if allowed else "OFF"
    title = "QA Live Alpha Allowed" if allowed else f"QA Alpha Off Filter {number:03d}"
    content = "live alpha market evidence for QA deep research" if allowed else "alpha off filter decoy market evidence"
    metadata = json.dumps(
        {
            "contentHash": f"qa-hash-{doc_id}",
            "markets": ["US"],
            "relatedTickers": [ticker],
            "impactTags": ["AI"],
            "relatedThemes": ["qa"],
            "normalizedUrl": url,
        },
        separators=(",", ":"),
    )
    path = f"research-inbox/articles/{doc_id}.md"
    connection.execute(
        "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (doc_id, path, title, "Reuters", "2026-07-20", "article", url, 1, metadata, "2026-07-20T00:00:00Z", content, "2026-07-20T00:00:00Z"),
    )
    connection.execute(
        "INSERT INTO chunks VALUES (?,?,?,?,?)",
        (f"{doc_id}:0000", doc_id, 0, content, "[]"),
    )
    connection.execute(
        "INSERT INTO chunks_fts VALUES (?,?,?,?,?)",
        (f"{doc_id}:0000", doc_id, title, "Reuters", content),
    )


def _insert_rss(connection: sqlite3.Connection, filename: str, url: str) -> None:
    connection.execute(
        "INSERT INTO rss_feed_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            filename,
            f"research-inbox/rss/{filename}",
            128,
            100,
            "QA Live RSS Alpha",
            "2026-07-20",
            "2026-07-20T00:00:00Z",
            url,
            "alpha live RSS evidence",
            "Reuters",
            url,
            "rss",
            "news",
            "summary_only",
            "2",
            "US",
            1,
            "2026-07-20T00:00:00Z",
        ),
    )


def _write_cli(adapters: Path) -> None:
    script = adapters / "qa_fake_cli.py"
    script.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations
            import os, sys, time
            if "--version" in sys.argv:
                print("folio-qa-cli 1.0")
                raise SystemExit(0)
            if "login" in sys.argv or "auth" in sys.argv:
                print("authenticated")
                raise SystemExit(0)
            mode_path = os.environ.get("QA_FAKE_CLI_MODE_FILE", "")
            mode = open(mode_path, encoding="utf-8").read().strip() if mode_path else os.environ.get("QA_FAKE_CLI_MODE", "")
            if mode == "slow":
                time.sleep(8)
            print("# QA Deep Research Report\\n\\n**한 줄 결론:** deterministic QA adapter\\n\\n## Source & Data Notes\\n- Reuters QA fixture")
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    command = adapters / "qa_fake_cli.cmd"
    command.write_text(f'@echo off\n"{__import__("sys").executable}" "%~dp0qa_fake_cli.py" %*\n', encoding="utf-8")


def _write_sitecustomize(adapters: Path) -> None:
    (adapters.parent / "sitecustomize.py").write_text(
        textwrap.dedent(
            """
            from __future__ import annotations
            import json, os, subprocess, traceback, urllib.request
            _original_urlopen = urllib.request.urlopen
            _original_run = subprocess.run
            _fake_url = os.environ.get("QA_FAKE_API_URL", "")
            _trace_path = os.environ.get("QA_RSS_TRACE_PATH", "")
            _fault_stage = os.environ.get("FOLIO_QA_FAULT_STAGE", "")
            _fault_arm_path = os.environ.get("QA_FAULT_ARM_PATH", "")
            _fault_consumed_path = f"{_fault_arm_path}.consumed" if _fault_arm_path else ""

            def _trace(kind, **payload):
                if not _trace_path:
                    return
                row = {"kind": kind, **payload}
                try:
                    with open(_trace_path, "a", encoding="utf-8") as handle:
                        handle.write(json.dumps(row, ensure_ascii=False) + "\\n")
                except OSError:
                    return

            def _route(request, *args, **kwargs):
                url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
                _trace("urlopen", url=url)
                if _fake_url and any(host in url for host in ("api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com")):
                    if isinstance(request, urllib.request.Request):
                        request = urllib.request.Request(_fake_url, data=request.data, headers=dict(request.header_items()), method=request.method)
                    else:
                        request = _fake_url
                return _original_urlopen(request, *args, **kwargs)
            urllib.request.urlopen = _route

            def _rss_fixture_run(*args, **kwargs):
                command = args[0] if args else kwargs.get("args")
                _trace(
                    "subprocess.run",
                    command=[str(part) for part in command] if isinstance(command, (list, tuple)) else str(command),
                    cwd=str(kwargs.get("cwd") or ""),
                )
                if isinstance(command, (list, tuple)) and any("rss_archive" in str(part) for part in command):
                    _trace("rss_intercept", command=[str(part) for part in command])
                    return subprocess.CompletedProcess(command, 0, "", "")
                return _original_run(*args, **kwargs)

            subprocess.run = _rss_fixture_run

            try:
                import features.common.research_library.rss.service as _rss_service
                _rss_original_import = _rss_service.import_rssarchive

                def _rss_import_trace(*args, **kwargs):
                    _trace("rss_start", args=[str(item) for item in args], kwargs={key: str(value) for key, value in kwargs.items()})
                    try:
                        result = _rss_original_import(*args, **kwargs)
                    except BaseException as exc:
                        _trace("rss_exception", type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
                        raise
                    _trace("rss_result", result=repr(result))
                    return result

                _rss_service.import_rssarchive = _rss_import_trace
            except BaseException as exc:
                _trace("rss_wrap_exception", type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())

            try:
                import features.smart_collections.resolution as _resolution_module
                _resolution_original = _resolution_module.resolve_collection

                def _resolution_trace(*args, **kwargs):
                    _trace("resolution_start")
                    try:
                        result = _resolution_original(*args, **kwargs)
                    except BaseException as exc:
                        _trace("resolution_exception", type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
                        raise
                    _trace("resolution_result", result=repr(result))
                    return result

                _resolution_module.resolve_collection = _resolution_trace
            except BaseException as exc:
                _trace("resolution_wrap_exception", type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())

            try:
                import features.topic_report.approved_research as _research_module
                _research_original = _research_module.prepare_approved_research

                def _research_trace(*args, **kwargs):
                    _trace("research_start")
                    try:
                        result = _research_original(*args, **kwargs)
                    except BaseException as exc:
                        _trace("research_exception", type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
                        raise
                    _trace("research_result", result=repr(result))
                    return result

                _research_module.prepare_approved_research = _research_trace
            except BaseException as exc:
                _trace("research_wrap_exception", type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())

            try:
                import features.common.research_library.indexing.service as _index_module
                _index_original = _index_module.build_index

                def _index_trace(*args, **kwargs):
                    _trace("index_start")
                    try:
                        result = _index_original(*args, **kwargs)
                    except BaseException as exc:
                        _trace("index_exception", type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
                        raise
                    _trace("index_result", result=repr(result))
                    return result

                _index_module.build_index = _index_trace
            except BaseException as exc:
                _trace("index_wrap_exception", type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())

            def _fault_after_artifact(phase):
                if phase != "artifacts_written" or _fault_stage != "after_artifact" or not _fault_arm_path:
                    return
                try:
                    armed = open(_fault_arm_path, encoding="utf-8").read().strip() == "armed"
                    consumed = os.path.exists(_fault_consumed_path)
                except OSError:
                    return
                if not armed or consumed:
                    return
                try:
                    with open(_fault_consumed_path, "w", encoding="utf-8") as handle:
                        handle.write("consumed\\n")
                except OSError:
                    return
                _trace("fault_exit", stage=phase, exitCode=91)
                os._exit(91)

            try:
                import features.common.job_json_commit as _commit_module
                _commit_original = _commit_module.JobArtifactCommitter.commit

                def _commit_fault_trace(self, bundle, store, lifecycle, *args, **kwargs):
                    existing_hook = kwargs.get("fault_hook")

                    def _composed_hook(phase):
                        if existing_hook is not None:
                            existing_hook(phase)
                        _fault_after_artifact(phase)

                    kwargs["fault_hook"] = _composed_hook
                    return _commit_original(self, bundle, store, lifecycle, *args, **kwargs)

                _commit_module.JobArtifactCommitter.commit = _commit_fault_trace
            except BaseException as exc:
                _trace("commit_wrap_exception", type=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def prepare_fixture(source_root: Path, runtime: Path) -> Fixture:
    runtime.mkdir(parents=True, exist_ok=False)
    (runtime / ".folio-qa-owned").write_text("folio-board-0-2-0\n", encoding="utf-8")
    workspace = runtime / "workspace"
    _copy_tree(source_root.resolve(), workspace)
    data = workspace / "data"
    inbox = workspace / "research-inbox"
    adapters = runtime / "adapters"
    data.mkdir(parents=True)
    for name in ("articles", "rss", "reports", "filings", "links"):
        (inbox / name).mkdir(parents=True)
    (workspace / "config").mkdir(parents=True, exist_ok=True)
    adapters.mkdir()
    _write_cli(adapters)
    (adapters / "cli-mode.txt").write_text("normal", encoding="utf-8")
    (adapters / "fault-arm.txt").write_text("disarmed\n", encoding="utf-8")
    _write_sitecustomize(adapters)
    connection = _init_db(data / "research-index.sqlite3")
    _insert_document(connection, 0, allowed=True)
    _insert_document(connection, 999, allowed=False, duplicate=True)
    for number in range(121):
        _insert_document(connection, number, allowed=False)
    connection.commit()
    connection.close()
    allowed = inbox / "articles" / "doc-allowed.md"
    allowed.write_text(
        "---\nsource: Reuters\nmarkets: [\"US\"]\nrelated_tickers: [\"QAE\"]\nurl: https://qa.example/allowed\n---\n"
        "# QA Live Alpha Allowed\n\nlive alpha market evidence for QA deep research\n",
        encoding="utf-8",
    )
    for number in range(121):
        path = inbox / "articles" / f"doc-off-{number:03d}.md"
        path.write_text(
            "---\nsource: Reuters\nmarkets: [\"US\"]\nrelated_tickers: [\"OFF\"]\nurl: "
            f"https://qa.example/off/{number:03d}\n---\n# QA Alpha Off Filter\n\nalpha off filter decoy market evidence\n",
            encoding="utf-8",
        )
    (inbox / "articles" / "doc-off-999.md").write_text(
        "---\nsource: Reuters\nmarkets: [\"US\"]\nrelated_tickers: [\"OFF\"]\nurl: https://qa.example/allowed\n---\n"
        "# QA Duplicate\n\nalpha duplicate URL decoy\n",
        encoding="utf-8",
    )
    manifest_connection = sqlite3.connect(data / "research-index.sqlite3")
    try:
        manifest_rows = []
        for path in sorted((inbox / "articles").glob("*.md")):
            doc_id = path.stem
            stat = path.stat()
            manifest_rows.append(
                (
                    path.relative_to(workspace).as_posix(),
                    f"{stat.st_size}:{stat.st_mtime_ns}",
                    1,
                    doc_id,
                    "2026-07-20T00:00:00Z",
                )
            )
        manifest_connection.executemany(
            "INSERT INTO file_manifest (path, file_signature, market_relevant, doc_id, modified_at) VALUES (?,?,?,?,?)",
            manifest_rows,
        )
        manifest_connection.commit()
    finally:
        manifest_connection.close()
    protected = {
        str(path): _sha(path)
        for path in (source_root / "AGENTS.md", source_root / "CLAUDE.md", source_root / "app.py")
        if path.is_file()
    }
    return Fixture(workspace, data, inbox, adapters, runtime / ".folio-qa-owned", protected)


def database_counts(path: Path) -> dict[str, JsonValue]:
    if not path.is_file():
        return {"exists": False}
    connection = sqlite3.connect(path)
    try:
        return {
            "exists": True,
            "documents": int(connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]),
            "rss": int(connection.execute("SELECT COUNT(*) FROM rss_feed_items").fetchone()[0]),
        }
    finally:
        connection.close()


def start_fake_api(mode_path: Path) -> FakeApi:
    requests: list[dict[str, JsonValue]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            mode = mode_path.read_text(encoding="utf-8").strip() if mode_path.exists() else "ok"
            requests.append({"path": self.path, "bodySha256": hashlib.sha256(body).hexdigest(), "mode": mode})
            if mode == "fail":
                payload = {"error": {"message": "qa fake api failure"}}
                status = 500
            else:
                payload = {
                    "id": "qa-response-1",
                    "output_text": "# QA Deep Research Report\\n\\n**한 줄 결론:** deterministic QA API\\n\\n## Source & Data Notes\\n- Reuters QA fixture",
                }
                status = 200
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, name="folio-qa-fake-api", daemon=True)
    thread.start()
    return FakeApi(server, thread, mode_path, requests, f"http://127.0.0.1:{server.server_port}/v1/responses")


def stop_fake_api(fake: FakeApi) -> None:
    fake.server.shutdown()
    fake.server.server_close()
    fake.thread.join(timeout=5)
