from features.daily_briefing.web_evidence import _proof


def test_unrelated_page_tokens_cannot_verify_quote():
    fact = dict(market="us", instrument="SPY", metric="close", unit="USD", value="560", sessionDate="2026-08-26", quote="SPY had an event")
    assert not _proof(fact, {}, "SPY had an event. Elsewhere: 2026-08-26 close 560 USD")


def test_index_cannot_verify_etf_even_if_number_matches():
    quote = "2026-08-26 S&P 500 close 560 USD"
    fact = dict(market="us", instrument="SPY", metric="close", unit="USD", value="560", sessionDate="2026-08-26", quote=quote)
    assert not _proof(fact, {}, quote)


def test_one_unambiguous_quote_is_supported_but_multiple_metrics_are_unknown():
    quote = "2026-08-26 SPY close 560 USD"
    fact = dict(market="us", instrument="SPY", metric="close", unit="USD", value="560", sessionDate="2026-08-26", quote=quote)
    assert _proof(fact, {}, quote)
    fact["quote"] += " while revenue was 90 USD"
    assert not _proof(fact, {}, fact["quote"])


def test_only_independently_verified_web_fact_reaches_final_price_validation():
    from features.daily_briefing.finalize import _facts
    row = dict(market="us", instrument="SPY", metric="oneDayPct", unit="percent", value="0.4",
        sessionDate="2026-08-26", verified=True, evidenceMethod="public_quote_exact",
        sourceId="web_test", sourceEvidenceHash="a" * 64)
    candidate = dict(marketScope="us", date="2026-08-26", sessionDate="2026-08-26", webLookup={"facts": [row]})
    assert any(f.key == "SPY" and f.change_pct == 0.4 for f in _facts(candidate))
    row.pop("sourceEvidenceHash")
    assert not _facts(candidate)
