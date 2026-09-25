"""Safe process-local Toss realtime fan-out (pinned AsyncAPI 1.2.2)."""
from __future__ import annotations

import asyncio
import contextlib
import json
import random
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from . import toss_open_api
from .toss_token_manager import TokenLease

TOSS_REALTIME_URL = "wss://openapi-ws.tossinvest.com/ws/v1"
SCHEMA_VERSION, MAX_TOPICS, DECLARATIONS_PER_SECOND = 1, 100, 5
PING_SECONDS, GRACE_SECONDS, STOP_TIMEOUT_SECONDS = 60.0, 8.0, 1.0
_SAFE_CODES = {"invalid_token", "token_expired", "rate_limited", "ip_allowlist_or_permission_denied", "provider_error", "connection_error", "unsupported", "credentials_missing", "disabled", "multi_process_unsupported"}
_DELAYED_YFINANCE_EXCHANGE_SUFFIXES = {
    "T", "HK", "AS", "AX", "DE", "L", "PA", "MI", "TO", "SI", "SS", "SZ",
    "SW", "HE", "ST", "CO", "OL", "BR", "VI", "MC", "LS", "IR", "WA", "PR",
    "BE", "IC", "BA", "SA", "MX", "TA", "JO", "IL", "BK", "JK", "KL", "NS",
    "BO", "NZ", "TW", "VN", "CA", "V", "F", "AT", "BD", "DU", "HA", "HM",
    "MU", "SG", "TL", "RG", "VS", "ME", "IS",
}


def subscription_target(symbol: str) -> tuple[str, str, str]:
    value = str(symbol or "").strip().upper()
    if value.startswith("^") or "=" in value or value in {"BTC-USD", "USDKRW=X"}:
        return value, "", "unsupported"
    if re.fullmatch(r"\d{6}(?:\.(?:KS|KQ))?", value):
        return value.split(".", 1)[0], "KR", ""
    if "." in value and value.rsplit(".", 1)[1] in _DELAYED_YFINANCE_EXCHANGE_SUFFIXES:
        return value, "", "unsupported"
    return (value, "US", "") if re.fullmatch(r"[A-Z][A-Z0-9.]{0,14}", value) else (value, "", "unsupported")


def _topic(symbol: str, market: str) -> str:
    return f"trade:{market.lower()}:{symbol}"


def _topic_target(value: object) -> tuple[str, str]:
    parts = str(value or "").split(":", 2)
    if len(parts) != 3 or parts[0].lower() != "trade":
        return "", ""
    market = {"kr": "KR", "us": "US"}.get(parts[1].lower(), "")
    symbol, parsed_market, reason = subscription_target(parts[2])
    return (symbol, market) if market and parsed_market == market and not reason else ("", "")


def _safe_code(value: object) -> str:
    code = str(value or "").strip().lower().replace("-", "_")
    aliases = {"access_token_expired": "token_expired", "invalid_access_token": "invalid_token", "stock_not_found": "unsupported", "symbol_market_mismatch": "unsupported", "rate_limit_exceeded": "rate_limited", "server_shutdown": "connection_error", "forbidden": "ip_allowlist_or_permission_denied"}
    code = aliases.get(code, code)
    return code if code in _SAFE_CODES else "provider_error"


@dataclass(frozen=True)
class RealtimeSubscription:
    id: str
    queue: asyncio.Queue[dict]
    symbol: str
    market: str


@dataclass
class _Subscriber:
    subscription: RealtimeSubscription
    remove_after: float | None = None


async def _default_connector(url: str, *, headers: dict[str, str]) -> Any:
    from websockets.asyncio.client import connect
    return await connect(url, additional_headers=headers, ping_interval=None)


class TossRealtimeHub:
    def __init__(self, *, connector: Callable[..., Awaitable[Any]] | None = None, token_issuer: Callable[[], TokenLease] | None = None, generation_supplier: Callable[[], int] | None = None, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep, jitter: Callable[[], float] = random.random, grace_seconds: float = GRACE_SECONDS) -> None:
        self._connector = connector or _default_connector
        self._token_issuer = token_issuer or toss_open_api.issue_access_token_lease
        self._generation_supplier = generation_supplier or (toss_open_api.active_token_generation if token_issuer is None else lambda: self._connected_generation or 0)
        self._clock, self._sleep, self._jitter, self._grace = clock, sleep, jitter, grace_seconds
        self._subscribers: dict[str, _Subscriber] = {}; self._rejected: set[str] = set(); self._declarations: deque[float] = deque()
        self._lock, self._wake = asyncio.Lock(), asyncio.Event(); self._running = False; self._runner: asyncio.Task[None] | None = None
        self._connection: Any | None = None; self._connected_generation: int | None = None; self._last_declaration: tuple[str, ...] = ()
        self._last_client_send = 0.0; self._declaration_pause_until = 0.0; self._immediate_reconnect = False; self._auth_breaker_generation: int | None = None

    @property
    def runner(self) -> asyncio.Task[None] | None: return self._runner

    async def start(self) -> None: self._running = True

    def reset_auth_breaker(self) -> None:
        """Explicit safe reactivation after credentials/operator remediation."""
        self._auth_breaker_generation = None
        self._wake.set()

    async def stop(self) -> None:
        self._running = False; self._wake.set(); connection, runner = self._connection, self._runner; self._connection = None; self._runner = None
        if connection is not None:
            with contextlib.suppress(Exception, asyncio.TimeoutError): await asyncio.wait_for(connection.close(), STOP_TIMEOUT_SECONDS)
        if runner is not None:
            runner.cancel()
            with contextlib.suppress(Exception, asyncio.TimeoutError, asyncio.CancelledError): await asyncio.wait_for(runner, STOP_TIMEOUT_SECONDS)

    async def subscribe(self, symbol: str) -> RealtimeSubscription:
        normalized, market, reason = subscription_target(symbol); sub = RealtimeSubscription(uuid.uuid4().hex, asyncio.Queue(maxsize=8), normalized, market)
        if reason:
            await sub.queue.put(self._status(sub, "unsupported", reason)); return sub
        async with self._lock:
            keys = {_topic(x.subscription.symbol, x.subscription.market) for x in self._active_locked()}
            if _topic(normalized, market) not in keys and len(keys) >= MAX_TOPICS:
                await sub.queue.put(self._status(sub, "rejected", "provider_error")); return sub
            self._subscribers[sub.id] = _Subscriber(sub)
            # Keep the local subscription for recovery, but do not imply an
            # upstream request can proceed while the 401 breaker owns it.
            if self._auth_breaker_generation is not None:
                await sub.queue.put(self._status(sub, "unavailable", "invalid_token"))
            else:
                await sub.queue.put(self._status(sub, "pending", ""))
            self._ensure_runner_locked(); self._wake.set()
        return sub

    async def unsubscribe(self, subscription_id: str) -> None:
        async with self._lock:
            item = self._subscribers.get(subscription_id)
            if item: item.remove_after = self._clock() + self._grace; self._wake.set()

    def safe_chart_status(self, symbol: str) -> dict[str, object]:
        _, market, reason = subscription_target(symbol)
        return {"liveEligible": bool(market), "liveStatus": "available" if market else "unsupported", "fallbackReason": reason}

    def _ensure_runner_locked(self) -> None:
        if self._running and (self._runner is None or self._runner.done()): self._runner = asyncio.create_task(self._run(), name="toss-realtime-hub")

    def _active_locked(self) -> list[_Subscriber]:
        now = self._clock()
        for key in [key for key, item in self._subscribers.items() if item.remove_after is not None and item.remove_after <= now]: self._subscribers.pop(key, None)
        return list(self._subscribers.values())

    async def _active(self) -> list[_Subscriber]:
        async with self._lock: return self._active_locked()

    async def _run(self) -> None:
        backoff, auth_retry = 1.0, False
        while self._running:
            if self._auth_breaker_generation is not None:
                # A token created elsewhere by the shared manager proves a new
                # generation; otherwise do not churn token issuance forever.
                if self._generation_supplier() > self._auth_breaker_generation:
                    self.reset_auth_breaker(); auth_retry = False
                else:
                    with contextlib.suppress(asyncio.TimeoutError): await asyncio.wait_for(self._wake.wait(), max(0.05, self._grace))
                    self._wake.clear()
                    continue
            if not await self._active():
                self._wake.clear()
                with contextlib.suppress(asyncio.TimeoutError): await asyncio.wait_for(self._wake.wait(), max(0.05, self._grace))
                continue
            lease: TokenLease | None = None
            try:
                self._immediate_reconnect = False
                lease = self._token_issuer(); connection = await self._connector(TOSS_REALTIME_URL, headers={"Authorization": f"Bearer {lease.token}"})
                self._connection, self._connected_generation = connection, lease.generation; self._last_client_send = self._clock()
                await self._broadcast_status("connecting", ""); await self._declare(connection, force=True); backoff = 1.0; auth_retry = False; await self._receive_loop(connection)
            except asyncio.CancelledError: return
            except Exception as exc:
                code = self._exception_code(exc)
                if code in {"invalid_token", "token_expired"} and lease is not None:
                    # Both rejected generations are removed. Only the first
                    # failure earns the immediate reconnect privilege.
                    toss_open_api.token_manager().invalidate_if_generation(lease.generation, error_code=code)
                    if not auth_retry:
                        auth_retry = True; self._immediate_reconnect = True
                    else:
                        self._auth_breaker_generation = lease.generation
                elif code == "ip_allowlist_or_permission_denied":
                    toss_open_api.token_manager().record_http_error(403, None, error_code=code)
                elif code == "rate_limited":
                    toss_open_api.token_manager().record_http_error(429, None, error_code=code)
                await self._broadcast_status("reconnecting" if self._immediate_reconnect else "unavailable", code)
            finally:
                connection, self._connection = self._connection, None; self._connected_generation = None
                if connection is not None:
                    with contextlib.suppress(Exception, asyncio.TimeoutError): await asyncio.wait_for(connection.close(), STOP_TIMEOUT_SECONDS)
            if not self._running or not await self._active(): continue
            if self._auth_breaker_generation is not None: continue
            if self._immediate_reconnect: continue
            await self._sleep(min(30.0, backoff) * (0.75 + min(0.25, max(0.0, self._jitter())))); backoff = min(30.0, backoff * 2)

    async def _receive_loop(self, connection: Any) -> None:
        while self._running and await self._active():
            if self._clock() - self._last_client_send >= PING_SECONDS:
                await connection.send("PING"); self._last_client_send = self._clock(); continue
            until_ping = max(0.001, PING_SECONDS - (self._clock() - self._last_client_send)); receive, wake = asyncio.create_task(connection.recv()), asyncio.create_task(self._wake.wait())
            try:
                done, _pending = await asyncio.wait({receive, wake}, timeout=until_ping, return_when=asyncio.FIRST_COMPLETED)
            finally:
                # Cancellation may arrive while asyncio.wait itself is pending;
                # a provider close is not required to unblock recv() for us.
                for task in (receive, wake):
                    if not task.done(): task.cancel()
                for task in (receive, wake):
                    with contextlib.suppress(Exception, asyncio.CancelledError): await task
            if not done:
                if self._connected_generation is not None and self._generation_supplier() != self._connected_generation: raise RuntimeError("token_generation_changed")
                await connection.send("PING"); self._last_client_send = self._clock(); continue
            if wake in done:
                self._wake.clear(); await self._declare(connection); continue
            await self._handle_frame(receive.result())
            if self._immediate_reconnect: return
            if self._connected_generation is not None and self._generation_supplier() != self._connected_generation: raise RuntimeError("token_generation_changed")

    async def _declare(self, connection: Any, *, force: bool = False) -> None:
        active = await self._active(); grouped: dict[str, set[str]] = {"us": set(), "kr": set()}
        for item in active:
            key = _topic(item.subscription.symbol, item.subscription.market)
            if key not in self._rejected: grouped[item.subscription.market.lower()].add(item.subscription.symbol)
        flat = tuple(sorted(f"trade:{market}:{code}" for market, codes in grouped.items() for code in codes))
        if not force and flat == self._last_declaration: return
        if self._clock() < self._declaration_pause_until: await self._sleep(self._declaration_pause_until - self._clock())
        while self._declarations and self._clock() - self._declarations[0] >= 1.0: self._declarations.popleft()
        if len(self._declarations) >= DECLARATIONS_PER_SECOND: await self._sleep(max(0.0, 1.0 - (self._clock() - self._declarations[0])))
        payload: list[dict[str, object]] = [{"type": f"trade:{market}", "codes": sorted(grouped[market])} for market in ("us", "kr") if grouped[market]]
        await connection.send(json.dumps(payload, separators=(",", ":"))); self._last_client_send = self._clock(); self._declarations.append(self._clock()); self._last_declaration = flat

    async def _handle_frame(self, frame: object) -> None:
        if isinstance(frame, bytes): frame = frame.decode("utf-8", "replace")
        if frame == "PONG": return
        try: value = json.loads(frame) if isinstance(frame, str) else frame
        except (TypeError, ValueError): return
        if not isinstance(value, dict): return
        kind = str(value.get("type") or "").lower()
        if kind == "pong": return
        if kind == "subscriptions":
            for target in value.get("subscribed") or []:
                symbol, market = _topic_target(target); await self._broadcast_status("subscribed", "", symbol=symbol, market=market)
            newly_rejected = False
            for rejected in value.get("rejected") or []:
                if not isinstance(rejected, dict): continue
                symbol, market = _topic_target(rejected.get("target")); code = _safe_code(rejected.get("code"))
                if symbol:
                    target = _topic(symbol, market)
                    newly_rejected = newly_rejected or target not in self._rejected
                    self._rejected.add(target); await self._broadcast_status("rejected", code, symbol=symbol, market=market)
            if newly_rejected and self._connection is not None: await self._declare(self._connection, force=True)
            return
        if kind == "message":
            symbol, market = _topic_target(value.get("topic")); data = value.get("data") if isinstance(value.get("data"), dict) else {}
            if not symbol or not market: return
            try: price = float(data.get("price"))
            except (TypeError, ValueError): return
            event = {"schemaVersion": SCHEMA_VERSION, "type": "tick", "status": "live", "provider": "toss_open_api", "symbol": symbol, "market": market, "asOf": str(data.get("timestamp") or "")[:40], "price": price, "currency": str(data.get("currency") or ("KRW" if market == "KR" else "USD"))[:8]}
            await self._broadcast(event, symbol=symbol, market=market); return
        if kind == "error":
            error = value.get("error") if isinstance(value.get("error"), dict) else {}; raw = str(error.get("code") or ""); code = _safe_code(raw)
            if raw == "server-shutdown": self._immediate_reconnect = True; await self._broadcast_status("reconnecting", code); return
            if raw == "rate-limit-exceeded":
                self._declaration_pause_until = self._clock() + 1.0; await self._broadcast_status("reconnecting", code)
                if self._connection is not None: await self._declare(self._connection, force=True)
                return
            await self._broadcast_status("unavailable", code)

    def _status(self, sub: RealtimeSubscription, status: str, code: str) -> dict:
        return {"schemaVersion": SCHEMA_VERSION, "type": "status", "status": status, "provider": "toss_open_api", "symbol": sub.symbol, "market": sub.market, "asOf": "", "price": None, "currency": "KRW" if sub.market == "KR" else ("USD" if sub.market == "US" else ""), "code": _safe_code(code) if code else ""}

    async def _broadcast_status(self, status: str, code: str, *, symbol: str = "", market: str = "") -> None:
        event = {"schemaVersion": SCHEMA_VERSION, "type": "status", "status": status, "provider": "toss_open_api", "symbol": symbol, "market": market, "asOf": "", "price": None, "currency": "KRW" if market == "KR" else ("USD" if market == "US" else ""), "code": _safe_code(code) if code else ""}; await self._broadcast(event, symbol=symbol, market=market)

    async def _broadcast(self, event: dict, *, symbol: str = "", market: str = "") -> None:
        async with self._lock:
            for item in self._active_locked():
                sub = item.subscription
                if symbol and (sub.symbol != symbol or sub.market != market): continue
                if sub.queue.full():
                    with contextlib.suppress(asyncio.QueueEmpty): sub.queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull): sub.queue.put_nowait(dict(event))

    @staticmethod
    def _exception_code(exc: BaseException) -> str:
        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if status is None:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
        try: status = int(status)
        except (TypeError, ValueError): status = 0
        if status == 401: return "invalid_token"
        if status == 403: return "ip_allowlist_or_permission_denied"
        if status == 429: return "rate_limited"
        return _safe_code(str(exc)) if str(exc) else "connection_error"
