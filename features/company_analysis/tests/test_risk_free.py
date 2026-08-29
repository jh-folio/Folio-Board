"""무위험수익률 조회 — 가드·캐시·폴백 계약.

가드는 함수 **맨 위**라 pytest 환경에서는 무조건 None이다 — 캐시 읽기 뒤에 두면
테스트가 개발자 워크스페이스의 실캐시를 읽어 DCF 수치가 머신마다 달라진다(로컬
통과·CI 실패). 아래 로직 테스트는 `PYTEST_CURRENT_TEST`를 지우고 fetcher를 스텁해서
네트워크 없이 검증한다.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

from features.company_analysis import risk_free as R


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "data_dir", lambda: tmp_path)
    return tmp_path / "company-analysis" / "market-cache"


@pytest.fixture
def unguarded(monkeypatch):
    """네트워크 fetcher를 실패로 스텁한다. 성공 fetch는 테스트가 덮어쓴다.

    가드 해제(`PYTEST_CURRENT_TEST` 삭제)는 **테스트 본문에서** 한다 — pytest가
    call 단계 시작 시 이 변수를 다시 설정하므로 픽스처에서 지운 것은 덮인다.
    """
    monkeypatch.setattr(R, "fred_api_key", lambda: "")
    monkeypatch.setattr(R, "_fetch_tnx", lambda: None)
    return monkeypatch


def _write_cache(cache_dir, *, rate, age_hours, source="fred_DGS10", shape=R.CACHE_SHAPE, **extra):
    cache_dir.mkdir(parents=True, exist_ok=True)
    as_of = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=age_hours)
    payload = {"shape": shape, "rate": rate, "source": source, "asOf": as_of.isoformat(), **extra}
    (cache_dir / "risk-free.json").write_text(json.dumps(payload), encoding="utf-8")


class TestGuard:
    def test_pytest_env_blocks_everything_including_cache_reads(self, workspace):
        _write_cache(workspace, rate=0.0466, age_hours=1)
        # PYTEST_CURRENT_TEST가 살아 있으므로 신선한 캐시조차 답하지 않는다.
        assert R.current_risk_free("USD") is None


class TestCurrentRiskFree:
    def test_fresh_cache_is_served_without_network(self, workspace, unguarded):
        unguarded.delenv("PYTEST_CURRENT_TEST", raising=False)
        _write_cache(workspace, rate=0.0466, age_hours=1)
        row = R.current_risk_free("USD")
        assert row is not None
        assert row["rate"] == 0.0466
        assert row["source"] == "fred_DGS10"

    def test_cached_string_rate_comes_back_as_float(self, workspace, unguarded):
        """저장값이 "0.0466" 문자열이어도 float로 돌려준다 — 그대로 나가면
        `rf + beta*erp`에서 TypeError로 분석 전체가 죽는다."""
        unguarded.delenv("PYTEST_CURRENT_TEST", raising=False)
        _write_cache(workspace, rate="0.0466", age_hours=1)
        row = R.current_risk_free("USD")
        assert isinstance(row["rate"], float)

    def test_stale_cache_survives_fetch_failure_up_to_the_cap(self, workspace, unguarded):
        unguarded.delenv("PYTEST_CURRENT_TEST", raising=False)
        _write_cache(workspace, rate=0.0466, age_hours=48)
        row = R.current_risk_free("USD")
        assert row is not None
        assert row["source"].startswith("stale_")

    def test_stale_cache_beyond_the_cap_is_refused(self, workspace, unguarded):
        """무제한 stale은 낡은 금리를 살아 있는 값처럼 주입한다 — 이 모듈이
        없애려는 편향의 재생산이라 상한(7일)을 넘기면 상수로 내려간다."""
        unguarded.delenv("PYTEST_CURRENT_TEST", raising=False)
        _write_cache(workspace, rate=0.0466, age_hours=(R.STALE_MAX_AGE_DAYS + 1) * 24)
        assert R.current_risk_free("USD") is None

    def test_failure_writes_a_cooldown_marker(self, workspace, unguarded):
        """실패를 기록하지 않으면 오프라인 환경에서 보고서마다 timeout을 다시 치른다."""
        unguarded.delenv("PYTEST_CURRENT_TEST", raising=False)
        assert R.current_risk_free("USD") is None
        marker = json.loads((workspace / "risk-free.json").read_text(encoding="utf-8"))
        assert marker.get("failedAt")

    def test_cooldown_skips_the_network(self, workspace, unguarded):
        unguarded.delenv("PYTEST_CURRENT_TEST", raising=False)
        _write_cache(
            workspace, rate=0.0466, age_hours=48,
            failedAt=dt.datetime.now(dt.timezone.utc).isoformat(),
        )
        calls = []
        unguarded.setattr(R, "_fetch_tnx", lambda: calls.append(1))
        row = R.current_risk_free("USD")
        assert calls == []  # 쿨다운 중에는 fetcher가 불리지 않는다
        assert row is not None and row["source"].startswith("stale_")

    def test_successful_fetch_records_source_and_observation_date(self, workspace, unguarded):
        unguarded.delenv("PYTEST_CURRENT_TEST", raising=False)
        unguarded.setattr(R, "_fetch_tnx", lambda: (0.0471, "2026-08-28"))
        row = R.current_risk_free("USD")
        assert row == {
            "rate": 0.0471, "source": "yfinance_^TNX",
            "asOf": row["asOf"], "observedAt": "2026-08-28",
        }
        saved = json.loads((workspace / "risk-free.json").read_text(encoding="utf-8"))
        assert saved["shape"] == R.CACHE_SHAPE

    def test_old_shape_cache_is_not_trusted(self, workspace, unguarded):
        unguarded.delenv("PYTEST_CURRENT_TEST", raising=False)
        _write_cache(workspace, rate=0.0466, age_hours=1, shape=0)
        assert R.current_risk_free("USD") is None  # fetcher 스텁이 실패라 상수로

    def test_non_usd_is_not_fetched(self, workspace, unguarded):
        """비USD OECD 계열은 관측이 9개월 뒤처져 있어 상수보다 낫다는 판단이 서지
        않았다(§9.2.3). 결정 전에는 조회하지 않는다."""
        unguarded.delenv("PYTEST_CURRENT_TEST", raising=False)
        _write_cache(workspace, rate=0.0466, age_hours=1)
        assert R.current_risk_free("KRW") is None
        assert R.current_risk_free("EUR") is None

    def test_broken_cache_rate_is_rejected(self, workspace, unguarded):
        unguarded.delenv("PYTEST_CURRENT_TEST", raising=False)
        _write_cache(workspace, rate=4.66, age_hours=1)  # 퍼센트를 소수로 안 나눈 값
        assert R.current_risk_free("USD") is None
