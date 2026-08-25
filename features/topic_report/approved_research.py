from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from features.agent_mode.market_state_context import (
    MarketStateProjection,
    MarketStateSelection,
    project_market_state,
)
from features.common.jcs import JsonValue
from features.common.research_library.indexing.research_index import hybrid_search
from features.common.research_library.search.filters import drop_press_releases
from features.common.research_library.search.multi_query import fuse_search_results
from features.market_memory.attempt_store import AttemptStore
from features.market_memory.market_state_ref import MarketStateRefQuery
from features.smart_collections.integration import resolve_approved_collection
from features.smart_collections.service import SmartCollectionService
from features.topic_report.approved_schema import ApprovedRequest
from features.topic_report.evidence import build_evidence_pack
from features.topic_report.resolution_schema import ResolutionSnapshotV1


_NEWS_PREFIXES = ("research-inbox/articles/", "research-inbox/rss/")

type EvidenceRow = dict[str, JsonValue]
type EvidenceSearch = Callable[[list[str], int, set[str] | None], list[EvidenceRow]]
type MemorySearch = Callable[[list[str], int], list[EvidenceRow]]


@dataclass(frozen=True, slots=True)
class PreparedResearch:
    resolution: ResolutionSnapshotV1
    evidencePack: Mapping[str, JsonValue]

    @property
    def evidence_items(self) -> list[EvidenceRow]:
        raw = self.evidencePack.get("items")
        return [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _search_index(
    data_dir: Path,
    queries: list[str],
    limit: int,
    allowed_doc_ids: set[str] | None,
    cache: dict | None = None,
) -> list[EvidenceRow]:
    """질의별로 검색해 RRF로 합친다.

    예전에는 질의를 공백으로 이어 붙여 한 번만 검색했다. FTS5가 토큰을 OR로 풀기
    때문에 어느 한 토큰만 스친 문서가 상위로 올라왔고, 그래서 축 전용 검색어가
    자기 몫의 자료를 데려오지 못했다. 보도자료는 근거에서 뺀다 — 발행처가 1곳뿐인
    정기 공시가 주제 리서치의 상위 근거로 올라오는 것을 실제로 봤다.
    """

    memo = cache if cache is not None else {}

    def run_one(query: str, per_query_limit: int) -> list[EvidenceRow]:
        # 하위 질문과 축이 같은 검색어를 공유한다(공통 질의는 돌려 쓰고, 축 검색어는
        # 그 축의 질문과 같다). 팩 하나를 만드는 동안 같은 질의를 여러 번 돌리지 않는다.
        key = (query, per_query_limit)
        if key not in memo:
            rows = hybrid_search(
                data_dir / "research-index.sqlite3",
                query,
                limit=per_query_limit,
                scope_prefixes=_NEWS_PREFIXES,
                allowed_doc_ids=allowed_doc_ids,
            )
            memo[key] = drop_press_releases([dict(row) for row in rows])
        return [dict(row) for row in memo[key]]

    cap = max(0, int(limit or 0))
    return fuse_search_results(
        [str(item).strip() for item in queries if str(item).strip()],
        run_one,
        limit=cap,
        per_query_limit=max(cap, 12),
    )


def _search_memory(data_dir: Path, keywords: list[str], limit: int) -> list[EvidenceRow]:
    try:
        from features.market_memory.memory import list_memory

        rows = list_memory(data_dir / "market-memory.sqlite3", limit=100)
    except (sqlite3.DatabaseError, OSError, ValueError):
        return []
    tokens = [str(item).strip().casefold() for item in keywords if str(item).strip()]
    if not tokens:
        return [dict(row) for row in rows[:limit]]
    matched = []
    for row in rows:
        text = " ".join(
            str(row.get(key) or "")
            for key in ("title", "summary", "storyThesis", "story", "storyFamily")
        ).casefold()
        score = sum(token in text for token in tokens)
        if score:
            matched.append((score, dict(row)))
    matched.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in matched[:limit]]


def admit_research(
    approved: ApprovedRequest,
    base_resolution: ResolutionSnapshotV1,
    *,
    search_docs: EvidenceSearch,
    search_memories: MemorySearch,
) -> PreparedResearch:
    allowed = (
        set(base_resolution.executionUniverseIds)
        if base_resolution.collectionId is not None
        else None
    )

    def constrained_search(queries: list[str], limit: int) -> list[EvidenceRow]:
        rows = search_docs(queries, limit, allowed)
        if allowed is None:
            return rows
        return [
            row
            for row in rows
            if str(row.get("id") or row.get("documentId") or "") in allowed
        ]

    pack = build_evidence_pack(
        approved.topicPlan.model_dump(mode="json"),
        search_docs=lambda queries, limit=12: constrained_search(list(queries), limit),
        search_memories=lambda keywords, limit=20: search_memories(list(keywords), limit),
        date=approved.asOfDate,
        deep_research=approved.deepResearch,
    )
    raw_items = pack.get("items")
    items = raw_items if isinstance(raw_items, list) else []
    selected = [
        str(item.get("documentId"))
        for item in items
        if isinstance(item, dict) and str(item.get("documentId") or "")
    ]
    if len(selected) != len(set(selected)):
        raise ValueError("duplicate_selected_evidence")
    if allowed is not None and not set(selected).issubset(allowed):
        raise ValueError("evidence_outside_collection")
    resolution = base_resolution.model_copy(update={"selectedEvidenceIds": selected})
    return PreparedResearch(resolution=resolution, evidencePack=pack)


def prepare_approved_research(
    data_dir: Path,
    collections: SmartCollectionService,
    approved: ApprovedRequest,
) -> PreparedResearch:
    base = resolve_approved_collection(collections, approved)
    query_cache: dict = {}
    return admit_research(
        approved,
        base,
        search_docs=lambda queries, limit, allowed: _search_index(
            data_dir,
            queries,
            limit,
            allowed,
            query_cache,
        ),
        search_memories=lambda keywords, limit: _search_memory(data_dir, keywords, limit),
    )


def prepare_market_state(
    data_dir: Path,
    approved: ApprovedRequest,
    clock: Callable[[], datetime],
) -> MarketStateProjection:
    collection_market = (
        approved.collectionRef.definitionSnapshot.market
        if approved.collectionRef is not None
        else None
    )
    selection = MarketStateSelection(
        policy=approved.marketStatePolicy,
        requested_scope=approved.marketStateScope,
        regions=tuple(approved.topicPlan.regions),
        collection_market=collection_market,
    )
    attempts: tuple[Mapping[str, JsonValue], ...] = ()
    if approved.marketStatePolicy == "include_current":
        state = AttemptStore(data_dir / "market-state-update-attempts.json").load()
        attempts = tuple(item.model_dump(mode="json") for item in state.attempts)
    query = MarketStateRefQuery(
        market_db_path=data_dir / "market-memory.sqlite3",
        research_db_path=data_dir / "research-index.sqlite3",
        scope="GLOBAL",
        now=clock(),
        failed_attempts=attempts,
    )
    return project_market_state(selection, query)
