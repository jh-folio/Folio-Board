import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.market_memory.snapshot import scrub_inline_refs

LOOKUP = {
    "rss:item:13": {"id": "rss:item:13", "source": "Bloomberg"},
    "rss:item:76": {"id": "rss:item:76", "source": "Reuters"},
    "rss:item:104": {"id": "rss:item:104", "source": "Reuters"},
}


def test_known_reference_becomes_the_publisher_name():
    text = "샌디스크 등 후속 실적 발표 종목의 주가 방향 (rss:item:13)"
    assert scrub_inline_refs(text, LOOKUP) == "샌디스크 등 후속 실적 발표 종목의 주가 방향 (Bloomberg)"


def test_repeated_publisher_is_named_once():
    text = "지멘스에너지 이익 3배·수주 사상 최대(rss:item:76, rss:item:104)."
    assert scrub_inline_refs(text, LOOKUP) == "지멘스에너지 이익 3배·수주 사상 최대 (Reuters)."


def test_unknown_reference_is_removed_not_shown():
    """rss:item:23은 사용자에게 출처가 아니라 새는 내부 구현이다."""
    text = "미 10년물이 4.6%대를 유지하는지 (rss:item:23)"
    assert scrub_inline_refs(text, LOOKUP) == "미 10년물이 4.6%대를 유지하는지"


def test_structured_ids_are_left_alone():
    payload = {
        "id": "rss:item:1",
        "sourceRefs": [{"id": "rss:item:13", "source": "Bloomberg"}],
        "summary": "가격이 올랐다 (rss:item:13).",
    }
    out = scrub_inline_refs(payload, LOOKUP)
    assert out["id"] == "rss:item:1"
    assert out["sourceRefs"] == [{"id": "rss:item:13", "source": "Bloomberg"}]
    assert out["summary"] == "가격이 올랐다 (Bloomberg)."


def test_punctuation_after_a_removed_reference_survives():
    """참조를 걷어낸 자리의 문장부호는 붙여서 남긴다 — 지우면 문장이 무너진다."""
    text = "미국 지수는 강세 (rss:item:23) , 한국은 약세다. 물가는 2.5 % 수준."
    assert scrub_inline_refs(text, LOOKUP) == "미국 지수는 강세, 한국은 약세다. 물가는 2.5% 수준."


def test_punctuation_after_a_named_reference_survives():
    text = "유동성은 완화적이다 (rss:item:76) ."
    assert scrub_inline_refs(text, LOOKUP) == "유동성은 완화적이다 (Reuters)."


def test_scrubbed_text_never_carries_control_characters():
    """치환 문자열이 역참조가 아니라 제어문자였던 적이 있다. 화면에 그대로 나갔다."""
    payload = {"summary": "판단 : 강세다 (rss:item:23) ."}
    out = scrub_inline_refs(payload, LOOKUP)
    assert out["summary"] == "판단: 강세다."
    assert not any(ord(char) < 32 for char in out["summary"])


def test_decimals_and_percentages_survive():
    text = "미 10년물이 4.627%로 내렸고 WTI는 -9.79%다."
    assert scrub_inline_refs(text, LOOKUP) == text


def test_market_interpretation_drops_citations_instead_of_naming_them():
    """시장 해석은 화면의 큰 본문이라 문장마다 매체명이 붙으면 읽히지 않는다.

    다른 필드는 매체명으로 살리고 이 필드만 지운다. 출처는 그 뷰의 sourceRefs가
    이미 갖고 있다.
    """
    payload = {
        "marketViews": {
            "kr": {
                "marketInterpretation": "유가가 급락했고 (rss:item:13), 증시가 올랐다 (rss:item:76).",
                "actionSummary": "관망이 낫다 (rss:item:13).",
                "sourceRefs": ["rss:item:13"],
            }
        }
    }
    out = scrub_inline_refs(payload, LOOKUP)
    view = out["marketViews"]["kr"]
    assert view["marketInterpretation"] == "유가가 급락했고, 증시가 올랐다."
    assert view["actionSummary"] == "관망이 낫다 (Bloomberg)."
    assert view["sourceRefs"] == ["rss:item:13"]


def test_empty_view_headline_falls_back_to_a_korean_market_label():
    """헤드라인이 비면 `EUROPE`가 아니라 `유럽`이 나와야 한다.

    나머지가 전부 한국어인 자리에 영문 코드가 앉으면 값이 빠진 티가 아니라
    고장으로 읽힌다.
    """
    from features.market_memory.snapshot import _market_view

    view = _market_view({"marketInterpretation": "정책 불확실성이 가격을 지배한다."}, "europe", {})
    assert view["headline"] == "유럽"


def test_interpretation_audit_counts_a_recital_lead():
    """계약이 깨졌는지 재서 남긴다. 자르거나 실패시키지는 않는다.

    첫 문장이 지수 등락 나열이면 `leadNumbers`가 그것을 말한다. 실측으로
    프롬프트에 같은 금지 규칙이 있는 채로 이 문장이 나왔다.
    """
    from features.market_memory.snapshot import _market_view

    recital = (
        "27일 유럽 증시는 전 지역이 하락 마감했고, 파리가 1.6%, 밀라노가 1.17%, "
        "마드리드가 0.9%, 런던이 0.7% 내렸습니다. 원인은 통화정책이었습니다."
    )
    audit = _market_view({"marketInterpretation": recital}, "europe", {})["interpretationAudit"]
    assert audit["sentences"] == 2
    assert audit["leadNumbers"] == 5

    clean = "유럽은 이익 개선보다 정책·재정 불확실성이 가격을 지배하는 시장이 됐습니다."
    assert _market_view({"marketInterpretation": clean}, "europe", {})["interpretationAudit"] == {
        "chars": len(clean),
        "sentences": 1,
        "numbers": 0,
        "leadNumbers": 0,
    }
