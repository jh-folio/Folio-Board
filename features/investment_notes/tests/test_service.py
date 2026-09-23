from datetime import UTC, datetime
import json
from pathlib import Path
from unittest.mock import patch

from features.investment_notes import service


def test_save_note_marks_user_text_as_hypothesis(tmp_path):
    notes_dir = tmp_path / "notes"
    db_path = tmp_path / "market-memory.sqlite3"
    with patch.object(service, "NOTES_DIR", notes_dir), patch.object(service, "MARKET_MEMORY_DB_PATH", db_path):
        note = service.save_note({
            "noteType": "company_thesis",
            "title": "NVDA thesis",
            "body": "AI capex 가설",
            "ticker": "nvda",
            "linkedReports": ["NVDA"],
            "tags": ["AI", "AI"],
        })

        assert note["ticker"] == "NVDA"
        assert note["layer"] == "hypothesis"
        assert note["sourceLayer"] == "user_synthesis"
        assert note["reuseAsHypothesis"] is True
        assert note["reuseAsEvidence"] is False
        assert note["tags"] == ["AI"]
        assert (notes_dir / f"{note['id']}.json").exists()


def test_list_notes_uses_native_note_index(tmp_path):
    notes_dir = tmp_path / "notes"
    db_path = tmp_path / "market-memory.sqlite3"
    with patch.object(service, "NOTES_DIR", notes_dir), patch.object(service, "MARKET_MEMORY_DB_PATH", db_path):
        service.save_note({"title": "달러 메모", "topic": "달러", "body": "강달러 부담"})
        service.save_note({"title": "NVDA", "ticker": "NVDA", "body": "마진 체크"})

        rows = service.list_notes(ticker="NVDA")

        assert len(rows) == 1
        assert rows[0]["title"] == "NVDA"
        assert "body" not in rows[0]
        assert rows[0]["summary"] == "마진 체크"


def test_update_note_preserves_created_at_and_updates_body(tmp_path):
    notes_dir = tmp_path / "notes"
    db_path = tmp_path / "market-memory.sqlite3"
    with patch.object(service, "NOTES_DIR", notes_dir), patch.object(service, "MARKET_MEMORY_DB_PATH", db_path):
        first = service.save_note({"title": "초안", "body": "old"})
        second = service.save_note({"id": first["id"], "title": "수정", "body": "new"})
        loaded = service.get_note(first["id"])

        assert second["createdAt"] == first["createdAt"]
        assert loaded["title"] == "수정"
        assert loaded["body"] == "new"


def test_save_note_preserves_user_thoughts_and_agent_interaction_log(tmp_path):
    notes_dir = tmp_path / "notes"
    db_path = tmp_path / "market-memory.sqlite3"
    with patch.object(service, "NOTES_DIR", notes_dir), patch.object(service, "MARKET_MEMORY_DB_PATH", db_path):
        note = service.save_note({
            "title": "NVDA 생각 정리",
            "body": "## 현재 관점\n\nAI 수혜는 유효하지만 가격 부담을 확인한다.",
            "rawThoughts": [
                {
                    "role": "user",
                    "body": "이 주식은 앞으로 받을 수혜가 커 보여서 관심 있음",
                    "createdAt": "2026-07-06T09:00:00+09:00",
                }
            ],
            "interactionLog": [
                {
                    "role": "agent",
                    "body": "수혜 가설, 반대 근거, 체크포인트로 나누어 정리했습니다.",
                    "createdAt": "2026-07-06T09:01:00+09:00",
                    "summary": "초안 정리",
                }
            ],
        })
        loaded = service.get_note(note["id"])

        assert loaded["body"].startswith("## 현재 관점")
        assert loaded["rawThoughts"][0]["body"] == "이 주식은 앞으로 받을 수혜가 커 보여서 관심 있음"
        assert loaded["interactionLog"][0]["role"] == "agent"
        assert loaded["interactionLog"][0]["summary"] == "초안 정리"


def test_linked_notes_payload_filters_by_ticker(tmp_path):
    notes_dir = tmp_path / "notes"
    db_path = tmp_path / "market-memory.sqlite3"
    with patch.object(service, "NOTES_DIR", notes_dir), patch.object(service, "MARKET_MEMORY_DB_PATH", db_path):
        service.save_note({"title": "AAPL", "ticker": "AAPL"})
        service.save_note({"title": "MSFT", "ticker": "MSFT"})

        payload = service.linked_notes_payload(ticker="AAPL")

        assert payload["ok"] is True
        assert payload["count"] == 1
        assert payload["notes"][0]["title"] == "AAPL"


def test_legacy_note_without_new_fields_migrates_with_safe_defaults(tmp_path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    db_path = tmp_path / "market-memory.sqlite3"
    legacy = {
        "id": "legacy-note",
        "noteType": "company_thesis",
        "title": "Legacy NVDA thesis",
        "body": "Older note body",
        "ticker": "nvda",
        "createdAt": "2026-01-02T03:04:05",
        "updatedAt": "2026-01-02T03:04:05",
    }
    (notes_dir / "legacy-note.json").write_text(
        json.dumps(legacy, ensure_ascii=False),
        encoding="utf-8",
    )

    with patch.object(service, "NOTES_DIR", notes_dir), patch.object(
        service,
        "MARKET_MEMORY_DB_PATH",
        db_path,
    ):
        indexed = service.list_notes(ticker="NVDA", include_body=True)
        migrated = service.save_note({"id": "legacy-note"})
        stored = service.get_note("legacy-note")

    assert len(indexed) == 1
    assert indexed[0]["body"] == "Older note body"
    assert migrated["createdAt"] == legacy["createdAt"]
    assert stored["rawThoughts"] == []
    assert stored["interactionLog"] == []
    assert stored["layer"] == "hypothesis"
    assert stored["sourceLayer"] == "user_synthesis"
    assert stored["reuseAsHypothesis"] is True
    assert stored["reuseAsEvidence"] is False


def test_checkpoint_save_and_update_touch_only_native_note_state(tmp_path):
    notes_dir = tmp_path / "investment-notes"
    db_path = tmp_path / "market-memory.sqlite3"
    protected = {
        name: tmp_path / name
        for name in (
            "portfolio.json",
            "watchlist.json",
            "smart-collections.json",
            "company-report.json",
        )
    }
    for name, path in protected.items():
        path.write_bytes(f"{name}:canary".encode())
    before = {name: (path.read_bytes(), path.stat().st_mtime_ns) for name, path in protected.items()}

    with patch.object(service, "NOTES_DIR", notes_dir), patch.object(
        service,
        "MARKET_MEMORY_DB_PATH",
        db_path,
    ):
        created = service.save_note(
            {
                "noteType": "checkpoint",
                "title": "NVDA 실적 확인",
                "body": "사용자 가설",
                "ticker": "nvda",
                "checkpointState": "open",
                "dueDate": "2026-07-27",
                "linkedReports": ["NVDA:2026-07-27"],
                "linkedCollectionIds": ["ai-watch"],
            }
        )
        updated = service.save_note(
            {
                "id": created["id"],
                "checkpointState": "checked",
                "lastCheckedDate": "2026-07-27",
            }
        )
        loaded = service.get_note(
            created["id"],
            clock=lambda: datetime(2026, 7, 27, 9, 30, tzinfo=UTC),
        )

    assert updated["checkpointState"] == "checked"
    assert loaded["dueState"] == "checked"
    assert loaded["linkedReports"] == ["NVDA:2026-07-27"]
    assert loaded["linkedCollectionIds"] == ["ai-watch"]
    assert loaded["layer"] == "hypothesis"
    assert loaded["reuseAsEvidence"] is False
    for name, path in protected.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before[name]


def test_legacy_checkpoint_file_loads_without_a_persisted_migration(tmp_path):
    notes_dir = tmp_path / "investment-notes"
    notes_dir.mkdir()
    legacy_path = notes_dir / "legacy-checkpoint.json"
    legacy_path.write_text(
        json.dumps(
            {
                "id": "legacy-checkpoint",
                "noteType": "checkpoint",
                "title": "다음 실적 확인",
                "body": "사용자 가설",
                "ticker": "NVDA",
                "createdAt": "2025-01-01T00:00:00Z",
                "updatedAt": "2025-01-01T00:00:00Z",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    before = (legacy_path.read_bytes(), legacy_path.stat().st_mtime_ns)

    loaded = service.get_note(
        "legacy-checkpoint",
        notes_dir=notes_dir,
        clock=lambda: datetime(2026, 7, 27, 9, 30, tzinfo=UTC),
    )

    assert loaded["checkpointState"] == "open"
    assert loaded["dueState"] == "unknown"
    assert loaded["dueDate"] == ""
    assert loaded["lastCheckedDate"] == ""
    assert (legacy_path.read_bytes(), legacy_path.stat().st_mtime_ns) == before


def test_note_ids_cannot_read_outside_the_notes_folder(tmp_path: Path):
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    outside = {"id": "secret", "title": "outside the notes folder", "body": "portfolio"}
    (tmp_path / "portfolio.json").write_text(json.dumps(outside), encoding="utf-8")

    with patch.object(service, "NOTES_DIR", notes_dir), patch.object(
        service, "MARKET_MEMORY_DB_PATH", tmp_path / "memory.sqlite3"
    ):
        for hostile in ("../portfolio", "..\\portfolio", "..%2Fportfolio", "sub/../../portfolio"):
            assert service.get_note(hostile) == {}
            saved = service.save_note({"id": hostile, "title": "new", "body": "b"})
            assert saved["title"] == "new"
            assert saved["body"] != "portfolio"
            assert (notes_dir / f"{saved['id']}.json").exists()
