"""화면 스냅샷을 만드는 서비스 조립을 한 곳에 둔다.

**버튼과 사전작업이 같은 라이프사이클을 타야 한다.** 예전에는 라우터만
`MarketStateHttpService`를 조립하고 사전작업은 `run_llm_market_state_snapshot()`으로
바로 저장해서, 자동으로 만들어진 스냅샷에는 attempt/watermark 메타가 없었다 —
reconcile이 볼 것이 없으니 중단된 갱신을 복구할 수도 없다.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from features.market_memory.http_service import (
    MarketStateHttpRuntime,
    MarketStateHttpService,
    MarketStateStorage,
)


def create_market_state_service(data_dir: Path) -> MarketStateHttpService:
    from features.market_memory.llm_snapshot_backend import LlmManualSnapshotBackend

    storage = MarketStateStorage.from_data_dir(Path(data_dir))
    clock = lambda: datetime.now(UTC)
    backend = LlmManualSnapshotBackend(storage.marketDbPath, clock)
    return MarketStateHttpService(MarketStateHttpRuntime(storage, clock, backend, lambda _boundary: None))
