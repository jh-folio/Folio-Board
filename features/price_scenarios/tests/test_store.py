import copy
import sqlite3

import pytest

from features.price_scenarios import store as store_module
from features.price_scenarios.store import PriceStore, PriceStoreError

from .snapshot_fixtures import PRICE, make, raw_rows


@pytest.fixture
def db(tmp_path):
    return PriceStore(tmp_path / "market-memory.sqlite3")


def moved(price):
    return {**PRICE, "value": price, "sessionDate": "2025-03-04"}


def test_reading_never_creates_files_or_tables(db):
    assert db.latest("US:ACME") is None and db.get("x") is None and db.history("US:ACME") == []
    assert db.criteria() is None and db.override("US:ACME") is None and db.reviews("x") == []
    assert not db.path.exists()


def test_save_is_idempotent_and_refuses_a_different_result_for_the_same_inputs(db):
    inputs, results = make()
    first = db.save_snapshot(inputs, results)
    assert first["created"] is True and first["snapshotId"].startswith("price-")
    assert db.save_snapshot(copy.deepcopy(inputs), copy.deepcopy(results)) == {"snapshotId": first["snapshotId"], "created": False}
    bad = copy.deepcopy(results)
    bad["scenarios"][0]["irr"] = "0.9999"
    with pytest.raises(PriceStoreError) as error:
        db.save_snapshot(inputs, bad)
    assert error.value.code == "non_reproducible"
    loaded = db.get(first["snapshotId"])
    assert loaded["results"] == results and loaded["inputs"] == inputs
    assert db.latest("US:ACME")["snapshotId"] == first["snapshotId"]
    with sqlite3.connect(db.path) as conn:
        assert conn.execute("select count(*) from price_snapshots").fetchone()[0] == 1
        assert conn.execute("select count(*) from price_snapshot_links").fetchone()[0] == 0  # nothing to supersede


def test_rows_are_immutable(db):
    inputs, results = make()
    saved = db.save_snapshot(inputs, results)
    db.save_criteria(required_return="6", holding_years=10)
    db.save_override("US:ACME", saved["snapshotId"], growth="0.1")
    with sqlite3.connect(db.path) as conn:
        for statement in ("UPDATE price_snapshots SET body='{}'", "DELETE FROM price_snapshots",
                          "UPDATE valuation_user_criteria SET required_return='1'", "DELETE FROM valuation_user_criteria",
                          "UPDATE valuation_assumption_overrides SET growth='1'", "DELETE FROM valuation_assumption_overrides"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable_price_scenario"):
                conn.execute(statement)


def test_a_changed_price_adds_a_snapshot_a_link_and_a_reason(db):
    first = db.save_snapshot(*make())
    second = db.save_snapshot(*make(price=moved("31.5")))
    assert second["created"] and second["snapshotId"] != first["snapshotId"]
    history = db.history("US:ACME")
    assert [row["snapshotId"] for row in history] == [second["snapshotId"], first["snapshotId"]]
    assert history[0]["supersedes"] == first["snapshotId"] and history[1]["supersedes"] is None
    assert history[0]["changeReasons"] == [{"code": "price_moved"}]
    assert db.latest("US:ACME")["snapshotId"] == second["snapshotId"]
    assert db.get(first["snapshotId"])["results"]  # an earlier result stays openable


def test_a_corrected_value_marks_every_earlier_snapshot_that_used_the_old_one(db):
    first = db.save_snapshot(*make(rows=raw_rows(eps_override={2024: "2.10"})))
    second = db.save_snapshot(*make(price=moved("30.5"), rows=raw_rows(eps_override={2024: "2.10"})))
    third = db.save_snapshot(*make(price=moved("31"), rows=raw_rows(eps_override={2024: "2.05"})))
    link = next(row for row in db.history("US:ACME") if row["snapshotId"] == third["snapshotId"])
    restated = [reason for reason in link["changeReasons"] if reason["code"] == "restated"]
    assert [(r["metric"], r["fiscalYear"]) for r in restated] == [("EPS Diluted", 2024)]
    for older in (first, second):
        reviews = db.reviews(older["snapshotId"])
        assert [(r["reason"], r["metric"], r["fiscalYear"], r["detectedBySnapshotId"]) for r in reviews] == [
            ("restated", "EPS Diluted", 2024, third["snapshotId"])]
    assert db.reviews(third["snapshotId"]) == []
    counts = {row["snapshotId"]: row["reviewCount"] for row in db.history("US:ACME")}
    assert counts == {first["snapshotId"]: 1, second["snapshotId"]: 1, third["snapshotId"]: 0}
    # the older snapshots' stored bodies did not change
    assert db.get(first["snapshotId"])["inputs"]["history"]["rows"] == make(rows=raw_rows(eps_override={2024: "2.10"}))[0]["history"]["rows"]


def test_a_new_split_is_a_share_event_not_a_restatement(db):
    db.save_snapshot(*make(rows=raw_rows(eps_override={2024: "21.0"})))
    split = {"eventDate": "2025-02-20", "ratio": "10", "kind": "split", "priceCheck": "reflected"}
    # the same old raw filing, plus a later filing that restates FY2024 on the new basis
    rows = [dict(row) for row in raw_rows(eps_override={2024: "21.0"})]
    refiled = [dict(row, value="2.1", filed="2025-03-01") if (row["fiscalYear"] == 2024 and row["metric"] == "EPS Diluted") else row
               for row in rows]
    second = db.save_snapshot(*make(price=moved("3"), rows=refiled, events=[split]))
    link = db.history("US:ACME")[0]
    assert link["snapshotId"] == second["snapshotId"]
    codes = [reason["code"] for reason in link["changeReasons"]]
    assert "share_event_added" in codes and "restated" not in codes and "price_moved" in codes
    assert db.reviews(db.history("US:ACME")[1]["snapshotId"]) == []


def test_a_failure_in_the_link_step_rolls_everything_back(db):
    first = db.save_snapshot(*make())
    with sqlite3.connect(db.path) as conn:
        conn.execute("CREATE TRIGGER fail_link BEFORE INSERT ON price_snapshot_links BEGIN SELECT RAISE(ABORT,'failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        db.save_snapshot(*make(price=moved("32")))
    assert [row["snapshotId"] for row in db.history("US:ACME")] == [first["snapshotId"]]
    with sqlite3.connect(db.path) as conn:
        assert conn.execute("select count(*) from price_snapshots").fetchone()[0] == 1
        assert conn.execute("select count(*) from price_snapshot_reviews").fetchone()[0] == 0


def test_only_the_current_method_version_is_writable_and_inputs_must_be_decimal_text(db):
    inputs, results = make()
    with pytest.raises(PriceStoreError) as error:
        db.save_snapshot({**inputs, "methodVersion": "price-scenario-1"}, results)
    assert error.value.code == "method_version_not_writable"
    with pytest.raises(ValueError):
        db.save_snapshot({**inputs, "price": {**inputs["price"], "value": 30.5}}, results)
    assert not db.path.exists()


def test_criteria_revisions_blank_means_unset_and_conflicts_are_visible(db):
    first = db.save_criteria(required_return="6", min_margin_of_safety="20", holding_years=10)
    assert (first["revisionId"], first["requiredReturn"], first["minMarginOfSafety"], first["holdingYears"]) == (1, "6", "20", 10)
    with pytest.raises(PriceStoreError) as error:
        db.save_criteria(required_return="7", holding_years=10)  # created from a stale view
    assert error.value.code == "revision_conflict"
    cleared = db.save_criteria(holding_years=10, expected_revision_id=1)  # releasing keeps the chosen period
    assert (cleared["requiredReturn"], cleared["minMarginOfSafety"], cleared["holdingYears"]) == (None, None, 10)
    zero = db.save_criteria(required_return="0", min_margin_of_safety="0", holding_years=5, expected_revision_id=2)
    assert (zero["requiredReturn"], zero["minMarginOfSafety"]) == ("0", "0")  # a real zero is not "unset"
    assert db.criteria()["revisionId"] == 3 and db.criteria(1)["requiredReturn"] == "6"


@pytest.mark.parametrize("fields,code,field", [
    ({"required_return": "-99.5", "holding_years": 10}, "out_of_range", "requiredReturn"),
    ({"required_return": "100.1", "holding_years": 10}, "out_of_range", "requiredReturn"),
    ({"required_return": "NaN", "holding_years": 10}, "invalid_number", "requiredReturn"),
    ({"required_return": 6.5, "holding_years": 10}, "invalid_number", "requiredReturn"),
    ({"min_margin_of_safety": "-1", "holding_years": 5}, "out_of_range", "minMarginOfSafety"),
    ({"min_margin_of_safety": "101", "holding_years": 5}, "out_of_range", "minMarginOfSafety"),
    ({"required_return": "6"}, "holding_years_required", "holdingYears"),
    ({"required_return": "6", "holding_years": 7}, "invalid_holding_years", "holdingYears"),
    ({"required_return": "6", "holding_years": True}, "invalid_holding_years", "holdingYears"),
])
def test_criteria_validation_rejects_without_repair(db, fields, code, field):
    with pytest.raises(PriceStoreError) as error:
        db.save_criteria(**fields)
    assert (error.value.code, error.value.field) == (code, field)
    assert db.criteria() is None


def test_boundary_values_are_accepted(db):
    row = db.save_criteria(required_return="-99", min_margin_of_safety="100", holding_years=5)
    assert (row["requiredReturn"], row["minMarginOfSafety"]) == ("-99", "100")
    row = db.save_criteria(required_return="100", min_margin_of_safety="0", holding_years=10, expected_revision_id=row["revisionId"])
    assert row["requiredReturn"] == "100"


def test_overrides_are_appended_per_instrument_with_blank_inheritance(db):
    snapshot = db.save_snapshot(*make())["snapshotId"]
    first = db.save_override("US:ACME", snapshot, growth="0.12", exit_pe="18", payout="0")
    assert (first["growth"], first["exitPE"], first["payout"], first["supersedesOverrideId"]) == ("0.12", "18", "0", None)
    second = db.save_override("US:ACME", snapshot, growth="", exit_pe=None, payout="0.5", expected_override_id=first["overrideId"])
    assert (second["growth"], second["exitPE"], second["payout"], second["supersedesOverrideId"]) == (None, None, "0.5", first["overrideId"])
    assert db.override("US:ACME")["overrideId"] == second["overrideId"] and db.override("US:ACME", first["overrideId"])["growth"] == "0.12"
    with pytest.raises(PriceStoreError) as error:
        db.save_override("US:ACME", snapshot, growth="0.1")  # stale expectation
    assert error.value.code == "revision_conflict"
    cleared = db.save_override("US:ACME", snapshot, expected_override_id=second["overrideId"])  # reset = a new all-blank revision
    assert (cleared["growth"], cleared["exitPE"], cleared["payout"]) == (None, None, None)


@pytest.mark.parametrize("fields,code", [
    ({"growth": "-1"}, "out_of_range"), ({"growth": "-1.5"}, "out_of_range"), ({"growth": "Infinity"}, "invalid_number"),
    ({"exit_pe": "0"}, "out_of_range"), ({"exit_pe": "-3"}, "out_of_range"), ({"payout": "1.01"}, "out_of_range"),
    ({"payout": "-0.01"}, "out_of_range"), ({"growth": 0.1}, "invalid_number")])
def test_override_validation(db, fields, code):
    snapshot = db.save_snapshot(*make())["snapshotId"]
    with pytest.raises(PriceStoreError) as error:
        db.save_override("US:ACME", snapshot, **fields)
    assert error.value.code == code and db.override("US:ACME") is None


def test_override_needs_a_snapshot_of_the_same_instrument(db):
    snapshot = db.save_snapshot(*make())["snapshotId"]
    for instrument, based_on, code in (("US:ACME", "price-missing", "snapshot_not_found"), ("US:OTHER", snapshot, "snapshot_instrument_mismatch")):
        with pytest.raises(PriceStoreError) as error:
            db.save_override(instrument, based_on, growth="0.1")
        assert error.value.code == code


def test_a_new_snapshot_never_rewrites_the_person_layer(db):
    first = db.save_snapshot(*make())["snapshotId"]
    db.save_criteria(required_return="6", holding_years=10)
    override = db.save_override("US:ACME", first, growth="0.1")
    before = db.criteria(), db.override("US:ACME")
    second = db.save_snapshot(*make(price=moved("33")))["snapshotId"]
    assert (db.criteria(), db.override("US:ACME")) == before
    assert db.override("US:ACME")["basedOnSnapshotId"] == first != second and override["overrideId"] == 1


def test_schema_backup_keeps_existing_tables_and_a_newer_schema_is_refused(tmp_path):
    path = tmp_path / "market-memory.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("create table notes(id text)")
        conn.execute("insert into notes values('keep')")
        before = list(conn.iterdump())
    store = PriceStore(path)
    store.save_snapshot(*make())
    backup = next((tmp_path / "backups").glob("*.sqlite3"))
    with sqlite3.connect(backup) as source, sqlite3.connect(tmp_path / "restore.sqlite3") as restored:
        source.backup(restored)
        assert list(restored.iterdump()) == before
    with sqlite3.connect(path) as conn:
        assert conn.execute("select * from notes").fetchall() == [("keep",)]
    store.ensure()  # re-entry is a no-op
    assert len(list((tmp_path / "backups").glob("*.sqlite3"))) == 1
    with sqlite3.connect(path) as conn:
        conn.execute("insert into price_scenario_schema values(?)", (store_module.SCHEMA_VERSION + 1,))
    with pytest.raises(RuntimeError, match="newer_than_runtime"):
        PriceStore(path).ensure()
