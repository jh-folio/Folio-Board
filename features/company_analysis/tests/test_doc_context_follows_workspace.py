"""저장된 원문은 워크스페이스를 따라가야 읽힌다.

`_doc_context_text()`는 `documents.path`가 짧은 스니펫만 들고 있을 때 원본 파일을 열어
10-K 원문을 채운다. 그런데 상대 경로를 앱 폴더(`ROOT`) 기준으로 이어 붙이고 경계까지
앱 폴더로 쟀다. `documents.path`는 **자료 폴더 기준**이므로(`workspace_relative()`),
`FOLIO_HOME`이 체크아웃 밖이면 한 건도 읽지 못한다.

`except Exception`이 삼켜서 터지지는 않는다. 그래서 더 나쁘다 — 원문 대신 스니펫이나
요약으로 조용히 내려앉고, 보고서가 얇아진 이유가 어디에도 남지 않는다.
"""
from __future__ import annotations

import pytest

from features.company_analysis.service import _doc_context_text

BODY = "ITEM 1A. RISK FACTORS " + ("본문 " * 800)


@pytest.fixture
def moved_workspace(tmp_path, monkeypatch):
    home = tmp_path / "workspace"
    (home / "research-inbox" / "filings").mkdir(parents=True)
    monkeypatch.setenv("FOLIO_HOME", str(home))

    from features.common import workspace

    workspace.reset_cache()
    assert workspace.workspace_root() == home.resolve()
    yield home
    monkeypatch.delenv("FOLIO_HOME", raising=False)
    workspace.reset_cache()


def test_a_workspace_relative_path_is_read_from_the_moved_workspace(moved_workspace):
    (moved_workspace / "research-inbox" / "filings" / "10k.txt").write_text(BODY, encoding="utf-8")

    text = _doc_context_text({"content": "짧은 스니펫", "path": "research-inbox/filings/10k.txt"})

    assert "RISK FACTORS" in text
    assert len(text) > len("짧은 스니펫")


def test_an_absolute_path_inside_the_moved_workspace_is_read(moved_workspace):
    target = moved_workspace / "research-inbox" / "filings" / "20f.txt"
    target.write_text(BODY, encoding="utf-8")

    assert "RISK FACTORS" in _doc_context_text({"content": "짧은", "absolutePath": str(target)})


def test_a_path_outside_the_workspace_falls_back_instead_of_reading(moved_workspace, tmp_path):
    """경계는 유지한다. 밖의 파일은 읽지 않고 가진 것으로 답한다."""
    outsider = tmp_path / "outside.txt"
    outsider.write_text(BODY, encoding="utf-8")

    text = _doc_context_text({"content": "", "summary": "요약만", "absolutePath": str(outsider)})

    assert text == "요약만"


def test_long_content_never_touches_the_disk(moved_workspace):
    """이미 본문이 충분하면 파일을 열 이유가 없다."""
    assert _doc_context_text({"content": BODY, "path": "research-inbox/filings/없는파일.txt"}) == BODY


def test_a_missing_file_falls_back_quietly(moved_workspace):
    assert _doc_context_text({"content": "", "summary": "요약", "path": "research-inbox/filings/없음.txt"}) == "요약"
