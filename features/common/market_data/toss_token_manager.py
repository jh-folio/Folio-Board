"""Process-local Toss Open API token lifecycle and safe provider health.

Toss invalidates a client's previous access token whenever a new one is issued.
The manager is consequently the only place that may issue a token in a Folio
server process.  It deliberately keeps tokens in memory and never records a
raw provider response, account value, credential, or token in its health view.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


TOKEN_SKEW_SECONDS = 60.0
_MAX_COUNTER = 1_000
_MAX_RETRY_AFTER_SECONDS = 86_400
_MAX_RATE_LIMIT_REMAINING = 10_000_000
_MAX_ERROR_CODE_LENGTH = 48
_SAFE_ERROR_CODES = frozenset({
    "disabled",
    "credentials_missing",
    "multi_process_unsupported",
    "token_response_invalid",
    "token_issue_failed",
    "invalid_token",
    "token_expired",
    "ip_allowlist_or_permission_denied",
    "rate_limited",
    "provider_contract_invalid",
    "provider_error",
})


def normalize_error_code(value: object) -> str:
    """Collapse provider/WS text to a short allowlisted public health code."""
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "access_token_expired": "token_expired",
        "token_expired": "token_expired",
        "invalid_access_token": "invalid_token",
        "invalid_token": "invalid_token",
        "unauthorized": "invalid_token",
        "http_401": "invalid_token",
        "http_403": "ip_allowlist_or_permission_denied",
        "http_429": "rate_limited",
    }
    normalized = aliases.get(raw, raw)
    return normalized if len(normalized) <= _MAX_ERROR_CODE_LENGTH and normalized in _SAFE_ERROR_CODES else "provider_error"


class TossTokenError(RuntimeError):
    """A typed, secret-free token/provider failure."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = str(code)
        super().__init__(message or self.code)

    def __repr__(self) -> str:
        return f"TossTokenError(code={self.code!r})"


class TossProviderError(RuntimeError):
    """Terminal REST authentication failure with no provider body attached."""

    def __init__(self, code: object) -> None:
        self.code = normalize_error_code(code)
        super().__init__(self.code)

    def __repr__(self) -> str:
        return f"TossProviderError(code={self.code!r})"


@dataclass(frozen=True, repr=False)
class TokenLease:
    """An in-memory token paired with the generation that issued it."""

    token: str
    generation: int

    def __repr__(self) -> str:
        return f"TokenLease(generation={self.generation})"


class WorkspaceFileLock:
    """A non-blocking OS lock held by one Folio server process.

    The lock file intentionally carries no PID or credential.  OS lock release
    (process exit/handle close) is the sole ownership signal, which avoids a
    stale-PID heuristic across Windows and POSIX hosts.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._handle = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = self.path.open("a+b")
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            if "handle" in locals():
                handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class TossTokenManager:
    """Single-flight, process-local OAuth token owner for REST and future WS.

    ``issuer`` is injected by the REST adapter.  Future WebSocket code calls
    :meth:`get_token` too, so it cannot race REST into invalidating its token.
    ``lock_factory`` and ``workspace_dir`` are constructor inputs to make the
    process-boundary contract directly testable without touching user data.
    """

    def __init__(
        self,
        *,
        workspace_dir: Path,
        enabled: Callable[[], bool],
        client_id: Callable[[], str],
        client_secret: Callable[[], str],
        lock_factory: Callable[[Path], WorkspaceFileLock] = WorkspaceFileLock,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._workspace_dir = Path(workspace_dir)
        self._enabled = enabled
        self._client_id = client_id
        self._client_secret = client_secret
        self._lock_factory = lock_factory
        self._monotonic = monotonic
        self._condition = threading.Condition(threading.RLock())
        self._token = ""
        self._expires_at = 0.0
        self._generation = 0
        self._issuing = False
        self._process_lock: WorkspaceFileLock | None = None
        self._lock_attempting = False
        self._lock_denied = False
        self._status = "not_activated"
        self._last_error_code = ""
        self._rate_limited_count = 0
        self._unauthorized_count = 0
        self._forbidden_count = 0
        self._rate_limit_remaining: int | None = None
        self._retry_after_seconds: int | None = None

    @property
    def lock_path(self) -> Path:
        return self._workspace_dir / "runtime-locks" / "toss-open-api.lock"

    def _configured(self) -> bool:
        return bool(str(self._client_id() or "").strip() and str(self._client_secret() or "").strip())

    def _set_error_locked(self, code: str, status: str = "unavailable") -> None:
        self._last_error_code = normalize_error_code(code)
        self._status = status

    def _ensure_configured(self) -> None:
        if not self._enabled():
            with self._condition:
                self._set_error_locked("disabled", "disabled")
            raise TossTokenError("disabled", "Toss Open API is disabled for this release")
        if not self._configured():
            with self._condition:
                self._set_error_locked("credentials_missing", "missing_credentials")
            raise TossTokenError("credentials_missing", "Toss Open API client_id/client_secret is not configured")

    def _acquire_process_lock(self) -> None:
        with self._condition:
            if self._process_lock is not None:
                return
            if self._lock_denied:
                raise TossTokenError("multi_process_unsupported")
            while self._lock_attempting:
                self._condition.wait()
                if self._process_lock is not None:
                    return
                if self._lock_denied:
                    raise TossTokenError("multi_process_unsupported")
            self._lock_attempting = True
        lock: WorkspaceFileLock | None = None
        acquired = False
        try:
            lock = self._lock_factory(self.lock_path)
            acquired = bool(lock.acquire())
        except Exception:
            acquired = False
        with self._condition:
            self._lock_attempting = False
            if acquired and lock is not None:
                self._process_lock = lock
                if self._status in {"not_activated", "ready", "disabled", "missing_credentials"}:
                    self._status = "ready"
            else:
                self._lock_denied = True
                self._set_error_locked("multi_process_unsupported")
            self._condition.notify_all()
            if self._process_lock is None:
                raise TossTokenError("multi_process_unsupported")

    def _valid_locked(self) -> bool:
        return bool(self._token and self._expires_at > self._monotonic() + TOKEN_SKEW_SECONDS)

    def get_token(self, issuer: Callable[[], tuple[str, int | float]]) -> TokenLease:
        """Return the current token or single-flight issue a new generation."""
        self._ensure_configured()
        self._acquire_process_lock()
        with self._condition:
            if self._valid_locked():
                return TokenLease(self._token, self._generation)
            while self._issuing:
                self._condition.wait()
                if self._valid_locked():
                    return TokenLease(self._token, self._generation)
            self._issuing = True
        try:
            token, expires_in = issuer()
            token = str(token or "").strip()
            if not token:
                raise TossTokenError("token_response_invalid", "Toss Open API token response did not include access_token")
            try:
                ttl = float(expires_in)
            except (TypeError, ValueError):
                ttl = 3600.0
            with self._condition:
                self._token = token
                self._expires_at = self._monotonic() + max(TOKEN_SKEW_SECONDS, ttl)
                self._generation += 1
                self._status = "active"
                return TokenLease(self._token, self._generation)
        except TossTokenError as exc:
            with self._condition:
                self._set_error_locked(exc.code)
            raise
        except Exception as exc:
            with self._condition:
                self._set_error_locked("token_issue_failed")
            raise TossTokenError("token_issue_failed") from exc
        finally:
            with self._condition:
                self._issuing = False
                self._condition.notify_all()

    def invalidate_if_generation(self, generation: int, *, error_code: str = "invalid_token") -> bool:
        """Invalidate only the token that actually received the auth failure."""
        with self._condition:
            if int(generation) != self._generation or not self._token:
                return False
            self._token = ""
            self._expires_at = 0.0
            self._set_error_locked(error_code, "degraded")
            return True

    def record_http_error(self, status_code: int, headers: object | None = None, *, error_code: object | None = None) -> str:
        """Record only bounded, non-sensitive provider error metadata."""
        status = int(status_code or 0)
        code = normalize_error_code(error_code if error_code is not None else f"http_{status}")
        with self._condition:
            if status == 401:
                self._unauthorized_count = min(_MAX_COUNTER, self._unauthorized_count + 1)
            elif status == 403:
                code = "ip_allowlist_or_permission_denied"
                self._forbidden_count = min(_MAX_COUNTER, self._forbidden_count + 1)
            elif status == 429:
                code = "rate_limited"
                self._rate_limited_count = min(_MAX_COUNTER, self._rate_limited_count + 1)
            self._set_error_locked(code, "degraded")
            self._record_rate_limit_headers_locked(headers)
        return code

    def record_provider_error(self, error_code: object) -> str:
        """Future WS/provider paths may report only a normalized safe code."""
        code = normalize_error_code(error_code)
        with self._condition:
            self._set_error_locked(code, "degraded")
        return code

    def _record_rate_limit_headers_locked(self, headers: object | None) -> None:
        if headers is None or not hasattr(headers, "get"):
            return
        for names, target, maximum in [
            (("x-ratelimit-remaining", "ratelimit-remaining"), "remaining", _MAX_RATE_LIMIT_REMAINING),
            (("retry-after",), "retry", _MAX_RETRY_AFTER_SECONDS),
        ]:
            raw = None
            for name in names:
                raw = headers.get(name)
                if raw is not None:
                    break
            try:
                value = max(0, min(maximum, int(float(raw))))
            except (TypeError, ValueError):
                continue
            if target == "remaining":
                self._rate_limit_remaining = value
            else:
                self._retry_after_seconds = value

    def health_snapshot(self) -> dict:
        """Return a bounded, browser-safe health projection without activation."""
        enabled = bool(self._enabled())
        configured = bool(enabled and self._configured())
        with self._condition:
            status = self._status
            if not enabled:
                status = "disabled"
            elif not configured:
                status = "missing_credentials"
            elif status == "not_activated":
                status = "ready"
            return {
                "enabled": enabled,
                "configured": configured,
                "status": status,
                "lastErrorCode": self._last_error_code or None,
                "authFailureCount": self._unauthorized_count,
                "rateLimit": {
                    "limitedCount": self._rate_limited_count,
                    "remaining": self._rate_limit_remaining,
                    "retryAfterSeconds": self._retry_after_seconds,
                },
            }

    def clear_cached_token_for_tests(self) -> None:
        """Test-only cache reset; it intentionally leaves a held OS lock intact."""
        with self._condition:
            self._token = ""
            self._expires_at = 0.0

    def close_for_tests(self) -> None:
        with self._condition:
            lock = self._process_lock
            self._process_lock = None
            self._token = ""
            self._expires_at = 0.0
        if lock is not None:
            lock.release()

    def __repr__(self) -> str:
        safe = self.health_snapshot()
        return f"TossTokenManager(status={safe['status']!r}, configured={safe['configured']!r})"
