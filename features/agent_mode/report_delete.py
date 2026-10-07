from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from contextlib import ExitStack
from pathlib import Path
from typing import Final, TypedDict

from features.common.markets import PRODUCT_MARKETS
from features.common.atomic_replace import replace_with_retry
from features.common.canonical_report_io import artifact_lock, atomic_write, safe_child_path


_SAFE_ID: Final = re.compile(r"^[A-Za-z0-9:_-]+$")
_JOURNAL_PREFIX: Final = ".report-delete-"
_JOURNAL_STAGES: Final = frozenset({"journaled", "renamed", "deleting", "unlinked", "refreshed"})


class _JournalEntry(TypedDict):
    original: str
    temporary: str
    expectedHash: str | None
    state: str


class _Journal(TypedDict):
    identity: str
    stage: str
    entries: list[_JournalEntry]
    receiptId: str | None


@dataclass(frozen=True, slots=True)
class DeleteRequest:
    root: Path
    identity: str
    primary_names: tuple[str, ...]
    target_names: tuple[str, ...]
    refresh: Callable[[], None] | None = None
    fault_stage: str | None = None
    expected_hashes: dict[str, str] | None = None
    receipt_id: str | None = None


@dataclass(frozen=True, slots=True)
class DeleteOutcome:
    deleted: bool
    identity: str
    removed_names: tuple[str, ...]


class InvalidDeleteRequestError(ValueError):
    field: str

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(field)

    def __str__(self) -> str:
        return f"invalid report deletion {self.field}"


class SourceChangedError(ValueError):
    """The reviewed source was replaced; never acquire its replacement."""


class DeleteRecoveryRequiredError(ValueError):
    pass


def _validated(request: DeleteRequest) -> DeleteRequest:
    if request.receipt_id is not None and re.fullmatch(r"[a-f0-9]{32}", request.receipt_id) is None:
        raise InvalidDeleteRequestError(field="receipt")
    if not _SAFE_ID.fullmatch(request.identity):
        raise InvalidDeleteRequestError(field="identity")
    if not request.primary_names or not request.target_names:
        raise InvalidDeleteRequestError(field="candidates")
    for name in (*request.primary_names, *request.target_names):
        if not name or Path(name).name != name:
            raise InvalidDeleteRequestError(field="candidate")
    if not set(request.primary_names).issubset(request.target_names):
        raise InvalidDeleteRequestError(field="primary candidates")
    if not all(_is_exact_candidate(request.identity, name) for name in request.target_names):
        raise InvalidDeleteRequestError(field="identity candidates")
    return request


# 삭제 허용 목록은 시장 계약에서 파생한다. 여기에 시장 이름을 다시 적으면
# 새 시장이 늘었을 때 이 안전장치만 조용히 뒤처진다.
_BRIEFING_MARKETS = tuple(market.value.lower() for market in PRODUCT_MARKETS)
_BRIEFING_IDENTITY_RE = re.compile(
    rf"briefing:(\d{{4}}-\d{{2}}-\d{{2}}):({'|'.join((*_BRIEFING_MARKETS, 'all', 'both'))})"
)


def _briefing_file_variants(date_text: str, scope: str = "") -> set[str]:
    stem = f"{date_text}.{scope}" if scope else date_text
    # Daily and weekly reports share the same deletion identity.  Keep both
    # filename families in the validation allowlist; the concrete delete
    # request still carries the exact files selected by the service.
    stems = (stem, f"{stem}.weekly")
    return {
        filename
        for candidate in stems
        for filename in (
            f"{candidate}.json",
            f"{candidate}.visuals.json",
            f"{candidate}.visuals.json.gz",
        )
    }


def _is_exact_candidate(identity: str, name: str) -> bool:
    briefing = _BRIEFING_IDENTITY_RE.fullmatch(identity)
    if briefing is not None:
        date_text, scope = briefing.groups()
        # 연결 분석은 어느 시장이 빠져도 더 이상 그 조합을 설명하지 않으므로
        # 시장 단위 삭제에서도 함께 지운다.
        link = {f"{date_text}.link.json"}
        if scope in {"all", "both"}:
            date_wide = set(_briefing_file_variants(date_text)) | link
            for market in _BRIEFING_MARKETS:
                date_wide |= _briefing_file_variants(date_text, market)
            return name in date_wide
        return name in (_briefing_file_variants(date_text, scope) | link)
    company = re.fullmatch(r"company:([A-Za-z0-9_-]+)", identity)
    if company is not None:
        return name == f"{company.group(1)}.json"
    topic = re.fullmatch(r"topic:([A-Za-z0-9_-]+)", identity)
    if topic is None:
        return False
    return re.fullmatch(
        rf"\d{{4}}-\d{{2}}-\d{{2}}_[a-z0-9_]+_{re.escape(topic.group(1))}\.json",
        name,
    ) is not None


def _journal_path(root: Path, identity: str) -> Path:
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return root / f"{_JOURNAL_PREFIX}{digest}.json"


def _write_journal(path: Path, payload: _Journal) -> None:
    atomic_write(path, json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def _parse_journal(path: Path) -> _Journal | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    identity = raw.get("identity")
    stage = raw.get("stage")
    entries = raw.get("entries")
    if not isinstance(identity, str) or _SAFE_ID.fullmatch(identity) is None:
        return None
    if path != _journal_path(path.parent, identity):
        return None
    if not isinstance(stage, str) or stage not in _JOURNAL_STAGES or not isinstance(entries, list):
        return None
    parsed_entries: list[_JournalEntry] = []
    token = path.stem.removeprefix(_JOURNAL_PREFIX)
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            return None
        original = entry.get("original")
        temporary = entry.get("temporary")
        if not isinstance(original, str) or not isinstance(temporary, str):
            return None
        if Path(original).name != original or Path(temporary).name != temporary:
            return None
        if temporary != f"{_JOURNAL_PREFIX}{token}.{index}.deleting":
            return None
        if not _is_exact_candidate(identity, original):
            return None
        expected = entry.get("expectedHash")
        state = entry.get("state", "legacy")
        if expected is not None and (not isinstance(expected, str) or re.fullmatch(r"[a-f0-9]{64}", expected) is None):
            return None
        if state not in {"legacy", "journaled", "renamed", "unlinked", "changed", "missing"}:
            return None
        parsed_entries.append({"original": original, "temporary": temporary, "expectedHash": expected, "state": state})
    if len({entry["original"] for entry in parsed_entries}) != len(parsed_entries):
        return None
    receipt = raw.get("receiptId")
    if receipt is not None and (not isinstance(receipt, str) or re.fullmatch(r"[a-f0-9]{32}", receipt) is None):
        return None
    return {"identity": identity, "stage": stage, "entries": parsed_entries, "receiptId": receipt}


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _recover_journal(path: Path, journal: _Journal, refresh: Callable[[], None] | None) -> bool:
    root = path.parent
    unresolved = False
    for entry in journal["entries"]:
        original = safe_child_path(root, entry["original"])
        temporary = safe_child_path(root, entry["temporary"])
        with artifact_lock(original):
            if temporary.exists():
                if entry["expectedHash"] and _checksum(temporary) != entry["expectedHash"]:
                    raise SourceChangedError("deletion_tombstone_changed")
                entry["state"] = "renamed"
                _write_journal(path, journal)
            elif entry["state"] == "journaled" and journal["stage"] == "journaled":
                if not original.exists():
                    entry["state"] = "missing"
                elif not entry["expectedHash"]:
                    unresolved = True
                    continue
                elif _checksum(original) != entry["expectedHash"]:
                    entry["state"] = "changed"
                else:
                    replace_with_retry(original, temporary)
                    entry["state"] = "renamed"
                    _write_journal(path, journal)
            elif entry["state"] == "legacy" and journal["stage"] == "journaled":
                # An old journal proves no hash or rename boundary. It cannot
                # authorize acquiring whatever currently occupies the name.
                unresolved = True
                continue
            if temporary.exists():
                temporary.unlink()
                entry["state"] = "unlinked"
            _write_journal(path, journal)
    if unresolved:
        return False
    if refresh is not None:
        refresh()
    if journal.get("receiptId"):
        journal["stage"] = "refreshed"
        _write_journal(path, journal)
    else:
        path.unlink()
    return True


def recover_report_deletes(
    root: Path,
    *,
    refresh: Callable[[], None] | None = None,
) -> tuple[str, ...]:
    """Forward-complete valid deletion journals; preserve malformed journals."""
    if not root.exists():
        return ()
    recovered: list[str] = []
    for path in sorted(root.glob(f"{_JOURNAL_PREFIX}*.json")):
        journal = _parse_journal(path)
        if journal is None:
            continue
        if _recover_journal(path, journal, refresh):
            recovered.append(journal["identity"])
    for staging in root.glob(f"{_JOURNAL_PREFIX}*.tmp"):
        staging.unlink()
    return tuple(recovered)


def _fault(request: DeleteRequest, stage: str) -> None:
    if request.fault_stage == stage:
        raise RuntimeError(stage)


def execute_report_delete(request: DeleteRequest) -> DeleteOutcome:
    """Delete an exact, predeclared candidate set with a durable journal."""
    request = _validated(request)
    root = request.root
    root.mkdir(parents=True, exist_ok=True)
    prior = _parse_journal(_journal_path(root, request.identity))
    recovered = recover_report_deletes(root, refresh=request.refresh)
    receipt = _parse_journal(_journal_path(root, request.identity))
    if receipt and receipt.get("receiptId") == request.receipt_id and request.receipt_id and receipt["stage"] == "refreshed":
        if any(safe_child_path(root, name).exists() for name in request.primary_names):
            raise SourceChangedError("source_changed")
        return DeleteOutcome(any(e["state"] == "unlinked" for e in receipt["entries"]), request.identity, tuple(e["original"] for e in receipt["entries"] if e["state"] == "unlinked"))
    if _journal_path(root, request.identity).exists():
        raise DeleteRecoveryRequiredError("recovery_requires_confirmation")
    if prior and request.identity in recovered:
        if any(safe_child_path(root, name).exists() for name in request.primary_names):
            raise SourceChangedError("source_changed")
        return DeleteOutcome(True, request.identity, tuple(e["original"] for e in prior["entries"]))
    with ExitStack() as locks:
        for name in sorted(request.target_names):
            locks.enter_context(artifact_lock(safe_child_path(root, name)))
        return _execute_locked(request)


def _execute_locked(request: DeleteRequest) -> DeleteOutcome:
    root = request.root
    if not any((root / name).exists() for name in request.primary_names):
        return DeleteOutcome(deleted=False, identity=request.identity, removed_names=())

    existing = tuple(name for name in request.target_names if (root / name).exists())
    journal_path = _journal_path(root, request.identity)
    token = journal_path.stem.removeprefix(_JOURNAL_PREFIX)
    entries = []
    for index, name in enumerate(existing):
        checksum = _checksum(safe_child_path(root, name))
        if request.expected_hashes is not None and request.expected_hashes.get(name) != checksum:
            raise SourceChangedError("source_changed")
        entries.append({"original": name, "temporary": f"{_JOURNAL_PREFIX}{token}.{index}.deleting", "expectedHash": checksum, "state": "journaled"})
    journal: _Journal = {"identity": request.identity, "stage": "journaled", "entries": entries, "receiptId": request.receipt_id}
    _write_journal(journal_path, journal)
    _fault(request, "journaled")

    for index, entry in enumerate(entries):
        replace_with_retry(safe_child_path(root, entry["original"]), safe_child_path(root, entry["temporary"]))
        entry["state"] = "renamed"
        _write_journal(journal_path, journal)
        _fault(request, f"renamed:{index}")
    journal["stage"] = "renamed"
    _write_journal(journal_path, journal)
    _fault(request, "renamed")

    journal["stage"] = "deleting"
    _write_journal(journal_path, journal)
    _fault(request, "deleting")
    for index, entry in enumerate(entries):
        (root / entry["temporary"]).unlink()
        entry["state"] = "unlinked"
        _write_journal(journal_path, journal)
        _fault(request, f"unlinked:{index}")
    journal["stage"] = "unlinked"
    _write_journal(journal_path, journal)
    _fault(request, "unlinked")

    if request.refresh is not None:
        request.refresh()
    journal["stage"] = "refreshed"
    _write_journal(journal_path, journal)
    _fault(request, "refreshed")
    if not request.receipt_id:
        journal_path.unlink()
    return DeleteOutcome(deleted=True, identity=request.identity, removed_names=existing)


def acknowledge_delete_receipt(root: Path, identity: str, receipt_id: str) -> None:
    """Remove metadata only after its coordinating operation durably owns the outcome."""
    path = _journal_path(root, identity)
    journal = _parse_journal(path)
    if journal and journal.get("receiptId") == receipt_id and journal["stage"] == "refreshed":
        path.unlink()
