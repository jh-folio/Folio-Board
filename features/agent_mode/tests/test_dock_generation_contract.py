"""도크 대화가 스레드 경로로 옮겨가도 살아남아야 하는 것들.

Task 7.6은 도크 대화를 서버에 저장해 다음 세션의 context로 쓰이게 한다. 저장 경로로
옮기는 과정에서 도크에만 있던 두 기능 — 보고서 수정 제안과 이미지 첨부 — 이 조용히
빠질 수 있어, 옮기기 전에 지금 동작을 고정한다.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from features.agent_mode import chat

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _seed_report(root: Path, date: str = "2026-08-06") -> Path:
    briefings = root / "briefings"
    briefings.mkdir(parents=True, exist_ok=True)
    path = briefings / f"{date}.us.json"
    path.write_text(json.dumps({
        "date": date, "marketScope": "us", "revision": 1,
        "markdown": "# Canonical\n\n## Evidence\n\n[source](https://example.com/s)",
        "sources": [{"url": "https://example.com/s"}],
    }, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def dock(monkeypatch, tmp_path):
    monkeypatch.setattr(chat, "DATA_DIR", tmp_path)
    monkeypatch.setattr(chat, "PROPOSALS_DIR", tmp_path / "agent-proposals")
    monkeypatch.setattr(chat, "BRIEFINGS_DIR", tmp_path / "briefings")
    monkeypatch.setattr(chat, "ANALYSIS_DIR", tmp_path / "company-analysis")
    monkeypatch.setattr(chat, "TOPIC_DIR", tmp_path / "topic-reports")
    return tmp_path


def _cli(output: str, captured: dict):
    # 실제 시그니처는 `adapter`도 받는다 — 이 대화만 다른 CLI로 돌리는 경로다.
    # `**_kwargs`는 `on_phase` 같은 additive 키워드 인자를 흡수해, 실제 시그니처가
    # 늘어나도 이 fake가 매번 따라 바뀌지 않게 한다.
    def run(prompt, adapter="", model="", job_id="", **_kwargs):
        captured["prompt"] = prompt
        return {"adapter": "test-cli", "output": output}
    return run


class TestReportRevisionProposal:
    """도크에서 보고서 수정을 요청하면 승인 대기 diff가 만들어진다."""

    def test_a_revision_request_produces_a_proposal(self, dock, monkeypatch):
        _seed_report(dock)
        captured: dict = {}
        revised = "# Canonical\n\n## Evidence\n\n[source](https://example.com/s)\n\n추가 문단"
        monkeypatch.setattr(chat.bridge, "bridge_status", lambda: {"available": True})
        monkeypatch.setattr(chat.bridge, "run_agent_prompt", _cli(
            json.dumps({"summary": "문단 추가", "revisedMarkdown": revised}), captured))

        result = chat.run_agent_chat(
            "이 브리핑에 문단을 추가해줘",
            {"surface": "briefing", "reportKind": "briefing", "reportId": f"2026-08-06.us", "marketScope": "us"},
            {},
        )

        assert result["mode"] == "task"
        assert result["proposal"]["diff"], "승인 화면에 보여줄 diff가 있어야 한다"
        assert result["proposal"]["artifactKind"] == "briefing"

    def test_the_saved_body_is_not_changed_before_approval(self, dock, monkeypatch):
        """제안을 만들 때 충돌 감지용 revision은 stamp되지만 본문은 그대로다."""
        path = _seed_report(dock)
        before = json.loads(path.read_text(encoding="utf-8"))["markdown"]
        monkeypatch.setattr(chat.bridge, "bridge_status", lambda: {"available": True})
        monkeypatch.setattr(chat.bridge, "run_agent_prompt", _cli(
            json.dumps({"summary": "s", "revisedMarkdown": "# 완전히 다른 본문"}), {}))

        chat.run_agent_chat("이 브리핑을 수정해줘",
                            {"reportKind": "briefing", "reportId": "2026-08-06.us", "marketScope": "us"}, {})

        after = json.loads(path.read_text(encoding="utf-8"))
        assert after["markdown"] == before, "승인 전에는 Canonical 본문이 바뀌지 않는다"
        assert "완전히 다른 본문" not in after["markdown"]


class TestImageAttachment:
    """이미지는 프롬프트에 경로로 실리고 바이트는 어디에도 남지 않는다."""

    def _attachment(self):
        return {"name": "shot.png", "size": len(PNG), "content": "", "imageData": base64.b64encode(PNG).decode()}

    def test_an_attached_image_reaches_the_prompt_as_a_path(self, dock, monkeypatch):
        captured: dict = {}
        monkeypatch.setattr(chat.bridge, "bridge_status", lambda: {"available": True})
        monkeypatch.setattr(chat.bridge, "run_agent_prompt", _cli("확인했습니다", captured))

        chat.run_agent_chat("이 스크린샷 읽어줘", {"surface": "agent_home"},
                            {"attachments": [self._attachment()]})

        assert "파일 경로:" in captured["prompt"]
        assert base64.b64encode(PNG).decode() not in captured["prompt"], "바이트가 프롬프트에 들어가면 안 된다"

    def test_the_scratch_file_is_gone_after_the_run(self, dock, monkeypatch):
        captured: dict = {}
        monkeypatch.setattr(chat.bridge, "bridge_status", lambda: {"available": True})
        monkeypatch.setattr(chat.bridge, "run_agent_prompt", _cli("ok", captured))

        chat.run_agent_chat("읽어줘", {"surface": "agent_home"}, {"attachments": [self._attachment()]})

        import re
        match = re.search(r"파일 경로: (.+)", captured["prompt"])
        assert match, "경로가 프롬프트에 있어야 한다"
        assert not Path(match.group(1).strip()).exists(), "실행이 끝나면 임시 파일이 남지 않는다"

    def test_the_result_never_carries_image_bytes(self, dock, monkeypatch):
        monkeypatch.setattr(chat.bridge, "bridge_status", lambda: {"available": True})
        monkeypatch.setattr(chat.bridge, "run_agent_prompt", _cli("ok", {}))

        result = chat.run_agent_chat("읽어줘", {"surface": "agent_home"}, {"attachments": [self._attachment()]})

        assert base64.b64encode(PNG).decode() not in json.dumps(result, ensure_ascii=False)
        assert result["options"]["attachments"][0]["hasImage"] is True


def test_without_a_cli_the_dock_still_answers(dock, monkeypatch):
    """CLI가 없어도 규칙 기반으로 답한다(LLM 없이 동작 원칙)."""
    monkeypatch.setattr(chat.bridge, "bridge_status", lambda: {"available": False, "message": "CLI 없음"})

    result = chat.run_agent_chat("안녕", {"surface": "agent_home"}, {})

    assert result["engine"] == "rules"
    assert result["reply"]
