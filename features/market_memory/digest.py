from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

from features.common.utils import kst_date, now_iso
from features.market_memory.memory import upsert_memory
from features.common.workspace import data_dir

ROOT = Path(__file__).resolve().parents[2]
MARKET_MEMORY_DB_PATH = data_dir() / "market-memory.sqlite3"

AXES = {
    "ai_semiconductor_supply_chain": {
        "label": "AI 반도체 공급망",
        "terms": ("ai", "nvidia", "hbm", "gpu", "semiconductor", "chip", "반도체", "하이닉스", "삼성전자"),
        "tags": ["AI", "Semiconductors"],
    },
    "ai_data_center_power_bottleneck": {
        "label": "AI 데이터센터 전력 병목",
        "terms": ("power", "grid", "data center", "utility", "전력", "데이터센터", "전선", "구리"),
        "tags": ["AI", "Energy"],
    },
    "rates_dollar_liquidity": {
        "label": "금리·달러 유동성",
        "terms": ("fed", "rate", "yield", "bond", "dollar", "금리", "국채", "달러", "환율"),
        "tags": ["금리", "환율"],
    },
    "middle_east_energy_risk": {
        "label": "중동 에너지 리스크",
        "terms": ("oil", "iran", "hormuz", "middle east", "crude", "유가", "중동", "이란", "호르무즈"),
        "tags": ["Energy"],
    },
    "korea_semiconductor_exports_fx_sensitivity": {
        "label": "한국 반도체 수출 수혜와 원화·수급 긴장",
        "terms": ("korea", "kospi", "krw", "export", "한국", "코스피", "원화", "수출", "반도체"),
        "tags": ["Semiconductors", "환율"],
    },
}


def _text(item: dict) -> str:
    return " ".join(str(item.get(key, "")) for key in ("title", "description", "summary", "media")).lower()


def _source(item: dict) -> dict:
    return {
        "title": str(item.get("title", ""))[:220],
        "source": str(item.get("media") or item.get("source") or "")[:80],
        "date": str(item.get("timestamp") or item.get("date") or "")[:30],
        "url": str(item.get("url", ""))[:500],
    }


def _matches_term(text: str, term: str) -> bool:
    term = term.lower()
    if re.fullmatch(r"[a-z0-9]+", term):
        return bool(re.search(rf"\b{re.escape(term)}\b", text))
    return term in text


def build_rss_digest(items: list[dict], *, limit: int = 12) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for item in items or []:
        hay = _text(item)
        for key, spec in AXES.items():
            if any(_matches_term(hay, term) for term in spec["terms"]):
                buckets[key].append(item)
                break
    digest = []
    for key, rows in buckets.items():
        spec = AXES[key]
        publishers = sorted({
            str(row.get("media") or row.get("source") or "").strip()
            for row in rows
            if str(row.get("media") or row.get("source") or "").strip()
        })
        sources = [_source(row) for row in rows[:6]]
        promotion = len(sources) >= 2 and len(publishers) >= 2
        digest.append({
            "stateKey": key,
            "stateLabel": spec["label"],
            "summary": f"{spec['label']} 관련 신호가 {len(sources)}개 자료에서 관찰됐다.",
            "sourceCount": len(sources),
            "publishers": publishers,
            "sources": sources,
            "tags": spec["tags"],
            "promotionCandidate": promotion,
        })
    digest.sort(key=lambda row: (row["promotionCandidate"], row["sourceCount"], len(row["publishers"])), reverse=True)
    return digest[: int(limit or 12)]


def promote_digest_items(digest_items: list[dict], *, date: str = "") -> list[dict]:
    date = date or kst_date()
    promoted = []
    for item in digest_items or []:
        if not item.get("promotionCandidate"):
            continue
        promoted.append({
            "date": date,
            "asOf": now_iso(),
            "title": f"{item['stateLabel']} RSS 단기 신호",
            "summary": item["summary"],
            "story": item["stateKey"],
            "storyFamily": item["stateLabel"],
            "storyThesis": item["summary"],
            "storyCheckpoint": "후속 가격 반응, 거래대금, 수급, 기업 가이던스 변화를 확인",
            "stateKey": item["stateKey"],
            "stateLabel": item["stateLabel"],
            "parentStory": item["stateKey"],
            "storyRelation": "same_family",
            "stateBias": "neutral",
            "category": "stock_bond",
            "region": "GLOBAL",
            "importance": "medium",
            "entryMode": "issue",
            "eventKind": "industry_trend",
            "sourceKind": "rss_digest",
            "tags": item.get("tags", []),
            "sources": item.get("sources", []),
            "dedupeKey": f"rss_digest:{date}:{item['stateKey']}",
        })
    return promoted


def run_rss_market_memory_update(date: str = "", items: list[dict] | None = None, *, refresh_regimes: bool = True) -> dict:
    if items is None:
        from features.common.research_library.rss.service import rss_feed_payload
        payload = rss_feed_payload({"limit": ["200"], "offset": ["0"]})
        items = payload.get("items", [])
    digest = build_rss_digest(items or [])
    promoted = promote_digest_items(digest, date=date or kst_date())
    saved = [upsert_memory(MARKET_MEMORY_DB_PATH, entry) for entry in promoted]
    # 활성/관찰 상태의 추세·근거 카운트는 규칙 기반으로 함께 갱신한다.
    # 화면에서 상태별 수동 갱신 버튼을 없앤 대신 이 경로가 자동으로 처리한다.
    regime_refresh = {"ok": False, "count": 0}
    # 저장해 둔 "다음 확인"을 새 근거와 대조한다. 규칙 기반이라 LLM 호출이 없고,
    # 근거 행이 방금 갱신된 뒤라야 대조할 것이 있으므로 추세 갱신 뒤에 돈다.
    checkpoint_verdicts = {"ok": False, "checkpointCount": 0, "changeCount": 0}
    thesis_verdicts = {"ok": False, "indexLoaded": False, "checkpointCount": 0, "changeCount": 0}
    if refresh_regimes:
        try:
            from features.market_memory.regime_v2 import refresh_all_regimes
            result = refresh_all_regimes(MARKET_MEMORY_DB_PATH)
            regime_refresh = {"ok": bool(result.get("ok")), "count": int(result.get("count") or 0)}
        except Exception:
            regime_refresh = {"ok": False, "count": 0, "error": "regime_refresh_failed"}
        try:
            from features.market_memory.checkpoint_verdicts import run_checkpoint_verdicts
            verdicts = run_checkpoint_verdicts(MARKET_MEMORY_DB_PATH)
            checkpoint_verdicts = {
                "ok": bool(verdicts.get("ok")),
                "checkpointCount": int(verdicts.get("checkpointCount") or 0),
                "changeCount": int(verdicts.get("changeCount") or 0),
            }
        except Exception:
            checkpoint_verdicts = {
                "ok": False, "checkpointCount": 0, "changeCount": 0,
                "error": "checkpoint_verdicts_failed",
            }
        # thesis 체크포인트는 같은 자리에서, 다른 풀(연구 인덱스 문서)로 판정한다.
        # 대상이 0건이면 인덱스를 열지 않으므로 기본 비용이 없다.
        try:
            from features.thesis_tracking.checkpoint_verdicts import run_thesis_checkpoint_verdicts
            thesis_result = run_thesis_checkpoint_verdicts(MARKET_MEMORY_DB_PATH)
            thesis_verdicts = {
                "ok": bool(thesis_result.get("ok")),
                "indexLoaded": bool(thesis_result.get("indexLoaded")),
                "checkpointCount": int(thesis_result.get("checkpointCount") or 0),
                "changeCount": int(thesis_result.get("changeCount") or 0),
            }
        except Exception:
            # 판정 실패가 수집 잡을 죽이지 않는다.
            thesis_verdicts = {
                "ok": False, "indexLoaded": False, "checkpointCount": 0, "changeCount": 0,
                "error": "thesis_checkpoint_verdicts_failed",
            }
    return {
        "ok": True,
        "digestCount": len(digest),
        "promotedCount": len(promoted),
        "saved": saved,
        "digest": digest,
        "regimeRefresh": regime_refresh,
        "checkpointVerdicts": checkpoint_verdicts,
        "thesisCheckpointVerdicts": thesis_verdicts,
    }
