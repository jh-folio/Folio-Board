"""Self-generated provenance marker shared by every export writer (원칙 5: 자기참조 금지).

New Obsidian/Notion exports write ``generated_by: GENERATED_BY_MARKER`` (currently
``"Folio Board"``). Every reader must keep recognizing the OLD value
(``"Folio OS"``) forever, so a note exported before the 2026-09 rename stays
excluded from evidence — a rename must never quietly widen what counts as
self-generated (plan §4.3, CLAUDE.md/AGENTS.md §5 원칙 5).

Two readers care about this, and they need it in different shapes:

- The Obsidian importer's self-reference classifier
  (``features/obsidian/importer/parser.py::classify``) only checks
  ``bool(generated_by)`` — it never compares the value, so it is already
  value-agnostic and safe with no code change (verified, not assumed — see
  that module's docstring).
- ``web/src/app/deepResearchPayload.ts::parseLedger`` is the one place in the
  whole codebase that compares the value directly (``normalizedMarker(...)``).
  It cannot import this Python module, so it carries its own
  ``SELF_GENERATED_MARKER_ALIASES`` TS constant — keep the two alias sets in
  sync by hand if the display name ever changes again.

Do not inline the literal ``"Folio Board"`` string at each export call site;
import ``GENERATED_BY_MARKER`` from here instead, so every writer stays in
sync automatically the next time the display name changes.
"""
from __future__ import annotations

import re

# The value every NEW export writes to `generated_by`. Only the writers in
# features/obsidian/export/service.py and features/thesis_tracking/service.py
# should reference this.
GENERATED_BY_MARKER = "Folio Board"

# Every normalized (lowercased, spaces/`_`/`-` stripped) form this app has ever
# written to `generated_by`. Add a new alias here — and to
# web/src/app/deepResearchPayload.ts's matching constant — together, in the
# same commit, if the display name changes again. Never delete an old alias:
# a note exported years ago must stay excluded from evidence forever.
SELF_GENERATED_MARKER_ALIASES = frozenset({"folioos", "folioboard"})

_NORMALIZE_RE = re.compile(r"[\s_-]+")


def normalize_marker(value: object) -> str:
    """Match web/src/app/deepResearchPayload.ts::normalizedMarker exactly."""
    text = str(value or "").strip().lower()
    return _NORMALIZE_RE.sub("", text)


def is_self_generated_marker(value: object) -> bool:
    """True if `value` (a `generated_by` field) names this app, old or new name."""
    return normalize_marker(value) in SELF_GENERATED_MARKER_ALIASES
