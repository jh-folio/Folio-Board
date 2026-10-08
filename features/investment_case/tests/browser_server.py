"""Disposable local browser fixtures. Never imports the operating app/config."""
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Body

from features.investment_case.routes import create_case_router, call
from features.investment_case.deletion import delete_source
from features.investment_case.deletion import source_delete_preview
from features.investment_case.paths import canonical
from features.agent_mode.report_delete import DeleteRequest, execute_report_delete

app = FastAPI()
ROOT = Path(tempfile.mkdtemp(prefix="folio-011-browser-"))


@app.post("/fixture")
def fixture(ownership: bool = False):
    key = uuid4().hex
    root = ROOT / key
    reports = root / "company-analysis"
    reports.mkdir(parents=True)
    original = {"id": "report-a", "company": {"ticker": "ABC", "market": "US"}, "title": "예시기업", "generatedAt": "2026-10-01T00:00:00Z", "markdown": "## 당시 기업 분석\n\n보고서 V1의 가정과 불확실성입니다."}
    (reports / "report-a.json").write_bytes(canonical(original))
    first_journal = None
    if ownership:
        from features.decision_readiness.tests.test_capture import seeded
        from features.thesis_tracking import store as thesis_store
        from features.thesis_tracking.model import Thesis
        from features.investment_case import service
        price = seeded(root, "ABC")
        with thesis_store.connect(price.path) as conn:
            thesis_store.upsert_thesis(conn, Thesis(ticker="ABC", core_thesis="반복 매출이 안정적으로 이어질 것", falsification_triggers=["현금 전환이 악화될 때"]), edit_source="manual")
            conn.commit()
        for action, revision in (("create", 0), ("journal", 1)):
            proposal = service.preview(root, {"instrumentId": "US:ABC", "expectedCaseRevision": revision, "action": action, "decisionText": "최초 결정의 불확실성도 남김"})
            first_journal = service.confirm(root, proposal["token"], uuid4().hex).get("journalId")
    router = create_case_router(root)

    @router.post("/revise")
    def revise():
        (reports / "report-a.json").write_bytes(canonical({**original, "markdown": "## 현재 기업 분석\n\n보고서 V2입니다."}))
        return {"ok": True}

    @router.post("/revise-reason")
    def revise_reason():
        from features.thesis_tracking import store as thesis_store
        from features.thesis_tracking.model import Thesis
        with thesis_store.connect(root / "market-memory.sqlite3") as conn:
            thesis_store.upsert_thesis(conn, Thesis(ticker="ABC", core_thesis="변경한 이유", falsification_triggers=["현금 전환의 새 조건"]), edit_source="manual")
            conn.commit()
        return {"ok": True}

    @router.post("/block-source")
    def block_source():
        (reports / "report-a.json").write_bytes(canonical({**original, "markdown": "Source stored at C:/private/research.md"}))
        return {"ok": True}

    @router.post("/new-report")
    def new_report():
        (reports / "report-b.json").write_bytes(canonical({**original, "id": "report-b", "generatedAt": "2026-10-07T08:00:00Z", "markdown": "새 정정 자료 B"}))
        return {"ok": True}

    @router.post("/interrupt-source-delete")
    def interrupt_delete():
        proposal = source_delete_preview(root, {"kind": "company", "id": "report-a"})
        operation = uuid4().hex
        try:
            delete_source(root, "company", "report-a", token=proposal["token"], operation_id=operation, fault="source:unlinked")
        except RuntimeError:
            pass
        (reports / "report-a.json").write_bytes(canonical({**original, "markdown": "새 원본 유지"}))
        return {"operationId": operation}

    @router.delete("/api/analysis-reports/{report_id}")
    def remove(report_id: str, confirmationToken: str | None = None, operationId: str | None = None):
        def fallback():
            outcome = execute_report_delete(DeleteRequest(root=reports, identity=f"company:{report_id}", primary_names=(f"{report_id}.json",), target_names=(f"{report_id}.json",)))
            return {"deleted": outcome.deleted, "id": report_id}
        return call(delete_source, root, "company", report_id, token=confirmationToken, operation_id=operationId, fallback=fallback)

    app.include_router(router, prefix=f"/fixtures/{key}")
    return {"prefix": f"/fixtures/{key}", "originalJournalId": first_journal}
