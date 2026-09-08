"""에이전트가 읽는 팩 파일에 앱 전용 payload를 싣지 않는다.

프롬프트는 팩 파일을 "읽어라"라고 지시하는데(`bridge._agent_prompt`), `internal`
(`visualScopeResults`, `groups`)은 에이전트가 쓰지 않으면서 팩의 대부분을 차지했다.

실측: 2026-09-07 KR 일간 팩이 7.32MB였고, Claude Code CLI가 이 파일을 통으로 읽지
못해 잘린 조각에서 답을 만들었다. 같은 팩의 `outputContract.minimumCharacters`가
2500인데 모델은 40이라고 답했고, 그 결과 필수 제목 8개가 모두 빠진 1517자짜리
출력이 나와 출력 계약 검사에서 잡이 죽었다. `internal`만 분리하면 0.93MB가 된다.

Codex는 같은 팩을 읽어냈기 때문에 이 결함은 어댑터를 바꾸기 전까지 보이지 않았다.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from features.agent_mode import schema


def _pack() -> dict:
    return {
        "taskType": "briefing",
        "artifactId": "2026-09-07",
        "packId": "p1",
        "prompt": "본문을 쓴다",
        "outputContract": {"minimumCharacters": 2500},
        "sources": [{"id": "s1"}],
        "internal": {"visualScopeResults": {"padding": "x" * 4096}, "groups": [{"g": "y" * 4096}]},
    }


def test_agent_pack_file_excludes_internal_and_stays_small(tmp_path):
    with patch.object(schema, "task_dir", return_value=tmp_path):
        path = schema.write_pack(_pack())
    document = json.loads(path.read_text(encoding="utf-8"))
    assert "internal" not in document
    assert document["outputContract"]["minimumCharacters"] == 2500
    sidecar = schema._internal_sidecar(path)
    assert sidecar.exists()
    assert path.stat().st_size < sidecar.stat().st_size


def test_read_pack_restores_internal_from_the_sidecar(tmp_path):
    with patch.object(schema, "task_dir", return_value=tmp_path):
        path = schema.write_pack(_pack())
    with patch.object(schema, "_allowed_pack_roots", return_value=(tmp_path.resolve(),)):
        restored = schema.read_pack(path)
    assert sorted(restored["internal"]) == ["groups", "visualScopeResults"]
    assert restored["internal"]["groups"][0]["g"].startswith("y")


def test_status_update_does_not_inline_internal_again(tmp_path):
    """상태만 바꾸는 호출이 사이드카를 본문으로 되돌리면 분리가 무의미해진다."""
    with patch.object(schema, "task_dir", return_value=tmp_path):
        path = schema.write_pack(_pack())
    with patch.object(schema, "_allowed_pack_roots", return_value=(tmp_path.resolve(),)):
        returned = schema.update_pack_status(path, status="done")
    assert "internal" not in json.loads(path.read_text(encoding="utf-8"))
    assert schema._internal_sidecar(path).exists()
    # 호출자는 예전과 같은 팩을 본다.
    assert sorted(returned["internal"]) == ["groups", "visualScopeResults"]
