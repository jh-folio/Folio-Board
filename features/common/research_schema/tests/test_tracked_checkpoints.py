"""구조화 체크포인트 스키마·검증·병합 테스트.

    py -3 features/common/research_schema/tests/test_tracked_checkpoints.py
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from features.common.research_schema.tracked_checkpoints import (
    MAX_CHECKPOINTS,
    MAX_HISTORY,
    append_history,
    checkpoint_id,
    checkpoint_label,
    checkpoint_labels,
    merge_checkpoint_lists,
    merge_with_templates,
    normalize_tracked_checkpoint,
    split_checkpoints,
)

NOW = "2026-08-30T00:00:00+00:00"


def _cp(**overrides):
    base = {
        "item": "전력 설비 기업 실적 가이던스 상향",
        "direction": "supporting",
        "matchers": {"tickers": ["gev"], "keywords": ["가이던스 상향", "전력설비"]},
    }
    base.update(overrides)
    return base


def test_normalize_keeps_schema_and_drops_unknown_keys():
    out = normalize_tracked_checkpoint(_cp(전송되지않는키="x", status="confirmed"), now=NOW)
    assert set(out) == {
        "id", "item", "direction", "matchers", "dueBy", "status",
        "createdAt", "lastVerdict", "history",
    }
    assert out["matchers"]["tickers"] == ["GEV"]           # 대문자 정규화
    assert out["status"] == "confirmed"
    assert out["createdAt"] == NOW
    assert out["id"].startswith("cp_") and len(out["id"]) == 11


def test_id_is_stable_for_same_item_and_matchers():
    first = normalize_tracked_checkpoint(_cp(), now=NOW)
    second = normalize_tracked_checkpoint(_cp(status="confirmed", createdAt="2026-01-01T00:00:00+00:00"), now=NOW)
    assert first["id"] == second["id"]
    other = normalize_tracked_checkpoint(_cp(item="다른 확인 항목"), now=NOW)
    assert other["id"] != first["id"]
    assert first["id"] == checkpoint_id("전력 설비 기업 실적 가이던스 상향", ["GEV"], ["가이던스 상향", "전력설비"])


def test_unknown_enum_direction_drops_the_element():
    """direction은 뜻이 뒤집히는 값이라 기본값을 주지 않는다."""
    assert normalize_tracked_checkpoint(_cp(direction="긍정"), now=NOW) is None
    assert normalize_tracked_checkpoint(_cp(direction=""), now=NOW) is None


def test_unknown_status_and_verdict_fall_back_without_dropping():
    out = normalize_tracked_checkpoint(
        _cp(status="확인됨", lastVerdict={"verdict": "좋음", "at": NOW}), now=NOW
    )
    assert out["status"] == "open"
    assert out["lastVerdict"] is None


def test_item_length_and_keyword_rules():
    long_item = normalize_tracked_checkpoint(_cp(item="가" * 200), now=NOW)
    assert len(long_item["item"]) == 120
    # keyword 1~6개, 각 2~40자
    trimmed = normalize_tracked_checkpoint(
        _cp(matchers={"keywords": ["a", "가" * 41, "정상 키워드", "정상 키워드", "둘째", "셋째", "넷째", "다섯", "여섯", "일곱"]}),
        now=NOW,
    )
    assert len(trimmed["matchers"]["keywords"]) == 6
    assert "a" not in trimmed["matchers"]["keywords"]
    assert "가" * 41 not in trimmed["matchers"]["keywords"]
    assert trimmed["matchers"]["keywords"].count("정상 키워드") == 1


def test_state_label_keyword_is_rejected():
    """상태 라벨 전문을 keyword로 쓰면 그 상태의 모든 근거가 매칭돼 과잉 확인이 된다."""
    out = normalize_tracked_checkpoint(
        _cp(matchers={"keywords": ["AI 데이터센터 전력 병목", "가이던스 상향"]}),
        now=NOW,
        forbidden_keywords=["AI데이터센터 전력병목"],   # 띄어쓰기가 달라도 같은 라벨이다
    )
    assert out["matchers"]["keywords"] == ["가이던스 상향"]
    dropped = normalize_tracked_checkpoint(
        _cp(matchers={"keywords": ["AI 데이터센터 전력 병목"]}),
        now=NOW,
        forbidden_keywords=["AI 데이터센터 전력 병목"],
    )
    assert dropped is None      # 남는 keyword가 없으면 그 체크포인트를 버린다


def test_narrative_requires_keyword_thesis_requires_ticker_and_keyword():
    no_keyword = _cp(matchers={"tickers": ["NVDA"], "keywords": []})
    assert normalize_tracked_checkpoint(no_keyword, scope="narrative", now=NOW) is None
    assert normalize_tracked_checkpoint(no_keyword, scope="thesis", now=NOW) is None

    keyword_only = _cp(matchers={"keywords": ["가이던스 상향"]})
    assert normalize_tracked_checkpoint(keyword_only, scope="narrative", now=NOW) is not None
    # 티커만으로는 "그 회사 뉴스가 있다"이지 가설 신호가 아니다.
    assert normalize_tracked_checkpoint(keyword_only, scope="thesis", now=NOW) is None
    assert normalize_tracked_checkpoint(_cp(), scope="thesis", now=NOW) is not None


def test_due_by_must_be_iso_date_after_creation():
    assert normalize_tracked_checkpoint(_cp(dueBy="2026-09-15"), now=NOW)["dueBy"] == "2026-09-15"
    assert normalize_tracked_checkpoint(_cp(dueBy="다음 분기"), now=NOW)["dueBy"] is None
    assert normalize_tracked_checkpoint(_cp(dueBy="2026-08-01"), now=NOW)["dueBy"] is None


def test_split_keeps_templates_and_caps_structured():
    stored = ["템플릿 문장 1", _cp(), {"item": "깨진 것", "direction": "??"}, "템플릿 문장 2"]
    structured, templates = split_checkpoints(stored, now=NOW)
    assert len(structured) == 1
    assert templates == ["템플릿 문장 1", "템플릿 문장 2"]

    many = [_cp(item=f"확인 항목 {i}") for i in range(12)]
    structured, _ = split_checkpoints(many, now=NOW)
    assert len(structured) == MAX_CHECKPOINTS


def test_merge_with_templates_preserves_structured_status():
    stored = [_cp(status="confirmed", history=[{"at": NOW, "from": "open", "to": "confirmed", "verdict": "confirmed"}]), "어제 템플릿"]
    merged = merge_with_templates(stored, ["오늘 템플릿 1", "오늘 템플릿 2"], now=NOW)
    assert merged[0]["status"] == "confirmed"
    assert len(merged[0]["history"]) == 1
    assert merged[1:] == ["오늘 템플릿 1", "오늘 템플릿 2"]   # 어제 템플릿은 사라진다


def test_merge_lists_inherits_status_and_history_for_same_id():
    existing = [_cp(
        status="challenged",
        createdAt="2026-08-01T00:00:00+00:00",
        lastVerdict={"verdict": "challenged", "at": "2026-08-20T00:00:00+00:00", "evidence": []},
        history=[{"at": "2026-08-20T00:00:00+00:00", "from": "open", "to": "challenged", "verdict": "challenged"}],
    )]
    incoming = [_cp()]      # LLM이 같은 항목을 다시 냈다 — status는 판정 pass만 바꾼다
    merged = merge_checkpoint_lists(existing, incoming, now=NOW)
    assert len(merged) == 1
    assert merged[0]["status"] == "challenged"
    assert merged[0]["createdAt"] == "2026-08-01T00:00:00+00:00"
    assert merged[0]["lastVerdict"]["verdict"] == "challenged"
    assert len(merged[0]["history"]) == 1


def test_merge_lists_keeps_open_leftovers_and_prunes_resolved():
    leftovers = [
        _cp(item="아직 열린 항목", status="open"),
        _cp(item="해소된 항목", status="confirmed", createdAt="2026-01-01T00:00:00+00:00"),
    ]
    incoming = [_cp(item=f"새 항목 {i}") for i in range(7)]
    merged = merge_checkpoint_lists(leftovers, incoming, now=NOW)
    items = [cp["item"] for cp in merged]
    assert len(merged) == MAX_CHECKPOINTS
    assert "아직 열린 항목" in items       # open은 유지
    assert "해소된 항목" not in items      # 해소된 것은 상한 안에서 정리


def test_history_cap_removes_oldest_first():
    checkpoint = normalize_tracked_checkpoint(_cp(), now=NOW)
    for i in range(MAX_HISTORY + 5):
        append_history(checkpoint, at=f"2026-08-{i % 28 + 1:02d}T00:00:00+00:00", from_status="open", to_status="confirmed", verdict="confirmed")
        checkpoint["history"][-1]["at"] = f"seq-{i}"
    assert len(checkpoint["history"]) == MAX_HISTORY
    assert checkpoint["history"][0]["at"] == "seq-5"


def test_checkpoint_label_reads_both_shapes():
    assert checkpoint_label("템플릿 문장") == "템플릿 문장"
    assert checkpoint_label(_cp()) == "전력 설비 기업 실적 가이던스 상향"
    assert checkpoint_label({"nothing": 1}) == ""
    assert checkpoint_labels(["문장", _cp(), {"nothing": 1}]) == ["문장", "전력 설비 기업 실적 가이던스 상향"]


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} tests passed")
    return True


if __name__ == "__main__":
    sys.exit(0 if _run_all() else 1)
