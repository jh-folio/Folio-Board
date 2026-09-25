from __future__ import annotations

import pytest
from fastapi import HTTPException

import app
from features.investment_review.review_v2 import ReviewRevisionConflict
from features.investment_review.schema import empty_review


def test_explicit_portfolio_rules_refresh_ignores_global_cli_default(monkeypatch):
    monkeypatch.setattr(app, "request_generation_mode", lambda _body: "llm_cli")
    monkeypatch.setattr(app, "submit_agent_task", lambda *_args, **_kwargs: pytest.fail("rules refresh must not submit CLI job"))
    seen = {}
    def generate(body):
        seen["body"] = body
        return {"reviewRevision": 1}
    monkeypatch.setattr(app, "generate_investment_review", generate)
    result = app.api_investment_review_generate({"generationMode": "rules"})
    assert result["reviewRevision"] == 1
    assert seen["body"]["useLlm"] is False


def test_rules_refresh_conflict_is_http_409_with_latest(monkeypatch):
    latest = empty_review("2026-09-01")
    monkeypatch.setattr(app, "generate_investment_review", lambda _body: (_ for _ in ()).throw(ReviewRevisionConflict(latest)))
    with pytest.raises(HTTPException) as raised:
        app.api_investment_review_generate({"generationMode": "rules", "date": "2026-09-01"})
    assert raised.value.status_code == 409
    assert raised.value.detail["code"] == "investment_review_revision_conflict"
    assert raised.value.detail["latest"] == latest
