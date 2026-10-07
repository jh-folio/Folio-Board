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
def fixture():
    key = uuid4().hex
    root = ROOT / key
    reports = root / "company-analysis"
    reports.mkdir(parents=True)
    original = {"id": "report-a", "company": {"ticker": "ABC", "market": "US"}, "title": "예시기업", "generatedAt": "2026-10-01T00:00:00Z", "markdown": "## 당시 기업 분석\n\n보고서 V1의 가정과 불확실성입니다."}
    (reports / "report-a.json").write_bytes(canonical(original))
    router = create_case_router(root)

    @router.post("/revise")
    def revise():
        (reports / "report-a.json").write_bytes(canonical({**original, "markdown": "## 현재 기업 분석\n\n보고서 V2입니다."}))
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
    return {"prefix": f"/fixtures/{key}"}
