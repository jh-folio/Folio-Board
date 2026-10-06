"""Capture once, calculate purely, verify unchanged sources, return references without saving."""
import datetime as dt
from . import SCHEMA_VERSION, METHOD_VERSION, SPEC_SHA256, DecisionError
from .inputs import LATEST, Files, capture, criteria, database, digest, evaluated_at, identity
from .comparison import candidate, comparability
from .portfolio_fit import raw_portfolio, current_composition


def comparison(root, candidates, *, criteria_revision=LATEST, at=None, reference_set=None, attribution_years=5, portfolio_basis=None, portfolio_basis_id=None):
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 8 or attribution_years not in {1, 3, 5}:
        raise DecisionError("invalid_comparison_request")
    identities = [identity(item.get("instrumentId")) for item in candidates]
    if len({item["instrumentId"] for item in identities}) != len(identities):
        raise DecisionError("duplicate_candidate")
    stamp = evaluated_at(at)
    replay = reference_set is not None
    ref_keys = {"methodVersion", "criteriaRevisionId", "candidates", "portfolioHash", "portfolioBasisId", "portfolioBasisFingerprint"}
    if replay and (not isinstance(reference_set, dict) or set(reference_set) != ref_keys or at is None or reference_set.get("methodVersion") != METHOD_VERSION or not isinstance(reference_set.get("candidates"), list) or len(reference_set["candidates"]) != len(candidates)):
        raise DecisionError("invalid_reference_set")
    if replay:
        revision = reference_set["criteriaRevisionId"]
        checksum = reference_set["portfolioHash"]
        if (revision is not None and (type(revision) is not int or revision < 1)) or (checksum is not None and (not isinstance(checksum, str) or len(checksum) != 64)):
            raise DecisionError("invalid_reference_set")
        if reference_set["portfolioBasisId"] != portfolio_basis_id or reference_set["portfolioBasisFingerprint"] != (portfolio_basis or {}).get("basisFingerprint"):
            raise DecisionError("invalid_reference_set")
    files = Files(root)
    with database(root) as conn:
        revision = reference_set.get("criteriaRevisionId") if replay else criteria_revision
        personal = criteria(conn, revision)
        if replay and criteria_revision is not LATEST and criteria_revision != revision:
            raise DecisionError("invalid_reference_set")
        portfolio_hash = reference_set.get("portfolioHash") if replay else LATEST
        if portfolio_hash is None:
            portfolio, checksum = {"positions": []}, None
        else:
            portfolio, checksum = raw_portfolio(files)
            if replay and checksum != portfolio_hash:
                raise DecisionError("comparison_inputs_changed", 409)
        captured = [capture(conn, files, ident, stamp, reference_set["candidates"][i] if replay else LATEST, item.get("snapshotId", LATEST)) for i, (ident, item) in enumerate(zip(identities, candidates))]
        if portfolio_basis is not None and portfolio_basis["portfolioHash"] != checksum:
            raise DecisionError("comparison_inputs_changed", 409)
        composition = current_composition(portfolio_basis) if portfolio_basis is not None else None
        output = [candidate(data, personal, stamp, attribution_years, portfolio, composition) for data in captured]
        refs = {"methodVersion": METHOD_VERSION, "criteriaRevisionId": (personal or {}).get("revisionId"),
                "candidates": [data["refs"] for data in captured], "portfolioHash": checksum,
                "portfolioBasisId": portfolio_basis_id, "portfolioBasisFingerprint": (portfolio_basis or {}).get("basisFingerprint")}
        files.verify()
    result = {"schemaVersion": SCHEMA_VERSION, "methodVersion": METHOD_VERSION, "specSha256": SPEC_SHA256,
              "evaluatedAt": stamp, "referenceSet": refs, "attributionYears": attribution_years, "candidates": output,
              "comparability": comparability(output), "notice": "선택한 순서로 같은 항목을 나란히 봅니다. 기준 충족은 입력한 조건의 계산상 충족이며, 순위나 투자 결론이 아닙니다. 저장되지 않은 화면입니다."}
    return {**result, "inputFingerprint": digest({"referenceSet": refs, "evaluatedAt": stamp, "attributionYears": attribution_years, "methodVersion": METHOD_VERSION})}


def readiness(root, instrument, *, snapshot_id=LATEST, criteria_revision=LATEST):
    out = comparison(root, [{"instrumentId": instrument, **({"snapshotId": snapshot_id} if snapshot_id is not LATEST else {})}], criteria_revision=criteria_revision)
    return {key: out[key] for key in ("schemaVersion", "methodVersion", "specSha256", "evaluatedAt", "inputFingerprint", "referenceSet")} | out["candidates"][0]
