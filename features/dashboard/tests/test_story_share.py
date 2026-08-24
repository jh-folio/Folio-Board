import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.dashboard.story_share import build_story_share

# 2026-08-04(화) 기준: US 직전 거래일 2026-08-03(월), 그 전 거래일 2026-07-31(금).
# select_briefing_docs(strict)의 sourceDates는 8/4 브리핑이면 8/3(US)·8/3(KR) 등이므로
# 테스트 문서 날짜는 window에 들어가도록 실제 계산으로 잡는다.


def _doc(date, title, market="US", path="research-inbox/rss/x.md"):
    return {
        "date": date,
        "title": title,
        "content": title,
        "path": path,
        "source": "TestWire",
        "markets": [market],
    }


def _docs_for(date, titles):
    return [_doc(date, title) for title in titles]


def test_top4_plus_other_and_share_sums_to_one():
    docs = _docs_for("2026-08-03", [
        "Nvidia AI chip demand surges",  # 반도체/AI
        "Samsung semiconductor capex up",  # 반도체/AI
        "Fed rate cut expectations grow",  # 금리
        "Treasury yields fall on rate bets",  # 금리
        "Oil prices jump on Middle East supply risk",  # 원자재/유가
        "Earnings guidance beats for tech",  # 실적
        "Dollar weakens against won exchange rate",  # 환율
        "Random local festival news with market word market",  # 분류 실패 → 그 외
    ])
    payload = build_story_share(docs, "2026-08-04", "us")
    assert payload["market"] == "us"
    labels = [row["label"] for row in payload["items"]]
    assert len([row for row in payload["items"] if not row["isOther"]]) <= 4
    assert labels[-1] == "그 외 이야기" or not any(row["isOther"] for row in payload["items"])
    total_share = sum(row["share"] for row in payload["items"])
    assert 0.95 <= total_share <= 1.05


def test_delta_is_percentage_points_against_previous_session():
    docs = (
        # 8/3(월) — 오늘 window
        _docs_for("2026-08-03", ["Nvidia AI chip demand", "AI semiconductor rally", "Fed rate decision looms"])
        # 7/31(금) — 직전 거래일 window
        + _docs_for("2026-07-31", ["Fed rate hike odds", "Rate cut bets rise", "Nvidia AI chip news"])
    )
    payload = build_story_share(docs, "2026-08-04", "us")
    # 비교 기준은 직전 **N거래일**이다(0.5.4). 하루만 보면 그날 수집량이 흔들리는 것만으로
    # 비중이 수십 %p 움직인다. 8/3은 그 창 안에 들어 있다.
    assert "2026-08-03" in payload["previousDates"]
    by_label = {row["label"]: row for row in payload["items"]}
    semis = by_label.get("반도체/AI")
    assert semis is not None
    assert semis["previousShare"] is not None
    assert isinstance(semis["deltaPp"], int)


def test_empty_days_warn_instead_of_failing():
    payload = build_story_share([], "2026-08-04", "kr")
    assert payload["collectedCount"] == 0
    assert "no_collected_news_for_date" in payload["warnings"]
    assert "no_previous_session_news" in payload["warnings"]
    assert payload["items"] == []
