"""Investment Review v2 route/service boundary.

The dated JSON authority is assembled in :mod:`review_v2`; this module keeps
FastAPI-compatible entrypoints thin.  Reads never generate or rewrite, and
only explicit generation touches ``data/investment-review/{date}.json``.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from features.common.canonical_report_io import safe_child_path
from features.investment_review.schema import empty_review, normalize_review
from features.common.workspace import data_dir
from features.common.jobs import diagnostic_stage_end, diagnostic_stage_failure, diagnostic_stage_start

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = data_dir()
REVIEW_DIR = DATA_DIR / "investment-review"
MEMORY_DB = DATA_DIR / "market-memory.sqlite3"

REVIEW_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def normalize_review_date(value) -> str:
    """리뷰 날짜는 YYYY-MM-DD 형식 하나만 받는다.

    사용자 입력 date가 그대로 캐시 파일 경로에 붙으므로, 형식을 검증하지 않으면
    `../portfolio` 같은 값이 `data/portfolio.json`을 리뷰 JSON으로 덮어쓴다
    (§6 절대 규칙 2). 브리핑의 `_valid_briefing_date()`와 같은 계약이다.
    """
    text = str(value or "").strip()
    if not text:
        return _today()
    if not REVIEW_DATE_RE.fullmatch(text):
        raise ValueError("invalid_review_date")
    try:
        dt.date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("invalid_review_date") from exc
    return text


def _cache_path(date: str) -> Path:
    """Compatibility-only path guard; v2 no longer has a cache writer."""
    return safe_child_path(REVIEW_DIR, f"{date}.json")


def _today() -> str:
    return dt.date.today().isoformat()


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 순수 집계 함수 (데이터 주입 — 테스트 용이)
# ---------------------------------------------------------------------------

def build_market_state(regime_states: list) -> list:
    out = []
    for s in regime_states or []:
        label = s.get("stateLabel") or s.get("storyFamily") or s.get("story") or s.get("stateKey") or ""
        if not label:
            continue
        out.append({
            "stateId": s.get("id") or s.get("stateId") or s.get("stateKey") or "",
            "label": label,
            "momentum": s.get("momentum") or "stable",
            "confidence": s.get("confidence"),
            "bias": s.get("bias") or "",
            "status": s.get("status") or "",
            "linkedCompanies": [str(t).upper() for t in (s.get("linkedCompanies") or [])][:6],
        })
    return out


def build_thesis_changes(theses: list, deltas_by_ticker: dict) -> list:
    out = []
    for t in theses or []:
        ticker = str(t.get("ticker") or "").upper()
        if not ticker:
            continue
        delta = (deltas_by_ticker or {}).get(ticker) or {}
        out.append({
            "ticker": ticker,
            "company": t.get("company") or "",
            "conviction": t.get("conviction") or "",
            "status": t.get("status") or "",
            "verdict": delta.get("verdict") or "insufficient_evidence",
            "deltaGeneratedAt": delta.get("generatedAt") or "",
        })
    return out


def _ticker_to_regimes(regime_states: list) -> dict:
    from features.investment_review.context_links import normalize_research_ticker

    idx: dict[str, list] = {}
    for s in regime_states or []:
        label = s.get("stateLabel") or s.get("storyFamily") or s.get("story") or ""
        for tk in (s.get("linkedCompanies") or []):
            ticker = normalize_research_ticker(tk)
            if not ticker:
                continue
            idx.setdefault(ticker, []).append(
                {"label": label, "momentum": s.get("momentum") or "stable", "bias": s.get("bias") or ""}
            )
    return idx


_POSITIVE_MOMENTUM = {"strengthening"}
_NEGATIVE_MOMENTUM = {"fading", "turning"}
_AT_RISK_VERDICTS = {"weakened", "at_risk", "broken"}
_POSITIVE_VERDICTS = {"strengthened"}


def _impact_for(regimes: list, verdict: str) -> str:
    v = str(verdict or "").lower()
    moms = {r.get("momentum") for r in regimes}
    if v in _AT_RISK_VERDICTS:
        return "watch"
    if moms & _NEGATIVE_MOMENTUM:
        return "watch"
    if v in _POSITIVE_VERDICTS or (moms & _POSITIVE_MOMENTUM):
        return "positive"
    return "neutral"


def build_portfolio_impacts(positions: list, watchlist: list, regime_states: list, thesis_changes: list) -> list:
    from features.investment_review.context_links import normalize_research_ticker

    reg_idx = _ticker_to_regimes(regime_states)
    verdict_idx = {
        ticker: c.get("verdict")
        for c in (thesis_changes or [])
        if (ticker := normalize_research_ticker(c.get("ticker")))
    }
    out = []
    indexes: dict[str, int] = {}

    def add(ticker, name, source):
        ticker = normalize_research_ticker(ticker)
        if not ticker:
            return
        existing_index = indexes.get(ticker)
        if existing_index is not None:
            if out[existing_index]["source"] != source:
                out[existing_index]["source"] = "both"
            return
        regimes = reg_idx.get(ticker, [])
        verdict = verdict_idx.get(ticker, "")
        indexes[ticker] = len(out)
        out.append({
            "ticker": ticker,
            "name": name or ticker,
            "source": source,
            "impact": _impact_for(regimes, verdict),
            "verdict": verdict or "",
            "linkedNarratives": [r["label"] for r in regimes if r.get("label")][:4],
        })

    for p in positions or []:
        add(p.get("ticker"), p.get("name"), "portfolio")
    for w in watchlist or []:
        if isinstance(w, dict):
            add(w.get("ticker") or w.get("symbol") or w.get("keyword"), w.get("name") or w.get("company"), "watchlist")
        else:
            add(w, w, "watchlist")
    return out


def aggregate_checkpoints(thesis_deltas: list, regime_states: list, *, limit: int = 12) -> list:
    from features.common.research_schema.checkpoints import (
        checkpoints_from_regime_state,
        checkpoints_from_thesis_delta,
    )
    thesis_rows = []
    for d in thesis_deltas or []:
        thesis_rows.extend(checkpoints_from_thesis_delta(d, artifact_id=str(d.get("ticker") or d.get("deltaId") or "")) or [])
    regime_rows = []
    for s in regime_states or []:
        regime_rows.extend(checkpoints_from_regime_state(s, artifact_id=str(s.get("id") or s.get("stateKey") or "")) or [])

    # 같은 문구라도 종목이 다르면 다른 체크포인트다. thesis delta의 기본 문구는 모든
    # 종목이 같아서 문구만으로 접으면 첫 종목만 살아남고, 티커별 필터를 거친 나머지
    # 종목은 근거 없이 "확인할 체크포인트 없음"이 된다.
    seen: set[tuple[str, str]] = set()

    def _dedup(rows: list) -> list:
        out = []
        for c in rows:
            text = str(c.get("checkpoint") or "").strip()
            key = (str(c.get("ticker") or "").strip().upper(), text)
            if not text or key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    thesis_rows = _dedup(thesis_rows)
    regime_rows = _dedup(regime_rows)

    # 소스별 정원. thesis가 먼저 수집되므로 정원 없이 자르면 종목이 6개만 넘어도
    # 시장(regime) 체크포인트가 0건이 되어, 리뷰가 시장 쪽 확인 사항을 통째로 잃는다.
    # 한쪽이 정원을 못 채우면 다른 쪽이 남은 자리를 흡수한다.
    limit = max(0, int(limit))
    thesis_quota = limit * 2 // 3
    regime_quota = limit - thesis_quota
    thesis_take = min(len(thesis_rows), max(thesis_quota, limit - min(len(regime_rows), regime_quota)))
    regime_take = min(len(regime_rows), limit - thesis_take)
    return thesis_rows[:thesis_take] + regime_rows[:regime_take]


def build_linked_notes(notes: list, *, limit: int = 12) -> list:
    out = []
    for n in notes or []:
        out.append({
            "title": n.get("title") or n.get("rel_path") or n.get("relPath") or "",
            "noteType": n.get("note_type") or n.get("noteType") or "",
            "ticker": str(n.get("ticker") or "").upper(),
            "relPath": n.get("rel_path") or n.get("relPath") or "",
        })
        if len(out) >= limit:
            break
    return out


def _count_by(rows: list, key: str) -> dict:
    counts: dict[str, int] = {}
    for r in rows or []:
        v = str(r.get(key) or "")
        if v:
            counts[v] = counts.get(v, 0) + 1
    return counts


_WEAK_VERDICTS = {"weakened", "at_risk", "broken"}


def build_stats(market_state: list, thesis_changes: list, portfolio_impacts: list, key_checkpoints: list) -> dict:
    return {
        "marketStrengthening": sum(1 for s in market_state or [] if s.get("momentum") == "strengthening"),
        "marketTotal": len(market_state or []),
        "thesisStrengthened": sum(1 for c in thesis_changes or [] if c.get("verdict") == "strengthened"),
        "thesisWeakened": sum(1 for c in thesis_changes or [] if c.get("verdict") in _WEAK_VERDICTS),
        "positionsPositive": sum(1 for p in portfolio_impacts or [] if p.get("impact") == "positive"),
        "positionsWatch": sum(1 for p in portfolio_impacts or [] if p.get("impact") == "watch"),
        "checkpointCount": len(key_checkpoints or []),
        "thesisDistribution": _count_by(thesis_changes, "verdict"),
        "impactDistribution": _count_by(portfolio_impacts, "impact"),
    }


def build_exposure(portfolio_impacts: list, *, limit: int = 8) -> list:
    counts: dict[str, int] = {}
    for p in portfolio_impacts or []:
        for nar in p.get("linkedNarratives") or []:
            if nar:
                counts[nar] = counts.get(nar, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"narrative": k, "count": v} for k, v in ranked[:limit]]


def build_summary(market_state: list) -> str:
    strong = [s.get("label") for s in market_state or [] if s.get("momentum") == "strengthening" and s.get("label")][:3]
    soft = [s.get("label") for s in market_state or [] if s.get("momentum") in ("fading", "turning", "conflicted") and s.get("label")][:2]
    parts = []
    if strong:
        parts.append("·".join(strong) + " 강화")
    if soft:
        parts.append("·".join(soft) + " 주의")
    return " / ".join(parts) or "아직 누적된 시장 내러티브가 없습니다. 브리핑·내러티브를 먼저 생성하세요."


_VERDICT_LABELS = {
    "strengthened": "강화", "maintained": "유지", "weakened": "약화",
    "at_risk": "이탈 주의", "broken": "이탈", "insufficient_evidence": "근거 부족",
}
_IMPACT_LABELS = {"positive": "긍정", "watch": "주의", "negative": "부정", "neutral": "중립"}
_MOMENTUM_LABELS = {
    "strengthening": "강화", "stable": "유지", "fading": "약화", "turning": "전환", "conflicted": "혼재",
}


def render_markdown(review: dict) -> str:
    lines = [f"# 투자 리뷰 — {review.get('date', '')}", ""]

    ms = review.get("marketState") or []
    lines.append("## 오늘의 시장 상태")
    if ms:
        for s in ms[:8]:
            mom = _MOMENTUM_LABELS.get(s.get("momentum"), s.get("momentum") or "")
            lines.append(f"- **{s.get('label')}**: {mom}")
    else:
        lines.append("- 누적된 시장 내러티브가 없습니다.")
    lines.append("")

    tc = review.get("thesisChanges") or []
    lines.append("## 내 Thesis 변화")
    if tc:
        for c in tc[:12]:
            verdict = _VERDICT_LABELS.get(c.get("verdict"), c.get("verdict") or "")
            lines.append(f"- **{c.get('ticker')}**: {verdict}")
    else:
        lines.append("- 등록된 thesis가 없습니다.")
    lines.append("")

    pi = review.get("portfolioImpacts") or []
    lines.append("## 포트폴리오 영향")
    if pi:
        for p in pi[:20]:
            impact = _IMPACT_LABELS.get(p.get("impact"), p.get("impact") or "")
            nar = ", ".join(p.get("linkedNarratives") or [])
            tail = f" · {nar}" if nar else ""
            lines.append(f"- **{p.get('ticker')}** ({impact}){tail}")
    else:
        lines.append("- 연결할 포트폴리오/워치리스트 종목이 없습니다.")
    lines.append("")

    kc = review.get("keyCheckpoints") or []
    lines.append("## 이번 주 체크포인트")
    if kc:
        # thesis 체크포인트의 기본 문구는 종목이 달라도 같다. 티커를 빼면 같은 줄이
        # 종목 수만큼 반복되어 어느 종목을 확인하라는 것인지 알 수 없다.
        for c in kc[:12]:
            ticker = str(c.get("ticker") or "").strip().upper()
            lines.append(f"- **{ticker}** {c.get('checkpoint')}" if ticker else f"- {c.get('checkpoint')}")
    else:
        lines.append("- 구조화된 체크포인트가 없습니다.")
    lines.append("")

    ln = review.get("linkedNotes") or []
    if ln:
        lines.append("## 연결된 내 노트")
        for n in ln[:12]:
            lines.append(f"- {n.get('title')}")
        lines.append("")

    if review.get("warnings"):
        lines.append("## 참고")
        for w in review["warnings"]:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("> 투자 리뷰는 개인 해석 보조입니다. 매수/매도 지시가 아닙니다.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 실데이터 로더 (방어적 — 실패 시 warnings에 남기고 빈 데이터)
# ---------------------------------------------------------------------------

def _load_regime_states(warnings: list) -> list:
    try:
        from features.market_memory.memory import list_states
        return list_states(MEMORY_DB, status="current", limit=40)
    except Exception:
        warnings.append("시장 내러티브를 불러오지 못했습니다.")
        return []


def _load_theses_with_deltas(warnings: list):
    try:
        from features.thesis_tracking.service import list_theses
        from features.thesis_tracking.store import connect, latest_delta
        theses = list_theses(db_path=str(MEMORY_DB), status=None)
        deltas: dict[str, dict] = {}
        conn = connect(str(MEMORY_DB))
        try:
            for t in theses:
                tk = str(t.get("ticker") or "").upper()
                if not tk:
                    continue
                d = latest_delta(conn, tk)
                if d:
                    deltas[tk] = d
        finally:
            conn.close()
        return theses, deltas
    except Exception:
        warnings.append("Thesis 데이터를 불러오지 못했습니다.")
        return [], {}


def _load_positions(warnings: list) -> list:
    try:
        from features.portfolio.service import get_portfolio
        return get_portfolio().get("positions", [])
    except Exception:
        warnings.append("포트폴리오를 불러오지 못했습니다.")
        return []


def _load_watchlist(warnings: list) -> list:
    try:
        from features.watchlist_notes.service import get_watchlist
        return get_watchlist() or []
    except Exception:
        warnings.append("워치리스트를 불러오지 못했습니다.")
        return []


def _load_notes(warnings: list) -> list:
    notes = []
    try:
        from features.investment_notes.service import list_notes as list_native_notes
        notes.extend(list_native_notes(limit=40))
    except Exception:
        warnings.append("Folio 투자 노트를 불러오지 못했습니다.")
    try:
        from features.obsidian.importer.note_index import connect, list_notes
        conn = connect(str(MEMORY_DB))
        try:
            notes.extend(list_notes(conn, importable=True))
        finally:
            conn.close()
    except Exception:
        warnings.append("Obsidian 노트를 불러오지 못했습니다.")
    return notes


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# 대시보드 마켓 탭.
# US 지수는 ETF가 아닌 지수 레벨(^GSPC/^NDX)을 쓰고, 한국 수치는 providers 체인
# (yfinance)으로 KOSPI·USD/KRW를 가져온다(CLAUDE.md 한국장 규칙).
# size: 중요도 표시용("lg" 핵심 지표 → 큰 카드, "sm" 보조 지표 → 작은 카드).
def _tape_item(label: str, value, change_pct, size: str = "sm") -> dict:
    has = isinstance(value, (int, float))
    return {
        "label": label,
        "value": value if has else None,
        "changePct": change_pct if isinstance(change_pct, (int, float)) else None,
        "status": "fresh" if has else "missing",
        "size": "lg" if size == "lg" else "sm",
    }


def _fetch_us_levels(symbols: dict, warnings: list) -> dict:
    """{yf_symbol: label} → {yf_symbol: {value, changePct}}. 마지막 두 종가로 1D 변화율 계산."""
    out: dict = {}
    try:
        import yfinance as yf
    except Exception:
        warnings.append("미국 지수 데이터를 불러오지 못했습니다.")
        return out
    for sym in symbols:
        try:
            hist = yf.Ticker(sym).history(period="7d", interval="1d", auto_adjust=False)
            if hist is None or hist.empty or "Close" not in hist:
                continue
            closes = [float(x) for x in hist["Close"].tolist() if x == x]
            if not closes:
                continue
            last = closes[-1]
            prev = closes[-2] if len(closes) >= 2 else None
            chg = (last / prev - 1.0) * 100.0 if prev else None
            out[sym] = {"value": last, "changePct": chg}
        except Exception:
            warnings.append(f"{symbols[sym]} 시세를 불러오지 못했습니다.")
    return out


def build_dashboard_tape(date: str, warnings: list) -> dict:
    us_syms = {
        "^GSPC": "S&P 500", "^NDX": "Nasdaq 100", "^DJI": "Dow Jones",
        "^RUT": "Russell 2000", "^TNX": "美 국채 10Y", "^VIX": "VIX",
        "DX-Y.NYB": "달러 인덱스", "GC=F": "금", "CL=F": "WTI 원유",
    }
    us = _fetch_us_levels(us_syms, warnings)

    kospi, kosdaq, fx = {}, {}, {}
    try:
        from features.common.market_data.providers import fetch_korea_market_data
        kr = fetch_korea_market_data(date)
        indices = kr.get("indices") or {}
        kospi = indices.get("KOSPI") or {}
        kosdaq = indices.get("KOSDAQ") or {}
        fx = (kr.get("fx") or {}).get("USDKRW") or {}
    except Exception:
        warnings.append("한국 시장 데이터를 불러오지 못했습니다.")

    def us_item(label, sym, size="sm"):
        d = us.get(sym) or {}
        return _tape_item(label, d.get("value"), d.get("changePct"), size)

    # 프론트는 8칸 그리드에 lg=2칸/sm=1칸으로 배치한다. 아래 순서가 곧 2행 레이아웃이다.
    # 1행: 미국 핵심(S&P·Nasdaq, lg) + 미국 보조(Dow·Russell·국채·VIX, sm)
    # 2행: 한국 핵심(KOSPI·KOSDAQ, lg) + 환율·원자재(USD/KRW·달러인덱스·금·원유, sm)
    items = [
        us_item("S&P 500", "^GSPC", "lg"),
        us_item("Nasdaq 100", "^NDX", "lg"),
        us_item("Dow Jones", "^DJI", "sm"),
        us_item("Russell 2000", "^RUT", "sm"),
        us_item("美 국채 10Y", "^TNX", "sm"),
        us_item("VIX", "^VIX", "sm"),
        _tape_item("KOSPI", kospi.get("close"), kospi.get("changePct"), "lg"),
        _tape_item("KOSDAQ", kosdaq.get("close"), kosdaq.get("changePct"), "lg"),
        _tape_item("USD/KRW", fx.get("close"), fx.get("changePct"), "sm"),
        us_item("달러 인덱스", "DX-Y.NYB", "sm"),
        us_item("금", "GC=F", "sm"),
        us_item("WTI 원유", "CL=F", "sm"),
    ]
    return {"items": items, "asOf": _now_iso()}


def _latest_report_file(folder: Path):
    if not folder.exists():
        return None, None
    files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        data = _read_json(path)
        if data:
            return path, data
    return None, None


def _load_recent_reports(warnings: list) -> list:
    out = []
    try:
        path, data = _latest_report_file(DATA_DIR / "briefings")
        if data:
            d = str(data.get("date") or path.stem)[:10]
            out.append({"type": "briefing", "id": path.stem, "title": f"{d} 시장 브리핑", "date": d, "view": "briefing"})
        path, data = _latest_report_file(DATA_DIR / "company-analysis")
        if data:
            company = data.get("company") if isinstance(data.get("company"), dict) else {}
            name = company.get("ticker") or company.get("name") or data.get("query") or path.stem
            out.append({"type": "analysis", "id": path.stem, "title": f"{name} 기업 분석", "date": str(data.get("date") or "")[:10], "view": "analysis"})
        path, data = _latest_report_file(DATA_DIR / "topic-reports")
        if data:
            label = data.get("topicLabel") or data.get("topicKey") or path.stem
            out.append({"type": "topic", "id": path.stem, "title": str(label), "date": str(data.get("date") or "")[:10], "view": "topicrpt"})
    except Exception:
        warnings.append("최근 보고서를 불러오지 못했습니다.")
    return out


# ---------------------------------------------------------------------------
# Read-only per-ticker investment context (0.2.3)
# ---------------------------------------------------------------------------

def _context_file_watermark(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return "missing"
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _context_directory_watermark(path: Path) -> str:
    if not path.is_dir():
        return "missing"
    entries = []
    for child in sorted(path.glob("*.json"), key=lambda item: item.name)[:200]:
        try:
            stat = child.stat()
        except OSError:
            continue
        entries.append(f"{child.name}:{stat.st_mtime_ns}:{stat.st_size}")
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def _context_source_watermarks(data_dir: Path) -> dict[str, str]:
    return {
        "portfolio": _context_file_watermark(data_dir / "portfolio.json"),
        "watchlist": _context_file_watermark(data_dir / "watchlist.json"),
        "marketMemory": _context_file_watermark(data_dir / "market-memory.sqlite3"),
        "marketMemoryWal": _context_file_watermark(data_dir / "market-memory.sqlite3-wal"),
        "researchIndex": _context_file_watermark(data_dir / "research-index.sqlite3"),
        "researchIndexWal": _context_file_watermark(data_dir / "research-index.sqlite3-wal"),
        "collections": _context_file_watermark(data_dir / "smart-collections.json"),
        "collectionState": _context_directory_watermark(data_dir / "smart-collection-state"),
        "companyReports": _context_directory_watermark(data_dir / "company-analysis"),
        "topicReports": _context_directory_watermark(data_dir / "topic-reports"),
    }


def _context_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _context_report_rows(data_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted((data_dir / "company-analysis").glob("*.json"), reverse=True)[:40]:
        report = _context_json(path, None)
        if not isinstance(report, dict):
            continue
        company = report.get("company") if isinstance(report.get("company"), dict) else {}
        rows.append({
            "id": report.get("id") or path.stem,
            "title": report.get("headline") or report.get("title") or path.stem,
            "type": "analysis",
            "generatedAt": report.get("generatedAt") or report.get("date") or "",
            "company": {"ticker": company.get("ticker") or ""},
        })
    for path in sorted((data_dir / "topic-reports").glob("*.json"), reverse=True)[:40]:
        report = _context_json(path, None)
        if not isinstance(report, dict):
            continue
        tickers: list[str] = []
        for value in (
            report.get("customTickers"),
            (report.get("topicPlan") or {}).get("approvedTickers")
            if isinstance(report.get("topicPlan"), dict)
            else None,
        ):
            if isinstance(value, dict):
                tickers.extend(str(ticker) for ticker in value)
            elif isinstance(value, list):
                tickers.extend(str(ticker) for ticker in value)
        rows.append({
            "id": report.get("id") or path.stem,
            "title": report.get("title") or report.get("topicLabel") or path.stem,
            "type": "topic",
            "generatedAt": report.get("generatedAt") or report.get("date") or "",
            "tickers": tickers,
        })
    return rows


def _context_inputs(data_dir: Path, collection_service=None) -> dict:
    portfolio = _context_json(data_dir / "portfolio.json", {"positions": []})
    if isinstance(portfolio, list):
        positions = portfolio
    elif isinstance(portfolio, dict) and isinstance(portfolio.get("positions"), list):
        positions = portfolio["positions"]
    else:
        positions = []
    watchlist = _context_json(data_dir / "watchlist.json", [])
    if not isinstance(watchlist, list):
        watchlist = []

    database = data_dir / "market-memory.sqlite3"
    regime_states = None
    thesis_deltas = None
    due_checkpoints = None
    if database.is_file():
        try:
            from features.market_memory.memory import list_states

            regime_states = list_states(database, status="current", limit=40)
        except Exception:
            regime_states = None
        try:
            from features.thesis_tracking.service import list_theses
            from features.thesis_tracking.store import connect, latest_delta

            theses = list_theses(db_path=str(database), status=None)
            thesis_deltas = []
            connection = connect(str(database))
            try:
                for thesis in theses:
                    ticker = str(thesis.get("ticker") or "").strip().upper()
                    if not ticker:
                        continue
                    delta = latest_delta(connection, ticker)
                    if delta:
                        thesis_deltas.append(delta)
            finally:
                connection.close()
        except Exception:
            thesis_deltas = None
        if regime_states is not None and thesis_deltas is not None:
            due_checkpoints = aggregate_checkpoints(thesis_deltas, regime_states, limit=40)

    collections = []
    collection_results = []
    collection_health = {}
    try:
        if collection_service is None and (data_dir / "smart-collections.json").is_file():
            from features.smart_collections.service import (
                SmartCollectionRuntime,
                SmartCollectionService,
            )

            collection_service = SmartCollectionService(
                SmartCollectionRuntime(dataDir=data_dir, clock=lambda: dt.datetime.now(dt.UTC))
            )
        if collection_service is not None:
            collection_list = collection_service.list(limit=50, offset=0)
            collections = collection_list.get("items") or []
            for collection in collections:
                collection_id = str(collection.get("id") or "")
                if not collection_id:
                    continue
                try:
                    workspace = collection_service.workspace(collection_id)
                except Exception:
                    collection_health[collection_id] = "unavailable"
                    continue
                collection_health[collection_id] = workspace.get("health") or "unknown"
                for item in workspace.get("recentEvidence") or []:
                    if not isinstance(item, dict):
                        continue
                    collection_results.append({
                        "collectionId": collection_id,
                        "evidenceId": item.get("id") or "",
                        "tickers": item.get("tickers") or [],
                    })
    except Exception:
        collections = None
        collection_results = None
        collection_health = None

    return {
        "positions": positions,
        "watchlist": watchlist,
        "regime_states": regime_states,
        "thesis_deltas": thesis_deltas,
        "due_checkpoints": due_checkpoints,
        "reports": _context_report_rows(data_dir),
        "collections": collections,
        "collection_results": collection_results,
        "collection_health": collection_health,
    }


@dataclass(frozen=True, slots=True)
class InvestmentContextRuntime:
    dataDir: Path
    clock: Callable[[], dt.datetime]
    inputLoader: Callable[[], dict] | None = None
    watermarkLoader: Callable[[], Mapping[str, str]] | None = None
    collectionService: object | None = None


class InvestmentContextNotFoundError(LookupError):
    code = "investment_context_not_found"


class InvestmentContextService:
    def __init__(self, runtime: InvestmentContextRuntime) -> None:
        self.runtime = runtime
        self._lock = threading.Lock()
        self._cached_watermark: tuple[tuple[str, str], ...] | None = None
        self._cached_contexts = ()

    def _watermark(self) -> tuple[tuple[str, str], ...]:
        values = (
            self.runtime.watermarkLoader()
            if self.runtime.watermarkLoader is not None
            else _context_source_watermarks(self.runtime.dataDir)
        )
        return tuple(sorted((str(key), str(value)) for key, value in values.items()))

    def _observed_at(self) -> str:
        current = self.runtime.clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=dt.UTC)
        return current.astimezone(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    def contexts(self):
        from features.investment_review.context_links import build_ticker_research_contexts

        watermark = self._watermark()
        with self._lock:
            if watermark == self._cached_watermark:
                return self._cached_contexts
            inputs = (
                self.runtime.inputLoader()
                if self.runtime.inputLoader is not None
                else _context_inputs(self.runtime.dataDir, self.runtime.collectionService)
            )
            contexts = build_ticker_research_contexts(
                positions=inputs.get("positions"),
                watchlist=inputs.get("watchlist"),
                regime_states=inputs.get("regime_states"),
                thesis_deltas=inputs.get("thesis_deltas"),
                due_checkpoints=inputs.get("due_checkpoints"),
                reports=inputs.get("reports"),
                collections=inputs.get("collections"),
                collection_results=inputs.get("collection_results"),
                collection_health=inputs.get("collection_health"),
                observed_at=self._observed_at(),
            )
            self._cached_contexts = contexts
            self._cached_watermark = watermark
            return contexts

    def summary(self) -> dict:
        contexts = self.contexts()
        source_counts = {
            source: sum(1 for context in contexts if context.source.value == source)
            for source in ("portfolio", "watchlist", "both")
        }
        stance_counts = {
            stance: sum(1 for context in contexts if context.stance.value == stance)
            for stance in ("positive", "watch", "negative", "neutral", "unknown")
        }
        watch = sorted(
            (context for context in contexts if context.stance.value == "watch"),
            key=lambda context: (
                -len(context.dueCheckpoints),
                -len(context.marketDrivers),
                context.ticker,
            ),
        )[:10]
        observed_at = contexts[0].observedAt if contexts else self._observed_at()
        return {
            "observedAt": observed_at,
            "counts": {
                "total": len(contexts),
                **source_counts,
                **stance_counts,
            },
            "watchContexts": [context.model_dump(mode="json") for context in watch],
        }

    def detail(self, ticker: str):
        from features.investment_review.context_links import normalize_research_ticker

        normalized = normalize_research_ticker(ticker)
        context = next((item for item in self.contexts() if item.ticker == normalized), None)
        if context is None:
            raise InvestmentContextNotFoundError(normalized)
        return context.model_dump(mode="json")


# ---------------------------------------------------------------------------
# 캐싱
# ---------------------------------------------------------------------------

def _load_latest() -> dict | None:
    if not REVIEW_DIR.exists():
        return None
    # 미래 날짜 저장본은 파일명 역순 정렬에서 언제나 1등이라 '최신 저장본' 자리를 영구히
    # 선점한다. 옛 버전이 남긴 파일이 있을 수 있으므로 읽을 때 걸러 낸다.
    today = _today()
    files = sorted((path for path in REVIEW_DIR.glob("*.json") if path.stem <= today), reverse=True)
    for path in files:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def _v2_data_dir() -> Path:
    """Keep the historical module globals patchable in focused tests."""
    return DATA_DIR


def build_review(
    *, date: str | None = None, include_portfolio: bool = True,
    include_watchlist: bool = False, include_obsidian: bool = False,
    use_llm: bool = False, force_refresh: bool = False, persist: bool = True,
) -> dict:
    """Build through the single v2 pipeline for rules, API and CLI drafts.

    ``include_watchlist`` remains accepted for compatibility but v2 deliberately
    excludes it from `positionReviews`; the Portfolio review only owns holdings.
    """
    from features.investment_review.review_v2 import build_candidate, finalize_and_commit
    requested = normalize_review_date(date)
    # The generation inputs are current authorities, not historical snapshots.
    # Preserve the established safety rule: an explicit persisted historical
    # date cannot masquerade as an as-of reconstruction.  CLI drafts retain
    # their requested label because their caller owns the eventual target.
    storage_date = _today() if persist and requested != _today() else requested
    context_recorder, context_stage = diagnostic_stage_start("context")
    try:
        candidate = build_candidate(
            _v2_data_dir(), REVIEW_DIR, storage_date, include_portfolio=include_portfolio,
            include_watchlist=include_watchlist, include_obsidian=include_obsidian,
        )
    except Exception as error:
        diagnostic_stage_failure(
            context_recorder, error, stage_id=context_stage,
            stage_code="context" if context_stage is not None else None,
            boundary="generic",
        )
        diagnostic_stage_end(context_recorder, context_stage, "context")
        raise
    diagnostic_stage_end(context_recorder, context_stage, "context")
    if requested != _today():
        candidate.setdefault("warnings", []).append(
            f"이 리뷰는 현재 데이터로 집계했습니다. {requested} 시점 데이터로 재구성한 것이 아닙니다."
        )
        if persist:
            candidate["warnings"].append(f"요청한 {requested} 대신 오늘({_today()}) 리뷰로 저장했습니다.")
    if persist:
        commit_recorder, commit_stage = diagnostic_stage_start("commit")
        try:
            result = finalize_and_commit(_v2_data_dir(), REVIEW_DIR, candidate)
        except Exception as error:
            diagnostic_stage_failure(
                commit_recorder, error, stage_id=commit_stage,
                stage_code="commit" if commit_stage is not None else None,
                boundary="save",
            )
            diagnostic_stage_end(commit_recorder, commit_stage, "commit")
            raise
        diagnostic_stage_end(commit_recorder, commit_stage, "commit")
        return result
    return candidate


def _effective_view(raw: dict, date: str) -> dict:
    """Normalize and derive state in memory.  It never writes or fetches quotes."""
    from features.investment_review.review_v2 import build_input_basis, effective_freshness, find_previous, gather_inputs
    view = normalize_review(raw, date=date)
    if view.get("sourceSchemaVersion") == 1:
        return view
    selection_version = str((view.get("inputBasis") or {}).get("reportSelectionVersion") or "")
    inputs = gather_inputs(_v2_data_dir(), analytics_authority=(view.get("inputBasis") or {}).get("analytics"),
                           report_selection_version=selection_version)
    basis = build_input_basis(inputs, previous=find_previous(REVIEW_DIR, date))
    state, freshness, reasons = effective_freshness(view, basis)
    view["reviewState"] = state
    view["freshness"] = freshness
    view["staleReasons"] = reasons
    view["stale"] = state == "stale"
    return view


def get_review(date: str | None = None) -> dict:
    """Read exactly one stored snapshot (or a non-persisted empty view).

    The old implementation created today's review during GET.  The Portfolio
    tab is now a reader; only the explicit generate action is allowed to write.
    """
    from features.investment_review.review_v2 import load_raw
    if date is None or str(date).strip() == "":
        latest = _load_latest()
        if not latest:
            return empty_review(_today())
        selected = normalize_review_date(latest.get("date") or _today())
        return _effective_view(latest, selected)
    selected = normalize_review_date(date)
    raw = load_raw(REVIEW_DIR, selected)
    return _effective_view(raw, selected) if raw else empty_review(selected)


def generate_review(body: dict | None = None) -> dict:
    body = body or {}
    return build_review(
        date=body.get("date"), include_portfolio=body.get("includePortfolio", True),
        include_watchlist=body.get("includeWatchlist", False), include_obsidian=body.get("includeObsidian", False),
        force_refresh=True, persist=True,
    )


def mark_reviewed(date: str, expected_review_revision: object) -> dict:
    from features.investment_review.review_v2 import mark_reviewed as _mark
    return _mark(_v2_data_dir(), REVIEW_DIR, normalize_review_date(date), expected_review_revision)


def review_history() -> dict:
    from features.investment_review.review_v2 import list_history
    return {"items": list_history(REVIEW_DIR)}
