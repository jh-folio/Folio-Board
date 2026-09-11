from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from features.company_analysis.valuation_basis import (
    build_valuation_basis,
    market_cashflow_is_compatible,
    normalize_currency,
    render_valuation_basis_context,
)


def _sec(currency="USD"):
    return {"ok": True, "currency": currency, "rows": []}


def _market(**overrides):
    data = {
        "ok": True,
        "price": 100.0,
        "sharesOutstanding": 10_000.0,
        "currency": "USD",
        "cashflowRows": [],
    }
    data.update(overrides)
    return data


def test_same_quote_and_reporting_currency_keeps_derived_market_cap_eligible():
    basis = build_valuation_basis(_sec("USD"), _market(), share_count=10_000)

    assert basis["priceCurrencyStatus"] == "same"
    assert basis["marketValueDerivedSafe"] is True
    assert basis["eligibility"]["per"]["eligible"] is True
    assert basis["eligibility"]["marketMultiples"]["eligible"] is True
    assert basis["eligibility"]["dcf"]["eligible"] is True


def test_mixed_quote_currency_blocks_price_based_valuation_without_fx():
    basis = build_valuation_basis(
        _sec("EUR"),
        _market(currency="USD", marketCap=1_000_000, financialCurrency="USD"),
        share_count=10_000,
    )

    assert basis["priceCurrencyStatus"] == "mismatch"
    assert basis["eligibility"]["per"]["eligible"] is False
    assert basis["eligibility"]["dcf"]["eligible"] is False
    assert "price_currency_mismatch" in basis["eligibility"]["per"]["reasonCodes"]
    context = render_valuation_basis_context(basis)
    assert "환산" in context
    assert "숫자를 추정하지 마세요" in context


def test_unknown_quote_currency_is_not_defaulted_to_usd():
    basis = build_valuation_basis(
        _sec("USD"),
        _market(currency=None, quoteCurrency=None, currencyKnown=False),
        share_count=10_000,
    )

    assert basis["quoteCurrency"] is None
    assert basis["eligibility"]["per"]["eligible"] is False
    assert "quote_currency_unknown" in basis["eligibility"]["per"]["reasonCodes"]


def test_cashflow_fallback_requires_separate_matching_financial_currency():
    rows = [{"year": "2025", "Free Cash Flow": 10.0}]
    same = build_valuation_basis(_sec("KRW"), _market(currency="KRW", financialCurrency="KRW", cashflowRows=rows), share_count=10_000)
    unknown = build_valuation_basis(_sec("KRW"), _market(currency="KRW", cashflowRows=rows), share_count=10_000)
    mixed = build_valuation_basis(_sec("KRW"), _market(currency="KRW", financialCurrency="USD", cashflowRows=rows), share_count=10_000)

    assert market_cashflow_is_compatible(same) is True
    assert market_cashflow_is_compatible(unknown) is False
    assert market_cashflow_is_compatible(mixed) is False


def test_provider_cashflow_is_not_used_when_reporting_currency_is_unknown():
    from features.company_analysis.report_rules import _market_cashflow_by_year

    market = _market(financialCurrency="USD", cashflowRows=[{"year": "2025", "Free Cash Flow": 10.0}])
    assert _market_cashflow_by_year(market, "Free Cash Flow", reporting_currency=None) == {}


def test_explicit_share_ratio_is_the_only_ratio_mismatch_signal():
    compatible = build_valuation_basis(_sec("USD"), _market(), share_count=10_000)
    mismatch = build_valuation_basis(_sec("USD"), _market(adrRatio=2), share_count=10_000)

    assert compatible["shareUnitStatus"] == "compatible"
    assert mismatch["shareUnitStatus"] == "mismatch"
    # PER needs price and EPS but not a share count; an explicit ratio mismatch
    # still blocks it, while absent share metadata alone does not.
    assert mismatch["eligibility"]["per"]["eligible"] is False
    assert "share_unit_mismatch" in mismatch["eligibility"]["dcf"]["reasonCodes"]


def test_pence_quote_units_are_not_silently_converted_to_pounds():
    assert normalize_currency("GBp") == "GBp"
    assert normalize_currency("GBX") == "GBX"
    assert normalize_currency("GBP") == "GBP"
    basis = build_valuation_basis(_sec("GBP"), _market(currency="GBp"), share_count=10_000)
    assert basis["priceCurrencyStatus"] == "mismatch"
    assert basis["eligibility"]["per"]["eligible"] is False


def test_missing_reporting_currency_does_not_get_a_usd_valuation_fallback():
    basis = build_valuation_basis(
        {"ok": True, "rows": []},
        _market(currency="USD", currencyKnown=True, marketCap=1_000_000),
        share_count=10_000,
    )

    assert basis["reportingCurrency"] is None
    assert basis["eligibility"]["per"]["eligible"] is False
    assert "reporting_currency_unknown" in basis["eligibility"]["per"]["reasonCodes"]


def test_known_enterprise_value_does_not_authorize_foreign_quote_market_cap_derivation():
    """A USD EV may remain usable while EUR price*shares cannot become USD cap."""
    from features.company_analysis.report_rules import build_valuation_metrics

    sec = {
        "ok": True,
        "currency": "USD",
        "rows": [
            {"metric": "Revenue", "annual": [{"end": "2025-12-31", "val": 1_000}]},
            {"metric": "EPS Diluted", "annual": [{"end": "2025-12-31", "val": 5}]},
            {"metric": "Shares Diluted", "annual": [{"end": "2025-12-31", "val": 10}]},
            {"metric": "Operating Cash Flow", "annual": [{"end": "2025-12-31", "val": 100}]},
            {"metric": "Capital Expenditure", "annual": [{"end": "2025-12-31", "val": 20}]},
        ],
    }
    market = _market(
        price=100,
        currency="EUR",
        quoteCurrency="EUR",
        marketValueCurrency="USD",
        marketValueCurrencyKnown=True,
        marketCap=None,
        enterpriseValue=1_100,
        financialCurrency="USD",
        ebitda=100,
        sharesOutstanding=10,
    )

    basis = build_valuation_basis(sec, market, share_count=10)
    assert basis["priceCurrencyStatus"] == "mismatch"
    assert basis["marketValueCurrencyStatus"] == "same"
    assert basis["marketValueDerivedSafe"] is False

    out = build_valuation_metrics({"ticker": "X"}, sec, market)
    assert "| PSR | 확인 필요" in out
    assert "| FCF Yield | 확인 필요" in out
    assert "| EV/EBITDA | 11.0x" in out


def test_provider_ebitda_over_revenue_is_rejected_not_divided():
    """실측: 000660.KS의 yfinance EBITDA가 매출의 약 11배로 나와 EV/EBITDA 1.2배라는
    터무니없는 값을 냈다. 같은 통화 라벨(KRW=KRW) 안의 크기 오류라 기존 통화 재확인은
    못 잡는다 — 매출을 넘는 EBITDA는 원본 데이터 오류로 보고 계산하지 않는다."""
    from features.company_analysis.report_rules import build_valuation_metrics

    sec = {
        "ok": True,
        "currency": "USD",
        "rows": [{"metric": "Revenue", "annual": [{"end": "2025-12-31", "val": 1_000}]}],
    }
    # 위 테스트와 같은 필드 구성이되 시세·재무 통화를 전부 USD로 맞춰(불일치 없음)
    # EBITDA 크기 자체만 본다.
    base = dict(
        price=100, currency="USD", quoteCurrency="USD",
        marketValueCurrency="USD", marketValueCurrencyKnown=True,
        financialCurrency="USD", enterpriseValue=5_500, sharesOutstanding=10,
    )
    out = build_valuation_metrics({"ticker": "X"}, sec, _market(**base, ebitda=11_000))
    assert "| EV/EBITDA | 확인 필요" in out

    # 매출 미만(정상적인 마진)이면 그대로 계산한다 — 회귀 방지.
    out = build_valuation_metrics({"ticker": "X"}, sec, _market(**base, ebitda=400))
    assert "| EV/EBITDA | 13.8x" in out


def _valuation_sec(currency="USD"):
    return {
        "ok": True,
        "currency": currency,
        "rows": [
            {"metric": "Revenue", "annual": [{"end": "2025-12-31", "val": 1_000_000}]},
            {"metric": "EPS Diluted", "annual": [{"end": "2025-12-31", "val": 5.0}]},
            {"metric": "Shares Diluted", "annual": [{"end": "2025-12-31", "val": 10_000}]},
            {"metric": "Operating Cash Flow", "annual": [{"end": "2025-12-31", "val": 100_000}]},
            {"metric": "Capital Expenditure", "annual": [{"end": "2025-12-31", "val": 20_000}]},
        ],
    }


def test_explicit_share_ratio_blocks_rules_and_chart_per_scenarios(monkeypatch):
    from features.company_analysis.report_rules import build_valuation_metrics
    from features.company_analysis.service import build_company_analysis_charts

    sec = _valuation_sec("USD")
    market = _market(adrRatio=2, marketCap=1_000_000)
    rules = build_valuation_metrics({"ticker": "ADR"}, sec, market)
    assert "| PER | 확인 필요" in rules
    assert "DCF 계산 불가" in rules

    monkeypatch.setattr("features.company_analysis.service._compute_price_returns", lambda *_args: None)
    charts = build_company_analysis_charts({
        "secFacts": sec,
        "company": {"ticker": "ADR"},
        "marketFinancialData": market,
    })
    assert charts["valuation"]["status"] == "unavailable"
    assert charts["valuationBasis"]["shareUnitStatus"] == "mismatch"
    assert all(row["id"] != "scenario_price" for row in charts["charts"])


def test_pence_quote_is_not_rendered_as_pound_currency():
    from features.company_analysis.report_rules import build_valuation_metrics

    out = build_valuation_metrics(
        {"ticker": "LSE"},
        _valuation_sec("GBP"),
        _market(currency="GBp", marketCap=1_000_000),
    )
    assert "GBp 100" in out
    assert "£100" not in out
    assert "PER | 확인 필요" in out


def test_api_and_cli_use_the_same_unavailable_currency_context(tmp_path, monkeypatch):
    """Exercise both production assembly paths, not only the policy helper."""
    from features.agent_mode import service as agent_service
    from features.company_analysis import generation_context as gen_ctx
    from features.company_analysis import generation_service
    from features.company_analysis import service as company_service
    from features.company_analysis.style import REQUIRED_SECTION_HEADINGS

    company = {"name": "Example Europe", "ticker": "EXEU"}
    materials = {
        "context": "로컬 자료 컨텍스트",
        "selectedDocs": [{"id": "doc-1", "title": "공식 자료", "source": "SEC", "date": "2026-01-01", "url": "https://example.test/doc"}],
        "secFacts": _valuation_sec("EUR"),
        "marketFinancialData": _market(currency="USD", marketCap=1_000_000),
        "rankedFiling": {"ok": True, "paragraphs": []},
        "company": company,
        "counts": {},
        "localIrEarningsCount": 0,
    }
    seen_api = []
    draft = "\n\n".join(f"## {heading}\n\n본문입니다." for heading in REQUIRED_SECTION_HEADINGS)

    def fake_llm(*_args, **kwargs):
        seen_api.append(kwargs.get("context", ""))
        return {"markdown": draft, "usedDocs": materials["selectedDocs"], "webSearch": False}, "ok"

    def write_pack(pack, *_args, **_kwargs):
        path = tmp_path / "cli-pack.json"
        path.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
        return path

    monkeypatch.setattr(company_service, "_compute_price_returns", lambda *_args: None)
    monkeypatch.setattr(company_service, "current_risk_free", lambda *_args: {"rate": 0.05, "source": "test"})
    with ExitStack() as stack:
        stack.enter_context(patch.object(gen_ctx, "load_index", return_value=[]))
        stack.enter_context(patch.object(gen_ctx, "search_documents", return_value=[]))
        stack.enter_context(patch.object(gen_ctx, "search_company_documents", return_value=[]))
        stack.enter_context(patch.object(gen_ctx, "infer_requested_company", return_value=company))
        stack.enter_context(patch.object(gen_ctx, "build_company_analysis_materials", return_value=materials))
        stack.enter_context(patch.object(gen_ctx, "company_external_search_context", return_value=""))
        stack.enter_context(patch.object(agent_service, "_write_pack", side_effect=write_pack))
        api = generation_service.analyze_company(
            "EXEU", runtime={
                "generate_llm_company_analysis": fake_llm,
                "use_web_search_for_analysis": lambda: False,
            },
        )
        cli_pack, cli_path = agent_service.prepare_company_analysis_pack("EXEU", web_search=False)

    assert cli_path == tmp_path / "cli-pack.json"
    assert seen_api and "주가 통화와 신고 통화" in seen_api[0]
    assert "PER 시나리오를 계산하지 않음" in seen_api[0]
    assert cli_pack["context"] == seen_api[0]
    assert api["analysisCharts"]["valuation"]["status"] == "unavailable"
    assert cli_pack["draftArtifact"]["analysisCharts"]["valuation"]["status"] == "unavailable"

    # Final acceptance also follows the actual generated artifacts through
    # canonical save and CLI writeback, with every storage root isolated.
    monkeypatch.setattr(company_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(company_service, "MARKET_MEMORY_DB_PATH", tmp_path / "market-memory.sqlite3")
    monkeypatch.setattr(company_service, "ANALYSIS_REPORTS_DIR", tmp_path / "api" / "company-analysis")
    api_saved = company_service.save_analysis_report(api)
    api_stored = json.loads((tmp_path / "api" / "company-analysis" / f"{api_saved['id']}.json").read_text(encoding="utf-8"))

    monkeypatch.setattr(company_service, "ANALYSIS_REPORTS_DIR", tmp_path / "cli" / "company-analysis")
    monkeypatch.setattr(agent_service, "save_analysis_report", company_service.save_analysis_report)
    cli_saved = agent_service.write_company_analysis_from_markdown(cli_pack, draft, persist=True)
    cli_stored = json.loads((tmp_path / "cli" / "company-analysis" / f"{cli_saved['id']}.json").read_text(encoding="utf-8"))
    for stored in (api_stored, cli_stored):
        assert stored["saved"] is True
        assert stored["markdown"] == draft
        assert stored["analysisCharts"]["valuationBasis"] == api["analysisCharts"]["valuationBasis"]
        assert stored["analysisCharts"]["valuation"]["status"] == "unavailable"
        assert stored["analysisCharts"]["dcf"]["status"] == "unavailable"


def test_unavailable_valuation_metadata_survives_actual_json_save(tmp_path, monkeypatch):
    from features.company_analysis import service as company_service

    exact_body = "# Exact body\n\n## 밸류에이션\n\n계산하지 않은 값"
    monkeypatch.setattr(company_service, "ANALYSIS_REPORTS_DIR", tmp_path / "company-analysis")
    monkeypatch.setattr(company_service, "MARKET_MEMORY_DB_PATH", tmp_path / "market-memory.sqlite3")
    report = {
        "company": {"name": "Example Europe", "ticker": "EXEU"},
        "generatedAt": "2099-12-31T00:00:00Z",
        "markdown": exact_body,
        "analysisCharts": {
            "valuation": {
                "status": "unavailable",
                "reasonCodes": ["price_currency_mismatch"],
                "unavailableReason": "주가 통화와 신고 통화가 다릅니다.",
            },
            "dcf": {
                "status": "unavailable",
                "reasonCodes": ["price_currency_mismatch"],
            },
        },
    }
    saved = company_service.save_analysis_report(report)
    stored_path = tmp_path / "company-analysis" / f"{saved['id']}.json"
    stored = json.loads(stored_path.read_text(encoding="utf-8"))

    assert stored["markdown"] == exact_body
    assert stored["saved"] is True
    assert stored["analysisCharts"]["valuation"]["status"] == "unavailable"
    assert stored["analysisCharts"]["valuation"]["reasonCodes"] == ["price_currency_mismatch"]
