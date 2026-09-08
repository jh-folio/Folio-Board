from __future__ import annotations

from features.common.diagnostics.routes import create_diagnostics_router
from features.common.diagnostics.runtime import DiagnosticsRuntime
from features.common.diagnostics.schema import new_context, run_id_for_job
from features.common.shared_jobs_schema import JobStatus


class _Job:
    def __init__(self, job_id: str, status: JobStatus) -> None:
        self.id = job_id
        self.status = status


def test_headless_detail_distinguishes_unknown_run_from_known_job_without_record(tmp_path):
    runtime = DiagnosticsRuntime(tmp_path)
    job_id = "job_" + new_context(feature_code="jobs", route_code="shared_worker", authority_kind="shared_job").run_id[4:]
    router = create_diagnostics_router(runtime_provider=lambda: runtime, job_lookup=lambda value: _Job(job_id, JobStatus.DONE) if value == job_id else None)
    get_run = next(route.endpoint for route in router.routes if route.path == "/api/diagnostics/runs/{run_id}")
    get_job = next(route.endpoint for route in router.routes if route.path == "/api/diagnostics/jobs/{job_id}")
    from fastapi import HTTPException
    try:
        get_run("run_00000000-0000-4000-8000-000000000000")
    except HTTPException as error:
        assert error.status_code == 404
    else:
        raise AssertionError("unknown run must be 404")
    assert get_job(job_id)["availabilityReason"] == "missing_unknown"
    runtime.close()


def test_headless_detail_uses_current_job_authority_without_private_job_data(tmp_path):
    runtime = DiagnosticsRuntime(tmp_path)
    context = new_context(feature_code="jobs", route_code="shared_worker", authority_kind="shared_job", job_id="job_" + new_context(feature_code="jobs", route_code="shared_worker", authority_kind="shared_job").run_id[4:])
    recorder = runtime.store.start(context)
    assert recorder is not None and recorder.finish("failed")
    job = _Job(context.job_id or "", JobStatus.FAILED)
    router = create_diagnostics_router(runtime_provider=lambda: runtime, job_lookup=lambda value: job if value == job.id else None)
    get_job = next(route.endpoint for route in router.routes if route.path == "/api/diagnostics/jobs/{job_id}")
    payload = get_job(job.id)
    assert payload["version"] == 1
    assert payload["authorityState"] == "matched"
    assert payload["runId"] == run_id_for_job(job.id)
    runtime.close()
