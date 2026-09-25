"""시장별 구조화 체크포인트.

체크포인트는 통합 markdown에서 한 번에 뽑히고 있었다. 그래서 두 가지가 동시에 깨졌다.

- 라벨 목록이 `미국장`·`한국장`뿐이라 **유럽·일본은 본문에 섹션이 멀쩡히 있는데도 항상
  0건**이었고, 그 자리에 "체크포인트 섹션을 찾지 못했습니다"라는 없는 갭이 매번 붙었다.
- 시장을 함께 만들면 결과가 통합 briefing 하나에 담겨 **미국 보고서에 한국장 확인
  조건이 저장**됐다. `/api/research-data/checkpoints`와 도크 대화가 그 값을 그대로 낸다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.research_schema.checkpoints import checkpoints_from_markdown
from features.daily_briefing import builder
from features.daily_briefing.schema import SINGLE_MARKET_SCOPES
from features.daily_briefing.service import MARKET_LABELS, briefing_checkpoint_headings
from features.agent_mode.briefing_contract import briefing_output_contract


def _section(scope):
    return (
        f"# {scope} briefing body\n\n"
        f"## 6. 다음 {MARKET_LABELS[scope]} 체크포인트\n"
        f"- {scope} 확인 조건 하나\n"
        f"- {scope} 확인 조건 둘\n"
    )


def _extract(markdown, scope):
    return checkpoints_from_markdown(
        markdown,
        artifact_type="briefing",
        artifact_id="2026-06-20",
        headings=briefing_checkpoint_headings([scope]),
    )


# --- 라벨 목록 --------------------------------------------------------------


def test_the_heading_list_is_derived_from_the_market_labels():
    """손으로 나열하면 시장이 늘 때 새 시장만 조용히 0건이 된다."""
    headings = briefing_checkpoint_headings()

    assert all(f"다음 {label} 체크포인트" in headings for label in MARKET_LABELS.values())
    assert "내일 확인할 체크포인트" in headings


@pytest.mark.parametrize("scope", SINGLE_MARKET_SCOPES)
def test_every_market_section_is_extractable(scope):
    rows = _extract(_section(scope), scope)

    assert [row["checkpoint"] for row in rows] == [
        f"{scope} 확인 조건 하나", f"{scope} 확인 조건 둘",
    ]
    assert rows[0]["sourceSection"] == f"6. 다음 {MARKET_LABELS[scope]} 체크포인트"


def test_a_scoped_heading_list_ignores_other_markets():
    """시장별 목록으로 물어야 어느 항목이 어느 시장 것인지 남는다."""
    assert _extract(_section("kr"), "us") == []


# --- 시장별 저장 ------------------------------------------------------------


def test_single_market_briefing_replaces_the_combined_checkpoints():
    combined = {
        "marketScope": "both",
        "markdown": "\n\n---\n\n".join([_section("us"), _section("kr")]),
        "checkpoints": [*_extract(_section("us"), "us"), *_extract(_section("kr"), "kr")],
        "briefings": {},
    }

    scoped = builder._single_market_briefing(combined, "us", _extract(_section("us"), "us"))

    assert [row["sourceSection"] for row in scoped["checkpoints"]] == [
        "6. 다음 미국장 체크포인트", "6. 다음 미국장 체크포인트",
    ]


def _scope_result(scope, *, with_section=True):
    contract = briefing_output_contract(scope, markets=[scope])
    names = ("NVIDIA", "Alphabet") if scope == "us" else ("Samsung Electronics", "SK hynix")
    headings = []
    checkpoint_heading = f"6. 다음 {MARKET_LABELS[scope]} 체크포인트"
    for section in contract["requiredSections"]:
        if not with_section and section == checkpoint_heading:
            continue
        if section == "US Market Briefing":
            headings.append("# US Market Briefing — 2026.06.19")
        elif section == "Korea Market Briefing":
            headings.append("# Korea Market Briefing — 2026.06.19")
        elif "주도한 기업 ①" in section:
            headings.append(f"## {section} — {names[0]}")
        elif "주도한 기업 ②" in section:
            headings.append(f"## {section} — {names[1]}")
        else:
            headings.append(f"## {section}")
        if with_section and section == checkpoint_heading:
            headings.extend((
                f"- {scope} 확인 조건 하나",
                f"- {scope} 확인 조건 둘",
            ))
    markdown = "\n\n".join(headings)
    markdown += "\n\n" + "**한 줄 결론:** 확인\n" * 7
    markdown += "· 확인 항목\n" * 18
    markdown += "근거 있는 분석 문장 " * 1000
    return {
        "markdown": markdown,
        "sessionMode": f"{scope}_close",
        "marketSessionDate": "2026-06-19",
        "sources": [],
        "generation": {"mode": "rules", "status": "ok", "provider": "fixture"},
        "status": "ok",
        "headlines": [],
        "groups": [],
        "issueCoverageRaw": [],
        "issueCoverage": [],
        "marketDrivers": [],
        "documents": [],
    }


def _patches(missing=()):
    """`checkpoints_from_markdown`과 `data_gaps_from_messages`는 일부러 두지 않는다.

    기존 저장 테스트는 둘 다 stub해서 이 경로를 한 번도 밟지 않았다.
    `missing`에 든 시장은 체크포인트 섹션이 없는 본문을 낸다.
    """
    return [
        patch.object(builder, "build_index"),
        patch.object(builder, "load_index", return_value={"documents": []}),
        patch.object(
            builder, "select_briefing_docs",
            return_value=([], "2026-06-19", {"sourceDates": ["2026-06-19"]}),
        ),
        patch.object(builder, "cached_market_snapshot", return_value={"ok": True}),
        patch.object(builder, "cached_korea_market_data", return_value={"ok": True}),
        patch.object(builder, "build_market_tape", return_value={}),
        patch.object(builder, "preflight_from_context", return_value={}),
        patch.object(builder, "list_briefing_memories", return_value=[]),
        patch.object(builder, "load_prev_briefing", return_value=None),
        patch.object(
            builder, "_scope_result",
            side_effect=lambda scope, *a, **k: _scope_result(scope, with_section=scope not in missing),
        ),
        patch.object(builder, "leading_company_subjects_from_markdown", return_value=[]),
        patch.object(
            builder, "collect_briefing_visuals",
            return_value={"visualRecommendations": [], "visualSnapshots": [], "sidecar": {}, "warnings": []},
        ),
        patch.object(builder, "session_doc_counts", return_value={}),
        patch.object(builder, "read_briefing_prompt", return_value="prompt"),
        patch.object(builder, "apply_quality_loop", side_effect=lambda kind, payload, **kwargs: payload),
        patch.object(builder, "build_memory_from_briefing", return_value=[]),
    ]


def _build_all_markets(root, missing=()):
    patches = [patch.object(builder, "BRIEFINGS_DIR", root), *_patches(missing)]
    for item in patches:
        item.start()
    try:
        return builder.build_briefing(
            "2026-06-20", persist=True, markets=list(SINGLE_MARKET_SCOPES), llm_override=False,
        )
    finally:
        for item in reversed(patches):
            item.stop()


def _gap_messages(saved):
    return [
        str(gap.get("message") or gap.get("description") or gap)
        for gap in saved.get("dataGaps") or []
    ]


def test_each_saved_market_file_carries_only_its_own_checkpoints():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _build_all_markets(root)

        for scope in SINGLE_MARKET_SCOPES:
            saved = json.loads(
                next(root.glob(f"*.{scope}.json")).read_text(encoding="utf-8")
            )
            sections = {row["sourceSection"] for row in saved["checkpoints"]}
            assert sections == {f"6. 다음 {MARKET_LABELS[scope]} 체크포인트"}, scope
            assert len(saved["checkpoints"]) == 2, scope
            # 섹션을 찾았으므로 없는 갭이 붙으면 안 된다.
            assert not any("체크포인트 섹션" in text for text in _gap_messages(saved)), scope


# --- 시장별 갭 --------------------------------------------------------------


def test_one_market_without_a_section_leaves_its_own_gap():
    """갭이 합본 기준이면 한 시장만 비었을 때 그 사실이 어디에도 남지 않는다."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _build_all_markets(root, missing=("jp",))

        missing_saved = json.loads(next(root.glob("*.jp.json")).read_text(encoding="utf-8"))
        assert missing_saved["checkpoints"] == []
        assert f"{MARKET_LABELS['jp']}: 체크포인트 섹션을 찾지 못했습니다." in _gap_messages(missing_saved)
        # 합본에는 체크포인트가 남아 있으므로 예전 전체 갭 문구는 붙지 않는다.
        assert not any(
            text.startswith("브리핑에서 구조화 가능한") for text in _gap_messages(missing_saved)
        )

        for scope in ("us", "kr", "europe"):
            saved = json.loads(next(root.glob(f"*.{scope}.json")).read_text(encoding="utf-8"))
            assert len(saved["checkpoints"]) == 2, scope
            assert not any(
                text.startswith(f"{MARKET_LABELS[scope]}: 체크포인트") for text in _gap_messages(saved)
            ), scope
