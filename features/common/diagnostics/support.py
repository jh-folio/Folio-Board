"""Safe context propagation and source-frame verification helpers."""
from __future__ import annotations

import ast
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Callable, Iterator, ParamSpec, TypeVar

from .schema import DiagnosticContext, Failure, SafeFrame

_CURRENT: ContextVar[DiagnosticContext | None] = ContextVar("folio_diagnostic_context", default=None)
_REQUEST_ID: ContextVar[str | None] = ContextVar("folio_diagnostic_request_id", default=None)
_FAILURE_CACHE_LIMIT = 32
_FAILURES: ContextVar[dict[int, tuple[BaseException, Failure]] | None] = ContextVar("folio_diagnostic_failures", default=None)
P = ParamSpec("P")
T = TypeVar("T")


def current_context() -> DiagnosticContext | None:
    """Convenience access only; observers must still pass context explicitly."""
    return _CURRENT.get()


def current_request_id() -> str | None:
    """The server-generated correlation ID for the current request only."""
    return _REQUEST_ID.get()


@contextmanager
def bind_failure_cache() -> Iterator[None]:
    """Keep one sanitized failure per live exception in a worker boundary."""
    token = _FAILURES.set({})
    try:
        yield
    finally:
        _FAILURES.reset(token)


def remember_failure(error: BaseException, failure: Failure) -> None:
    cache = _FAILURES.get()
    key = id(error)
    if cache is None or key in cache:
        # Preserve the first concrete boundary for one exact exception.
        return
    if len(cache) >= _FAILURE_CACHE_LIMIT:
        cache.pop(next(iter(cache)))
    # Retaining the exact object prevents recycled `id()` values from being
    # attributed to an unrelated later exception in this bounded worker turn.
    cache[key] = (error, failure)


def remembered_failure(error: BaseException) -> Failure | None:
    cache = _FAILURES.get()
    stored = cache.get(id(error)) if cache is not None else None
    return stored[1] if stored is not None and stored[0] is error else None


@contextmanager
def bind_request_id(request_id: str) -> Iterator[str]:
    """Bind a validated server ID around one request and always reset it."""
    from .schema import valid_id

    parsed = valid_id(request_id, "req")
    token = _REQUEST_ID.set(parsed)
    try:
        yield parsed
    finally:
        _REQUEST_ID.reset(token)


@contextmanager
def bind_context(context: DiagnosticContext) -> Iterator[DiagnosticContext]:
    """Set a frozen context and always reset it at the current boundary."""
    token: Token[DiagnosticContext | None] = _CURRENT.set(context)
    try:
        yield context
    finally:
        _CURRENT.reset(token)


def context_bound(context: DiagnosticContext, callback: Callable[P, T]) -> Callable[P, T]:
    """Make explicit context propagation safe for thread/executor boundaries."""
    def invoke(*args: P.args, **kwargs: P.kwargs) -> T:
        with bind_context(context):
            return callback(*args, **kwargs)
    return invoke


def verified_source_frame(*, app_root: Path, module_code: str, function_code: str, line: int) -> SafeFrame | None:
    """Return a frame only when its module and function are real shipped code.

    This deliberately reads source structure rather than traceback text.  A
    caller cannot smuggle arbitrary paths, source lines, locals, or a function
    name from a dynamic/external module into a persisted diagnostic.
    """
    try:
        frame = SafeFrame(module_code, function_code, line)
        root = app_root.resolve(strict=True)
        unresolved = root / (module_code.replace(".", "/") + ".py")
        if unresolved.is_symlink():
            return None
        candidate = unresolved.resolve(strict=True)
        candidate.relative_to(root)
        if not candidate.is_file() or candidate.is_symlink():
            return None
        tree = ast.parse(candidate.read_text(encoding="utf-8"), filename=str(candidate))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_code:
                end = getattr(node, "end_lineno", node.lineno)
                if node.lineno <= line <= end:
                    return frame
    except (OSError, SyntaxError, ValueError):
        return None
    return None
