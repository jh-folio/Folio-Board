"""현재 보유에서 목표 프리셋 만들기.

`targetWeight`는 화면 어디에서도 넣을 수 없다(보유 표에 칸이 없다). 그 값이 있는
포지션만 담으면 결과는 **항상 빈 프리셋**이고, 버튼이 아무 일도 하지 않는다.
"""
from __future__ import annotations

import pytest

from features.portfolio import service


@pytest.fixture
def saved(monkeypatch):
    """시세가 붙은 보유 스냅샷. 네트워크를 타지 않는다."""
    snapshot = {
        "positions": [
            {"ticker": "NVDA", "symbol": "NVDA", "name": "NVIDIA", "market": "US",
             "currency": "USD", "assetClass": "Equity", "sector": "Technology",
             "targetWeight": None, "weight": 0.25},
            {"ticker": "005930", "symbol": "005930.KS", "name": "SamsungElec", "market": "KR",
             "currency": "KRW", "assetClass": "Equity", "sector": "Technology",
             "targetWeight": None, "weight": 0.55},
            {"ticker": "MSFT", "symbol": "MSFT", "name": "Microsoft", "market": "US",
             "currency": "USD", "assetClass": "Equity", "sector": "Technology",
             "targetWeight": None, "weight": 0.20},
        ],
    }
    monkeypatch.setattr(service, "portfolio_summary", lambda: snapshot)
    return snapshot


def test_current_weights_become_the_target(saved):
    preset = service.preset_from_current_portfolio("목표")

    assert preset["name"] == "목표"
    weights = {row["ticker"]: row["weight"] for row in preset["positions"]}
    assert weights == {"NVDA": 0.25, "005930": 0.55, "MSFT": 0.20}


def test_an_explicit_target_wins_over_the_current_weight(saved):
    saved["positions"][0]["targetWeight"] = 0.4

    preset = service.preset_from_current_portfolio()
    weights = {row["ticker"]: row["weight"] for row in preset["positions"]}
    assert weights["NVDA"] == 0.25
    assert weights["MSFT"] == 0.20


def test_positions_without_a_quote_are_left_out(saved):
    """비중을 계산할 수 없는 종목을 0으로 담으면 목표에서 뺀 것처럼 보인다."""
    saved["positions"][2]["weight"] = None

    preset = service.preset_from_current_portfolio()
    assert [row["ticker"] for row in preset["positions"]] == ["NVDA", "005930"]


def test_an_empty_portfolio_makes_an_empty_preset(monkeypatch):
    monkeypatch.setattr(service, "portfolio_summary", lambda: {"positions": []})

    draft = service.preset_from_current_portfolio()
    assert draft["draft"] is True
    assert "id" not in draft and "revision" not in draft
    assert draft["positions"] == []


@pytest.fixture
def analytics(monkeypatch):
    """시세가 붙은 보유 + 저장된 목표 프리셋.

    `weight`는 실제 `portfolio_summary()`가 채워 주는 값이다(평가액 / 전체 평가액).
    빼먹으면 현재 비중이 전부 0으로 나와 테스트가 실제와 달라진다.
    """
    monkeypatch.setattr(service, "portfolio_summary", lambda: {
        "positions": [
            {"id": "a", "ticker": "NVDA", "name": "NVIDIA", "sector": "Tech", "market": "US",
             "quoteCurrency": "USD", "assetClass": "Equity",
             "marketValueUsd": 6000.0, "costUsd": 4000.0, "pnlUsd": 2000.0, "weight": 0.6},
            {"id": "b", "ticker": "MSFT", "name": "Microsoft", "sector": "Tech", "market": "US",
             "quoteCurrency": "USD", "assetClass": "Equity",
             "marketValueUsd": 4000.0, "costUsd": 3000.0, "pnlUsd": 1000.0, "weight": 0.4},
        ],
        "summary": [], "cash": [], "baseCurrency": "USD", "fxRates": {},
    })


def test_without_a_preset_there_is_nothing_to_compare(analytics, monkeypatch):
    monkeypatch.setattr(service, "get_portfolio_preset", lambda pid: None)
    assert service.portfolio_analytics()["analytics"]["targetWeights"]["hasTargets"] is False


def test_a_preset_becomes_the_target_to_compare_against(analytics, monkeypatch):
    """프리셋과 포지션 targetWeight가 서로 몰라서 차이 표가 한 번도 뜨지 않았다."""
    monkeypatch.setattr(service, "get_portfolio_preset", lambda pid: {
        "id": "p1", "name": "균형",
        "positions": [{"ticker": "NVDA", "weight": 0.5}, {"ticker": "MSFT", "weight": 0.5}],
    })

    targets = service.portfolio_analytics("p1")["analytics"]["targetWeights"]
    assert targets["hasTargets"] is True
    assert targets["presetName"] == "균형"

    rows = {row["ticker"]: row for row in targets["items"]}
    # NVDA는 60% 들고 있는데 목표가 50% → 10%p 초과, 1만 달러의 10% = 1,000 달러 초과
    assert rows["NVDA"]["currentWeight"] == pytest.approx(0.6)
    assert rows["NVDA"]["targetWeight"] == pytest.approx(0.5)
    assert rows["NVDA"]["diffWeight"] == pytest.approx(0.1)
    assert rows["NVDA"]["diffAmountUsd"] == pytest.approx(1000.0)
    assert rows["MSFT"]["diffWeight"] == pytest.approx(-0.1)


def test_a_target_you_do_not_own_yet_still_gets_a_row(analytics, monkeypatch):
    """목표에는 있는데 아직 안 산 종목이 조정에서 가장 중요한 정보다."""
    monkeypatch.setattr(service, "get_portfolio_preset", lambda pid: {
        "id": "p1", "name": "균형",
        "positions": [{"ticker": "NVDA", "weight": 0.4}, {"ticker": "MSFT", "weight": 0.4}, {"ticker": "AVGO", "weight": 0.2}],
    })

    rows = {row["ticker"]: row for row in service.portfolio_analytics("p1")["analytics"]["targetWeights"]["items"]}
    assert "AVGO" in rows
    assert rows["AVGO"]["currentWeight"] == 0.0
    assert rows["AVGO"]["targetWeight"] == pytest.approx(0.2)
    assert rows["AVGO"]["diffWeight"] == pytest.approx(-0.2)
