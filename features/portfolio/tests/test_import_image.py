from __future__ import annotations

import shutil

import pytest

from features.portfolio import import_image
from features.portfolio.import_schema import import_preview, normalize_draft


def test_broker_neutral_normalization_defaults_existing_ticker_to_skip():
    row = normalize_draft({"ticker": "nvda", "quantity": "1,250", "averagePrice": "$98.20"}, {"NVDA"})
    assert row["ticker"] == "NVDA"
    assert row["quantity"] == 1250
    assert row["averagePrice"] == 98.2
    assert row["status"] == "confirmed"
    assert row["action"] == "skip"
    assert normalize_draft({"name": "unknown"})["status"] == "unresolved"


def test_preview_never_writes_portfolio_and_temp_is_cleaned(tmp_path, monkeypatch):
    observed = {}
    monkeypatch.setattr(import_image, "validate_image", lambda source, mime_type: None)
    monkeypatch.setattr(import_image, "preprocess_image", lambda source, target: shutil.copyfile(source, target))

    def fake_extract(path):
        observed["directory"] = path.parent
        assert path.exists()
        return ([{"ticker": "SPY", "quantity": 2, "averagePrice": 500}], {"ready": True})

    monkeypatch.setattr(import_image, "extract_local", fake_extract)
    payload = import_image.preview_image(tmp_path, b"not-a-real-image", content_type="image/png")
    assert payload["persisted"] is False
    assert payload["drafts"][0]["ticker"] == "SPY"
    assert not (tmp_path / "portfolio.json").exists()
    assert not observed["directory"].exists()




def test_preview_contract_has_only_normalized_rows_not_raw_ocr():
    payload = import_preview([{"ticker": "005930", "quantity": "10"}], [], engine="fixture")
    serialized = str(payload).lower()
    assert "bounding" not in serialized
    assert "raw_ocr" not in serialized
    assert payload["drafts"][0]["status"] == "needs_review"


@pytest.mark.parametrize("consent", [False, True])
def test_retired_vision_mode_rejected_before_processing(tmp_path, monkeypatch, consent):
    monkeypatch.setattr(import_image, "validate_image", lambda *a, **kw: pytest.fail("image processed"))
    with pytest.raises(ValueError, match="portfolio_image_mode_unsupported"):
        import_image.preview_image(tmp_path, b"image", content_type="image/png", mode="vision", consent=consent)
    assert list(tmp_path.iterdir()) == []
