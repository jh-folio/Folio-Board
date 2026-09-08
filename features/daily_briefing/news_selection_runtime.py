"""Runtime boundary for the Q5 daily-news selection experiment.

This module is intentionally a small facade around :mod:`news_selection`.
It owns the parts which are easy to get wrong at a call site: the feature mode
is opt-in, a prior report is pinned before intake, search is bounded and local,
and shadow/off never change the writer's operational input.  It does not write
reports, update market memory, call a model, or create a cache/database.

The returned metadata is diagnostic only.  Article bodies are kept in the
candidate list for the caller which already owns that data, while assessment
rows contain bounded excerpts and no private paths or raw search queries.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Iterable, Mapping

from features.common.research_schema.evidence import is_countable_evidence
from features.common.market_calendar import infer_doc_markets
from features.daily_briefing.news_selection import (
    BASELINE_SELECTOR_VERSION,
    MAX_CANDIDATES,
    MAX_DEEP_EVENTS,
    MAX_EXCERPT_CHARS,
    SUPPORTED_ACTIVE_MARKETS,
    SUPPORTED_MODES,
    assess_news_candidates,
    select_prior_briefing_baseline,
)


MODE_ENV = "BRIEFING_NEWS_SELECTION_MODE"
DEFAULT_MODE = "off"
MAX_SEARCH_QUERIES = 4
SEARCH_LIMIT = 12
MAX_RUNTIME_SECONDS = 60.0
SUPPORTED_MARKETS = frozenset({"us", "kr", "europe", "jp"})


def search_documents(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """Lazy bridge kept patchable for tests and safe for service import order."""

    from features.common.research_library.search.service import search_documents as _search_documents

    return _search_documents(*args, **kwargs)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _date(value: Any) -> str:
    return _text(value)[:10]


def _normalise_mode(value: Any) -> str:
    mode = _lower(value)
    return mode if mode in SUPPORTED_MODES else DEFAULT_MODE


def configured_news_selection_mode() -> str:
    """Return the process setting; an absent or invalid value is ``off``."""

    return _normalise_mode(os.getenv(MODE_ENV, DEFAULT_MODE))


def _normalise_markets(markets: Any) -> tuple[str, ...]:
    if isinstance(markets, str):
        values = markets.split(",")
    else:
        values = markets or ()
    result = []
    for value in values:
        market = _lower(value)
        if market in SUPPORTED_MARKETS and market not in result:
            result.append(market)
    return tuple(result)


def _report_kind(report: Mapping[str, Any]) -> str:
    return _lower(report.get("kind") or report.get("briefingKind") or "daily") or "daily"


def _report_market(report: Mapping[str, Any]) -> str:
    direct = _lower(report.get("market") or report.get("marketScope"))
    if direct in SUPPORTED_MARKETS:
        return direct
    values = report.get("includedMarkets") or report.get("markets")
    if isinstance(values, (list, tuple, set)) and len(values) == 1:
        market = _lower(next(iter(values)))
        return market if market in SUPPORTED_MARKETS else ""
    return ""


def _load_existing_reports() -> list[dict[str, Any]]:
    """Read committed report JSON only; this runs before any evidence intake."""

    from features.common.workspace import data_dir

    folder = Path(data_dir()) / "briefings"
    if not folder.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json"), key=lambda item: item.name, reverse=True):
        # Sidecars and arbitrary files are not briefing baselines.
        if path.name.endswith(".link.json") or ".visuals" in path.name:
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _session_and_source_dates(date_text: str, market: str, kind: str, analysis_as_of: str) -> tuple[str, list[str]]:
    if kind == "weekly":
        return date_text, [date_text]
    try:
        from features.common.market_calendar import briefing_market_windows
        from features.daily_briefing.schema import briefing_session_date

        windows = briefing_market_windows(date_text, as_of=analysis_as_of or None)
        session = briefing_session_date(date_text, market, market_windows=windows)
        dates = set()
        for key in ("sourceDates", "source_dates"):
            value = windows.get(key)
            if isinstance(value, (list, tuple, set)):
                dates.update(_date(item) for item in value if _date(item))
        # Keep the requested market's own session and briefing date available;
        # a source window may also contain the adjacent market's prior session.
        dates.update((_date(session), date_text))
        return _date(session) or date_text, sorted(dates)
    except Exception:
        return date_text, [date_text]


def _baseline_report_view(report: Mapping[str, Any], market: str) -> dict[str, Any] | None:
    if _report_market(report) == market:
        return deepcopy(dict(report))
    sections = report.get("briefings")
    section = sections.get(market) if isinstance(sections, Mapping) else None
    if not isinstance(section, Mapping):
        return None
    result = deepcopy(dict(section))
    result.setdefault("market", market)
    result.setdefault("marketScope", market)
    result.setdefault("kind", _report_kind(report))
    return result


def _safe_baseline_dict(selection: Any) -> dict[str, Any]:
    """Copy the selector result without exposing a mutable report reference."""

    if hasattr(selection, "as_dict"):
        value = selection.as_dict()
    elif isinstance(selection, Mapping):
        value = dict(selection)
    else:
        value = {"status": "baseline_missing", "reason": "baseline_missing"}
    value = deepcopy(value)
    if isinstance(value.get("report"), Mapping):
        value["report"] = deepcopy(dict(value["report"]))
    return value


def _safe_baseline_report(report: Mapping[str, Any], *, kind: str = "daily") -> dict[str, Any]:
    """Retain only comparison metadata needed by the runtime pack.

    Canonical markdown and personal/hypothesis fields are deliberately absent;
    a serialized selection context must not become an evidence or private-note
    transport.
    """

    identity_keys = {
        "id", "market", "marketScope", "kind", "briefingKind", "date",
        "sessionDate", "marketSessionDate", "analysisSessionDate", "cutoff",
        "sourceCutoff", "dataCutoff", "inputCutoff", "asOf", "generatedAt",
        "committedAt", "savedAt", "selectionVersion", "newsSelectionVersion",
        "policyVersion", "version", "canonicalRevision", "writerIds", "sourceIds",
        "checkpoints", "checkpointQuestions", "previousCheckpoints", "checkpoint",
        "checklist",
    }
    result = {key: deepcopy(value) for key, value in report.items() if key in identity_keys}
    if _text(report.get("markdown")):
        from features.daily_briefing.service import extract_prev_checklist

        result["writerPreviousChecklist"] = extract_prev_checklist(_text(report["markdown"]), kind=kind)
    for key in ("checkpoints", "checkpointQuestions", "previousCheckpoints", "checkpoint", "checklist"):
        value = result.get(key)
        if isinstance(value, (list, tuple)):
            compact: list[Any] = []
            for item in value[:2]:
                if isinstance(item, Mapping):
                    item = {
                        item_key: _text(item.get(item_key))[:240]
                        for item_key in ("question", "text", "condition")
                        if _text(item.get(item_key))
                    }
                elif _text(item):
                    item = _text(item)[:240]
                if item:
                    compact.append(item)
            result[key] = compact
        elif isinstance(value, Mapping):
            result[key] = {
                _text(item_key)[:80]: _text(item_value)[:240]
                for item_key, item_value in list(value.items())[:2]
                if _text(item_key) and _text(item_value)
            }
        elif _text(value):
            result[key] = _text(value)[:240]
    if not any(result.get(key) for key in ("checkpoints", "checkpointQuestions", "previousCheckpoints", "checkpoint", "checklist")):
        markdown = report.get("markdown")
        if _text(markdown):
            try:
                from features.daily_briefing.service import extract_prev_checklist

                checklist = extract_prev_checklist(_text(markdown), kind=kind)
            except Exception:
                checklist = ""
            if checklist:
                result["checkpointQuestions"] = [checklist[:MAX_EXCERPT_CHARS]]
    for key in ("sourceRefs", "sources"):
        refs = report.get(key)
        if not isinstance(refs, (list, tuple)):
            continue
        compact: list[dict[str, Any]] = []
        for ref in refs:
            if not isinstance(ref, Mapping):
                continue
            row = {
                key: deepcopy(ref[key])
                for key in ("id", "sourceId", "eventKey", "observedPeriod", "correctionOf", "revisionAt", "publishedAt")
                if _text(ref.get(key))
            }
            if row:
                compact.append(row)
            if len(compact) >= MAX_CANDIDATES:
                break
        result[key] = compact
    return result


def pin_selection_context(
    date: str,
    markets: Iterable[str] | str,
    kind: str = "daily",
    analysis_as_of: str | None = None,
) -> dict[str, Any]:
    """Pin same-market/kind prior baselines before the intake phase.

    The context is a detached snapshot.  Callers may subsequently mutate the
    reports or candidate documents without changing the pinned identity/copy.
    ``analysis_as_of`` is passed to the existing selector as the current
    cutoff; no timestamp is invented when it is absent.
    """

    date_text = _date(date)
    target_kind = _lower(kind) or "daily"
    target_markets = _normalise_markets(markets)
    mode = configured_news_selection_mode()
    as_of = _text(analysis_as_of) or _now_iso()
    session_dates: dict[str, str] = {}
    source_dates: dict[str, list[str]] = {}
    for market in target_markets:
        session_dates[market], source_dates[market] = _session_and_source_dates(
            date_text, market, target_kind, as_of
        )
    if mode == "off":
        # Off is a zero-work contract: in particular, do not touch the report
        # directory merely to construct an unused baseline.
        return {
            "date": date_text,
            "markets": list(target_markets),
            "kind": target_kind,
            "analysisAsOf": as_of,
            "mode": mode,
            "baselineSelectorVersion": BASELINE_SELECTOR_VERSION,
            "sessionDates": session_dates,
            "sourceDates": source_dates,
            "baselines": {market: {"status": "not_run", "reason": "mode_off"} for market in target_markets},
        }
    loaded_reports = _load_existing_reports()
    # Aggregate files are a storage compatibility shape.  Flatten their
    # already-committed market sections before selecting a baseline so a US
    # run cannot accidentally use a KR (or aggregate) lineage row.
    reports: list[dict[str, Any]] = []
    for report in loaded_reports:
        if not isinstance(report, Mapping):
            continue
        direct = _report_market(report)
        if direct:
            reports.append(dict(report))
            continue
        sections = report.get("briefings")
        if isinstance(sections, Mapping):
            for section_market, section in sections.items():
                if _lower(section_market) not in SUPPORTED_MARKETS or not isinstance(section, Mapping):
                    continue
                view = _baseline_report_view(report, _lower(section_market))
                if view:
                    reports.append(view)
    baselines: dict[str, dict[str, Any]] = {}
    for market in target_markets:
        selection = select_prior_briefing_baseline(
            reports,
            market=market,
            kind=target_kind,
            current_session_date=session_dates.get(market) or date_text,
            current_cutoff=as_of,
            selector_version=BASELINE_SELECTOR_VERSION,
        )
        baselines[market] = _safe_baseline_dict(selection)
        # Ensure report copies cannot retain references supplied by a test
        # loader or a future storage adapter.
        report = baselines[market].get("report")
        if isinstance(report, Mapping):
            baselines[market]["report"] = _safe_baseline_report(report, kind=target_kind)
    return {
        "date": date_text,
        "markets": list(target_markets),
        "kind": target_kind,
        "analysisAsOf": as_of,
        "mode": mode,
        "baselineSelectorVersion": BASELINE_SELECTOR_VERSION,
        "sessionDates": session_dates,
        "sourceDates": source_dates,
        "baselines": baselines,
    }


def _context_mode(context: Mapping[str, Any] | None, market: str, kind: str) -> tuple[str, str]:
    requested = _normalise_mode((context or {}).get("mode") if isinstance(context, Mapping) else None)
    if requested == DEFAULT_MODE and not context:
        requested = configured_news_selection_mode()
    # The first-stage runtime is US/KR daily only.  JP/EU and weekly remain
    # exactly on the existing selection path even when a broad mode is set.
    if kind != "daily" or market not in SUPPORTED_ACTIVE_MARKETS:
        return requested, "off"
    return requested, requested


def _cutoff_value(context: Mapping[str, Any] | None) -> str:
    value = _text((context or {}).get("analysisAsOf")) if isinstance(context, Mapping) else ""
    return value


def _doc_market_matches(doc: Mapping[str, Any], market: str, *, unknown_ok: bool = False) -> bool:
    explicit = doc.get("market") or doc.get("marketScope") or doc.get("defaultMarket")
    if explicit:
        values = explicit if isinstance(explicit, (list, tuple, set)) else [explicit]
        return market in {_lower(value) for value in values}
    values = doc.get("markets") or doc.get("includedMarkets")
    if isinstance(values, (list, tuple, set)) and values:
        return market in {_lower(value) for value in values}
    try:
        inferred = {str(value).lower() for value in infer_doc_markets(dict(doc))}
    except Exception:
        inferred = set()
    if inferred & {market, "global", "both"}:
        return True
    return unknown_ok and not inferred


def _is_allowed_news(
    doc: Mapping[str, Any],
    market: str,
    cutoff: str,
    *,
    existing: bool,
    allowed_dates: set[str] | None = None,
) -> bool:
    path = _text(doc.get("path")).replace("\\", "/").lower()
    if path and not (path.startswith("research-inbox/articles/") or path.startswith("research-inbox/rss/")):
        return False
    if not path and not existing:
        # Search hits are expected to carry their indexed path.  Do not allow a
        # malformed hit to escape the article/rss lane.
        return False
    if cutoff:
        value = _date(doc.get("date") or doc.get("publishedAt"))
        cutoff_day = _date(cutoff)
        if not value or value > cutoff_day:
            return False
        if allowed_dates is not None and value not in allowed_dates:
            return False
        # Date-only intake records cannot support an exact replay claim, but
        # timestamped records on the cutoff day can be fail-closed precisely.
        published = _text(doc.get("publishedAt") or doc.get("published_at"))
        if not published:
            published = _text(doc.get("publishedAtKst") or doc.get("published_at_kst"))
            if published:
                try:
                    parsed = datetime.fromisoformat(published)
                    if parsed.tzinfo is None:
                        published = parsed.isoformat() + "+09:00"
                except ValueError:
                    published = ""
        if published and _timestamp_after(published, cutoff):
            return False
    return _doc_market_matches(doc, market, unknown_ok=existing)


def _timestamp_after(value: str, cutoff: str) -> bool:
    """Compare timestamps only when both sides carry parseable time data."""

    if len(value) <= 10 or len(cutoff) <= 10:
        return False
    try:
        left = datetime.fromisoformat(value.replace("Z", "+00:00"))
        right = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    except ValueError:
        return False
    if left.tzinfo is None or right.tzinfo is None:
        return False  # An unknown timezone is not an exact replay boundary.
    return left.astimezone(timezone.utc) > right.astimezone(timezone.utc)


def _candidate_id(candidate: Mapping[str, Any], index: int) -> str:
    value = _text(candidate.get("id") or candidate.get("candidateId"))
    return value or f"candidate_{index}"


def _source_id(candidate: Mapping[str, Any]) -> str:
    value = _text(candidate.get("sourceId") or candidate.get("source_id"))
    if value:
        return f"source:{value}"
    value = _text(candidate.get("url"))
    if value:
        return f"url:{value.split('#', 1)[0].lower()}"
    publisher = _lower(candidate.get("publisher") or candidate.get("source"))
    title = " ".join(_lower(candidate.get("title")).split())
    return f"headline:{publisher}|{title}|{_date(candidate.get('date') or candidate.get('publishedAt'))}"


def _event_identity(candidate: Mapping[str, Any]) -> str:
    return "|".join(
        (
            _source_id(candidate),
            _text(candidate.get("observedPeriod") or candidate.get("period")),
            _text(candidate.get("correctionOf") or candidate.get("revisionOf")),
            _text(candidate.get("revisionAt") or candidate.get("revisionId")),
        )
    )


def _baseline_writer_ids(context: Mapping[str, Any] | None, market: str) -> set[str]:
    if not isinstance(context, Mapping):
        return set()
    baseline = (context.get("baselines") or {}).get(market)
    if not isinstance(baseline, Mapping):
        return set()
    values: list[Any] = []
    for key in ("writerIds", "sourceIds"):
        value = baseline.get(key)
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        elif _text(value):
            values.append(value)
    report = baseline.get("report")
    if isinstance(report, Mapping):
        for key in ("writerIds", "sourceIds"):
            value = report.get(key)
            if isinstance(value, (list, tuple, set)):
                values.extend(value)
            elif _text(value):
                values.append(value)
        for key in ("sourceRefs", "sources"):
            refs = report.get(key)
            if isinstance(refs, (list, tuple)):
                for ref in refs:
                    if isinstance(ref, Mapping):
                        values.extend((ref.get("sourceId"), ref.get("id"), ref.get("url"), ref.get("eventKey")))
    result: set[str] = set()
    for value in values:
        text = _lower(value)
        if not text:
            continue
        result.add(text)
        # Writer IDs in older reports are raw source IDs, while assessment
        # rows carry the bounded ``source:`` identity prefix.
        result.add(f"source:{text}")
        if text.startswith(("http://", "https://")):
            result.add(f"url:{text.split('#', 1)[0]}")
    return result


def _safe_assessment_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Remove path and body fields before passing a candidate to diagnostics."""

    value = {
        key: deepcopy(item)
        for key, item in candidate.items()
        if key not in {"path", "absolutePath", "content", "fullText", "rawText"}
    }
    # A short summary is enough for the bounded excerpt contract.
    if not _text(value.get("summary")) and _text(candidate.get("content")):
        value["summary"] = _text(candidate.get("content"))[:MAX_EXCERPT_CHARS]
    for key in ("summary", "snippet"):
        if _text(value.get(key)):
            value[key] = _text(value[key])[:MAX_EXCERPT_CHARS]
    return value


def _baseline_questions(context: Mapping[str, Any] | None, market: str) -> list[str]:
    if not isinstance(context, Mapping):
        return []
    baseline = (context.get("baselines") or {}).get(market)
    if not isinstance(baseline, Mapping) or baseline.get("status") != "baseline_ready":
        return []
    report = baseline.get("report")
    if not isinstance(report, Mapping):
        return []
    values: list[Any] = []
    for key in ("checkpoints", "checkpointQuestions", "previousCheckpoints"):
        value = report.get(key)
        if isinstance(value, (list, tuple)):
            values.extend(value)
    # Some saved reports keep the checkpoint text in a compact checklist map.
    checklist = report.get("checkpoint") or report.get("checklist")
    if isinstance(checklist, Mapping):
        values.extend(checklist.values())
    elif _text(checklist):
        values.append(checklist)
    if not values and _text(report.get("markdown")):
        try:
            from features.daily_briefing.service import extract_prev_checklist

            extracted = extract_prev_checklist(_text(report.get("markdown")), kind="daily")
        except Exception:
            extracted = ""
        if extracted:
            values.append(extracted)
    questions: list[str] = []
    for value in values:
        if isinstance(value, Mapping):
            value = value.get("question") or value.get("text") or value.get("condition")
        question = " ".join(_text(value).split())[:240]
        if question and question not in questions:
            questions.append(question)
        if len(questions) >= 2:
            break
    return questions


def _baseline_ready(context: Mapping[str, Any] | None, market: str) -> bool:
    if not isinstance(context, Mapping):
        return False
    baselines = context.get("baselines")
    value = baselines.get(market) if isinstance(baselines, Mapping) else None
    return isinstance(value, Mapping) and _lower(value.get("status")) == "baseline_ready"


def _search_queries(market: str, kind: str, questions: Iterable[str] = ()) -> tuple[str, ...]:
    # Query strings are intentionally not returned in metadata.  Checkpoint
    # searches only run when a real pinned checkpoint exists; the remaining
    # calls are deliberately open exploration rather than sentiment scoring.
    queries: list[str] = []
    values = list(questions)
    if values:
        checkpoint = " ; ".join(values[:2])
        queries.extend((f"{checkpoint} support", f"{checkpoint} challenge"))
    queries.extend((f"{market} {kind} general open", f"{market} {kind} new company event"))
    return tuple(queries[:MAX_SEARCH_QUERIES])


def _collect_search_candidates(
    index: Any,
    *,
    market: str,
    kind: str,
    cutoff: str,
    deadline: float,
    questions: Iterable[str] = (),
    allowed_dates: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(index, Mapping):
        return [], {"queriesAttempted": 0, "searchStatus": "unavailable"}
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    attempted = 0
    for query in _search_queries(market, kind, questions)[:MAX_SEARCH_QUERIES]:
        if time.monotonic() >= deadline:
            break
        attempted += 1
        try:
            hits = search_documents(index, query=query, limit=SEARCH_LIMIT, scope="news") or []
        except Exception:
            # Diagnostics must not persist raw errors, paths, or query text.
            continue
        for hit in hits:
            if not isinstance(hit, Mapping) or not _is_allowed_news(
                hit, market, cutoff, existing=False, allowed_dates=allowed_dates
            ):
                continue
            key = _event_identity(hit)
            if key in seen:
                continue
            seen.add(key)
            found.append(deepcopy(dict(hit)))
            if len(found) >= MAX_CANDIDATES:
                break
        if len(found) >= MAX_CANDIDATES:
            break
    return found[:MAX_CANDIDATES], {
        "queriesAttempted": attempted,
        "searchStatus": "complete" if attempted == MAX_SEARCH_QUERIES else "partial",
    }


def _direct_evidence(candidate: Mapping[str, Any]) -> bool:
    if not is_countable_evidence(dict(candidate)):
        return False
    return bool(_text(candidate.get("title")) and (_text(candidate.get("url")) or _text(candidate.get("source"))))


def _role(candidate: Mapping[str, Any], *, novel: bool, direct: bool) -> str:
    # Candidate metadata is untrusted editorial input.  A source cannot make
    # itself a ``judgment_change`` merely by declaring that role; the semantic
    # pass (or the deterministic fallback below) owns role assignment.
    if not direct:
        return "unassigned"
    companies = candidate.get("companies")
    if novel and isinstance(companies, (list, tuple)) and companies:
        return "new_signal"
    if novel:
        return "core_flow"
    return "unassigned"


def _active_proposal(
    candidates: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    *,
    top_n: int,
    baseline_writer_ids: set[str],
    original_ids: list[str],
    baseline_known: bool,
    semantic_rows: Mapping[str, Mapping[str, Any]] | None = None,
    semantic_evaluated: bool = False,
    semantic_required: bool = False,
) -> tuple[list[str], list[dict[str, Any]], bool]:
    superseded: set[str] = set()
    for candidate in candidates:
        target = _lower(candidate.get("correctionOf") or candidate.get("revisionOf"))
        if not target:
            continue
        for other in candidates:
            if other is candidate:
                continue
            tokens = {
                _lower(other.get("id")),
                _lower(other.get("candidateId")),
                _lower(other.get("sourceId") or other.get("source_id")),
                _source_id(other).lower(),
                _event_identity(other).lower(),
            }
            if target in tokens:
                superseded.add(_candidate_id(other, 0))
    rows: list[dict[str, Any]] = []
    for candidate, assessment in zip(candidates, assessments):
        if _candidate_id(candidate, 0) in superseded and not _text(candidate.get("correctionOf") or candidate.get("revisionOf")):
            continue
        if assessment.get("status") != "assessed" or not _direct_evidence(candidate):
            continue
        source = _text(assessment.get("sourceIdentity")).lower() or _source_id(candidate).lower()
        event = _text(assessment.get("eventKey")).lower() or _event_identity(candidate).lower()
        repeated_event = event in baseline_writer_ids
        repeated_source = source in baseline_writer_ids
        has_new_observation = bool(
            _text(candidate.get("observedPeriod") or candidate.get("period"))
            or _text(candidate.get("correctionOf") or candidate.get("revisionOf"))
            or _text(candidate.get("revisionAt") or candidate.get("revisionId"))
        )
        # A source-level writer ID is enough to suppress a repeated headline,
        # but not a separately identified new period/correction.
        novel: bool | None = (
            not repeated_event and (not repeated_source or has_new_observation)
            if baseline_known
            else None
        )
        enriched = dict(assessment)
        enriched["novel"] = novel
        enriched["directEvidence"] = True
        enriched["roleDecision"] = _role(candidate, novel=bool(novel), direct=True) if novel is not None else "unassigned"
        enriched["semanticAssessment"] = "unavailable"
        enriched["semanticAssessmentReason"] = "no_validated_same_input_assessment"
        semantic = (semantic_rows or {}).get(_candidate_id(candidate, 0))
        if isinstance(semantic, Mapping):
            enriched["semanticAssessment"] = _lower(semantic.get("assessmentStatus")) or "not_evaluated"
            enriched["semanticAssessmentReason"] = _lower(semantic.get("reason"))
            enriched["semanticVerdict"] = _lower(semantic.get("verdict"))
            enriched["hypothesisEffects"] = deepcopy(semantic.get("hypothesisEffects") or [])
            enriched["explanationImportance"] = _lower(semantic.get("explanationImportance")) or "unknown"
            enriched["judgmentUpdateImportance"] = _lower(semantic.get("judgmentUpdateImportance")) or "unknown"
            enriched["novelty"] = _lower(semantic.get("novelty")) or "unknown"
            # Validated semantic roles are derived by news_semantics from the
            # relationship rows.  Candidate editorialRole metadata is never
            # copied into this decision.
            roles = semantic.get("editorialRoles")
            if isinstance(roles, (list, tuple)) and roles:
                enriched["roleDecision"] = "judgment_change" if "judgment_change" in roles else _lower(roles[0])
        rows.append(enriched)
    # Role queues keep existing core market coverage ahead of optional company
    # events without inventing a weighted score.  Input order remains the
    # deterministic tie-breaker inside each queue.
    original_set = set(original_ids)
    core_ids = {_candidate_id(row, 0) for row in candidates if _candidate_id(row, 0) in original_set and not row.get("companies")}
    ordered: list[dict[str, Any]] = [row for row in rows if row.get("candidateId") in core_ids]
    importance_order = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
    # Ordinal axes, not a synthetic weighted materiality score. Python's
    # stable sort preserves candidate order when both axes tie.
    ranked = sorted(rows, key=lambda row: (
        importance_order.get(row.get("judgmentUpdateImportance"), 3),
        importance_order.get(row.get("explanationImportance"), 3),
    ))
    for role in ("judgment_change", "checkpoint_result", "core_flow", "new_signal"):
        ordered.extend(
            row for row in ranked
            if row.get("roleDecision") == role
            and row not in ordered
        )
    ordered.extend(row for row in rows if row not in ordered)
    rows = ordered
    selection_rows = (
        [row for row in rows if row.get("semanticAssessment") == "assessed"]
        if semantic_required else rows
    )
    proposed = [_text(row.get("candidateId")) for row in selection_rows[: max(0, int(top_n))] if _text(row.get("candidateId"))]
    # A proposal is only applied when it contains a valid, genuinely new
    # candidate.  This prevents active mode from being an operational no-op
    # while also preventing every queried article from being promoted.
    valid_new = [
        row for row in selection_rows
        if row.get("novel") is True
        and row.get("roleDecision") in {"new_signal", "core_flow", "judgment_change"}
        and (
            # Keep the legacy deterministic proposal only until the semantic
            # callback is explicitly wired.  Once an adapter is supplied,
            # active mode is fail-closed on a validated same-input result.
            not semantic_required
            or row.get("semanticAssessment") == "assessed"
        )
    ]
    operational = [_text(value) for value in proposed]
    original_target = [_text(value) for value in original_ids[: max(0, int(top_n))]]
    if semantic_required and original_target:
        # Active mode cannot drop the existing market-core pack because the
        # semantic callback only validated a subset.  A correction can cover
        # the superseded original event, but an unevaluated candidate cannot.
        correction_targets = {
            _lower(row.get("correctionOf") or row.get("revisionOf"))
            for row in candidates
            if _candidate_id(row, 0) in operational
        }
        core_target = {
            _candidate_id(row, 0) for row in candidates
            if _candidate_id(row, 0) in original_target and not row.get("companies")
        }
        if any(value.lower() not in {item.lower() for item in operational} and value.lower() not in correction_targets for value in core_target):
            return operational, rows, False
    changed = bool(valid_new) and (semantic_evaluated or not semantic_required) and operational != original_target
    return operational, rows, changed


def prepare_selection_candidates(
    docs: Iterable[Mapping[str, Any]] | None,
    index: Mapping[str, Any] | None,
    market: str,
    kind: str = "daily",
    pinned_context: Mapping[str, Any] | None = None,
    baseline_writer_ids: Iterable[str] | None = None,
    top_n: int = 24,
    *,
    semantic_callback: Any | None = None,
    semantic_adapter_limits_verified: bool | None = None,
    semantic_request_ledger: Any | None = None,
    semantic_cache: Any | None = None,
    cancelled: Any | None = None,
    deadline: float | None = None,
    selected_markets: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Prepare bounded Q5 candidates while preserving mode boundaries.

    ``off`` returns the original candidate list byte-for-byte in the
    ``operationalCandidates`` field and performs no search or assessment.
    ``shadow`` performs bounded local evaluation but returns the same
    operational IDs.  ``active`` is scoped to US/KR daily and can apply only
    a validated, direct-evidence proposal.
    """

    original = list(docs or [])
    target_market = _lower(market)
    target_kind = _lower(kind) or "daily"
    requested, effective = _context_mode(pinned_context, target_market, target_kind)
    original_ids = [_candidate_id(row, i) for i, row in enumerate(original) if isinstance(row, Mapping)]
    top_n = min(MAX_CANDIDATES, max(0, int(top_n)))
    if effective == "off":
        return {
            "mode": requested,
            "effectiveMode": effective,
            "operationalCandidates": original,
            "selectedCandidateIds": original_ids[:top_n],
            "proposedRanking": [],
            "assessments": [],
            "metadata": {},
            "proposalFallbackReason": "unsupported_scope" if requested != "off" else "",
        }

    started = time.monotonic()
    runtime_deadline = started + MAX_RUNTIME_SECONDS
    if deadline is not None:
        try:
            runtime_deadline = min(runtime_deadline, float(deadline))
        except (TypeError, ValueError):
            runtime_deadline = started
    cutoff = _cutoff_value(pinned_context)
    context_dates = (pinned_context or {}).get("sourceDates", {}) if isinstance(pinned_context, Mapping) else {}
    allowed_dates = None
    if isinstance(context_dates, Mapping):
        values = context_dates.get(target_market)
        if isinstance(values, (list, tuple, set)):
            allowed_dates = {_date(value) for value in values if _date(value)}
    initial = [
        deepcopy(dict(row))
        for row in original
        if isinstance(row, Mapping)
        and _is_allowed_news(
            row,
            target_market,
            cutoff,
            existing=True,
            allowed_dates=allowed_dates,
        )
    ]
    searched, search_meta = _collect_search_candidates(
        index,
        market=target_market,
        kind=target_kind,
        cutoff=cutoff,
        deadline=runtime_deadline,
        questions=_baseline_questions(pinned_context, target_market),
        allowed_dates=allowed_dates,
    )
    # Reserve a quarter of the pre-Top-N budget for independent local search;
    # a large existing pack must not consume all 96 slots before open/checkpoint
    # candidates have a chance to enter.
    search_reserve = min(24, MAX_CANDIDATES)
    merged = initial[: max(0, MAX_CANDIDATES - search_reserve)]
    seen = {_event_identity(row) for row in merged}
    for row in searched:
        key = _event_identity(row)
        if key not in seen and len(merged) < MAX_CANDIDATES:
            merged.append(row)
            seen.add(key)

    safe_candidates = [_safe_assessment_candidate(row) for row in merged]
    assessments = assess_news_candidates(
        safe_candidates,
        market=target_market,
        kind=target_kind,
        candidate_limit=MAX_CANDIDATES,
        deep_limit=MAX_DEEP_EVENTS,
    )
    # Semantic evaluation is intentionally injected.  Importing this module
    # must never select a provider or bridge, and absent/unverified adapters
    # remain ``not_evaluated`` rather than being represented as no change.
    from features.daily_briefing.news_semantics import evaluate_news_semantics

    semantic_result = evaluate_news_semantics(
        merged,
        pinned_context,
        market=target_market,
        kind=target_kind,
        mode=effective,
        selected_markets=selected_markets,
        analysis_as_of=_cutoff_value(pinned_context),
        semantic_callback=semantic_callback,
        adapter_limits_verified=semantic_adapter_limits_verified,
        request_ledger=semantic_request_ledger,
        cache=semantic_cache,
        deadline=runtime_deadline,
        cancelled=cancelled,
    )
    semantic_rows = {
        _text(row.get("candidateId")): row
        for row in (semantic_result.get("rows") or [])
        if isinstance(row, Mapping) and _text(row.get("candidateId"))
    }
    writer_ids: set[str] = set()
    for value in baseline_writer_ids or ():
        text = _lower(value)
        if text:
            writer_ids.update({text, f"source:{text}"})
    writer_ids |= _baseline_writer_ids(pinned_context, target_market)
    proposal_ids, proposed_rows, proposal_applied = _active_proposal(
        merged,
        assessments,
        top_n=top_n,
        baseline_writer_ids=writer_ids,
        original_ids=original_ids,
        baseline_known=_baseline_ready(pinned_context, target_market),
        semantic_rows=semantic_rows,
        semantic_evaluated=semantic_result.get("status") == "evaluated",
        semantic_required=True,
    )
    can_apply_active = effective == "active" and _baseline_ready(pinned_context, target_market)
    selected_ids = proposal_ids if can_apply_active and proposal_applied else original_ids[:top_n]
    proposal_applied = bool(can_apply_active and proposal_applied)
    if effective != "active":
        proposal_applied = False
    selected_by_id = {_candidate_id(row, i): row for i, row in enumerate(merged)}
    selected_candidates = [selected_by_id[item] for item in selected_ids if item in selected_by_id]
    if effective == "active" and proposal_applied:
        operational_candidates = selected_candidates
    else:
        # Shadow, unsupported active, and an invalid/empty active proposal all
        # fall back to the exact input selection.
        operational_candidates = original
    elapsed = max(0.0, time.monotonic() - started)
    return {
        "mode": requested,
        "effectiveMode": effective,
        "operationalCandidates": operational_candidates,
        "selectedCandidateIds": selected_ids,
        "proposedRanking": proposed_rows,
        "assessments": proposed_rows,
        "proposalApplied": proposal_applied,
        "proposalFallbackReason": (
            "baseline_not_ready" if effective == "active" and not _baseline_ready(pinned_context, target_market) else ""
        ),
        "metadata": {
            "candidateCount": len(merged),
            "candidateCap": MAX_CANDIDATES,
            "deepCandidateCap": MAX_DEEP_EVENTS,
            "excerptChars": MAX_EXCERPT_CHARS,
            "searchQueries": search_meta.get("queriesAttempted", 0),
            "searchStatus": search_meta.get("searchStatus", "unavailable"),
            "assessmentStatus": "complete" if merged else "no_candidates",
            "semanticAssessment": semantic_result.get("status", "not_evaluated"),
            "semanticAssessmentReason": semantic_result.get("reason", ""),
            "semanticCoverageStatus": semantic_result.get("coverageStatus", "not_run"),
            "semanticCandidateCount": semantic_result.get("eventCount", 0),
            "semanticBudgetUnassessedCount": semantic_result.get("budgetUnassessedCount", 0),
            "semanticInputBytes": semantic_result.get("inputBytes", 0),
            "semanticOutputBytes": semantic_result.get("outputBytes", 0),
            "semanticDuplicateCount": semantic_result.get("duplicateCount", 0),
            "semanticRequestCount": semantic_result.get("requestCount", 0),
            "semanticCacheHit": bool(semantic_result.get("cacheHit")),
            "semanticInputHash": _text(semantic_result.get("inputHash")),
            "elapsedMs": round(elapsed * 1000),
        },
        "semanticEvaluation": semantic_result,
    }


def safe_selection_metadata(
    result: Mapping[str, Any] | None,
    context: Mapping[str, Any] | None,
    scope: str,
) -> dict[str, Any]:
    """Project runtime diagnostics into a bounded, report-safe metadata map.

    This is the only helper intended for attaching selection telemetry to a
    public report.  It excludes assessment rows, excerpts, article paths,
    bodies, and search queries.  ``off`` intentionally returns no metadata.
    """

    if not isinstance(result, Mapping):
        return {}
    mode = _normalise_mode(result.get("mode"))
    if mode == "off":
        return {}
    effective = _normalise_mode(result.get("effectiveMode"))
    rows = result.get("assessments")
    rows = rows if isinstance(rows, (list, tuple)) else []
    status_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    reason_codes: list[str] = []
    for row in rows[:MAX_CANDIDATES]:
        if not isinstance(row, Mapping):
            continue
        status = _lower(row.get("assessmentStatus") or row.get("status")) or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
        role = _lower(row.get("roleDecision"))
        if role:
            role_counts[role] = role_counts.get(role, 0) + 1
        reason = _lower(row.get("reason") or row.get("assessmentReason"))
        if reason and reason not in reason_codes:
            reason_codes.append(reason)
    baseline = {}
    if isinstance(context, Mapping):
        value = (context.get("baselines") or {}).get(_lower(scope))
        if isinstance(value, Mapping):
            pin = value.get("pin") if isinstance(value.get("pin"), Mapping) else {}
            baseline = {
                "status": _lower(value.get("status")) or "unknown",
                "reportId": _text(value.get("reportId") or pin.get("reportId")),
                "sessionDate": _date(value.get("sessionDate") or pin.get("sessionDate")),
                "version": _text(value.get("version") or pin.get("version")),
                "contentHash": _text(value.get("contentHash") or pin.get("contentHash")),
                "reasonCodes": [
                    _lower(item) for item in (value.get("reasonCodes") or []) if _text(item)
                ][:8],
            }
    selected = [
        _text(value)
        for value in (result.get("selectedCandidateIds") or [])[:MAX_CANDIDATES]
        if _text(value)
    ]
    semantic = result.get("semanticEvaluation")
    semantic_status = "not_evaluated"
    semantic_reason = ""
    semantic_coverage = "not_run"
    semantic_importance: dict[str, dict[str, int]] = {
        "explanation": {},
        "judgmentUpdate": {},
        "novelty": {},
    }
    if isinstance(semantic, Mapping):
        semantic_status = _lower(semantic.get("status")) or semantic_status
        semantic_reason = _lower(semantic.get("reason"))
        semantic_coverage = _lower(semantic.get("coverageStatus")) or semantic_coverage
        for row in list(semantic.get("rows") or [])[:MAX_DEEP_EVENTS]:
            if not isinstance(row, Mapping):
                continue
            for field, bucket in (
                ("explanationImportance", semantic_importance["explanation"]),
                ("judgmentUpdateImportance", semantic_importance["judgmentUpdate"]),
                ("novelty", semantic_importance["novelty"]),
            ):
                value = _lower(row.get(field)) or "unknown"
                bucket[value] = bucket.get(value, 0) + 1
    metadata = result.get("metadata") if isinstance(result.get("metadata"), Mapping) else {}
    proposal_digest = hashlib.sha256("|".join(selected).encode("utf-8")).hexdigest()[:16]
    return {
        "mode": mode,
        "effectiveMode": effective,
        "market": _lower(scope),
        "kind": _lower((context or {}).get("kind")) if isinstance(context, Mapping) else "daily",
        "proposalApplied": bool(result.get("proposalApplied")),
        "proposalFallbackReason": _lower(result.get("proposalFallbackReason")),
        "selectedCandidateIds": selected,
        "selectionHash": proposal_digest,
        "baseline": baseline,
        "candidateCount": int(metadata.get("candidateCount", 0) or 0),
        "assessmentStatusCounts": status_counts,
        "roleCounts": role_counts,
        "reasonCodes": reason_codes[:8],
        "semanticAssessment": semantic_status,
        "semanticAssessmentReason": semantic_reason,
        "semanticCoverageStatus": semantic_coverage,
        "semanticImportance": semantic_importance,
        "semanticRequestCount": int((semantic or {}).get("requestCount", 0) or 0) if isinstance(semantic, Mapping) else 0,
        "semanticCacheHit": bool((semantic or {}).get("cacheHit")) if isinstance(semantic, Mapping) else False,
        "semanticBudgetUnassessedCount": int((semantic or {}).get("budgetUnassessedCount", 0) or 0) if isinstance(semantic, Mapping) else 0,
        "semanticInputHash": _text((semantic or {}).get("inputHash"))[:64] if isinstance(semantic, Mapping) else "",
        "semanticAssessments": [
            {**{key: deepcopy(row.get(key)) for key in (
                "eventRef", "candidateId", "assessmentStatus", "verdict",
                "explanationImportance", "judgmentUpdateImportance", "currentEvidenceRefs", "claimRefs",
            )}, "hypothesisEffects": [
                {key: deepcopy(effect.get(key)) for key in ("hypothesisRef", "relation", "currentEvidenceRefs", "claimRefs")}
                for effect in (row.get("hypothesisEffects") or [])[:8] if isinstance(effect, Mapping)
            ]}
            for row in ((semantic or {}).get("rows") or [])[:MAX_DEEP_EVENTS] if isinstance(row, Mapping)
        ] if isinstance(semantic, Mapping) else [],
    }


__all__ = [
    "DEFAULT_MODE",
    "MODE_ENV",
    "MAX_CANDIDATES",
    "MAX_DEEP_EVENTS",
    "MAX_EXCERPT_CHARS",
    "configured_news_selection_mode",
    "pin_selection_context",
    "prepare_selection_candidates",
    "safe_selection_metadata",
]
