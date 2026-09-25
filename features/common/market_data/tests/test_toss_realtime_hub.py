from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI

from features.common.market_data.routes import create_market_data_router
from features.common.market_data.toss_realtime_hub import MAX_TOPICS, TossRealtimeHub, subscription_target
from features.common.market_data.toss_token_manager import TokenLease


class _Socket:
    def __init__(self):
        self.frames: asyncio.Queue[object] = asyncio.Queue()
        self.sent: list[dict] = []
        self.closed = False
        self.recv_tasks: set[asyncio.Task] = set()

    async def recv(self):
        task = asyncio.current_task()
        if task is not None: self.recv_tasks.add(task)
        try:
            return await self.frames.get()
        finally:
            if task is not None: self.recv_tasks.discard(task)

    async def send(self, value):
        try:
            self.sent.append(json.loads(value))
        except (TypeError, ValueError):
            self.sent.append(value)

    async def close(self):
        self.closed = True


class _LocalWebSocket:
    """FastAPI WebSocket seam: avoids requiring optional httpx2 in this lock."""

    def __init__(self, symbol: str):
        self.query_params = {"symbol": symbol}
        self.events: list[dict] = []

    async def accept(self):
        return None

    async def send_json(self, event):
        self.events.append(event)

    async def close(self):
        return None

    async def receive(self):
        await asyncio.sleep(0.01)
        return {"type": "websocket.disconnect"}


def _hub(socket: _Socket, *, grace_seconds: float = 0.01) -> TossRealtimeHub:
    async def connect(_url, *, headers):
        assert headers == {"Authorization": "Bearer token-1"}
        return socket

    return TossRealtimeHub(
        connector=connect,
        token_issuer=lambda: TokenLease("token-1", 1),
        grace_seconds=grace_seconds,
    )


def _run(coro):
    return asyncio.run(coro)


async def _next_status(queue, status):
    while True:
        event = await asyncio.wait_for(queue.get(), 1)
        if event["status"] == status:
            return event


def test_pinned_realtime_fixture_has_fixed_contract_versions():
    payload = json.loads((Path(__file__).parent / "fixtures" / "toss_realtime_frames_1.2.2.json").read_text(encoding="utf-8"))
    assert payload["metadata"] == {
        "restOpenApiVersion": "1.2.14", "asyncApiVersion": "1.2.2",
        "source": "pinned_extracted_fixture", "network": "forbidden",
    }
    assert payload["frames"]["declaration"] == [{"type": "trade:us", "codes": ["AAPL"]}, {"type": "trade:kr", "codes": ["005930"]}]
    assert payload["frames"]["subscriptions"]["rejected"][0]["target"] == "trade:kr:005930"
    assert payload["frames"]["message"]["topic"] == "trade:us:AAPL"
    assert payload["frames"]["ping"] == "PING"
    assert payload["frames"]["pong"] == {"type": "pong"}
    assert payload["frames"]["rateLimitError"]["error"]["code"] == "rate-limit-exceeded"


def test_visible_symbol_contract_excludes_indices_and_foreign_or_non_stock_symbols():
    assert subscription_target("005930.KS") == ("005930", "KR", "")
    assert subscription_target("NVDA") == ("NVDA", "US", "")
    assert subscription_target("BRK.B") == ("BRK.B", "US", "")
    for symbol in (
        "^KS11", "7203.T", "AIR.PA", "NESN.SW", "NOKIA.HE", "ERIC-B.ST", "AAPL.MC", "OR.PA", "PKN.WA",
        "VIE.AT", "BAS.BD", "DTE.DU", "HEN3.HA", "HML.HM", "MUV2.MU", "SGO.PA", "TELIA.TL", "RNO.RG",
        "NOVO.VS", "MST.ME", "BIR.IS", "NESTE.HE", "USDKRW=X", "BTC-USD", "<bad>",
    ):
        assert subscription_target(symbol)[2] == "unsupported"


def test_single_upstream_full_replace_safe_projection_and_no_stream_volume():
    async def scenario():
        socket = _Socket()
        hub = _hub(socket)
        await hub.start()
        first = await hub.subscribe("005930.KS")
        second = await hub.subscribe("NVDA")
        assert (await first.queue.get())["status"] == "pending"
        assert (await second.queue.get())["status"] == "pending"
        await asyncio.sleep(0.02)
        assert len(socket.sent) == 1
        assert socket.sent[0] == [{"type": "trade:us", "codes": ["NVDA"]}, {"type": "trade:kr", "codes": ["005930"]}]
        await socket.frames.put(json.dumps({"type": "message", "topic": "trade:kr:005930", "data": {"timestamp": "2026-09-01T09:35:00+09:00", "price": "70000", "currency": "KRW", "account": "secret", "volume": 999}}))
        event = await _next_status(first.queue, "live")
        assert event == {"schemaVersion": 1, "type": "tick", "status": "live", "provider": "toss_open_api", "symbol": "005930", "market": "KR", "asOf": "2026-09-01T09:35:00+09:00", "price": 70000.0, "currency": "KRW"}
        await _next_status(second.queue, "connecting")
        assert second.queue.empty()
        await hub.stop()
    _run(scenario())


def test_topic_cap_counts_topics_not_multiple_local_viewers():
    async def scenario():
        socket = _Socket()
        hub = _hub(socket)
        await hub.start()
        for number in range(MAX_TOPICS):
            await hub.subscribe(f"T{number}")
        duplicate = await hub.subscribe("T0")
        rejected = await hub.subscribe("OVERFLOW")
        assert (await duplicate.queue.get())["status"] == "pending"
        assert (await rejected.queue.get())["status"] == "rejected"
        await hub.stop()
    _run(scenario())


def test_hub_start_is_lifecycle_safe_and_does_not_connect_until_a_local_subscriber_exists():
    async def scenario():
        socket = _Socket()
        hub = _hub(socket)
        await hub.start()
        await asyncio.sleep(0.01)
        assert socket.sent == []
        assert hub.runner is None
        await hub.stop()
    _run(scenario())


def test_local_subscription_is_pending_until_official_ack_and_never_fakes_subscribed():
    async def scenario():
        socket = _Socket()
        hub = _hub(socket)
        sub = await hub.subscribe("AAPL")
        assert (await sub.queue.get())["status"] == "pending"
        # No runner means no upstream acknowledgement can have happened.
        assert hub.runner is None
        hub._connection = socket
        await hub._handle_frame({"type": "subscriptions", "subscribed": ["trade:us:AAPL"], "rejected": []})
        assert (await sub.queue.get())["status"] == "subscribed"
    _run(scenario())


def test_declarations_coalesce_and_obey_five_per_second_limit_with_injected_clock():
    async def scenario():
        socket = _Socket()
        now = [0.0]
        waits = []

        async def sleep(seconds):
            waits.append(seconds)
            now[0] += seconds

        hub = TossRealtimeHub(
            connector=lambda *_args, **_kwargs: None,
            token_issuer=lambda: TokenLease("token-1", 1), clock=lambda: now[0], sleep=sleep,
        )
        sub = await hub.subscribe("NVDA")
        await sub.queue.get()
        for _ in range(6):
            await hub._declare(socket, force=True)
        assert len(socket.sent) == 6
        assert any(wait >= 1.0 for wait in waits)
    _run(scenario())


def test_grace_removal_is_bounded_without_an_upstream_connection():
    async def scenario():
        socket = _Socket()
        now = [0.0]
        hub = TossRealtimeHub(
            connector=lambda _url, *, headers: _connected(socket, headers),
            token_issuer=lambda: TokenLease("token-1", 1), clock=lambda: now[0], grace_seconds=0.01,
        )
        sub = await hub.subscribe("NVDA")
        await sub.queue.get()
        await hub.unsubscribe(sub.id)
        assert len(await hub._active()) == 1
        now[0] = 0.02
        assert await hub._active() == []
    _run(scenario())


async def _connected(socket, headers):
    assert headers == {"Authorization": "Bearer token-1"}
    return socket


def test_subscriptions_ack_partial_reject_is_safe_and_redeclares_only_remaining_topics():
    async def scenario():
        socket = _Socket()
        hub = _hub(socket)
        await hub.start()
        sub = await hub.subscribe("005930")
        await sub.queue.get()
        await asyncio.sleep(0.02)
        await hub._handle_frame({"type": "subscriptions", "subscribed": ["trade:kr:005930"], "rejected": [{"target": "trade:kr:005930", "code": "stock-not-found", "message": "raw provider detail"}]})
        event = await _next_status(sub.queue, "rejected")
        assert event["status"] == "rejected"
        assert event["code"] == "unsupported"
        assert "account" not in event
        await hub._declare(socket, force=True)
        assert socket.sent[-1] == []
        await hub.stop()
    _run(scenario())


def test_official_error_frames_are_safe_and_keep_no_raw_provider_message():
    async def scenario():
        socket = _Socket()
        hub = _hub(socket)
        sub = await hub.subscribe("AAPL")
        await sub.queue.get()
        hub._connection = socket
        await hub._handle_frame({"type": "error", "error": {"code": "server-shutdown", "message": "raw secret response"}})
        event = await _next_status(sub.queue, "reconnecting")
        assert event["code"] == "connection_error"
        assert "message" not in event
        assert hub._immediate_reconnect is True
    _run(scenario())


def test_adversarial_extra_provider_fields_are_never_projected():
    async def scenario():
        fixture = json.loads((Path(__file__).parent / "fixtures" / "toss_realtime_adversarial.json").read_text(encoding="utf-8"))
        hub = _hub(_Socket())
        sub = await hub.subscribe("AAPL")
        await sub.queue.get()
        await hub._handle_frame(fixture["message"])
        event = await _next_status(sub.queue, "live")
        assert set(event) == {"schemaVersion", "type", "status", "provider", "symbol", "market", "asOf", "price", "currency"}
    _run(scenario())


def test_handshake_status_mapping_never_rotates_403_or_429_tokens():
    class _HandshakeError(Exception):
        def __init__(self, status):
            self.status_code = status

    assert TossRealtimeHub._exception_code(_HandshakeError(401)) == "invalid_token"
    assert TossRealtimeHub._exception_code(_HandshakeError(403)) == "ip_allowlist_or_permission_denied"
    assert TossRealtimeHub._exception_code(_HandshakeError(429)) == "rate_limited"

    class _Response:
        def __init__(self, status_code): self.status_code = status_code

    class _InvalidStatus(Exception):
        def __init__(self, status_code): self.response = _Response(status_code)

    assert TossRealtimeHub._exception_code(_InvalidStatus(401)) == "invalid_token"
    assert TossRealtimeHub._exception_code(_InvalidStatus(403)) == "ip_allowlist_or_permission_denied"
    assert TossRealtimeHub._exception_code(_InvalidStatus(429)) == "rate_limited"


def test_ack_without_new_rejection_does_not_redeclare_and_invalid_topic_is_dropped():
    async def scenario():
        socket = _Socket()
        hub = _hub(socket)
        sub = await hub.subscribe("AAPL")
        await sub.queue.get()
        hub._connection = socket
        await hub._declare(socket, force=True)
        before = len(socket.sent)
        for _ in range(3):
            await hub._handle_frame({"type": "subscriptions", "subscribed": ["trade:us:AAPL"], "rejected": []})
        assert len(socket.sent) == before
        while not sub.queue.empty():
            await sub.queue.get()
        await hub._handle_frame({"type": "message", "topic": "bad:topic", "data": {"price": "1"}})
        assert sub.queue.empty()
    _run(scenario())


def test_busy_receive_loop_checks_ping_deadline_before_waiting_for_the_next_frame():
    async def scenario():
        now = [60.0]

        class _PingSocket:
            sent = []
            async def recv(self):
                return {"type": "message", "topic": "trade:us:AAPL", "data": {"price": "1"}}
            async def send(self, value):
                self.sent.append(value)
                hub._running = False
            async def close(self):
                return None

        socket = _PingSocket()
        hub = TossRealtimeHub(token_issuer=lambda: TokenLease("t", 1), clock=lambda: now[0])
        sub = await hub.subscribe("AAPL")
        await sub.queue.get()
        hub._running, hub._connected_generation, hub._last_client_send = True, 1, 0.0
        await hub._receive_loop(socket)
        assert socket.sent == ["PING"]
    _run(scenario())


def test_two_handshake_401s_open_auth_breaker_until_explicit_reset(monkeypatch):
    class _Response:
        status_code = 401

    class _InvalidStatus(Exception):
        response = _Response()

    class _Manager:
        def __init__(self): self.invalidated = []
        def invalidate_if_generation(self, generation, *, error_code): self.invalidated.append((generation, error_code)); return True
        def record_http_error(self, *_args, **_kwargs): return ""

    async def scenario():
        manager, calls, issues = _Manager(), [], []
        leases = [TokenLease("one", 1), TokenLease("two", 2), TokenLease("three", 3)]
        socket = _Socket()
        async def connect(_url, *, headers):
            calls.append(headers)
            if len(calls) <= 2: raise _InvalidStatus()
            return socket
        def issue():
            issues.append(1)
            return leases.pop(0)
        hub = TossRealtimeHub(connector=connect, token_issuer=issue, grace_seconds=0.01)
        monkeypatch.setattr("features.common.market_data.toss_open_api.token_manager", lambda: manager)
        await hub.start(); sub = await hub.subscribe("AAPL"); await sub.queue.get()
        await asyncio.sleep(0.04)
        assert len(issues) == len(calls) == 2
        assert manager.invalidated == [(1, "invalid_token"), (2, "invalid_token")]
        assert (await _next_status(sub.queue, "unavailable"))["code"] == "invalid_token"
        late = await hub.subscribe("NVDA")
        assert await late.queue.get() == {"schemaVersion": 1, "type": "status", "status": "unavailable", "provider": "toss_open_api", "symbol": "NVDA", "market": "US", "asOf": "", "price": None, "currency": "USD", "code": "invalid_token"}
        await asyncio.sleep(0.03)
        assert len(issues) == len(calls) == 2
        hub.reset_auth_breaker()
        await asyncio.sleep(0.03)
        assert len(issues) == len(calls) == 3
        await hub.stop()
    _run(scenario())


def test_stop_cancels_and_awaits_recv_and_wake_children_under_stress():
    async def scenario():
        for _ in range(200):
            socket = _Socket()
            hub = _hub(socket)
            await hub.start()
            sub = await hub.subscribe("AAPL")
            await sub.queue.get()
            # Let the runner reach its provider recv()/Event.wait() pair.
            await asyncio.sleep(0)
            await hub.stop()
            await asyncio.sleep(0)
            assert socket.recv_tasks == set()
            pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task() and task.get_name() == "toss-realtime-hub"]
            assert pending == []
    _run(scenario())


def test_unsupported_local_websocket_never_starts_an_upstream_connection(tmp_path):
    socket = _Socket()
    app = FastAPI()
    app.include_router(create_market_data_router(tmp_path, realtime_hub=_hub(socket)))
    endpoint = next(route.endpoint for route in app.router.routes[-1].original_router.routes if getattr(route, "path", "") == "/api/market/realtime/chart")
    local = _LocalWebSocket("^KS11")
    _run(endpoint(local))
    assert local.events[0]["status"] == "unsupported"
    assert socket.sent == []
