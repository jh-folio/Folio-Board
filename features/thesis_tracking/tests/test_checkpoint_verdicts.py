"""thesis 체크포인트 판정 — 근거 풀은 연구 인덱스 문서다.

    py -3 -m pytest features/thesis_tracking/tests/test_checkpoint_verdicts.py -q

실제 인덱스도 네트워크도 열지 않는다 — 인덱스 로더와 검색을 스텁으로 넣는다.
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from features.common.research_library.search import service as search_service
from features.thesis_tracking import checkpoint_verdicts as CV
from features.thesis_tracking import model as M
from features.thesis_tracking import store

AS_OF = "2026-08-30T00:00:00+00:00"
TICKER = "NVDA"


def _checkpoint(**overrides):
    base = {
        "item": "데이터센터 매출 가이던스 상향",
        "direction": "supporting",
        "matchers": {"tickers": [TICKER], "keywords": ["가이던스 상향"]},
        "status": "open",
        "createdAt": "2026-08-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def _doc(**overrides):
    base = {
        "path": "research-inbox/rss/2026-08-20-nvda.md",
        "date": "2026-08-20",
        "title": "엔비디아, 데이터센터 가이던스상향",
        "summary": "다음 분기 전망을 올렸다.",
        "companies": [{"ticker": TICKER, "name": "NVIDIA"}],
        "impactTags": ["AI"],
    }
    base.update(overrides)
    return base


def _seed_thesis(db_path, checkpoints, *, status="active"):
    conn = store.connect(db_path)
    store.upsert_thesis(conn, M.Thesis(
        ticker=TICKER, company="NVIDIA", core_thesis="AI 가속기 수요가 이어진다",
        status=status, next_checkpoints=["템플릿 문장"],
    ))
    if checkpoints is not None:
        store.save_thesis_checkpoints(conn, TICKER, checkpoints + ["템플릿 문장"])
    conn.close()


def _stored(db_path):
    conn = store.connect(db_path)
    row = conn.execute("SELECT next_checkpoints_json FROM thesis WHERE ticker=?", (TICKER,)).fetchone()
    conn.close()
    return json.loads(row["next_checkpoints_json"])


class _Spy:
    def __init__(self, index=None):
        self.calls = 0
        self.index = index if index is not None else {"documents": []}

    def __call__(self):
        self.calls += 1
        return self.index


@pytest.fixture
def stub_search(monkeypatch):
    def _install(docs):
        def fake(index, query="", company="", limit=50, scope="all", **filters):
            return list(docs)
        monkeypatch.setattr(search_service, "search_documents", fake)
    return _install


# --- 0건 gate ------------------------------------------------------------

def test_no_structured_checkpoints_does_not_open_the_index():
    """load_index는 실측 4.7초다 — 판정할 것이 없으면 수집 잡이 그 값을 치르지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, None)          # 템플릿 문장만 있는 thesis
        spy = _Spy()
        result = CV.run_thesis_checkpoint_verdicts(db_path, as_of=AS_OF, index_loader=spy)
        assert spy.calls == 0
        assert result["indexLoaded"] is False
        assert result["checkpointCount"] == 0


def test_empty_thesis_table_does_not_open_the_index():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        store.connect(db_path).close()       # 스키마만 만든다(오늘의 실제 상태: 0행)
        spy = _Spy()
        result = CV.run_thesis_checkpoint_verdicts(db_path, as_of=AS_OF, index_loader=spy)
        assert spy.calls == 0 and result["thesisCount"] == 0


def test_closed_thesis_is_not_judged():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, [_checkpoint()], status="closed")
        spy = _Spy()
        result = CV.run_thesis_checkpoint_verdicts(db_path, as_of=AS_OF, index_loader=spy)
        assert spy.calls == 0 and result["checkpointCount"] == 0


# --- 판정 ----------------------------------------------------------------

def test_supporting_direction_confirms_and_copies_doc_id(stub_search):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, [_checkpoint()])
        stub_search([_doc()])
        spy = _Spy()
        result = CV.run_thesis_checkpoint_verdicts(db_path, as_of=AS_OF, index_loader=spy)
        assert spy.calls == 1 and result["changeCount"] == 1

        stored = [c for c in _stored(db_path) if isinstance(c, dict)][0]
        assert stored["status"] == "confirmed"
        # 문서 풀에는 role 분류가 없다 — 사본 키는 docId이고 role을 싣지 않는다.
        assert stored["lastVerdict"]["evidence"] == [{
            "docId": "research-inbox/rss/2026-08-20-nvda.md",
            "date": "2026-08-20",
            "title": "엔비디아, 데이터센터 가이던스상향",
        }]
        assert stored["history"][-1]["to"] == "confirmed"
        assert "템플릿 문장" in _stored(db_path)


def test_challenging_direction_reports_challenged(stub_search):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, [_checkpoint(
            item="주문 취소 보도", direction="challenging",
            matchers={"tickers": [TICKER], "keywords": ["주문 취소"]},
        )])
        stub_search([_doc(title="엔비디아 대형 고객 주문취소 보도")])
        result = CV.run_thesis_checkpoint_verdicts(db_path, as_of=AS_OF, index_loader=_Spy())
        assert result["changeCount"] == 1
        assert [c for c in _stored(db_path) if isinstance(c, dict)][0]["status"] == "challenged"


def test_keyword_miss_leaves_status_open(stub_search):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, [_checkpoint()])
        stub_search([_doc(title="엔비디아 신제품 발표", summary="행사 요약")])
        result = CV.run_thesis_checkpoint_verdicts(db_path, as_of=AS_OF, index_loader=_Spy())
        assert result["changeCount"] == 0
        assert [c for c in _stored(db_path) if isinstance(c, dict)][0]["status"] == "open"


def test_document_without_the_company_tag_is_not_evidence(stub_search):
    """제목 부분일치로 딸려 온 남의 기사가 확인 신호가 되면 안 된다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, [_checkpoint()])
        stub_search([_doc(companies=[{"ticker": "AMD", "name": "AMD"}])])
        result = CV.run_thesis_checkpoint_verdicts(db_path, as_of=AS_OF, index_loader=_Spy())
        assert result["results"][0]["evidenceCount"] == 0
        assert result["changeCount"] == 0


def test_second_run_is_idempotent(stub_search):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, [_checkpoint()])
        stub_search([_doc()])
        CV.run_thesis_checkpoint_verdicts(db_path, as_of=AS_OF, index_loader=_Spy())
        second = CV.run_thesis_checkpoint_verdicts(db_path, as_of=AS_OF, index_loader=_Spy())
        assert second["changeCount"] == 0
        assert len([c for c in _stored(db_path) if isinstance(c, dict)][0]["history"]) == 1


def test_verdict_does_not_touch_last_reviewed_at(stub_search):
    """기계 판정은 사용자의 검토가 아니다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, [_checkpoint()])
        conn = store.connect(db_path)
        before = conn.execute("SELECT last_reviewed_at FROM thesis WHERE ticker=?", (TICKER,)).fetchone()[0]
        conn.close()
        stub_search([_doc()])
        CV.run_thesis_checkpoint_verdicts(db_path, as_of=AS_OF, index_loader=_Spy())
        conn = store.connect(db_path)
        after = conn.execute("SELECT last_reviewed_at FROM thesis WHERE ticker=?", (TICKER,)).fetchone()[0]
        conn.close()
        assert after == before


# --- 노트 동기화 생존 ----------------------------------------------------

def test_note_resync_preserves_verdict_status(stub_search):
    """Vault/노트 재동기화는 문자열 목록만 갈아끼운다 — 판정 status와 이력이 살아남는다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        _seed_thesis(db_path, [_checkpoint()])
        stub_search([_doc()])
        CV.run_thesis_checkpoint_verdicts(db_path, as_of=AS_OF, index_loader=_Spy())

        conn = store.connect(db_path)
        store.upsert_thesis(conn, M.Thesis(
            ticker=TICKER, company="NVIDIA", core_thesis="AI 가속기 수요가 이어진다",
            next_checkpoints=["오늘 노트에서 읽은 문장"],
        ))
        conn.close()

        stored = _stored(db_path)
        structured = [c for c in stored if isinstance(c, dict)]
        assert len(structured) == 1
        assert structured[0]["status"] == "confirmed"
        assert len(structured[0]["history"]) == 1
        assert "오늘 노트에서 읽은 문장" in stored
        assert "템플릿 문장" not in stored      # 문자열 목록은 갈아끼운다


def _run_all():
    sys.exit(pytest.main([os.path.abspath(__file__), "-q"]))


if __name__ == "__main__":
    _run_all()
