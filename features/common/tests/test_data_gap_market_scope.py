from features.common.research_schema.data_gaps import (
    data_gap_applies_to,
    data_gaps_from_messages,
)


def test_market_is_stored_and_participates_in_stable_identity():
    us = data_gaps_from_messages(["price missing"], artifact_type="briefing", artifact_id="x", market="us")[0]
    kr = data_gaps_from_messages(["price missing"], artifact_type="briefing", artifact_id="x", market="kr")[0]

    assert us["market"] == "us" and kr["market"] == "kr"
    assert us["id"] != kr["id"]


def test_single_market_projection_keeps_global_and_own_market_only():
    gaps = [
        {"market": "", "message": "legacy"},
        {"market": "both", "message": "global"},
        {"market": "us", "message": "us"},
        {"market": "kr", "message": "kr"},
    ]

    assert [row["message"] for row in gaps if data_gap_applies_to(row, "us")] == ["legacy", "global", "us"]
