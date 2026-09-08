"""Bounded, privacy-safe execution diagnostics.

This package is intentionally inert at import time.  Producers create a
``DiagnosticsStore`` with their already-authoritative data root and may use a
``DiagnosticRecorder`` on a best-effort basis; diagnostics never owns a job,
commit, retry, or result.
"""

from .record import DiagnosticRecorder
from .schema import DiagnosticContext, DiagnosticValidationError, new_context, safe_exception_failure, safe_failure
from .store import DiagnosticsStore
from .retention import DiagnosticsRetentionService

__all__ = (
    "DiagnosticContext",
    "DiagnosticRecorder",
    "DiagnosticsStore",
    "DiagnosticsRetentionService",
    "DiagnosticValidationError",
    "new_context",
    "safe_failure",
    "safe_exception_failure",
)
