"""Exact original-decision references for newly generated Portfolio reviews."""
from features.decision_readiness.portfolio_fit import instrument_for
from .capture import case_id
from .ownership import entries, original_id
from .paths import database
from . import store


def original_decisions(root, positions):
    references = []
    seen = set()
    with database(root) as conn:
        for position in positions:
            instrument = instrument_for(position)
            if not instrument or instrument in seen:
                continue
            seen.add(instrument)
            key = case_id(instrument)
            case = store.case(conn, key)
            history = entries(root, conn, key) if case else []
            original = original_id(history, case["episode_id"] if case else None)
            source = next((row for row in history if row["id"] == original), {})
            references.append({"instrumentId": instrument, "caseId": key, "journalId": original,
                               "bodyHash": source.get("bodyHash"), "recordedAt": source.get("recordedAt"),
                               "status": source.get("status", "not_recorded"), "sourceLayer": "hypothesis", "reuseAsEvidence": False})
    return sorted(references, key=lambda row: row["instrumentId"])
