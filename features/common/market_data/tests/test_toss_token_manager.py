import concurrent.futures
import sys
import threading
import time
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from features.common.market_data import toss_open_api
from features.common.market_data.toss_token_manager import TossProviderError, TossTokenError, TossTokenManager, WorkspaceFileLock


class Clock:
    def __init__(self, value: float = 1_000.0):
        self.value = value

    def __call__(self) -> float:
        return self.value


class FakeLock:
    def __init__(self, _path: Path, *, acquired: bool = True) -> None:
        self.acquired = acquired
        self.released = False

    def acquire(self) -> bool:
        return self.acquired

    def release(self) -> None:
        self.released = True


def manager(tmp_path, *, clock=None, lock_factory=FakeLock) -> TossTokenManager:
    return TossTokenManager(
        workspace_dir=tmp_path,
        enabled=lambda: True,
        client_id=lambda: "client-id",
        client_secret=lambda: "super-secret-value",
        lock_factory=lock_factory,
        monotonic=clock or Clock(),
    )


def test_single_flight_issues_one_token_for_concurrent_callers(tmp_path):
    gate = threading.Barrier(8)
    started = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()
    subject = manager(tmp_path)

    def issuer():
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        assert release.wait(timeout=2)
        return "token-one", 3600

    def worker():
        gate.wait(timeout=2)
        return subject.get_token(issuer)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker) for _ in range(8)]
        assert started.wait(timeout=2)
        release.set()
        leases = [future.result(timeout=2) for future in futures]

    assert calls == 1
    assert {lease.generation for lease in leases} == {1}
    assert "token-one" not in repr(subject)
    assert "token-one" not in repr(leases[0])


def test_lazy_module_manager_initialization_is_singleton_under_race(tmp_path, monkeypatch):
    original = toss_open_api.TossTokenManager
    created = []
    factory_lock = threading.Lock()

    def factory(**kwargs):
        # Widen construction enough that a missing init lock fails reliably.
        time.sleep(0.01)
        instance = original(**kwargs)
        with factory_lock:
            created.append(instance)
        return instance

    monkeypatch.setattr(toss_open_api, "_TOKEN_MANAGER", None)
    monkeypatch.setattr(toss_open_api, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(toss_open_api, "TossTokenManager", factory)
    gate = threading.Barrier(16)

    def worker():
        gate.wait(timeout=2)
        return toss_open_api.token_manager()

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        values = [future.result(timeout=2) for future in [pool.submit(worker) for _ in range(16)]]

    assert len(created) == 1
    assert {id(value) for value in values} == {id(created[0])}


def test_cache_and_monotonic_sixty_second_skew(tmp_path):
    clock = Clock()
    subject = manager(tmp_path, clock=clock)
    calls = []

    def issuer():
        calls.append(True)
        return f"token-{len(calls)}", 120

    assert subject.get_token(issuer).generation == 1
    clock.value += 59
    assert subject.get_token(issuer).generation == 1
    clock.value += 1
    assert subject.get_token(issuer).generation == 2
    assert len(calls) == 2


def test_generation_aware_invalidation_never_clears_newer_token(tmp_path):
    subject = manager(tmp_path)
    first = subject.get_token(lambda: ("token-one", 3600))
    assert subject.invalidate_if_generation(first.generation) is True
    second = subject.get_token(lambda: ("token-two", 3600))
    assert second.generation == first.generation + 1
    assert subject.invalidate_if_generation(first.generation) is False
    assert subject.get_token(lambda: pytest.fail("new token must remain cached")).generation == second.generation


def test_health_normalizes_external_error_text_and_counts_one_auth_failure(tmp_path):
    subject = manager(tmp_path)
    lease = subject.get_token(lambda: ("token-one", 3600))
    assert subject.record_provider_error("WS rejected: secret=super-secret-value and an arbitrarily long detail" * 3) == "provider_error"
    assert subject.record_http_error(401) == "invalid_token"
    assert subject.invalidate_if_generation(lease.generation) is True
    health = subject.health_snapshot()
    assert health["lastErrorCode"] == "invalid_token"
    assert health["authFailureCount"] == 1
    assert len(health["lastErrorCode"]) <= 48
    assert "super-secret-value" not in repr(health)


def test_disabled_and_missing_credentials_never_issue(tmp_path):
    disabled = TossTokenManager(
        workspace_dir=tmp_path,
        enabled=lambda: False,
        client_id=lambda: "client",
        client_secret=lambda: "secret",
        lock_factory=FakeLock,
    )
    missing = TossTokenManager(
        workspace_dir=tmp_path,
        enabled=lambda: True,
        client_id=lambda: "",
        client_secret=lambda: "",
        lock_factory=FakeLock,
    )
    with pytest.raises(TossTokenError) as disabled_error:
        disabled.get_token(lambda: pytest.fail("issuer must not run"))
    with pytest.raises(TossTokenError) as missing_error:
        missing.get_token(lambda: pytest.fail("issuer must not run"))
    assert disabled_error.value.code == "disabled"
    assert missing_error.value.code == "credentials_missing"
    assert disabled.health_snapshot()["status"] == "disabled"
    assert missing.health_snapshot()["status"] == "missing_credentials"


def test_process_lock_rejection_blocks_token_issue_and_is_safe(tmp_path):
    subject = manager(tmp_path, lock_factory=lambda path: FakeLock(path, acquired=False))
    with pytest.raises(TossTokenError, match="multi_process_unsupported"):
        subject.get_token(lambda: pytest.fail("issuer must not run"))
    health = subject.health_snapshot()
    assert health["lastErrorCode"] == "multi_process_unsupported"
    assert "super-secret-value" not in repr(subject)
    assert "super-secret-value" not in repr(health)


def test_workspace_file_lock_uses_os_ownership_not_a_pid_marker(tmp_path):
    first = WorkspaceFileLock(tmp_path / "runtime-locks" / "toss-open-api.lock")
    second = WorkspaceFileLock(tmp_path / "runtime-locks" / "toss-open-api.lock")
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
    assert second.acquire() is True
    second.release()


@pytest.fixture
def configured_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLIO_ENABLE_TOSS_OPEN_API", "1")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_ID", "client-id")
    monkeypatch.setenv("TOSS_OPEN_API_CLIENT_SECRET", "super-secret-value")
    subject = TossTokenManager(
        workspace_dir=tmp_path,
        enabled=toss_open_api.toss_open_api_enabled,
        client_id=toss_open_api.toss_open_api_client_id,
        client_secret=toss_open_api.toss_open_api_client_secret,
        lock_factory=FakeLock,
    )
    monkeypatch.setattr(toss_open_api, "_TOKEN_MANAGER", subject)
    toss_open_api._TOKEN_CACHE.clear()
    yield subject
    subject.close_for_tests()


def test_rest_401_reissues_once_and_uses_new_token(configured_adapter):
    calls = []

    def transport(method, url, *, headers=None, data=None, timeout=10):
        calls.append((method, headers or {}))
        if url.endswith("/oauth2/token"):
            return {"access_token": f"token-{sum(1 for kind, _ in calls if kind == 'POST')}", "expires_in": 3600}
        if headers["Authorization"] == "Bearer token-1":
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
        return {"result": []}

    assert toss_open_api.fetch_toss_prices(["AAPL"], transport=transport) == []
    assert [kind for kind, _ in calls] == ["POST", "GET", "POST", "GET"]
    assert configured_adapter.health_snapshot()["lastErrorCode"] == "invalid_token"
    assert configured_adapter.health_snapshot()["authFailureCount"] == 1


def test_stale_401_retries_once_with_latest_generation_without_invalidating_it(configured_adapter):
    calls = []

    def transport(method, url, *, headers=None, data=None, timeout=10):
        calls.append((method, headers or {}))
        if url.endswith("/oauth2/token"):
            return {"access_token": "token-one", "expires_in": 3600}
        if headers["Authorization"] == "Bearer token-one":
            first = configured_adapter.invalidate_if_generation(1)
            assert first is True
            latest = configured_adapter.get_token(lambda: ("token-two", 3600))
            assert latest.generation == 2
            raise urllib.error.HTTPError(url, 401, "stale", {}, None)
        assert headers["Authorization"] == "Bearer token-two"
        return {"result": []}

    assert toss_open_api.fetch_toss_prices(["AAPL"], transport=transport) == []
    assert [kind for kind, _ in calls] == ["POST", "GET", "GET"]
    assert configured_adapter.get_token(lambda: pytest.fail("latest token must stay cached")).generation == 2


def test_concurrent_401_waits_for_inflight_reissue_then_each_retries_once(configured_adapter):
    calls = []
    calls_lock = threading.Lock()
    first_generation_failures = threading.Barrier(2)
    second_issue_started = threading.Event()
    release_second_issue = threading.Event()

    def transport(method, url, *, headers=None, data=None, timeout=10):
        with calls_lock:
            calls.append((method, headers or {}))
            post_count = sum(1 for request, _ in calls if request == "POST")
        if url.endswith("/oauth2/token"):
            if post_count == 1:
                return {"access_token": "token-one", "expires_in": 3600}
            second_issue_started.set()
            assert release_second_issue.wait(timeout=2)
            return {"access_token": "token-two", "expires_in": 3600}
        if headers["Authorization"] == "Bearer token-one":
            first_generation_failures.wait(timeout=2)
            raise urllib.error.HTTPError(url, 401, "rejected", {}, None)
        assert headers["Authorization"] == "Bearer token-two"
        return {"result": []}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(toss_open_api.fetch_toss_prices, ["AAPL"], transport=transport) for _ in range(2)]
        assert second_issue_started.wait(timeout=2)
        # Both first failures are recorded before generation two is released.
        deadline = time.monotonic() + 2
        while configured_adapter.health_snapshot()["authFailureCount"] < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert configured_adapter.health_snapshot()["authFailureCount"] == 2
        release_second_issue.set()
        assert [future.result(timeout=2) for future in futures] == [[], []]

    assert [request for request, _ in calls].count("POST") == 2
    assert [request for request, _ in calls].count("GET") == 4


@pytest.mark.parametrize("kind", ["http", "payload"])
def test_second_invalid_token_is_terminal_safe_and_clears_rejected_cache(configured_adapter, kind):
    calls = []

    def transport(method, url, *, headers=None, data=None, timeout=10):
        calls.append((method, headers or {}))
        if url.endswith("/oauth2/token"):
            ordinal = sum(1 for request, _ in calls if request == "POST")
            return {"access_token": f"token-{ordinal}", "expires_in": 3600}
        if kind == "http":
            raise urllib.error.HTTPError(url, 401, "raw upstream rejected token", {}, None)
        return {"error": {"code": "invalid_token", "detail": "raw upstream rejected token"}}

    with pytest.raises(TossProviderError) as error:
        toss_open_api.fetch_toss_prices(["AAPL"], transport=transport)
    assert error.value.code == "invalid_token"
    assert "raw upstream" not in repr(error.value)
    assert [request for request, _ in calls] == ["POST", "GET", "POST", "GET"]
    # Both rejected generations are gone; this is a third issue rather than a
    # stale cache reuse, but no request is sent through the fake provider here.
    assert configured_adapter.get_token(lambda: ("token-three", 3600)).generation == 3
    assert configured_adapter.health_snapshot()["authFailureCount"] == 2


def test_explicit_invalid_token_payload_reissues_once(configured_adapter):
    calls = []

    def transport(method, url, *, headers=None, data=None, timeout=10):
        calls.append((method, headers or {}))
        if url.endswith("/oauth2/token"):
            return {"access_token": f"token-{sum(1 for kind, _ in calls if kind == 'POST')}", "expires_in": 3600}
        if headers["Authorization"] == "Bearer token-1":
            return {"error": {"code": "invalid_token"}}
        return {"result": []}

    assert toss_open_api.fetch_toss_prices(["AAPL"], transport=transport) == []
    assert [kind for kind, _ in calls] == ["POST", "GET", "POST", "GET"]


def test_explicit_expired_token_keeps_specific_safe_health_code(configured_adapter):
    calls = []

    def transport(method, url, *, headers=None, data=None, timeout=10):
        calls.append((method, headers or {}))
        if url.endswith("/oauth2/token"):
            ordinal = sum(1 for request, _ in calls if request == "POST")
            return {"access_token": f"token-{ordinal}", "expires_in": 3600}
        if headers["Authorization"] == "Bearer token-1":
            return {"error": {"code": "access_token_expired"}}
        return {"result": []}

    assert toss_open_api.fetch_toss_prices(["AAPL"], transport=transport) == []
    assert configured_adapter.health_snapshot()["lastErrorCode"] == "token_expired"


def test_pinned_specs_are_local_constants_not_mutable_runtime_authority():
    assert toss_open_api.TOSS_REST_OPENAPI_VERSION == "1.2.14"
    assert toss_open_api.TOSS_REALTIME_ASYNCAPI_VERSION == "1.2.2"
    source = Path(toss_open_api.__file__).read_text(encoding="utf-8")
    assert "openapi-docs/latest" not in source


@pytest.mark.parametrize("status, expected", [(403, "ip_allowlist_or_permission_denied"), (429, "rate_limited")])
def test_rest_403_and_429_do_not_rotate_token(configured_adapter, status, expected):
    calls = []

    def transport(method, url, *, headers=None, data=None, timeout=10):
        calls.append((method, headers or {}))
        if url.endswith("/oauth2/token"):
            return {"access_token": "token-one", "expires_in": 3600}
        raise urllib.error.HTTPError(url, status, "provider failure", {"retry-after": "9"}, None)

    with pytest.raises(urllib.error.HTTPError):
        toss_open_api.fetch_toss_prices(["AAPL"], transport=transport)
    with pytest.raises(urllib.error.HTTPError):
        toss_open_api.fetch_toss_prices(["AAPL"], transport=transport)
    assert [kind for kind, _ in calls].count("POST") == 1
    health = configured_adapter.health_snapshot()
    assert health["lastErrorCode"] == expected
    assert health["rateLimit"]["retryAfterSeconds"] == 9
    assert "token-one" not in repr(health)
