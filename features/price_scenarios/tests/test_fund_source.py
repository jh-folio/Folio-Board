import json
from concurrent.futures import CancelledError
import pytest
from features.price_scenarios import collect
from .test_collect import collector, sec

FUNDS = {"fields": ["cik", "seriesId", "classId", "symbol"],
         "data": [[1064642, "S000006983", "C000019036", "SPYM"]]}


def test_spym_equity_metadata_official_exact_fund_and_cache(tmp_path, sec, monkeypatch):
    made, _ = collector(tmp_path)
    calls = []
    made.sec_bytes = lambda url: calls.append(url) or json.dumps(FUNDS).encode()
    made.instrument_type = lambda symbol: "EQUITY"
    # A normal company does not request the fund list.
    made.collect("US", "AAPL")
    assert calls == [collect.SEC_FACTS_URL.format(cik="0000320193")]
    calls.clear()
    monkeypatch.setattr(collect.sec_companyfacts, "resolve_cik", lambda *a: "")
    for _ in range(2):
        with pytest.raises(collect.CollectionError) as e:
            made.collect("US", "SPYM")
        assert e.value.code == "fund_not_supported"
    assert calls == [collect.SEC_FUNDS_URL]
    with pytest.raises(collect.CollectionError) as e:
        made.collect("US", "SPY")
    assert (e.value.code, e.value.sub_code) == ("company_not_found", "no_cik")


@pytest.mark.parametrize("kind", [None, "EQUITY", TimeoutError()])
def test_kind_unknown_or_failure_can_use_official_list(tmp_path, sec, monkeypatch, kind):
    made, _ = collector(tmp_path)
    monkeypatch.setattr(collect.sec_companyfacts, "resolve_cik", lambda *a: "")
    def lookup(symbol):
        if isinstance(kind, Exception):
            raise kind
        return kind
    made.instrument_type = lookup
    made.sec_bytes = lambda url: json.dumps(FUNDS).encode()
    with pytest.raises(collect.CollectionError) as e:
        made.collect("US", "SPYM")
    assert e.value.code == "fund_not_supported"


def test_type_confirmed_skips_list_and_list_failure_keeps_no_cik(tmp_path, sec, monkeypatch):
    made, _ = collector(tmp_path)
    monkeypatch.setattr(collect.sec_companyfacts, "resolve_cik", lambda *a: "")
    calls = []
    def fail(url):
        calls.append(url)
        raise TimeoutError()
    made.sec_bytes = fail
    made.instrument_type = lambda symbol: "ETF"
    with pytest.raises(collect.CollectionError) as e:
        made.collect("US", "SGOV")
    assert e.value.code == "fund_not_supported" and calls == []
    made.instrument_type = lambda symbol: "EQUITY"
    with pytest.raises(collect.CollectionError) as e:
        made.collect("US", "SPYM")
    assert (e.value.code, e.value.sub_code) == ("company_not_found", "no_cik")
    assert calls == [collect.SEC_FUNDS_URL]
    # KR type probe never touches the SEC list.
    assert made._is_fund("379800", "KR") is False
    assert calls == [collect.SEC_FUNDS_URL]
    made.cancel = lambda: (_ for _ in ()).throw(CancelledError())
    with pytest.raises(CancelledError):
        made._sec_fund("SPYM")
