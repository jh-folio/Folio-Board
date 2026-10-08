"""Explicit personal research records; never an evidence or report authority."""

SCHEMA_VERSION = 1
METHOD_VERSION = "investment-case-1"
SPEC_SHA256 = "cebb0b696818d8de2aa4f422525ff6e0acd929575fdd23b6838970665f0241e6"
MAX_BYTES = 5 * 1024 * 1024
STAGES = frozenset({"researching", "considering", "owned", "archived"})
KINDS = frozenset({"decision", "stage_change", "partial_change", "reason_replaced", "reentry", "ownership_review", "postmortem"})
SLOTS = ("company", "research", "macro", "price", "reason", "delta", "review", "readiness")


class CaseError(ValueError):
    """Only the enum code and bounded details cross the HTTP boundary."""

    def __init__(self, code, status=400, **details):
        super().__init__(code)
        self.code, self.status, self.details = code, status, details
