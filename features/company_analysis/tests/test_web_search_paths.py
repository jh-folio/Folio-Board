"""두 생성 경로가 웹 검색을 같은 방법으로 정하는지 못박는다(§6 규칙 14).

`app.py`가 CLI만 `bool_override(...) is True`로 접던 시절, 화면이 `webSearch`를 보내지
않으므로 CLI는 언제나 꺼졌고 바로 아래 API 경로는 같은 `None`을 설정값으로 풀어 켜졌다.
같은 요청이 경로에 따라 정반대가 된다. 실측으로 로컬 문서 0건인 회사의 CLI 보고서에
`webLookup`이 없고 `sourceLedger`가 0건이었다 — 자료 공백을 메우는 유일한 경로가
그 설치에서 죽어 있었다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from features.company_analysis import web_lookup
from features.llm_settings.client import bool_override

APP = Path(__file__).resolve().parents[3] / "app.py"


def _resolve(raw, setting: bool) -> bool:
    """`app.py`가 쓰는 규칙. 두 경로가 이 한 줄을 공유해야 한다."""
    value = bool_override(raw)
    return setting if value is None else value


@pytest.mark.parametrize("raw", [None, "true", "false", "1", "0"])
@pytest.mark.parametrize("setting", [True, False])
def test_both_paths_agree_for_every_input(raw, setting):
    assert _resolve(raw, setting) == _resolve(raw, setting)


def test_missing_parameter_follows_the_setting_not_a_hard_off():
    """화면은 `webSearch`를 보내지 않는다. 그때 설정이 이겨야 한다."""
    assert _resolve(None, True) is True
    assert _resolve(None, False) is False


def test_explicit_false_still_wins_over_the_setting():
    assert _resolve("false", True) is False


def test_app_no_longer_folds_the_cli_path_with_is_true():
    """`is True`로 접으면 `None`이 조용히 False가 된다. 그 표현이 돌아오지 않게 한다."""
    source = APP.read_text(encoding="utf-8")
    assert not re.search(r'bool_override\([^)]*webSearch[^)]*\)\s+is\s+True', source)
    assert "use_web_search_for_analysis() if web_search is None else web_search" in source


def test_a_company_with_no_local_documents_asks_for_the_web():
    """이 판정이 도달하지 못하면 웹 조회 패스 전체가 죽은 코드다."""
    assert web_lookup.needs_web_lookup(document_count=0, data_gaps={}) is True
    assert web_lookup.needs_web_lookup(document_count=20, data_gaps={}) is False
