"""RSS archive reading, filtering, feed pagination, merge export, and import."""
import datetime as dt
import os
import re
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

from features.common.utils import normalize, clean_brief_text, clean_embedded_sections, read_json
from features.common.market_calendar import MARKET_TAGGER_VERSION, infer_doc_markets
from features.common.dataframe_ops import filter_archive_records
from features.common.research_library.rss.feed_config import (
    feed_language_for_media,
    feed_market_for_media,
    feed_metadata_for_query,
)
from features.common.research_library.rss.normalizer import markets_with_feed_fallback
from features.common.research_library.rss.retention import (
    delete_expired as delete_expired_rss,
    prune_orphan_evidence,
    reclaim_index_space,
    reclaimable_bytes,
)
from features.common.research_library.indexing.service import (
    RESEARCH_DB_PATH,
    canonical_news_source,
    infer_source,
    parse_rssarchive_markdown,
    rss_item_is_market_relevant,
    build_index,
)
from features.common.workspace import data_dir, moved_pending_restart, research_inbox_dir

ROOT = Path(__file__).resolve().parents[4]
RSS_INBOX_DIR = research_inbox_dir() / "rss"
RSS_ARCHIVE_MODULE = "features.common.research_library.rss.rss_archive"

# 수집 서브프로세스 상한. 300초는 정상 실행도 못 끝낸다 — 실측으로 10일치 공백을
# 메우는 실행이 8~10분 걸렸고, 매시 자동 수집이 전부 300초에서 잘려 **한 건도 쓰지
# 못한 채** `done`으로 기록됐다(2026-08-14~24, 열흘). 잘린 실행은 파일을 남기지 않아
# 다음 실행이 같은 backlog를 다시 시도하므로 스스로 회복되지 않는다.
RSS_COLLECT_TIMEOUT_SECONDS = max(300, int(os.environ.get("RSS_COLLECT_TIMEOUT_SECONDS", "1800")))

RSS_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H-%M-%S",
)
RSS_FILENAME_TS_FORMAT = "%Y-%m-%d %H-%M-%S"
RSS_DISPLAY_TS_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_RSS_LIMIT = 200
# VACUUM은 실측 728MB 기준 12~29초 동안 DB를 잠근다. 이만큼은 돌려받아야 값을 한다.
RECLAIM_THRESHOLD_BYTES = 50_000_000
RSS_CACHE_TABLE = "rss_feed_items"
RSS_CACHE_REFRESH_TTL_SECONDS = int(os.environ.get("RSS_CACHE_REFRESH_TTL_SECONDS", "30") or 30)
_RSS_CACHE_LAST_REFRESH = 0.0
_RSS_CACHE_LAST_STATS = {"files": 0, "updated": 0, "deleted": 0, "skipped": False}
_RSS_IMPORT_LOCK = threading.Lock()


def _collection_created_count(output):
    match = re.search(r"(?m)^Done\. Created\s+(\d+)\s+file\(s\)\.", str(output or ""))
    return int(match.group(1)) if match else None


def response_tail(text, lines=30):
    rows = [line for line in str(text or "").splitlines() if line.strip()]
    return "\n".join(rows[-lines:])


def parse_feed_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in RSS_DATETIME_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_archive_filename(path):
    parts = path.stem.split(" - ", 2)
    ts_text = parts[0] if len(parts) > 0 else ""
    media = parts[1] if len(parts) > 1 else ""
    title = parts[2] if len(parts) > 2 else path.stem
    parsed = None
    if ts_text:
        try:
            parsed = dt.datetime.strptime(ts_text, RSS_FILENAME_TS_FORMAT)
        except ValueError:
            parsed = None
    return ts_text, parsed, media, title


# `infer_doc_markets`가 내는 순서. 합집합을 만들 때도 같은 순서로 되돌려, 화면과 저장값이
# 어디서 왔는지에 따라 달라지지 않게 한다.
_MARKET_TAG_ORDER = ("US", "KR", "EUROPE", "JP", "GLOBAL")


def _merge_market_tags(inferred, stored):
    """Union of fresh inference and the tag saved at collection time.

    `UNKNOWN`은 "신호 없음"이라 무엇이든 하나라도 있으면 사라진다. 둘 다 비어 있을 때만
    남고, 그 뒤에 feed 힌트가 채운다.
    """
    merged = {token for token in list(inferred or []) + list(stored or []) if token and token != "UNKNOWN"}
    ordered = [token for token in _MARKET_TAG_ORDER if token in merged]
    # 계약 밖의 값이 저장돼 있어도 버리지 않는다(예전 표기·수기 편집).
    ordered += sorted(merged - set(_MARKET_TAG_ORDER))
    return ordered or ["UNKNOWN"]


def archive_item(path):
    raw = path.read_text(encoding="utf-8", errors="replace")
    meta, body = parse_rssarchive_markdown(raw)
    ts_text, parsed_ts, media, title_from_name = parse_archive_filename(path)
    timestamp = meta.get("date", "") if meta else ""
    if timestamp and len(timestamp) == 10 and parsed_ts:
        timestamp = parsed_ts.strftime(RSS_DISPLAY_TS_FORMAT)
    elif parsed_ts and not timestamp:
        timestamp = parsed_ts.strftime(RSS_DISPLAY_TS_FORMAT)
    title = (meta or {}).get("title") or title_from_name or path.stem
    description = normalize((meta or {}).get("summary") or (meta or {}).get("description") or "")
    if not description:
        description = normalize(body.replace(f"# {title}", "", 1) if body else "")
    description = clean_brief_text(description, 520)
    configured_feed = feed_metadata_for_query((meta or {}).get("query", ""))
    resolved_source = canonical_news_source(
        (meta or {}).get("source") or media or infer_source(f"{title} {description}", path.name),
        (meta or {}).get("url", ""),
        title,
    ) or "User Archive"
    # 시장 힌트와 같은 두 단계다. 저장 자료의 83%가 `query` 없는 legacy 파일이라 feed URL
    # 조회만으로는 대부분 비어 있었다(실측 9,834행). 매체는 어느 피드에서 왔든 한 언어로
    # 쓰므로 시장과 달리 모호해지지 않는다.
    language = str(
        (meta or {}).get("language")
        or configured_feed.get("language")
        or feed_language_for_media(resolved_source)
        or ""
    ).strip().lower()
    # 저장된 태그를 `infer_doc_markets`의 입력으로 넘기지 않는다. 그러면 사다리 1단계로
    # 걸려 옛 표가 만든 태그가 그대로 메아리치고, 표를 고쳐도 저장 자료가 따라오지 않는다.
    # 대신 새로 추론한 뒤 **합집합**으로 얹는다 — 저장 태그는 수집 당시 본문 전체를 보고
    # 만들어졌으므로 버리면 정보가 준다. 실측(2026-08-09)에서 새 표는 태그를 더하기만 하고
    # 지운 적이 없어(추가 156건·손실 0건) 합집합이 재추론과 사실상 같은 결과를 낸다.
    raw_markets = (meta or {}).get("markets")
    stored = [
        str(value).strip().upper()
        for value in (raw_markets if isinstance(raw_markets, list) else str(raw_markets or "").split(","))
        if str(value).strip()
    ]
    markets = infer_doc_markets({
        "title": title,
        "summary": description,
        # 요약 520자가 아니라 본문을 넘긴다. `infer_doc_markets`가 1,600자로 자르므로
        # 수집 당시와 같은 창을 본다.
        "content": body or description,
        "url": (meta or {}).get("url", ""),
        "source": resolved_source,
    })
    markets = _merge_market_tags(markets, stored)
    # 수집 경로와 같은 사후 보정을 여기에도 둔다. 이 경로가 없어서 UNKNOWN 3,912건이
    # 재구성 때마다 그대로 살아남았다. 힌트는 두 단계로 찾는다 — 저장된 feed URL이
    # 우선이고, 없으면 매체명이다. 저장 자료의 83%가 `query` 없는 legacy 파일이라
    # URL만으로는 17%밖에 닿지 못한다. 매체가 여러 시장의 피드를 갖고 있으면
    # (Reuters·연합인포맥스) 어느 피드에서 왔는지 알 수 없으므로 추측하지 않는다.
    markets = markets_with_feed_fallback(
        markets,
        configured_feed.get("default_market") or feed_market_for_media(resolved_source),
    )
    return {
        "filename": path.name,
        "title": title,
        "timestamp": timestamp,
        "timestampSort": (parse_feed_datetime(timestamp) or parsed_ts or dt.datetime.min).isoformat(),
        "url": (meta or {}).get("url", ""),
        "normalizedUrl": (meta or {}).get("normalizedUrl", ""),
        "description": description,
        "media": resolved_source,
        "collector": (meta or {}).get("collector", ""),
        "sourceType": (meta or {}).get("sourceType", ""),
        "collectionStatus": (meta or {}).get("collectionStatus", ""),
        "reliabilityTier": (meta or {}).get("reliabilityTier", ""),
        "language": language,
        "markets": markets,
        "market": ",".join(markets),
    }


def ensure_rss_cache(conn):
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {RSS_CACHE_TABLE} (
            filename TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            title TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            timestamp_sort TEXT NOT NULL,
            url TEXT NOT NULL,
            description TEXT NOT NULL,
            media TEXT NOT NULL,
            normalized_url TEXT NOT NULL DEFAULT '',
            collector TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL DEFAULT '',
            collection_status TEXT NOT NULL DEFAULT '',
            reliability_tier TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT '',
            markets TEXT NOT NULL DEFAULT '',
            tagger_version INTEGER NOT NULL DEFAULT 0,
            visible INTEGER NOT NULL,
            parsed_at TEXT NOT NULL
        )
        """
    )
    existing_cols = {row[1] for row in conn.execute(f"PRAGMA table_info({RSS_CACHE_TABLE})").fetchall()}
    added_identity_columns = False
    for col, ddl in {
        "normalized_url": "TEXT NOT NULL DEFAULT ''",
        "collector": "TEXT NOT NULL DEFAULT ''",
        "source_type": "TEXT NOT NULL DEFAULT ''",
        "collection_status": "TEXT NOT NULL DEFAULT ''",
        "reliability_tier": "TEXT NOT NULL DEFAULT ''",
        "language": "TEXT NOT NULL DEFAULT ''",
        "markets": "TEXT NOT NULL DEFAULT ''",
        # 0은 "이 행이 어느 표로 태깅됐는지 모른다"는 뜻이라 반드시 한 번 다시 읽힌다.
        "tagger_version": "INTEGER NOT NULL DEFAULT 0",
    }.items():
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE {RSS_CACHE_TABLE} ADD COLUMN {col} {ddl}")
            if col == "language":
                added_identity_columns = True
    # 국가 필터는 없앴다. 컬럼을 지우는 것 자체보다 중요한 것은 **다시 읽게 만드는 것**이다 —
    # 언어를 선언할 수 있는 피드가 유럽·일본뿐이던 시절에 파싱된 행은 언어가 비어 있고,
    # 파일이 바뀐 적이 없어 평소 새로고침으로는 영원히 그대로다(실측 19,770행).
    #
    # 여기서 캐시를 무효화하지는 않는다. 다시 읽어야 하는지는 `tagger_version`이 행마다
    # 들고 있고, 업그레이드하면 그 컬럼이 0으로 새로 생겨 어차피 전 행이 한 번 다시
    # 읽힌다 — 언어도 그때 같이 채워진다. 여기서 또 무효화하면, `DROP COLUMN`이
    # 실패하는 DB에서(SQLite 3.35 미만이거나 인덱스·뷰가 걸린 경우) `ensure_rss_cache`가
    # 불릴 때마다, 즉 피드를 열 때마다 22,000행을 다시 읽는다.
    if "country" in existing_cols:
        conn.execute("DROP INDEX IF EXISTS idx_rss_feed_country_time")
        try:
            conn.execute(f"ALTER TABLE {RSS_CACHE_TABLE} DROP COLUMN country")
        except sqlite3.OperationalError:
            # 못 지워도 읽는 곳이 없으니 그대로 둔다. 다음 실행에서 다시 시도한다.
            pass
    if added_identity_columns:
        # Preserve every old row but force the next ordinary refresh to reparse
        # unchanged Markdown so exact feed-URL metadata can be filled in.
        conn.execute(f"UPDATE {RSS_CACHE_TABLE} SET mtime_ns = -1")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_rss_feed_visible_time ON {RSS_CACHE_TABLE}(visible, timestamp_sort DESC)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_rss_feed_source_time ON {RSS_CACHE_TABLE}(media, timestamp_sort DESC)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_rss_feed_language_time ON {RSS_CACHE_TABLE}(language, timestamp_sort DESC)")


def _repair_cached_media(conn):
    """Repair source labels written by older canonicalization rules."""
    cursor = conn.execute(
        f"""UPDATE {RSS_CACHE_TABLE}
            SET media = '연합뉴스'
            WHERE media IN ('', 'User Archive')
              AND (LOWER(url) LIKE '%yna.co.kr%' OR filename LIKE '% - 연합뉴스 - %')"""
    )
    return max(0, int(cursor.rowcount or 0))


_RSS_CACHE_MEDIA_REPAIRED = False


def _connect_cache():
    global _RSS_CACHE_MEDIA_REPAIRED
    RESEARCH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 인덱싱/수집 작업이 같은 DB에 길게 쓰는 동안에도 피드 조회가 5초 기본
    # 타임아웃으로 실패하지 않도록 대기 시간을 늘리고 WAL을 사용한다.
    conn = sqlite3.connect(str(RESEARCH_DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass  # 다른 프로세스가 쓰기 중이면 기본 저널 모드로 계속 진행한다.
    ensure_rss_cache(conn)
    # media 보정은 쓰기 잠금이 필요하므로 프로세스당 1회만 시도하고,
    # 잠금 충돌 시 조회 경로를 막지 않고 다음 연결에서 재시도한다.
    if not _RSS_CACHE_MEDIA_REPAIRED:
        try:
            if _repair_cached_media(conn):
                conn.commit()
            _RSS_CACHE_MEDIA_REPAIRED = True
        except sqlite3.OperationalError:
            pass
    return conn


def _archive_item_for_cache(path):
    item = archive_item(path)
    visible = rss_item_is_market_relevant(item["title"], item["description"], item["url"])
    return item, visible


def _row_to_item(row):
    return {
        "filename": row["filename"],
        "title": row["title"],
        "timestamp": row["timestamp"],
        "timestampSort": row["timestamp_sort"],
        "url": row["url"],
        "normalizedUrl": row["normalized_url"],
        # 캐시는 파일 mtime 기준 증분 갱신이라, 과거에 오염된 설명이 남아 있을 수 있어
        # 읽는 시점에 임베디드 섹션 마커를 정리한다.
        "description": clean_brief_text(clean_embedded_sections(row["description"]), 520),
        "media": row["media"],
        "collector": row["collector"],
        "sourceType": row["source_type"],
        "collectionStatus": row["collection_status"],
        "reliabilityTier": row["reliability_tier"],
        "language": row["language"],
        "markets": [token for token in str(row["markets"] or "").split(",") if token],
        "market": row["markets"],
    }


def _rss_row_dedupe_key(row):
    normalized_url = str(row["normalized_url"] or "").strip().lower()
    url = str(row["url"] or "").strip().lower()
    if normalized_url:
        return f"url:{normalized_url}"
    if url:
        return f"url:{url}"
    title = " ".join(str(row["title"] or "").strip().lower().split())
    media = " ".join(str(row["media"] or "").strip().lower().split())
    description = " ".join(str(row["description"] or "").strip().lower().split())[:180]
    return f"text:{media}:{title}:{description}"


def _dedupe_rss_rows(rows):
    seen = set()
    deduped = []
    for row in rows:
        key = _rss_row_dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _cache_table_exists():
    if not RESEARCH_DB_PATH.exists():
        return False
    try:
        with sqlite3.connect(str(RESEARCH_DB_PATH), timeout=30) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (RSS_CACHE_TABLE,),
            ).fetchone()
            return bool(row)
    except Exception:
        return False


def refresh_rss_feed_cache(progress=None, force=False):
    """Incrementally sync RSS Markdown metadata into research-index.sqlite3.

    The feed UI needs only metadata and a short description. Reading every
    Markdown file on each page request gets slow as the archive grows, so this
    cache reparses only new/changed files and lets feed pagination run in SQL.
    """
    global _RSS_CACHE_LAST_REFRESH, _RSS_CACHE_LAST_STATS
    now_ts = dt.datetime.now().timestamp()
    if (
        not force
        and _RSS_CACHE_LAST_REFRESH
        and now_ts - _RSS_CACHE_LAST_REFRESH < RSS_CACHE_REFRESH_TTL_SECONDS
        and _cache_table_exists()
    ):
        return {**_RSS_CACHE_LAST_STATS, "skipped": True}

    if not RSS_INBOX_DIR.exists():
        _RSS_CACHE_LAST_REFRESH = now_ts
        _RSS_CACHE_LAST_STATS = {"files": 0, "updated": 0, "deleted": 0, "skipped": False}
        return {"files": 0, "updated": 0, "deleted": 0}

    files = [p for p in RSS_INBOX_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".md"]
    by_name = {p.name: p for p in files}
    now = dt.datetime.now().isoformat(timespec="seconds")
    updated = 0
    deleted = 0
    with _connect_cache() as conn:
        existing = {
            row["filename"]: row
            for row in conn.execute(
                f"SELECT filename, size, mtime_ns, tagger_version FROM {RSS_CACHE_TABLE}"
            )
        }
        missing = set(existing) - set(by_name)
        for filename in missing:
            conn.execute(f"DELETE FROM {RSS_CACHE_TABLE} WHERE filename = ?", (filename,))
            deleted += 1
        for idx, path in enumerate(files, 1):
            stat = path.stat()
            previous = existing.get(path.name)
            # 파일이 그대로여도 태깅 표가 바뀌었으면 다시 읽는다. 파일 변경만 보던
            # 시절에는 표를 고쳐도 이미 저장된 자료가 옛 태그로 남았다.
            if (
                previous
                and int(previous["size"]) == stat.st_size
                and int(previous["mtime_ns"]) == stat.st_mtime_ns
                and int(previous["tagger_version"] or 0) == MARKET_TAGGER_VERSION
            ):
                continue
            try:
                item, visible = _archive_item_for_cache(path)
            except Exception:
                ts_text, parsed_ts, media, title_from_name = parse_archive_filename(path)
                timestamp = parsed_ts.strftime(RSS_DISPLAY_TS_FORMAT) if parsed_ts else ts_text
                item = {
                    "filename": path.name,
                    "title": title_from_name or path.stem,
                    "timestamp": timestamp,
                    "timestampSort": (parsed_ts or dt.datetime.min).isoformat(),
                    "url": "",
                    "description": "",
                    "media": canonical_news_source(media, "", title_from_name) or media or "User Archive",
                    "language": "",
                }
                visible = False
            conn.execute(
                f"""
                INSERT INTO {RSS_CACHE_TABLE}
                    (filename, path, size, mtime_ns, title, timestamp, timestamp_sort, url, description, media,
                     normalized_url, collector, source_type, collection_status, reliability_tier, language,
                     markets, tagger_version, visible, parsed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(filename) DO UPDATE SET
                    path=excluded.path,
                    size=excluded.size,
                    mtime_ns=excluded.mtime_ns,
                    title=excluded.title,
                    timestamp=excluded.timestamp,
                    timestamp_sort=excluded.timestamp_sort,
                    url=excluded.url,
                    description=excluded.description,
                    media=excluded.media,
                    normalized_url=excluded.normalized_url,
                    collector=excluded.collector,
                    source_type=excluded.source_type,
                    collection_status=excluded.collection_status,
                    reliability_tier=excluded.reliability_tier,
                    language=excluded.language,
                    markets=excluded.markets,
                    tagger_version=excluded.tagger_version,
                    visible=excluded.visible,
                    parsed_at=excluded.parsed_at
                """,
                (
                    path.name,
                    str(path),
                    stat.st_size,
                    stat.st_mtime_ns,
                    item.get("title", ""),
                    item.get("timestamp", ""),
                    item.get("timestampSort", ""),
                    item.get("url", ""),
                    item.get("description", ""),
                    item.get("media", ""),
                    item.get("normalizedUrl", ""),
                    item.get("collector", ""),
                    item.get("sourceType", ""),
                    item.get("collectionStatus", ""),
                    str(item.get("reliabilityTier", "")),
                    item.get("language", ""),
                    ",".join(item.get("markets") or []),
                    MARKET_TAGGER_VERSION,
                    1 if visible else 0,
                    now,
                ),
            )
            updated += 1
            # 대량 변경(예: 아카이브 일괄 수리) 시 쓰기 잠금을 오래 붙잡지 않도록
            # 주기적으로 커밋해 다른 요청이 끼어들 수 있게 한다.
            if updated % 200 == 0:
                conn.commit()
            if progress and updated % 250 == 0:
                progress(f"RSS 피드 캐시 갱신 중입니다. {idx}/{len(files)}개 확인", progress=70)
        conn.commit()
    _RSS_CACHE_LAST_REFRESH = now_ts
    _RSS_CACHE_LAST_STATS = {"files": len(files), "updated": updated, "deleted": deleted, "skipped": False}
    return dict(_RSS_CACHE_LAST_STATS)


def rss_archive_file_visible(path):
    item = archive_item(path)
    return rss_item_is_market_relevant(item["title"], item["description"], item["url"])


def list_archive_files():
    if not RSS_INBOX_DIR.exists():
        return []
    files = [p for p in RSS_INBOX_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".md"]
    files.sort(key=lambda p: parse_archive_filename(p)[1] or dt.datetime.min, reverse=True)
    return files


def normalize_feed_range(qs):
    start_value = qs.get("start", [""])[0].strip()
    end_value = qs.get("end", [""])[0].strip()
    start_dt = parse_feed_datetime(start_value)
    end_dt = parse_feed_datetime(end_value)
    if end_dt and re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}$", end_value):
        end_dt = end_dt + dt.timedelta(seconds=59)
    return start_value, end_value, start_dt, end_dt


def archive_media(path):
    item = archive_item(path)
    media = item.get("media", "")
    return "" if media == "User Archive" and "연합뉴스" in path.stem else media


def _normalize_market_filter(value):
    token = str(value or "").strip().upper()
    if token == "EU":  # 경계 alias만 받고 저장/조회값은 EUROPE다.
        token = "EUROPE"
    return token if token in {"US", "KR", "EUROPE", "JP", "GLOBAL", "UNKNOWN"} else ""


# 보도자료 와이어(PR Newswire, GlobeNewswire)는 RSS 피드 화면에 노출하지 않는다.
# 기업이 직접 낸 1차 자료라 매체 교차 확인이 없고 발행량이 많아, 목록을 훑는 화면에서는
# 뉴스를 밀어낸다. 수집·인덱싱은 그대로 두어 워치리스트 종목 뉴스와 기업분석 보조자료로
# 계속 쓰인다. 목록과 출처 드롭다운이 같은 조건을 쓰도록 상수로 공유한다.
_HIDE_PRESS_RELEASE_SQL = "(source_type IS NULL OR source_type != 'press_release')"


def _configured_source_names() -> set[str]:
    """현재 `config/rss_feeds.yaml`에서 수집 중인 매체 이름.

    aggregating 피드는 `only_publishers`로 원 발행처 이름을 다시 태그하므로
    (Yahoo Finance -> Reuters) 그 이름도 함께 허용한다.
    """
    from features.common.config_bootstrap import resolve_config
    from features.common.research_library.rss.feed_config import load_rss_feeds

    names: set[str] = set()
    for feed in load_rss_feeds(resolve_config("rss_feeds.yaml")):
        publishers = [str(row).strip() for row in feed.get("only_publishers") or [] if str(row).strip()]
        if publishers:
            names.update(publishers)
        else:
            media = str(feed.get("media") or "").strip()
            if media:
                names.add(media)
    return names


def _selectable_sources(rows) -> list[str]:
    """드롭다운에 남길 출처.

    수집 경로가 사라진 매체(피드를 지웠거나 이름이 바뀐 경우)는 고를 수 있어도
    새 항목이 늘지 않아 사용자를 오도한다. 과거 항목은 목록에 그대로 보이되
    필터 대상에서만 뺀다. 설정을 읽지 못하면 기존 동작대로 전부 노출한다.
    """
    names = [str(row["media"]).strip() for row in rows if str(row["media"] or "").strip()]
    try:
        configured = _configured_source_names()
    except Exception:
        return names
    if not configured:
        return names
    return [name for name in names if name in configured]


def _scope_visibility_sql():
    """관심 시장 범위의 SQL 절.

    태그가 비었거나 GLOBAL/UNKNOWN이 섞인 항목은 항상 보인다. 시장 토큰은
    서로의 부분 문자열이 아니므로(US/KR/EUROPE/JP/GLOBAL/UNKNOWN) LIKE로 안전하다.
    """
    from features.common.market_scope import ALWAYS_VISIBLE, load_market_scope

    allowed = list(load_market_scope()["selected"]) + list(ALWAYS_VISIBLE)
    clauses = ["markets = ''"]
    params: list = []
    for token in allowed:
        clauses.append("(markets = ? OR markets LIKE ? OR markets LIKE ? OR markets LIKE ?)")
        params.extend([token, f"{token},%", f"%,{token},%", f"%,{token}"])
    return "(" + " OR ".join(clauses) + ")", params


def _cache_where(start_dt=None, end_dt=None, source="", market="", language=""):
    clauses = ["visible = 1", _HIDE_PRESS_RELEASE_SQL]
    params = []
    if start_dt:
        clauses.append("timestamp_sort >= ?")
        params.append(start_dt.isoformat())
    if end_dt:
        clauses.append("timestamp_sort <= ?")
        params.append(end_dt.isoformat())
    if source:
        clauses.append("media = ?")
        params.append(str(source).strip())
    market = _normalize_market_filter(market)
    if market:
        clauses.append("(markets = ? OR markets LIKE ? OR markets LIKE ? OR markets LIKE ?)")
        params.extend([market, f"{market},%", f"%,{market},%", f"%,{market}"])
    scope_sql, scope_params = _scope_visibility_sql()
    clauses.append(scope_sql)
    params.extend(scope_params)
    # 유럽은 6개국이 한 시장으로 묶이므로, 국가 필터가 없으면 독일 기사만 보는 방법이
    # 없다. 언어는 원문을 읽을 수 있는 항목만 추릴 때 쓴다.
    language = str(language or "").strip().lower()
    if language:
        clauses.append("language = ?")
        params.append(language)
    return " AND ".join(clauses), params


def rss_cache_files(start_dt=None, end_dt=None, source="", market="", limit=None, offset=0, language=""):
    refresh_rss_feed_cache()
    where, params = _cache_where(start_dt, end_dt, source, market, language)
    sql = f"SELECT filename FROM {RSS_CACHE_TABLE} WHERE {where} ORDER BY timestamp_sort DESC, filename DESC"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = [*params, int(limit), int(offset)]
    with _connect_cache() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [RSS_INBOX_DIR / row["filename"] for row in rows]


def filter_archive_files(files, start_dt=None, end_dt=None, source=""):
    # Kept for older callers/tests. The feed API uses rss_cache_files().
    source = str(source or "").strip()
    records = []
    for idx, path in enumerate(files):
        entry_dt = parse_archive_filename(path)[1]
        records.append({
            "_idx": idx,
            "path": path,
            "timestampSort": entry_dt.isoformat() if entry_dt else "",
            "source": archive_media(path),
        })
    filtered = filter_archive_records(
        records,
        start_iso=start_dt.isoformat() if start_dt else "",
        end_iso=end_dt.isoformat() if end_dt else "",
        source=source,
    )
    return [row["path"] for row in filtered]


def rss_available_sources(files):
    refresh_rss_feed_cache()
    with _connect_cache() as conn:
        rows = conn.execute(
            f"SELECT DISTINCT media FROM {RSS_CACHE_TABLE} "
            f"WHERE visible = 1 AND media != '' AND {_HIDE_PRESS_RELEASE_SQL} ORDER BY media"
        ).fetchall()
    return _selectable_sources(rows)


def rss_feed_payload(qs):
    offset = max(0, int(qs.get("offset", [0])[0] or 0))
    limit = int(qs.get("limit", [50])[0] or 50)
    limit = min(max(limit, 1), MAX_RSS_LIMIT)
    _, _, start_dt, end_dt = normalize_feed_range(qs)
    source = qs.get("source", [""])[0].strip()
    market = _normalize_market_filter(qs.get("market", [""])[0])
    language = qs.get("language", [""])[0].strip().lower()
    cache_stats = refresh_rss_feed_cache()
    where, params = _cache_where(start_dt, end_dt, source, market, language)
    with _connect_cache() as conn:
        rows = conn.execute(
            f"""
            SELECT filename, title, timestamp, timestamp_sort, url, normalized_url, description, media,
                   collector, source_type, collection_status, reliability_tier, language, markets
            FROM {RSS_CACHE_TABLE}
            WHERE {where}
            ORDER BY timestamp_sort DESC, filename DESC
            """,
            params,
        ).fetchall()
        source_rows = conn.execute(
            f"SELECT DISTINCT media FROM {RSS_CACHE_TABLE} "
            f"WHERE visible = 1 AND media != '' AND {_HIDE_PRESS_RELEASE_SQL} ORDER BY media"
        ).fetchall()
        # 선택지는 출처처럼 필터를 타지 않은 질의에서 만든다. 필터 결과에서 뽑으면
        # de를 고른 순간 목록이 de 하나가 되어 다른 언어로 되돌아갈 방법이 사라진다.
        language_rows = conn.execute(
            f"SELECT DISTINCT language FROM {RSS_CACHE_TABLE} "
            f"WHERE visible = 1 AND language != '' AND {_HIDE_PRESS_RELEASE_SQL} ORDER BY language"
        ).fetchall()
    deduped_rows = _dedupe_rss_rows(rows)
    total = len(deduped_rows)
    page_rows = deduped_rows[offset:offset + limit]
    return {
        "items": [_row_to_item(row) for row in page_rows],
        "offset": offset,
        "limit": limit,
        "total": total,
        "sources": _selectable_sources(source_rows),
        "source": source,
        "market": market,
        "language": language,
        "markets": ["US", "KR", "EUROPE", "JP", "GLOBAL", "UNKNOWN"],
        "languages": sorted({str(row["language"]) for row in language_rows if str(row["language"] or "")}),
        "has_more": offset + limit < total,
        "cache": cache_stats,
    }


def rss_merge_payload(qs):
    start_value, end_value, start_dt, end_dt = normalize_feed_range(qs)
    source = qs.get("source", [""])[0].strip()
    market = _normalize_market_filter(qs.get("market", [""])[0])
    # 내려받는 병합 파일이 화면에 보이는 목록과 같은 범위여야 한다.
    language = qs.get("language", [""])[0].strip().lower()
    files = rss_cache_files(start_dt, end_dt, source, market, language=language)
    if start_dt and end_dt:
        filename = f"archive-{start_dt:%Y%m%d-%H%M}_to_{end_dt:%Y%m%d-%H%M}.md"
        range_label = f"{start_value.replace('T', ' ')} to {end_value.replace('T', ' ')}"
    elif start_dt:
        filename = f"archive-from-{start_dt:%Y%m%d-%H%M}.md"
        range_label = f"From {start_value.replace('T', ' ')}"
    elif end_dt:
        filename = f"archive-until-{end_dt:%Y%m%d-%H%M}.md"
        range_label = f"Up to {end_value.replace('T', ' ')}"
    else:
        filename = "archive-all.md"
        range_label = "All time"
    chunks = [
        "# Archive Export",
        f"- Generated: {dt.datetime.now().strftime(RSS_DISPLAY_TS_FORMAT)}",
        f"- Range: {range_label}",
        f"- Items: {len(files)}",
        "",
    ]
    body = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            body.append(text)
    return filename, "\n".join(chunks) + "\n" + "\n\n---\n\n".join(body) + "\n"


def rss_save_full_text_enabled():
    """앱 트리거 수집이 기사 전문을 저장할지 여부 (설정 탭 자동화 > RSS 수집).

    automation 모듈은 이 모듈을 import하므로 순환을 피해 설정 파일을 직접 읽는다.
    """
    settings = read_json(data_dir() / "automation-settings.json", {})
    rss_cfg = settings.get("rss") if isinstance(settings, dict) else {}
    if not isinstance(rss_cfg, dict):
        rss_cfg = {}
    return bool(rss_cfg.get("saveFullText", True))


def rss_retention_days():
    """보관 기간 (설정 탭 자동화 > RSS 수집). saveFullText와 같은 이유로 파일을 직접 읽는다."""
    from features.common.research_library.rss.retention import normalize_days

    settings = read_json(data_dir() / "automation-settings.json", {})
    rss_cfg = settings.get("rss") if isinstance(settings, dict) else {}
    if not isinstance(rss_cfg, dict):
        rss_cfg = {}
    return normalize_days(rss_cfg.get("retentionDays"))


# 옮기기 직후(재시작 전)에 수집·정리가 하는 일을 사용자에게 그대로 말한다. 조용히
# 건너뛰면 자동 수집이 도는 줄 알고 며칠을 보낸다.
WORKSPACE_MOVED_MESSAGE = (
    "자료 위치를 옮겼습니다. 서버를 재시작하기 전까지는 RSS 수집과 보관 기간 정리를 "
    "실행하지 않습니다 — 지금 수집하면 새 자료가 옛 폴더와 새 폴더로 갈립니다."
)


def _workspace_moved_skip():
    return {
        "output": WORKSPACE_MOVED_MESSAGE,
        "added": 0,
        "total": len(list(RSS_INBOX_DIR.glob("*.md"))) if RSS_INBOX_DIR.exists() else 0,
        "skipped": "workspace_moved",
        "cache": {},
        "retention": {"deleted": 0, "skipped": "workspace_moved"},
        "index": {},
    }


def _import_rssarchive_locked(run_collection=True, progress=None, extra_args=None):
    if moved_pending_restart():
        # 수집 서브프로세스는 표지를 읽어 **새** 폴더의 evidence DB에 쓰는데, 여기서
        # 넘기는 `--archive-dir`(RSS_INBOX_DIR)은 import 시점에 굳은 **옛** 폴더다.
        # 재시작 후에는 새 폴더만 읽으므로 이 창에서 모은 기사는 파일 없는 행으로만
        # 남아 색인·브리핑에서 사라진다.
        if progress:
            progress(WORKSPACE_MOVED_MESSAGE, progress=100)
        return _workspace_moved_skip()
    output = []
    before = len(list(RSS_INBOX_DIR.glob("*.md")))
    collector_created = None
    collection_error = ""
    if progress:
        progress(f"RSS 수집 준비 중입니다. 기존 RSS 파일 {before}개", progress=5)
    if run_collection:
        try:
            if progress:
                progress("RSS 피드를 수집하는 중입니다.", progress=12)
            _cf = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            command = [sys.executable, "-m", RSS_ARCHIVE_MODULE, "--archive-dir", str(RSS_INBOX_DIR), "--collectors", "rss"]
            if rss_save_full_text_enabled():
                command.append("--save-full-text")
            if extra_args:
                command.extend(str(v) for v in extra_args)
            proc = subprocess.run(
                command,
                cwd=str(ROOT), text=True, encoding="utf-8", errors="replace",
                capture_output=True, timeout=RSS_COLLECT_TIMEOUT_SECONDS,
                creationflags=_cf,
            )
            if proc.stdout.strip():
                output.append(proc.stdout.strip())
                collector_created = _collection_created_count(proc.stdout)
            if proc.stderr.strip():
                output.append(proc.stderr.strip())
        except subprocess.TimeoutExpired:
            collection_error = "timeout"
            output.append(
                f"RSS collection timed out after {RSS_COLLECT_TIMEOUT_SECONDS}s. "
                "RSS_COLLECT_TIMEOUT_SECONDS로 상한을 늘릴 수 있습니다."
            )
        except Exception as exc:
            # 이유를 버리면 왜 안 되는지 알 길이 없다. 예외 종류는 코드 식별자라
            # 사용자 자료가 아니다 — 원문 메시지는 담지 않는다.
            collection_error = type(exc).__name__
            output.append(f"RSS collection failed ({collection_error}).")
    after = len(list(RSS_INBOX_DIR.glob("*.md")))
    added = collector_created if collector_created is not None else max(after - before, 0)
    output.append(f"RSS collection finished. Added {added}, total {after}.")
    output.append(f"RSS folder: {RSS_INBOX_DIR}")
    # 보관 기간이 지난 파일은 여기서 지운다. 바로 뒤의 캐시 갱신과 재색인이 남은 행을
    # 걷어내므로 정리 비용이 따로 들지 않는다 — 정리 전용 재색인을 한 번 더 돌리면
    # 수집 때마다 같은 일을 두 번 하게 된다.
    retention = delete_expired_rss(rss_retention_days())
    if retention.get("deleted"):
        after -= retention["deleted"]
        output.append(
            f"Retention removed {retention['deleted']} files older than {retention['days']} days."
        )
        if progress:
            progress(f"보관 기간({retention['days']}일)이 지난 {retention['deleted']}개를 정리했습니다.", progress=58)
    if progress:
        progress(f"RSS 수집 완료: 신규 {added}개, 총 {after}개. 피드 캐시를 갱신합니다.", progress=62)
    cache = refresh_rss_feed_cache(progress=progress, force=True)
    if progress:
        progress(f"RSS 피드 캐시 갱신 완료: 변경 {cache.get('updated', 0)}개, 삭제 {cache.get('deleted', 0)}개. 인덱스를 갱신합니다.", progress=68)
    index = build_index(incremental=True, progress=progress)
    if retention.get("deleted"):
        # 인덱서도 피드 캐시도 evidence 표는 건드리지 않는다. 재색인 뒤에 정리해야
        # 파일이 사라진 행만 정확히 남는다.
        retention["evidencePruned"] = prune_orphan_evidence()
    # 한국 lead 승격은 이미 수집한 evidence 행을 다시 읽을 뿐 네트워크도 자격증명도
    # 쓰지 않는다. 이 호출이 lead 보존 기간(3/14/30일)을 집행하는 유일한 경로이므로
    # automation kind rss에만 두면 수동 수집·시장 재개 수집에서는 lead가 무기한 쌓인다.
    try:
        from features.common.research_library.signals.runtime import promote_kr_rss_leads

        promote_kr_rss_leads(data_dir())
    except Exception:
        pass
    try:
        from features.dashboard.story_share import invalidate_story_share_cache

        invalidate_story_share_cache()
    except Exception:
        pass
    return {
        "output": "\n".join(output),
        "collection": {"ok": not collection_error, "error": collection_error},
        "added": added,
        "total": after,
        "cache": cache,
        "retention": retention,
        "index": {"count": index.get("count", 0), "generatedAt": index.get("generatedAt", ""), "incremental": index.get("incremental", {})},
    }


def collect_markets_now(markets, progress=None):
    """방금 켠 시장의 피드만 즉시, 나이 제한 없이 수집한다.

    RSS는 피드가 내어주는 최근 항목까지만 받을 수 있다. 꺼져 있던 기간의
    공백을 완전히 메우지는 못하므로, 받을 수 있는 것을 최대한 받는 통로다.
    """
    from features.common.market_scope import normalize_selected

    wanted = normalize_selected(markets)
    if not wanted:
        return {"ok": False, "message": "수집할 시장이 없습니다."}
    with _RSS_IMPORT_LOCK:
        return _import_rssarchive_locked(
            run_collection=True,
            progress=progress,
            extra_args=["--only-markets", ",".join(wanted), "--max-age-days", "0"],
        )


def import_rssarchive(run_collection=True, progress=None):
    # 자동화, 브리핑 prerequisite, 수동 버튼이 같은 저장소를 공유한다.
    # 한 번에 하나만 실행해 dedupe state와 실행별 신규 개수를 안정적으로 유지한다.
    with _RSS_IMPORT_LOCK:
        return _import_rssarchive_locked(run_collection=run_collection, progress=progress, extra_args=None)


def run_retention_now(progress=None):
    """설정 화면의 `지금 정리`. 수집 없이 정리만 하고 파일 크기까지 줄인다.

    VACUUM은 **여기서만** 한다. 실측 728MB 기준 29초 동안 DB를 통째로 잠그므로,
    매시간 도는 수집이 파일 하나를 지웠다고 매번 물릴 수 없다. 자동 수집은 지운
    자리를 SQLite가 재사용하게 두어 크기를 묶어 두고, 실제로 파일을 줄이는 일은
    사용자가 부를 때 한다.
    """
    with _RSS_IMPORT_LOCK:
        if moved_pending_restart():
            # 정리 대상은 호출 시점에 판정한 **새** 폴더(방금 복사한 사본)인데, 이
            # 프로세스의 색인과 피드 캐시는 옛 폴더를 본다. 그대로 지우면 옮겨 놓은
            # 자료가 줄어든다.
            if progress:
                progress(WORKSPACE_MOVED_MESSAGE, progress=100)
            return {
                "retention": {"deleted": 0, "skipped": "workspace_moved"},
                "skipped": "workspace_moved",
                "output": WORKSPACE_MOVED_MESSAGE,
            }
        days = rss_retention_days()
        if progress:
            progress("보관 기간이 지난 RSS 자료를 확인하는 중입니다.", progress=5)
        removed = delete_expired_rss(days)
        if not removed.get("deleted"):
            # 지울 것이 없어도 돌려받을 공간은 있을 수 있다 — 임베딩을 blob으로 바꾸면
            # 실측 728MB에서 348MB가 빈 페이지로 남는다. 재색인은 건너뛰고 회수만 한다.
            spare = reclaimable_bytes()
            if spare < RECLAIM_THRESHOLD_BYTES:
                if progress:
                    progress("보관 기간이 지난 자료가 없고 돌려받을 공간도 없습니다.", progress=100)
                return {"retention": removed, "skipped": True}
            if progress:
                progress(f"지울 자료는 없지만 검색 색인에서 {spare // 1_000_000}MB를 돌려받습니다.", progress=40)
            removed["reclaimed"] = reclaim_index_space()
            return {"retention": removed, "skipped": False}
        if progress:
            progress(f"{removed['deleted']}개를 지웠습니다. 피드 캐시와 색인을 다시 만듭니다.", progress=20)
        cache = refresh_rss_feed_cache(progress=progress, force=True)
        index = build_index(incremental=True, progress=progress)
        removed["evidencePruned"] = prune_orphan_evidence()
        if progress:
            progress("검색 색인 파일 크기를 줄이는 중입니다. 1분 정도 걸릴 수 있습니다.", progress=88)
        removed["reclaimed"] = reclaim_index_space()
        try:
            from features.dashboard.story_share import invalidate_story_share_cache

            invalidate_story_share_cache()
        except Exception:
            pass
        return {
            "retention": removed,
            "skipped": False,
            "cache": cache,
            "index": {"count": index.get("count", 0), "generatedAt": index.get("generatedAt", "")},
        }
