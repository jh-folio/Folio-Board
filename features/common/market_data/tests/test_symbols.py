from features.common.market_data.symbols import yfinance_symbol_candidates


def test_bare_kr_codes_get_exchange_suffix_candidates():
    """저장 규약이 bare 6자리라(워치리스트가 접미사를 떼기까지 한다) provider 경계가
    .KS→.KQ 순서로 시도해야 한다 — yfinance는 bare 코드를 404로 거절한다(실측)."""
    assert yfinance_symbol_candidates("005930") == ("005930.KS", "005930.KQ")
    assert yfinance_symbol_candidates(" 005930 ") == ("005930.KS", "005930.KQ")


def test_non_kr_symbols_pass_through():
    assert yfinance_symbol_candidates("AMD") == ("AMD",)
    assert yfinance_symbol_candidates("7203.T") == ("7203.T",)
    assert yfinance_symbol_candidates("^GSPC") == ("^GSPC",)
    assert yfinance_symbol_candidates("") == ("",)
