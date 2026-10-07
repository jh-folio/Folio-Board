"""Workspace-bounded reads and shared serialization. No read creates a file."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from features.common.canonical_report_io import artifact_lock, atomic_write
from features.decision_readiness.inputs import Files
from . import CaseError


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def byte_hash(value):
    return hashlib.sha256(value).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def identifier(value, size=32):
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{size}}}", value):
        raise CaseError("invalid_record_id")
    return value


def safe_path(root, *parts):
    root = Path(root).resolve()
    if any(not isinstance(p, str) or not p or p in {".", ".."} or os.path.basename(p) != p or "/" in p or "\\" in p for p in parts):
        raise CaseError("invalid_storage_path")
    resolved = os.path.realpath(root.joinpath(*parts))
    if not os.path.normcase(resolved).startswith(os.path.normcase(os.path.join(str(root), ""))):
        raise CaseError("source_path_outside_workspace", 503)
    return Path(resolved)


def journal_path(root, journal_id, *, pending=False):
    key = identifier(journal_id)
    return safe_path(root, "decision-journals", f".pending-{key}.json" if pending else f"{key}.json")


def parse(raw):
    try:
        value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError):
        raise CaseError("source_file_invalid", 503) from None
    if not isinstance(value, dict):
        raise CaseError("source_file_invalid", 503)
    return value


class SourceFiles(Files):
    def path(self, relative):
        return safe_path(self.root, *relative.split("/"))

    def catalog(self, folder):
        directory = self.path(folder)
        names = tuple(sorted(p.name for p in directory.glob("*.json") if not p.name.startswith("."))) if directory.exists() else ()
        # Files.verify compares its complete glob, including hidden journals.
        self.catalogs[folder] = tuple(sorted(p.name for p in directory.glob("*.json"))) if directory.exists() else ()
        return names


@contextmanager
def database(root):
    path = safe_path(root, "market-memory.sqlite3")
    if not path.exists():
        yield None
        return
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        version = conn.execute("PRAGMA data_version").fetchone()[0]
        yield conn
        conn.rollback()
        if conn.execute("PRAGMA data_version").fetchone()[0] != version:
            raise CaseError("inputs_changed", 409)


@contextmanager
def action_lock(root):
    with artifact_lock(safe_path(root, "investment-case")):
        yield


def write_document(path, value):
    raw = canonical(value)
    atomic_write(path, raw)
    return byte_hash(raw)
