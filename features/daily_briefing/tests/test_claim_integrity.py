from features.daily_briefing.claim_integrity import enforce_claim_integrity


def _source(text: str, identifier: str = "src_1") -> dict:
    return {"sourceId": identifier, "title": text, "summary": text}


def test_unsupported_capital_flow_is_downgraded_without_llm_call() -> None:
    markdown = "채권에서 이탈한 자금이 반도체로 이동했다. 반도체는 자금의 대체 목적지였다."
    guarded, ledger = enforce_claim_integrity(markdown, [_source("채권 약세와 반도체 강세")], mode="active")
    assert "이탈한 자금이" not in guarded
    assert "자금의 대체 목적지" not in guarded
    assert "동시에 나타났지만" in guarded
    assert "근거는 부족하다" in guarded
    assert ledger["integrity"]["status"] == "review"
    assert {row["status"] for row in ledger["integrity"]["findings"]} == {"downgraded"}


def test_explicit_capital_flow_source_preserves_claim() -> None:
    markdown = "채권에서 이탈한 자금이 반도체로 이동했다."
    guarded, ledger = enforce_claim_integrity(
        markdown, [_source("채권 자금 이탈 뒤 반도체로 자금 이동", "src_flow")], mode="active",
    )
    assert guarded == markdown
    assert ledger["integrity"]["findings"][0]["status"] == "supported"
    assert ledger["integrity"]["findings"][0]["supportingSourceIds"] == ["src_flow"]


def test_sector_breadth_requires_direct_breadth_evidence() -> None:
    guarded, ledger = enforce_claim_integrity(
        "삼성전자가 올랐고 반도체 소부장 강세가 이어졌다.",
        [_source("삼성전자 3% 상승")],
        mode="active",
    )
    assert "일부 반도체 소부장 종목의 강세" in guarded
    assert ledger["integrity"]["reasonCodes"] == ["direct_source_relationship_missing"]


def test_diagnose_mode_records_but_does_not_rewrite() -> None:
    markdown = "업종 전반의 강세가 나타났다."
    guarded, ledger = enforce_claim_integrity(markdown, [], mode="diagnose")
    assert guarded == markdown
    assert ledger["integrity"]["findings"][0]["status"] == "review"
