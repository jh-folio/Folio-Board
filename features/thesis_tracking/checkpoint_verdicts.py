"""thesis 구조화 체크포인트 판정 — 근거 풀은 **연구 인덱스 문서**다.

내러티브와 같은 pass·같은 스키마이고 판정 코어(`evaluate_checkpoint`·`apply_verdict`)
를 그대로 재사용한다. 다른 것은 근거 풀 하나다.

- 풀은 그 종목 **태그가 붙은** 뉴스 문서를 **날짜순**으로 모은다. `search_documents`의
  브라우즈 경로는 관련도 점수순 상위 200건이라, 보도가 많은 종목(실측 GOOGL 9,387건
  태그)에서는 이번 주 기사가 상한 밖으로 잘려 판정이 영영 `no_signal`이 된다 —
  워치리스트가 이미 문서화한 바로 그 버그("검색 상위 200건 안에서만 세어 AMD가
  297건인데 69건으로 나왔다"). 판정은 컷오프 이후의 문서만 보므로 풀도 컷오프
  이후만 담으면 상한이 필요 없다.
- `market_memory` 행을 보조로 섞지 않는다(계획 A.2 결정): 두 풀을 합치면 어느 풀이
  판정했는지 설명할 수 없다.
- **문서 풀에는 role 분류가 없다.** `role_pool=False`로 부르고 체크포인트의
  `direction`이 판정 방향을 정한다. 근거 사본 키는 `docId`이며 `role`을 넣지 않는다.
  `docId`는 **URL 우선**이다 — 파일 경로는 RSS 보관 기간 정리가 지우고 재수집이
  다시 만드는 값이라, 30일 뒤 사본이 아무것도 가리키지 못한다.
- **회사명·티커는 매칭 재료가 아니다.** 풀이 이미 그 종목이라 회사 태그를 haystack에
  넣으면 회사명 keyword가 모든 기사에 걸려 매일 confirmed가 된다. 그래서 행에
  matchedTerms를 싣지 않고(haystack = 제목+요약), validator에도 티커·회사명을
  금지어로 넘긴다.
- **구조화 체크포인트가 0건이면 인덱스를 열지 않는다.** `load_index()`는 실측 4.7초라
  수집 자동화 경로에서 공짜가 아니다. 오늘 thesis는 0행이므로 이 gate 덕에 기본
  비용이 0이다.

판정 이력은 체크포인트 dict 안의 `history` 배열이다(상한 20). 새 테이블을 만들지 않는다.
"""
from __future__ import annotations

import datetime as dt

from features.common.research_schema.tracked_checkpoints import (
    partition_checkpoints,
    rewrite_checkpoints,
)
from features.market_memory.checkpoint_verdicts import apply_verdict, evaluate_checkpoint

# 판정 대상 상태 — 닫힌 thesis는 확인할 것이 없다.
JUDGED_STATUSES = ("active", "watch")
# 컷오프 이후 문서가 비정상적으로 많아도 판정 비용이 폭주하지 않게 하는 안전판.
# 날짜순이라 잘리는 것은 가장 오래된 쪽이다(관련도순 상한과 달리 최신이 안 잘린다).
DOC_POOL_CAP = 500


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _doc_id(doc: dict) -> str:
    # URL 우선 — 경로는 보관 기간 정리(retention)가 지운다.
    return str(doc.get("url") or doc.get("path") or doc.get("id") or "")


def _forbidden_terms(thesis: dict) -> list:
    """티커·회사명은 keyword가 될 수 없다 — 풀이 이미 그 종목이라 전부 매칭된다."""
    return [thesis.get("ticker"), thesis.get("company")]


def _tagged_with(doc: dict, ticker: str, company: str) -> bool:
    """그 회사 **태그가 붙은** 문서만 남긴다.

    제목·본문 부분일치로 물러서지 않는다 — 두 글자 티커에서는 그것이 남의 기사를
    잔뜩 물어 온다(`MU`가 "무역"에 걸리는 식). 연결 열쇠는 종목 코드다(워치리스트 규칙).
    """
    from features.common.company_lookup import company_matches_query

    for tagged in doc.get("companies") or []:
        if not isinstance(tagged, dict):
            continue
        if ticker and company_matches_query(tagged, ticker):
            return True
        if company and company_matches_query(tagged, company):
            return True
    return False


def earliest_cutoff_date(checkpoints: list) -> str:
    """판정이 실제로 볼 수 있는 가장 이른 근거 날짜. 풀을 이 날짜 이후로 좁힌다."""
    dates = []
    for checkpoint in checkpoints or []:
        last = (checkpoint.get("lastVerdict") or {}).get("at")
        dates.append(str(last or checkpoint.get("createdAt") or "")[:10])
    valid = [d for d in dates if len(d) == 10]
    return min(valid) if valid else ""


def thesis_evidence_rows(index, thesis: dict, *, since: str = "", cap: int = DOC_POOL_CAP) -> list:
    """그 thesis 종목의 뉴스 문서를 판정 코어가 읽는 행 모양으로 만든다.

    인덱스를 직접 훑어 **태그 일치 + 날짜 필터**로 모으고 날짜순으로 정렬한다.
    관련도 점수는 쓰지 않는다 — 판정에서 신선도가 관련도를 이긴다.
    """
    # search/service.py가 쓰는 것과 같은 news 판정을 쓴다(scope="news"와 동일 경계).
    from features.daily_briefing.service import is_news_document

    ticker = str(thesis.get("ticker") or "").strip()
    company = str(thesis.get("company") or "").strip()
    if not (ticker or company):
        return []
    rows: list = []
    for doc in (index or {}).get("documents") or []:
        if not is_news_document(doc):
            continue
        date = str(doc.get("date") or "")[:10]
        if since and date and date < since:
            continue
        if not _tagged_with(doc, ticker, company):
            continue
        doc_id = _doc_id(doc)
        if not doc_id:
            continue
        rows.append({
            "docId": doc_id,
            "evidenceDate": date,
            "title": str(doc.get("title") or ""),
            "summary": str(doc.get("summary") or doc.get("searchSnippet") or ""),
            # matchedTerms를 싣지 않는다 — 회사 태그가 haystack에 들어가면 회사명
            # keyword가 모든 기사에 걸린다(모듈 docstring).
        })
    rows.sort(key=lambda row: row["evidenceDate"], reverse=True)
    return rows[:cap]


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
                thesis.get("next_checkpoints"), scope="thesis", scope_key=ticker,
                forbidden_keywords=_forbidden_terms(thesis), now=as_of,
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
            try:
                results.append(
                    _judge_one_thesis(conn, store, index, thesis, ticker, structured, as_of=as_of)
                )
            except Exception as exc:  # noqa: BLE001 - thesis 하나가 나머지 판정을 막지 않는다
                results.append({"ticker": ticker, "error": type(exc).__name__, "evaluated": 0, "changes": [], "verdicts": []})
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


def _judge_one_thesis(conn, store, index, thesis: dict, ticker: str, structured: list, *, as_of: str) -> dict:
    evidence_rows = thesis_evidence_rows(index, thesis, since=earliest_cutoff_date(structured))
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
            rewrite_checkpoints(
                thesis.get("next_checkpoints"), updated, scope="thesis", scope_key=ticker,
                forbidden_keywords=_forbidden_terms(thesis), now=as_of,
            ),
        )
    return {
        "ticker": ticker,
        "evaluated": len(structured),
        "evidenceCount": len(evidence_rows),
        "changes": changes,
        "verdicts": verdicts,
    }
