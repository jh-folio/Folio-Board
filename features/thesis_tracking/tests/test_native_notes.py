"""네이티브 노트 ↔ thesis 레지스트리 (0.6 Stage B).

    py -3 -m pytest features/thesis_tracking/tests/test_native_notes.py -q

네트워크·실제 워크스페이스를 건드리지 않는다 — 임시 DB와 임시 노트 폴더뿐이다.
"""
import os
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from features.investment_notes import service as note_service
from features.thesis_tracking import native_notes as NN
from features.thesis_tracking import service as TS
from features.thesis_tracking import store as ST

TICKER = "NVDA"

TEMPLATE_BODY = """## 핵심 Thesis

AI 가속기 수요가 2년은 이어진다.

## 핵심 가정

- 데이터센터 자본지출이 유지된다
- 경쟁사 진입이 느리다

## 이탈 조건

- 대형 고객이 자체 칩으로 이동한다

## 다음 리뷰 체크포인트

- 다음 분기 데이터센터 매출
"""


def _note(**overrides):
    base = {
        "id": "note-1",
        "noteType": "company_thesis",
        "title": "엔비디아 투자 논리",
        "body": TEMPLATE_BODY,
        "ticker": TICKER,
        "company": "NVIDIA",
        "label": "NVIDIA",
        "createdAt": "2026-08-01T00:00:00+00:00",
        "updatedAt": "2026-08-30T00:00:00+00:00",
    }
    base.update(overrides)
    return base


# --- 노트 → Thesis 변환 --------------------------------------------------

def test_template_note_fills_every_section():
    thesis = NN.thesis_from_note(_note())
    assert thesis.ticker == TICKER
    assert thesis.core_thesis.startswith("AI 가속기 수요")
    assert len(thesis.key_assumptions) == 2
    assert thesis.falsification_triggers == ["대형 고객이 자체 칩으로 이동한다"]
    assert thesis.next_checkpoints == ["다음 분기 데이터센터 매출"]
    assert thesis.source == "native_note"
    assert thesis.note_path == "native_note:note-1"


def test_free_form_note_uses_the_first_paragraph():
    """노트를 쓰는 방식을 강요하지 않는다 — 템플릿이 아니어도 등록된다."""
    thesis = NN.thesis_from_note(_note(body="# 제목\n\n- 불릿\n\n전력 수요가 구조적으로 늘어난다.\n다음 줄도 같은 문단.\n\n다른 문단"))
    assert thesis.core_thesis == "전력 수요가 구조적으로 늘어난다. 다음 줄도 같은 문단."


def test_thoughts_only_note_uses_the_latest_thought():
    """노트 패널의 기본 입구는 `생각만 기록`이라 본문이 빈 노트가 흔하다 —
    그때 제목을 논지로 삼으면 등록은 되는데 알맹이가 없다."""
    thesis = NN.thesis_from_note(_note(body="", rawThoughts=[
        {"body": "먼저 떠오른 생각", "createdAt": "2026-08-01T00:00:00+00:00"},
        {"body": "애프터마켓 수요가 가격 결정력을 지킨다", "createdAt": "2026-08-02T00:00:00+00:00"},
    ]))
    assert thesis.core_thesis == "애프터마켓 수요가 가격 결정력을 지킨다"


def test_note_without_body_or_thoughts_falls_back_to_the_title():
    thesis = NN.thesis_from_note(_note(body="", rawThoughts=[]))
    assert thesis.core_thesis == "엔비디아 투자 논리"


def test_note_without_ticker_is_not_a_thesis():
    assert NN.thesis_from_note(_note(ticker="")) is None


# --- 빈자리만 자동, 갱신은 명시적 ----------------------------------------

def test_first_note_fills_the_empty_slot():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        result = NN.register_thesis_from_note(_note(), db_path=db_path)
        assert result["status"] == "created"
        conn = ST.connect(db_path)
        stored = ST.get_thesis(conn, TICKER)
        conn.close()
        assert stored["source"] == "native_note"
        assert stored["core_thesis"].startswith("AI 가속기 수요")


def test_second_note_does_not_overwrite_an_existing_thesis():
    """공들인 thesis가 지나가는 메모에 조용히 덮이지 않는다(§8.2)."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        NN.register_thesis_from_note(_note(), db_path=db_path)
        result = NN.register_thesis_from_note(
            _note(id="note-2", body="## 핵심 Thesis\n\n지나가는 메모."), db_path=db_path
        )
        assert result["status"] == "skipped_existing"
        conn = ST.connect(db_path)
        stored = ST.get_thesis(conn, TICKER)
        conn.close()
        assert stored["core_thesis"].startswith("AI 가속기 수요")


def test_explicit_overwrite_updates_and_keeps_operating_fields():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        NN.register_thesis_from_note(_note(), db_path=db_path)
        TS.upsert_manual_thesis({"ticker": TICKER, "review_cycle": "monthly", "conviction": "high"}, db_path=db_path)

        result = NN.register_thesis_from_note(
            _note(body="## 핵심 Thesis\n\n새 논리로 바꿨다."), db_path=db_path, overwrite=True
        )
        assert result["status"] == "updated"
        conn = ST.connect(db_path)
        stored = ST.get_thesis(conn, TICKER)
        conn.close()
        assert stored["core_thesis"] == "새 논리로 바꿨다."
        # 노트에 없는 운영 필드가 기본값으로 되돌아가지 않는다.
        assert stored["review_cycle"] == "monthly"
        assert stored["conviction"] == "high"


def test_structured_checkpoints_survive_note_promotion():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        NN.register_thesis_from_note(_note(), db_path=db_path)
        conn = ST.connect(db_path)
        ST.save_thesis_checkpoints(conn, TICKER, [{
            "id": "cp_x", "item": "데이터센터 매출 가이던스 상향", "direction": "supporting",
            "matchers": {"tickers": [TICKER], "keywords": ["가이던스 상향"]},
            "status": "confirmed", "createdAt": "2026-08-01T00:00:00+00:00",
            "lastVerdict": None, "history": [],
        }])
        conn.close()

        NN.register_thesis_from_note(_note(body=TEMPLATE_BODY), db_path=db_path, overwrite=True)
        conn = ST.connect(db_path)
        stored = ST.get_thesis(conn, TICKER)
        conn.close()
        structured = [c for c in stored["next_checkpoints"] if isinstance(c, dict)]
        assert len(structured) == 1 and structured[0]["status"] == "confirmed"


def test_link_on_save_never_raises():
    """등록 실패가 노트 저장을 되돌리지 않는다."""
    assert NN.link_note_on_save(_note(), db_path="/") ["status"] in {"failed", "created"}
    assert NN.link_note_on_save({"noteType": "investment_note"})["status"] == "skipped_not_thesis"


# --- 저장 훅 -------------------------------------------------------------

def test_saving_a_company_thesis_note_registers_the_thesis(monkeypatch):
    """노트 색인과 thesis 레지스트리는 같은 DB다 — 훅도 호출자가 준 경로를 쓴다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "market-memory.sqlite3"
        monkeypatch.setattr(note_service, "NOTES_DIR", Path(tmp) / "investment-notes")

        saved = note_service.save_note(
            {"noteType": "company_thesis", "title": "엔비디아", "body": TEMPLATE_BODY, "ticker": TICKER, "company": "NVIDIA"},
            db_path=db_path,
        )
        assert saved["noteType"] == "company_thesis"
        conn = ST.connect(db_path)
        stored = ST.get_thesis(conn, TICKER)
        conn.close()
        assert stored and stored["source"] == "native_note"


def test_saving_a_plain_note_does_not_touch_the_registry(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "market-memory.sqlite3"
        monkeypatch.setattr(note_service, "NOTES_DIR", Path(tmp) / "investment-notes")

        note_service.save_note(
            {"noteType": "investment_note", "title": "메모", "body": "생각", "ticker": TICKER},
            db_path=db_path,
        )
        conn = ST.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM thesis").fetchone()[0]
        conn.close()
        assert count == 0


# --- 수동 입력(부분 갱신) ------------------------------------------------

def test_manual_thesis_creates_without_obsidian():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        out = TS.upsert_manual_thesis({"ticker": "amd", "company": "AMD", "core_thesis": "MI 시리즈가 자리 잡는다"}, db_path=db_path)
        assert out["ticker"] == "AMD"
        assert out["source"] == "manual"


def test_manual_thesis_only_overrides_supplied_keys():
    """한 칸만 고치는 호출이 나머지를 지우면 안 된다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        TS.upsert_manual_thesis({
            "ticker": TICKER, "company": "NVIDIA", "core_thesis": "AI 수요가 이어진다",
            "key_assumptions": ["자본지출 유지"], "conviction": "high",
        }, db_path=db_path)
        out = TS.upsert_manual_thesis({"ticker": TICKER, "conviction": "medium"}, db_path=db_path)
        assert out["conviction"] == "medium"
        assert out["core_thesis"] == "AI 수요가 이어진다"
        assert out["key_assumptions"] == ["자본지출 유지"]


def test_manual_thesis_accepts_camel_case():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        out = TS.upsert_manual_thesis({"ticker": TICKER, "coreThesis": "카멜 표기", "keyMetrics": ["매출"]}, db_path=db_path)
        assert out["core_thesis"] == "카멜 표기"
        assert out["key_metrics"] == ["매출"]


def test_manual_thesis_requires_ticker():
    with pytest.raises(ValueError):
        TS.upsert_manual_thesis({"core_thesis": "티커가 없다"})


def test_manual_edit_keeps_the_source_note_reference():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        NN.register_thesis_from_note(_note(), db_path=db_path)
        out = TS.upsert_manual_thesis({"ticker": TICKER, "conviction": "high"}, db_path=db_path)
        assert out["note_path"] == "native_note:note-1"


# --- Vault 소유권 --------------------------------------------------------

def test_vault_sync_does_not_overwrite_app_authored_theses(monkeypatch):
    """Vault 동기화는 thesis를 열 때마다 돈다 — 소유자를 보지 않으면 앱에서 만든
    thesis가 같은 티커의 옛 노트로 조용히 되돌아간다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        vault_note = Path(tmp) / "NVDA.md"
        vault_note.write_text(
            "---\ntype: company_thesis\nticker: NVDA\n---\n\n## 핵심 Thesis\n\nVault 쪽 논리.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(TS, "scan_vault", lambda **_: None)
        monkeypatch.setattr(
            TS, "list_hypotheses",
            lambda **_: [{"note_type": "company_thesis", "path": str(vault_note)}],
        )

        TS.upsert_manual_thesis({"ticker": TICKER, "core_thesis": "앱에서 쓴 논리"}, db_path=db_path)
        summary = TS.sync_theses_from_vault(db_path=db_path)
        assert summary["skipped_not_owned"] == 1
        conn = ST.connect(db_path)
        stored = ST.get_thesis(conn, TICKER)
        conn.close()
        assert stored["core_thesis"] == "앱에서 쓴 논리"


def test_vault_sync_still_fills_empty_slots_and_updates_its_own(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "market-memory.sqlite3")
        vault_note = Path(tmp) / "NVDA.md"
        vault_note.write_text(
            "---\ntype: company_thesis\nticker: NVDA\n---\n\n## 핵심 Thesis\n\n첫 논리.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(TS, "scan_vault", lambda **_: None)
        monkeypatch.setattr(
            TS, "list_hypotheses",
            lambda **_: [{"note_type": "company_thesis", "path": str(vault_note)}],
        )
        assert TS.sync_theses_from_vault(db_path=db_path)["theses_upserted"] == 1

        vault_note.write_text(
            "---\ntype: company_thesis\nticker: NVDA\n---\n\n## 핵심 Thesis\n\n고친 논리.\n",
            encoding="utf-8",
        )
        assert TS.sync_theses_from_vault(db_path=db_path)["theses_upserted"] == 1
        conn = ST.connect(db_path)
        stored = ST.get_thesis(conn, TICKER)
        conn.close()
        assert stored["core_thesis"] == "고친 논리."


# --- 승격 action ---------------------------------------------------------

def test_promote_note_requires_a_company_thesis_note(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "market-memory.sqlite3"
        monkeypatch.setattr(note_service, "NOTES_DIR", Path(tmp) / "investment-notes")
        plain = note_service.save_note(
            {"noteType": "investment_note", "title": "메모", "body": "생각", "ticker": TICKER},
            db_path=db_path,
        )
        with pytest.raises(ValueError):
            TS.promote_note_to_thesis(plain["id"], db_path=db_path)


def test_promote_note_missing_note_raises():
    with pytest.raises(LookupError):
        TS.promote_note_to_thesis("does-not-exist")


def _run_all():
    sys.exit(pytest.main([os.path.abspath(__file__), "-q"]))


if __name__ == "__main__":
    _run_all()
