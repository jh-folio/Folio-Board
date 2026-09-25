"""저장 경로 이관과 주제 없는 대화.

도크가 대화의 집이 되면서 저장 위치가 `agent-consultations`에서 `agent-threads`로
옮겨간다. 개인 데이터라 이관 중 실패해도 원본을 잃으면 안 되고, 주제 없는 도크
대화가 포트폴리오 대화로 둔갑해서도 안 된다.
"""
from __future__ import annotations

import json

import pytest

from features.agent_mode import consultation_store as store
from features.agent_mode.consultation_schema import SCOPE_KINDS, UNSCOPED_KIND, normalize_scope


class TestScopeFallback:
    """알 수 없는 주제는 주제 없음이지 포트폴리오가 아니다."""

    @pytest.mark.parametrize("value", [None, {}, {"kind": ""}, {"kind": "bogus"}, {"kind": "  "}])
    def test_unknown_scope_becomes_unscoped(self, value):
        assert normalize_scope(value)["kind"] == UNSCOPED_KIND

    def test_unscoped_is_never_portfolio(self):
        assert normalize_scope({"kind": "nonsense"})["kind"] != "portfolio"

    @pytest.mark.parametrize("kind", ["watchlist", "portfolio", "briefing", "company_analysis"])
    def test_real_scopes_survive(self, kind):
        assert normalize_scope({"kind": kind})["kind"] == kind

    def test_unscoped_kind_is_a_known_scope(self):
        assert UNSCOPED_KIND in SCOPE_KINDS

    def test_challenge_intent_is_bounded_and_unknown_intent_is_dropped(self):
        assert normalize_scope({"kind": "watchlist", "intent": "challenge"})["intent"] == "challenge"
        assert normalize_scope({"kind": "watchlist", "intent": "anything_else"})["intent"] == ""


class TestMigration:
    def _legacy(self, root, name, payload):
        directory = root / store.LEGACY_DIRNAME
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_saved_sessions_move_to_the_thread_directory(self, tmp_path):
        self._legacy(tmp_path, "a.json", {"id": "a"})
        self._legacy(tmp_path, "b.json", {"id": "b"})

        result = store.migrate_legacy_sessions(tmp_path)

        assert result["moved"] == 2
        moved = sorted(p.name for p in (tmp_path / store.THREADS_DIRNAME).glob("*.json"))
        assert moved == ["a.json", "b.json"]
        assert json.loads((tmp_path / store.THREADS_DIRNAME / "a.json").read_text(encoding="utf-8")) == {"id": "a"}

    def test_running_twice_moves_nothing_more(self, tmp_path):
        self._legacy(tmp_path, "a.json", {"id": "a"})
        store.migrate_legacy_sessions(tmp_path)
        assert store.migrate_legacy_sessions(tmp_path) == {"moved": 0, "skipped": 0, "failed": 0}

    def test_a_name_collision_keeps_both_files(self, tmp_path):
        """새 경로에 같은 이름이 있으면 덮어쓰지 않는다. 원본도 남긴다."""
        self._legacy(tmp_path, "dup.json", {"id": "legacy"})
        target = tmp_path / store.THREADS_DIRNAME
        target.mkdir(parents=True, exist_ok=True)
        (target / "dup.json").write_text(json.dumps({"id": "existing"}), encoding="utf-8")

        result = store.migrate_legacy_sessions(tmp_path)

        assert result == {"moved": 0, "skipped": 1, "failed": 0}
        assert json.loads((target / "dup.json").read_text(encoding="utf-8")) == {"id": "existing"}
        assert (tmp_path / store.LEGACY_DIRNAME / "dup.json").exists(), "원본을 잃으면 안 된다"

    def test_no_legacy_directory_is_not_an_error(self, tmp_path):
        assert store.migrate_legacy_sessions(tmp_path) == {"moved": 0, "skipped": 0, "failed": 0}

    def test_sessions_dir_migrates_on_first_use(self, tmp_path):
        self._legacy(tmp_path, "a.json", {"id": "a"})
        resolved = store.sessions_dir(tmp_path)
        assert resolved.name == store.THREADS_DIRNAME
        assert (resolved / "a.json").exists()


def test_a_migrated_session_is_readable_through_the_store(tmp_path):
    """이관은 파일 이동이 아니라 대화가 계속 보이는 것이 목적이다."""
    created = store.create_session(tmp_path, {"title": "이관 확인", "scope": {"kind": "watchlist", "id": "NVDA"}})
    moved = (tmp_path / store.THREADS_DIRNAME / f"{created['id']}.json").read_bytes()
    legacy = tmp_path / store.LEGACY_DIRNAME
    legacy.mkdir(parents=True, exist_ok=True)
    (legacy / f"{created['id']}.json").write_bytes(moved)
    (tmp_path / store.THREADS_DIRNAME / f"{created['id']}.json").unlink()

    session = store.get_session(tmp_path, created["id"])

    assert session["title"] == "이관 확인"
    assert session["scope"]["kind"] == "watchlist"
