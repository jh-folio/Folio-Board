"""딥 리서치 초안 이전 단계의 재개 체크포인트.

딥 실행에서 값비싼 것은 쓰기가 아니라 그 앞이다 — 웹 조회(최대 4회), 축 브리프(최대
8회), 논지 선정(1회). 그런데 이 셋은 전부 `build_approved_report()`의 지역 변수라
초안 호출이 죽으면 함께 사라졌다. 실측으로 어댑터 사용량 한도(429)에 걸린 실행이
11분과 성공한 축 브리프를 통째로 버리고 `deep_initial_engine_failed_without_candidate`로
끝났고, 다시 누르면 같은 호출을 처음부터 다시 태워 남은 사용량을 또 먹었다.

여기서는 성공한 단계를 파일로 남겨 **같은 계획을 다시 실행하면 남은 단계부터** 이어
가게 한다. 초안 이후는 이미 `quality_generation/candidate_store.py`가 담당한다.

경계:
- 저장 위치는 `data/job-context/` **밖**이다. 그 폴더는 잡이 종료되는 순간
  `shared_jobs_private.cleanup_owner()`가 통째로 지운다(비공개 pack 계약). 실패한 잡의
  체크포인트를 거기 두면 정확히 필요한 순간에 사라진다.
- 재개는 **같은 계획·같은 기준일·같은 근거**일 때만 성립한다. 근거 팩은 그 시점 자료의
  스냅샷이라, 어제 브리프로 오늘 보고서를 쓰면 어제 자료로 오늘을 말하게 된다.
  지문(fingerprint)이 다르거나 유효기간이 지나면 없는 것으로 본다.
- 성공한 단계만 남긴다. `status != "ok"`인 축 브리프는 저장하지 않아 다음 실행이 그
  축을 다시 시도한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from features.common.atomic_replace import write_bytes_atomic

SCHEMA_VERSION = 1
# 근거 팩의 유효기간. 넘으면 재개하지 않고 처음부터 만든다.
DEFAULT_TTL_HOURS = 24
_KEY = re.compile(r"[A-Za-z0-9_.-]{1,120}")


def ttl_hours() -> int:
    try:
        return max(1, int(os.environ.get("TOPIC_RESUME_TTL_HOURS", DEFAULT_TTL_HOURS)))
    except (TypeError, ValueError):
        return DEFAULT_TTL_HOURS


def resume_key(as_of_date: str, plan_hash: str) -> str:
    """같은 승인 계획의 같은 기준일이면 같은 키.

    `approved_generation_support.py`가 artifact_id로 쓰는 것과 같은 모양이라
    저장물과 재개 파일이 같은 이름으로 묶인다.
    """
    key = f"{str(as_of_date or '').strip()}_{str(plan_hash or '').strip()[:12]}"
    return key if _KEY.fullmatch(key) else ""


def fingerprint(
    *,
    plan_hash: str,
    as_of_date: str,
    selected_evidence_ids: Sequence[str],
    adapter: str,
    requested_mode: str,
    task_policy: dict | None = None,
    input_snapshot: dict | None = None,
) -> str:
    """재개가 성립하는 조건. 하나라도 다르면 이어 쓰지 않는다."""
    payload = json.dumps(
        {
            "inputSnapshot": input_snapshot,
            "planHash": str(plan_hash or ""),
            "asOfDate": str(as_of_date or ""),
            "evidence": [str(row or "") for row in selected_evidence_ids],
            "adapter": str(adapter or ""),
            "requestedMode": str(requested_mode or ""),
            # A continuation may reuse expensive intermediate stages only when
            # it was accepted under the same task configuration.  Store the
            # secret-free request fields; credentials never enter a resume
            # file.
            "taskPolicy": {
                "taskKey": str((task_policy or {}).get("taskKey") or ""),
                "source": str((task_policy or {}).get("source") or ""),
                "mode": str((task_policy or {}).get("mode") or ""),
                "provider": str((task_policy or {}).get("provider") or ""),
                "model": str((task_policy or {}).get("model") or ""),
                "reasoningEffort": str((task_policy or {}).get("reasoningEffort") or "provider_default"),
                "policyRevision": int((task_policy or {}).get("policyRevision") or 0),
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResumeStore:
    """단계별 체크포인트 하나를 읽고 쓴다. 실패가 생성을 죽이지 않는다."""

    def __init__(self, root: Path, *, key: str, fingerprint: str) -> None:
        self.root = root.resolve()
        self.key = key
        self.fingerprint = fingerprint
        self._state: dict | None = None

    @property
    def enabled(self) -> bool:
        return bool(_KEY.fullmatch(self.key) and self.key not in {".", ".."} and self.fingerprint)

    def _path(self) -> Path:
        return self.root / f"{self.key}.json"

    def _fresh(self, state: dict) -> bool:
        if state.get("schemaVersion") != SCHEMA_VERSION:
            return False
        if str(state.get("fingerprint") or "") != self.fingerprint:
            return False
        try:
            updated = datetime.fromisoformat(str(state.get("updatedAt") or "").replace("Z", "+00:00"))
        except ValueError:
            return False
        age = (datetime.now(UTC) - updated.astimezone(UTC)).total_seconds()
        return 0 <= age <= ttl_hours() * 3600

    def load(self) -> dict:
        """재개 가능한 단계들. 없거나 못 믿으면 빈 dict."""
        if self._state is not None:
            return self._state
        self._state = {}
        if not self.enabled:
            return self._state
        try:
            raw = self._path().read_text(encoding="utf-8")
            state = json.loads(raw)
        except (OSError, ValueError):
            return self._state
        if not isinstance(state, dict) or not self._fresh(state):
            return self._state
        stages = state.get("stages")
        self._state = stages if isinstance(stages, dict) else {}
        return self._state

    def web_lookups(self) -> list[dict]:
        rows = self.load().get("webLookups")
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def axis_briefs(self) -> list[dict]:
        rows = self.load().get("axisBriefs")
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def thesis(self) -> dict:
        row = self.load().get("thesis")
        return dict(row) if isinstance(row, dict) and row else {}

    def _write(self, stages: dict) -> None:
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "fingerprint": self.fingerprint,
            "key": self.key,
            "updatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "stages": stages,
        }
        write_bytes_atomic(
            self._path(),
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        )

    def _merge(self, stage: str, value) -> None:
        # 체크포인트 저장 실패가 생성을 죽이지 않는다. 못 남기면 다음 실행이 그 단계를
        # 다시 할 뿐이고, 그건 지금과 같은 동작이다.
        if not self.enabled:
            return
        try:
            stages = dict(self.load())
            stages[stage] = value
            self._state = stages
            self._write(stages)
        except (OSError, ValueError, TypeError):
            return

    def put_web_lookup(self, lookup: dict) -> None:
        """축 하나의 조회 결과. 축 단위로 남겨야 중간에 끊겨도 앞부분이 산다."""
        if lookup.get("status") != "ok":
            return
        rows = [row for row in self.web_lookups() if row.get("axisKey") != lookup.get("axisKey")]
        self._merge("webLookups", [*rows, dict(lookup)])

    def put_axis_brief(self, brief: dict) -> None:
        if str(brief.get("status") or "") != "ok":
            return
        rows = [row for row in self.axis_briefs() if row.get("axisKey") != brief.get("axisKey")]
        self._merge("axisBriefs", [*rows, dict(brief)])

    def put_thesis(self, thesis: dict) -> None:
        if thesis:
            self._merge("thesis", dict(thesis))

    def clear(self) -> None:
        if not self.enabled:
            return
        try:
            self._path().unlink(missing_ok=True)
        except OSError:
            return
        self._state = {}


def prune(root: Path) -> int:
    """유효기간이 지난 재개 파일 제거. 남겨 두면 쓰이지도 않으면서 쌓인다."""
    removed = 0
    cutoff = ttl_hours() * 3600
    try:
        entries = list(root.glob("*.json"))
    except OSError:
        return 0
    for path in entries:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            updated = datetime.fromisoformat(
                str(state.get("updatedAt") or "").replace("Z", "+00:00")
            )
            stale = (datetime.now(UTC) - updated.astimezone(UTC)).total_seconds() > cutoff
        except (OSError, ValueError, AttributeError):
            stale = True
        if stale:
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except OSError:
                continue
    return removed
