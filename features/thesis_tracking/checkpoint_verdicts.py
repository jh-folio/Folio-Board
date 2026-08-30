"""thesis 구조화 체크포인트 판정 — 근거 풀은 **연구 인덱스 문서**다.

내러티브와 같은 pass·같은 스키마이고 판정 코어(`evaluate_checkpoint`·`apply_verdict`)
를 그대로 재사용한다. 다른 것은 근거 풀 하나다.

- 풀은 `search_documents(company=ticker, scope="news")` — Thesis Delta와 워치리스트
  뉴스가 이미 쓰는 그 풀이다. `market_memory` 행을 보조로 섞지 않는다(계획 A.2 결정):
  두 풀을 합치면 어느 풀이 판정했는지 설명할 수 없다.
- **문서 풀에는 role 분류가 없다.** 그래서 `role_pool=False`로 부르고 체크포인트의
  `direction`이 판정 방향을 정한다. 근거 사본 키도 `memoryId`가 아니라 `docId`이며
  `role`을 넣지 않는다 — 분류가 없다는 사실을 숨기지 않는다.
- **구조화 체크포인트가 0건이면 인덱스를 열지 않는다.** `load_index()`는 실측 4.7초라
  수집 자동화 경로에서 공짜가 아니다. 오늘 thesis는 0행이므로 이 gate 덕에 기본
  비용이 0이다.

판정 이력은 체크포인트 dict 안의 `history` 배열이다(상한 20). 새 테이블을 만들지 않는다.
"""
from __future__ import annotations

import datetime as dt

from features.common.research_schema.tracked_checkpoints import (
    normalize_tracked_checkpoint,
    partition_checkpoints,
)
from features.market_memory.checkpoint_verdicts import apply_verdict, evaluate_checkpoint

# 판정 대상 상태 — 닫힌 thesis는 확인할 것이 없다.
JUDGED_STATUSES = ("active", "watch")
DOC_POOL_LIMIT = 200
MAX_MATCHED_TERMS = 12


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _doc_id(doc: dict) -> str:
    return str(doc.get("path") or doc.get("url") or doc.get("id") or "")


def _matched_terms(doc: dict) -> list:
    """ticker matcher가 볼 수 있는 것 — 문서에 붙은 회사 태그와 주제 태그.

    본문에서 티커를 찾지 않는 규칙(`matches_checkpoint`)이 여기에도 그대로 걸린다.
    """
    terms: list = []
    for company in doc.get("companies") or []:
        for value in (company.get("ticker"), company.get("name")):
            text = str(value or "").strip()
            if text and text not in terms:
                terms.append(text)
    for tag in (doc.get("impactTags") or []) + (doc.get("sectors") or []):
        text = str(tag or "").strip()
        if text and text not in terms:
            terms.append(text)
    return terms[:MAX_MATCHED_TERMS]


def _tagged_with(doc: dict, ticker: str, company: str) -> bool:
    """그 회사 **태그가 붙은** 문서만 남긴다.

    `search_documents`의 회사 필터는 태그가 안 맞으면 제목·본문 부분일치로 물러서는데,
    두 글자 티커에서는 그것이 남의 기사를 잔뜩 물어 온다(`MU`가 "무역"에 걸리는 식).
    워치리스트가 배운 것과 같은 규칙 — 연결 열쇠는 종목 코드다.
    """
    from features.common.company_lookup import company_matches_query

    for tagged in doc.get("companies") or []:
        if ticker and company_matches_query(tagged, ticker):
            return True
        if company and company_matches_query(tagged, company):
            return True
    return False


def thesis_evidence_rows(index, thesis: dict, *, limit: int = DOC_POOL_LIMIT) -> list:
    """그 thesis 종목의 뉴스 문서를 판정 코어가 읽는 행 모양으로 만든다."""
    from features.common.research_library.search.service import search_documents

    ticker = str(thesis.get("ticker") or "").strip()
    company = str(thesis.get("company") or "").strip()
    query_company = ticker or company
    if not query_company:
        return []
    docs = search_documents(index, company=query_company, limit=limit, scope="news")
    rows: list = []
    for doc in docs:
        if not _tagged_with(doc, ticker, company):
            continue
        doc_id = _doc_id(doc)
        if not doc_id:
            continue
        rows.append({
            "docId": doc_id,
            "evidenceDate": str(doc.get("date") or "")[:10],
            "title": str(doc.get("title") or ""),
            "summary": str(doc.get("summary") or doc.get("searchSnippet") or ""),
            "matchedTerms": _matched_terms(doc),
        })
    return rows


def _rewrite(stored: list, updated: dict, *, ticker: str, as_of: str) -> list:
    """바뀐 원소만 제자리 교체 — 검증 실패 dict·템플릿·순서는 그대로 남는다."""
    rewritten: list = []
    for element in stored:
        if isinstance(element, dict):
            normalized = normalize_tracked_checkpoint(
                element, scope="thesis", scope_key=ticker, now=as_of
            )
            if normalized and normalized["id"] in updated:
                rewritten.append(updated.pop(normalized["id"]))
                continue
        rewritten.append(element)
    return rewritten


def run_thesis_checkpoint_verdicts(db_path=None, *, as_of: str = "", index_loader=None) -> dict:
    """thesis 구조화 체크포인트를 판정한다. 대상이 없으면 인덱스를 열지 않는다."""
    from features.thesis_tracking import store

    as_of = as_of or _now()
    conn = store.connect(db_path)
    try:
        theses = [t for t in store.list_theses(conn) if t.get("status") in JUDGED_STATUSES]
        targets: list = []
        for thesis in theses:
            ticker = str(thesis.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            structured, _invalid, _templates = partition_checkpoints(
                thesis.get("next_checkpoints"), scope="thesis", scope_key=ticker, now=as_of
            )
            if structured:
                targets.append((thesis, ticker, structured))
        if not targets:
            # 0건 gate — 여기서 끝난다. load_index를 부르지 않는다.
            return {
                "ok": True, "asOf": as_of, "indexLoaded": False,
                "thesisCount": 0, "checkpointCount": 0, "changeCount": 0, "results": [],
            }

        if index_loader is None:
            from features.common.research_library.indexing.service import load_index as index_loader
        index = index_loader()

        results: list = []
        for thesis, ticker, structured in targets:
            evidence_rows = thesis_evidence_rows(index, thesis)
            changes: list = []
            verdicts: list = []
            updated: dict = {}
            for checkpoint in structured:
                outcome = evaluate_checkpoint(checkpoint, evidence_rows, as_of=as_of, role_pool=False)
                result = apply_verdict(checkpoint, outcome, as_of=as_of)
                verdicts.append({
                    "checkpointId": checkpoint["id"],
                    "item": checkpoint["item"],
                    "verdict": outcome["verdict"],
                    "status": checkpoint["status"],
                })
                if result["changed"]:
                    updated[checkpoint["id"]] = checkpoint
                    changes.append({"checkpointId": checkpoint["id"], **result})
            if updated:
                store.save_thesis_checkpoints(
                    conn, ticker,
                    _rewrite(thesis.get("next_checkpoints") or [], updated, ticker=ticker, as_of=as_of),
                )
            results.append({
                "ticker": ticker,
                "evaluated": len(structured),
                "evidenceCount": len(evidence_rows),
                "changes": changes,
                "verdicts": verdicts,
            })
        return {
            "ok": True,
            "asOf": as_of,
            "indexLoaded": True,
            "thesisCount": len(results),
            "checkpointCount": sum(item["evaluated"] for item in results),
            "changeCount": sum(len(item["changes"]) for item in results),
            "results": results,
        }
    finally:
        conn.close()
