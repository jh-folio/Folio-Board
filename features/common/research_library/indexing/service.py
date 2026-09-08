"""Document parsing, indexing pipeline, and market-relevance classification."""
import datetime as dt
import hashlib
import json
import re
import sqlite3
import threading
import time
from pathlib import Path

from features.common.utils import (
    clean_embedded_sections,
    normalize,
    now_iso,
    read_json,
    summarize,
    url_host_matches,
    write_json,
)
from features.common.taxonomy import normalize_tag
from features.common.company_lookup import (
    TRUSTED_SOURCES,
    company_terms,
    company_term_matches,
    find_companies,
    term_in_text,
)
from features.common.dataframe_ops import sort_records
from features.common.text.tokenize import word_count as shared_word_count
from features.common.research_library.indexing.research_index import (
    MANIFEST_METADATA_VERSION,
    hybrid_search,
    load_documents_from_db,
    read_manifest,
    sync_index,
    write_manifest,
)
from features.common.research_library.rss.feed_config import feed_metadata_for_query
from features.common.workspace import data_dir, research_inbox_dir, workspace_root

ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = data_dir()
INBOX_DIR = research_inbox_dir()
PDF_CACHE_DIR = DATA_DIR / "pdf-cache"
RESEARCH_DB_PATH = DATA_DIR / "research-index.sqlite3"

INDEX_LOCK = threading.Lock()

SECTOR_TERMS = {
    # TAG_ALIASES(market_memory)와 동일한 어휘 사용
    "Semiconductors": ["semiconductor", "chip", "memory", "hbm", "gpu", "ai server", "반도체", "메모리", "HBM"],
    "AI": ["artificial intelligence", "AI", "machine learning", "large language model", "인공지능", "생성형 AI"],
    "Data Centers": ["data center", "hyperscaler", "데이터센터"],
    "Battery": ["battery", "EV battery", "배터리", "2차전지", "리튬"],
    # "energy" 단독 제거 — 기술 기사의 "energy efficiency/consumption"에서 오분류 발생
    # "gas"/"oil" 단독 제거 — 복합어로만 매칭
    "Energy": ["crude oil", "oil price", "natural gas", "oil refinery", "원유", "유가", "정유", "원전"],
    "Defense": ["defense", "aerospace", "방산", "군수"],
    # "bank"/"은행" 단독 제거 — "central bank", "bank analyst" 등으로 기술주에 오분류됨
    # bond/yield/금리/채권은 IMPACT_TERMS에서 이미 처리 — Financials에서 제거
    "Financials": ["investment bank", "brokerage", "은행주", "증권사", "보험사", "금융주"],
    "Automobiles": ["automaker", "vehicle", "automotive", "자동차", "전기차", "완성차"],
}
IMPACT_TERMS = {
    "매출 성장": ["revenue", "sales", "demand", "order", "수요", "매출", "수주"],
    "마진": ["margin", "cost", "pricing", "profit", "마진", "원가", "이익"],
    "규제": ["regulation", "tariff", "sanction", "규제", "관세", "제재"],
    "금리": ["rate", "yield", "fed", "fomc", "금리", "연준", "국채"],
    "환율": ["dollar", "currency", "fx", "원달러", "환율"],
    "공급망": ["supply", "inventory", "shortage", "공급망", "재고"],
    "수급": ["volume", "foreign buying", "거래대금", "외국인", "기관", "순매수", "순매도"],
}
MARKET_TERMS = ["stock", "stocks", "shares", "market", "earnings", "revenue", "guidance", "analyst", "fed", "yield", "oil", "AI", "주식", "증시", "주가", "실적", "공시", "거래대금", "외국인", "기관", "코스피", "코스닥", "반도체", "금리", "환율", "유가"]
GENERAL_NOISE = ["sports", "celebrity", "weather", "스포츠", "연예", "날씨", "맛집", "여행"]
TEXT_EXTENSIONS = {".txt", ".md", ".html", ".htm", ".json", ".csv"}

RSS_MARKET_TERMS = [
    "주가", "증시", "코스피", "코스닥", "상장", "공시", "실적", "영업이익", "매출", "가이던스",
    "투자", "외국인", "기관", "수급", "반도체", "AI", "인공지능", "데이터센터", "배터리",
    "2차전지", "자동차", "전기차", "방산", "금리", "환율", "유가", "관세", "규제", "정책",
    "정부", "국회", "산업", "공급망", "수출", "목표주가", "밸류에이션",
]
RSS_STRONG_MARKET_TERMS = ["주가", "증시", "코스피", "코스닥", "상장", "공시", "실적", "영업이익", "가이던스", "기관", "수급", "순매수", "순매도", "반도체", "배터리", "전기차", "방산", "금리", "환율", "유가", "관세", "규제", "정책", "목표주가", "밸류에이션"]
RSS_COMPANY_HINTS = ["삼성", "하이닉스", "현대차", "기아", "LG", "SK", "네이버", "카카오", "셀트리온", "두산", "한화", "포스코", "롯데", "CJ", "HD현대", "엔비디아", "테슬라", "애플", "브로드컴", "델"]
RSS_NOISE_TERMS = ["맛집", "외식", "랍스터", "홈다이닝", "여행", "패션", "뷰티", "화장품", "액세서리", "다이소", "빵덕후", "쇼핑백", "연예", "스포츠", "날씨", "할인", "세일", "가성비", "장바구니", "프라이스", "선물세트"]


def rss_item_is_market_relevant(title, description, url):
    text = normalize(f"{title} {description} {url}").lower()
    if re.search(r"^\s*\[포토\]", title or ""):
        return False
    relevant = sum(1 for term in RSS_MARKET_TERMS if term.lower() in text)
    strong = sum(1 for term in RSS_STRONG_MARKET_TERMS if term.lower() in text)
    company = any(term.lower() in text for term in RSS_COMPANY_HINTS)
    noise = sum(1 for term in RSS_NOISE_TERMS if term.lower() in text)
    is_kr = url_host_matches(url, "hankyung.com", "mk.co.kr", "einfomax.co.kr") or any(src in text for src in ["한국경제", "매일경제", "연합인포맥스"]) or bool(re.search(r"[가-힣]", text))
    if is_kr and noise >= 2 and strong < 2:
        return False
    return relevant >= 1 or company or not is_kr


def find_terms(text, mapping):
    hay = normalize(text).lower()
    out = []
    for label, terms in mapping.items():
        if any(term_in_text(t, hay) for t in terms):
            out.append(label)
    return out


def source_weight(source):
    return TRUSTED_SOURCES.get(source, 5)


def infer_source(text, path):
    hay = f"{text} {path}".lower()
    for source in TRUSTED_SOURCES:
        if source.lower() in hay:
            return source
    return "User Archive"


def canonical_news_source(source, url="", title=""):
    title_hay = normalize(title).lower()
    if url_host_matches(url, "barrons.com") or "barron's" in title_hay or "barrons" in title_hay:
        return "Barron's"
    if url_host_matches(url, "wsj.com") or "wall street journal" in title_hay:
        return "WSJ"
    if url_host_matches(url, "marketwatch.com") or "marketwatch" in title_hay:
        return "MarketWatch"
    if url_host_matches(url, "cnbc.com") or "cnbc" in title_hay:
        return "CNBC"
    if url_host_matches(url, "einfomax.co.kr") or "연합인포맥스" in title_hay:
        return "연합인포맥스"
    if url_host_matches(url, "yna.co.kr") or "연합뉴스" in title_hay:
        return "연합뉴스"
    if source == "Dow Jones":
        return "Dow Jones"
    if source == "연합뉴스":
        return "연합뉴스"
    return source


def market_relevance(text, path=""):
    hay = normalize(text).lower()
    if "research-inbox/rss" in str(path).replace("\\", "/").lower():
        title = str(text).split("\n", 1)[0][:220]
        if not rss_item_is_market_relevant(title, text, ""):
            return 0, False
    score = 0
    score += len(find_companies(text)) * 12
    score += sum(1 for t in MARKET_TERMS if term_in_text(t, hay)) * 4
    score += len(find_terms(text, SECTOR_TERMS)) * 3
    score += len(find_terms(text, IMPACT_TERMS)) * 3
    score -= sum(1 for t in GENERAL_NOISE if term_in_text(t, hay)) * 5
    if "rss" not in str(path).lower():
        return 100, True
    return score, score >= 12


def _frontmatter_value(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if text == "null":
        return ""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, (str, int, float)):
            return str(parsed)
        return parsed
    except Exception:
        return text.strip("\"'")


def parse_frontmatter(raw):
    m = re.match(r"^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$", raw)
    if not m:
        return {}, raw
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            key = k.strip()
            meta[key] = _frontmatter_value(v)
    aliases = {
        "collection_status": "collectionStatus",
        "source_type": "sourceType",
        "normalized_url": "normalizedUrl",
        "published_at_kst": "publishedAtKst",
        "collected_at_kst": "collectedAtKst",
        "query_source": "querySource",
        "language": "language",
        "country": "country",
        "relevance_score": "relevanceScore",
        "search_score": "searchScore",
        "reliability_tier": "reliabilityTier",
        "related_tickers": "relatedTickers",
        "related_themes": "relatedThemes",
        "markets": "markets",
        "narrative_ids": "narrativeIds",
        "event_id": "eventId",
    }
    for src, dest in aliases.items():
        if src in meta and dest not in meta:
            meta[dest] = meta[src]
    return meta, m.group(2)


def parse_rssarchive_markdown(raw):
    front_meta, front_body = parse_frontmatter(raw)
    if front_meta:
        title = str(front_meta.get("title") or "").strip()
        summary_match = re.search(r"##\s+Summary\s*\n+([\s\S]*?)(?:\n##\s+|\Z)", front_body, re.I)
        full_match = re.search(r"##\s+Full Text\s*\n+([\s\S]*?)(?:\n##\s+|\Z)", front_body, re.I)
        summary = normalize(summary_match.group(1)) if summary_match else ""
        full_text = normalize(full_match.group(1)) if full_match else ""
        placeholder = "Full text is not saved by default"
        if placeholder.lower() in full_text.lower():
            full_text = ""
        return {
            "title": title,
            "source": canonical_news_source(front_meta.get("source", ""), front_meta.get("url", ""), title),
            "url": front_meta.get("url", ""),
            "normalizedUrl": front_meta.get("normalizedUrl", ""),
            "date": str(front_meta.get("date") or front_meta.get("publishedAtKst") or "")[:10],
            "collectionStatus": front_meta.get("collectionStatus", ""),
            "collector": front_meta.get("collector", ""),
            "sourceType": front_meta.get("sourceType", ""),
            "query": front_meta.get("query", ""),
            "querySource": front_meta.get("querySource", ""),
            "language": front_meta.get("language", ""),
            "country": front_meta.get("country", ""),
            "reliabilityTier": front_meta.get("reliabilityTier", ""),
            "markets": front_meta.get("markets") or [],
            "summary": summary,
        }, f"# {title}\n\n{full_text or summary or front_body}"
    fields = {}
    current = None
    for line in raw.splitlines():
        m = re.match(r"^-\s+([^:]+):\s*(.*)$", line)
        if m:
            current = m.group(1).strip()
            fields[current] = m.group(2).strip()
        elif current and line.startswith("  "):
            fields[current] += "\n" + line.strip()
    if fields.get("Title") or fields.get("URL"):
        title = fields.get("Title", "")
        # 과거 upgrade 경로가 새 포맷 body 전체를 Summary/Description 필드에
        # 밀어넣은 파일이 있어, 임베디드 섹션 마커를 정리하고 Summary 본문만 쓴다.
        summary = clean_embedded_sections(fields.get("Summary", "") or fields.get("Description", ""))
        full_text = clean_embedded_sections(fields.get("Full Text", ""))
        body = full_text or summary
        meta = {
            "title": title,
            "source": canonical_news_source(fields.get("Source", ""), fields.get("URL", ""), title),
            "url": fields.get("URL", ""),
            "date": fields.get("Timestamp (UTC+9)", "")[:10],
            "collectionStatus": fields.get("Collection Status", ""),
            "summary": summary,
        }
        return meta, f"# {title}\n\n{body}"
    return None, None


def title_from_body(body, fallback):
    for line in str(body).splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()[:160]
        if len(line) > 20:
            return line[:160]
    return fallback


def read_pdf(path):
    stat = path.stat()
    key = hashlib.sha256(f"{path}:{stat.st_size}:{stat.st_mtime}".encode()).hexdigest()[:16]
    cache = PDF_CACHE_DIR / f"{key}.json"
    cached = read_json(cache, None)
    if cached:
        return cached.get("text", ""), cached.get("pages", 0)
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        text = normalize("\n".join(pages))[:900000]
        write_json(cache, {"text": text, "pages": len(reader.pages), "extractedAt": now_iso()})
        return text, len(reader.pages)
    except Exception:
        write_json(cache, {"text": "", "pages": 0, "error": "pdf_extraction_failed", "extractedAt": now_iso()})
        return "", 0


def file_type(path):
    parts = {p.lower() for p in path.parts}
    if "filings" in parts:
        return "filing"
    if "reports" in parts:
        return "report"
    if "links" in parts:
        return "link"
    return "article"


def parse_links(text):
    return sorted(set(re.findall(r"https?://[^\s)]+", str(text))))


def file_signature(path):
    stat = path.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def document_content_hash(content):
    return hashlib.sha256(str(content or "").encode("utf-8", errors="replace")).hexdigest()


def workspace_relative(path):
    """자료 폴더 기준 상대 경로. `documents.path`에 저장되는 값이다.

    앱 폴더(`ROOT`) 기준이면 자료를 문서 폴더로 옮긴 순간 색인이 `ValueError`로 죽는다 —
    `INBOX_DIR`은 `FOLIO_HOME`을 따라가는데 여기만 앱 폴더를 봤다. 기본값에서는 자료
    폴더가 곧 앱 폴더라 저장되는 문자열이 같으므로, 이미 만들어진 색인은 그대로 읽힌다.
    """
    root = workspace_root()
    try:
        return path.relative_to(root)
    except ValueError:
        # 자료 폴더 밖의 파일. 옛 동작(앱 폴더 기준)으로 한 번 더 시도하고, 그것도
        # 아니면 절대 경로를 쓴다. 어느 쪽이든 예외로 색인 전체를 멈추지 않는다.
        try:
            return path.relative_to(ROOT)
        except ValueError:
            return path


def should_index_file(path):
    rel = workspace_relative(path).as_posix().lower()
    if rel == "research-inbox/rss/.state.json":
        return False
    return True


def build_document(path):
    rel = workspace_relative(path).as_posix()
    ext = path.suffix.lower()
    stat = path.stat()
    signature = file_signature(path)
    raw = ""
    meta = {}
    readable = True
    pages = 0
    if ext == ".pdf":
        body, pages = read_pdf(path)
        raw = body
    elif ext in TEXT_EXTENSIONS:
        raw = path.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_frontmatter(raw)
        if not meta:
            parsed_meta, parsed_body = parse_rssarchive_markdown(raw)
            if parsed_meta:
                meta, body = parsed_meta, parsed_body
        raw = body
    else:
        raw = f"{ext} files are tracked by metadata only."
        readable = False
    body = normalize(raw)
    title = meta.get("title") or title_from_body(raw, path.stem)
    url = meta.get("url") or (parse_links(raw)[0] if parse_links(raw) else "")
    date = meta.get("date") or dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
    source = canonical_news_source(meta.get("source") or infer_source(f"{title} {body}", rel), url, title) or "User Archive"
    configured_feed = feed_metadata_for_query(meta.get("query", ""))
    language = str(meta.get("language") or configured_feed.get("language") or "").strip().lower()
    # 피드 설정에는 국가가 없다(언어로 대체). 옛 파일의 front matter 값만 그대로 보존한다.
    country = str(meta.get("country") or "").strip().upper()
    companies = find_companies(f"{title} {body}")
    sectors = sorted(set(normalize_tag(t) for t in ([c["sector"] for c in companies] + find_terms(f"{title} {body}", SECTOR_TERMS))))
    impact = [normalize_tag(t) for t in find_terms(f"{title} {body}", IMPACT_TERMS)]
    score, relevant = market_relevance(f"{title} {body}", rel)
    if rel.lower().startswith("research-inbox/rss/"):
        rss_summary = meta.get("summary") or meta.get("description") or body[:700]
        if not rss_item_is_market_relevant(title, rss_summary, url):
            score, relevant = 0, False
    return {
        "id": hashlib.sha256(f"{rel}:{stat.st_mtime}:{title}".encode()).hexdigest()[:16],
        "title": title,
        "path": rel,
        "fileSignature": signature,
        "contentHash": document_content_hash(body),
        "absolutePath": str(path),
        "type": file_type(path),
        "source": source,
        "sourceWeight": source_weight(source),
        "url": url,
        "normalizedUrl": meta.get("normalizedUrl", ""),
        "collector": meta.get("collector", ""),
        "sourceType": meta.get("sourceType", ""),
        "query": meta.get("query", ""),
        "querySource": meta.get("querySource", ""),
        "language": language,
        "country": country,
        "reliabilityTier": meta.get("reliabilityTier", ""),
        "relatedTickers": meta.get("relatedTickers", []) or [],
        "relatedThemes": meta.get("relatedThemes", []) or [],
        "markets": meta.get("markets", []) or [],
        "narrativeIds": meta.get("narrativeIds", []) or [],
        "eventId": meta.get("eventId", ""),
        "collectionStatus": meta.get("collectionStatus", ""),
        "date": date[:10],
        "modifiedAt": dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc).isoformat(),
        "readable": readable,
        "companies": companies,
        "sectors": sectors,
        "impactTags": impact,
        "links": parse_links(raw),
        "marketRelevance": score,
        "marketRelevant": relevant,
        "summary": meta.get("summary") or summarize(body, 3),
        "wordCount": shared_word_count(body),
        "content": body,
        "pages": pages,
    }


def build_index(incremental=True, progress=None):
    with INDEX_LOCK:
        if incremental:
            existing_manifest = read_manifest(RESEARCH_DB_PATH)
            existing_docs = {
                doc["path"]: doc
                for doc in load_documents_from_db(RESEARCH_DB_PATH)
                if doc.get("path")
            }
        else:
            existing_manifest = {}
            existing_docs = {}
        file_manifest = {}
        docs = []
        scanned = 0
        reused = 0
        rebuilt = 0
        skipped = 0
        removed = 0
        seen_paths = set()
        files = [path for path in INBOX_DIR.rglob("*") if path.is_file() and should_index_file(path)]
        total_files = len(files)
        if progress:
            progress(f"자료 폴더를 스캔했습니다. 파일 {total_files}개를 확인합니다.", progress=5)
        for path in files:
            scanned += 1
            if progress and (scanned == 1 or scanned % 50 == 0 or scanned == total_files):
                pct = 5 + int((scanned / max(total_files, 1)) * 65)
                progress(f"인덱싱 중: {scanned}/{total_files} 파일 확인", progress=min(pct, 70))
            rel = workspace_relative(path).as_posix()
            seen_paths.add(rel)
            if not path.is_file():
                continue
            previous = existing_docs.get(rel)
            previous_manifest = existing_manifest.get(rel, {}) if isinstance(existing_manifest.get(rel, {}), dict) else {}
            try:
                signature = file_signature(path)
            except Exception:
                continue
            if (
                incremental
                and previous_manifest.get("fileSignature") == signature
                and int(previous_manifest.get("metadataVersion") or 1) >= MANIFEST_METADATA_VERSION
            ):
                if previous_manifest.get("marketRelevant") and previous:
                    docs.append(previous)
                    reused += 1
                else:
                    skipped += 1
                file_manifest[rel] = previous_manifest
                continue
            doc = build_document(path)
            rebuilt += 1
            file_manifest[rel] = {
                "fileSignature": doc.get("fileSignature", signature),
                "marketRelevant": bool(doc.get("marketRelevant")),
                "id": doc.get("id", ""),
                "modifiedAt": doc.get("modifiedAt", ""),
                "metadataVersion": MANIFEST_METADATA_VERSION,
            }
            if doc["marketRelevant"]:
                docs.append(doc)
        if existing_docs:
            removed = len(set(existing_docs) - seen_paths)
        docs = sort_records(docs, ["date", "sourceWeight", "marketRelevance"], descending=True)
        index = {
            "generatedAt": now_iso(),
            "inbox": str(INBOX_DIR),
            "count": len(docs),
            "documents": docs,
            "fileManifest": file_manifest,
            "incremental": {
                "enabled": bool(incremental),
                "scanned": scanned,
                "reused": reused,
                "rebuilt": rebuilt,
                "skippedIrrelevant": skipped,
                "removed": removed,
            },
        }
        if progress:
            progress("SQLite/FTS 검색 인덱스를 동기화하는 중입니다.", progress=82)
        sqlite_synced = False
        from features.common.jobs import (
            diagnostic_prove_complete_coverage,
            diagnostic_stage_end,
            diagnostic_stage_failure,
            diagnostic_stage_start,
        )
        commit_recorder, commit_stage = diagnostic_stage_start("commit")
        try:
            index["sqlite"] = sync_index(RESEARCH_DB_PATH, index)
            sqlite_synced = True
        except Exception as error:
            index["sqlite"] = {"error": "sqlite_index_failed"}
            diagnostic_stage_failure(
                commit_recorder, error, stage_id=commit_stage,
                stage_code="commit", boundary="save",
            )
        # 우리가 방금 문서를 바꿨다. 서명 확인(5초)을 기다리지 않고 바로 버린다.
        invalidate_index_cache()
        # sync가 실패하면 매니페스트를 갱신하지 않는다. sync_index는 단일 트랜잭션이라
        # 실패 시 documents/chunks가 통째로 롤백되는데, 매니페스트만 새 서명으로 남으면
        # 다음 증분 실행이 그 파일들을 "이미 처리됨"으로 건너뛰어 파일이 다시 바뀌기
        # 전까지 색인에서 영구히 빠진다(전체 재색인만이 복구 경로였다). 옛 매니페스트를
        # 그대로 두면 다음 실행이 같은 파일을 다시 읽어 스스로 복구한다.
        if sqlite_synced:
            try:
                write_manifest(RESEARCH_DB_PATH, file_manifest)
            except Exception as error:
                index.setdefault("sqlite", {})["manifestError"] = "manifest_update_failed"
                diagnostic_stage_failure(
                    commit_recorder, error, stage_id=commit_stage,
                    stage_code="commit", boundary="save",
                )
        else:
            index.setdefault("sqlite", {})["manifestError"] = "manifest_skipped_after_sync_failure"
        # Write slim status JSON — no documents or fileManifest
        try:
            write_json(DATA_DIR / "index.json", {
                "generatedAt": index["generatedAt"],
                "inbox": str(INBOX_DIR),
                "count": index["count"],
                "incremental": index["incremental"],
                "sqlite": index.get("sqlite", {}),
            })
        except Exception as error:
            diagnostic_stage_failure(
                commit_recorder, error, stage_id=commit_stage,
                stage_code="commit", boundary="save",
            )
            diagnostic_stage_end(commit_recorder, commit_stage, "commit")
            diagnostic_prove_complete_coverage()
            raise
        diagnostic_stage_end(commit_recorder, commit_stage, "commit")
        # Only this concrete index producer—not a generic taskType label—can
        # attest that its observed persistence boundary has been traversed.
        diagnostic_prove_complete_coverage()
        if progress:
            progress(f"인덱싱 완료: 문서 {len(docs)}건, 재사용 {reused}건, 재처리 {rebuilt}건", progress=98)
        return index


def list_indexed_documents(company: str = "", limit: int = 50, offset: int = 0):
    """Return paginated document list with company tags for the index status UI."""
    import json as _json
    import sqlite3

    if not RESEARCH_DB_PATH.exists():
        return {"total": 0, "documents": [], "generatedAt": ""}

    conn = sqlite3.connect(str(RESEARCH_DB_PATH))
    try:
        status = read_json(DATA_DIR / "index.json", {})
        generated_at = status.get("generatedAt", "")

        q_lower = company.strip().lower()
        rows = conn.execute(
            "SELECT path, title, date, metadata_json FROM documents WHERE metadata_json IS NOT NULL ORDER BY date DESC, path"
        ).fetchall()

        results = []
        for path, title, date, meta_json in rows:
            try:
                meta = _json.loads(meta_json)
            except Exception:
                continue
            companies = meta.get("companies") or []
            if q_lower:
                match = any(
                    q_lower in (c.get("ticker") or "").lower()
                    or q_lower in (c.get("name") or "").lower()
                    for c in companies
                )
                if not match:
                    continue
            results.append({
                "path": path,
                "title": title or path.rsplit("/", 1)[-1],
                "date": date or "",
                "companies": [
                    {"ticker": c.get("ticker", ""), "name": c.get("name", ""), "cik": c.get("cik", "")}
                    for c in companies
                ],
            })

        total = len(results)
        page = results[offset: offset + limit]
        return {"total": total, "documents": page, "generatedAt": generated_at}
    finally:
        conn.close()


# 인덱스 캐시. 호출자가 14곳이고 한 번 읽는 데 문서 13,030건 기준 1.6초(디스크가 식어
# 있으면 6.2초)가 든다. 캐시가 없던 시절 앱을 켜고 첫 탭이 13.9초 걸렸다(대시보드
# 이야기 비중 = load_index + 네 시장 계산).
#
# 유효성 판정에 DB를 읽지 않는다. 두 가지를 시도해 보고 둘 다 버렸다 —
# 파일 mtime은 같은 파일 안의 `rss_feed_items` 캐시가 피드를 열 때마다 바꾸고,
# `documents`의 `MAX(updated_at)`은 실측에서 26초 만에 움직였다(색인이 바뀌지 않아도
# 갱신된다). 둘 다 쓰면 캐시가 거의 매번 버려진다.
#
# 대신 `documents`에 쓰는 곳이 `build_index()` 하나뿐이라는 사실을 쓴다. 그 경로가
# 끝나면서 `invalidate_index_cache()`를 부른다. RSS 수집 subprocess는 `evidence_items`만
# 쓰고 문서는 건드리지 않는다. TTL은 그래도 혹시 모를 외부 변경을 위한 안전망이다.
_INDEX_CACHE_LOCK = threading.Lock()
_INDEX_CACHE = None            # (loaded_at, index)
_INDEX_REFRESHING = False
INDEX_CACHE_TTL_SECONDS = 300.0


def invalidate_index_cache() -> None:
    """인덱스를 우리가 갱신했을 때 부른다."""
    global _INDEX_CACHE
    with _INDEX_CACHE_LOCK:
        _INDEX_CACHE = None


def _refresh_index_cache_async() -> None:
    """낡은 캐시를 뒤에서 갈아 끼운다. 기다리는 사람은 없다."""
    global _INDEX_REFRESHING
    with _INDEX_CACHE_LOCK:
        if _INDEX_REFRESHING:
            return
        _INDEX_REFRESHING = True

    def _worker() -> None:
        global _INDEX_CACHE, _INDEX_REFRESHING
        try:
            index = _read_index_from_store()
            with _INDEX_CACHE_LOCK:
                _INDEX_CACHE = (time.monotonic(), index)
        except Exception:  # noqa: BLE001 - 갱신 실패 시 옛 값을 계속 쓴다
            pass
        finally:
            with _INDEX_CACHE_LOCK:
                _INDEX_REFRESHING = False

    threading.Thread(target=_worker, name="folio-index-refresh", daemon=True).start()


def _read_index_from_store():
    # Try SQLite first; fall back to legacy JSON during first migration run
    if RESEARCH_DB_PATH.exists():
        docs = load_documents_from_db(RESEARCH_DB_PATH)
        # 판정 기준은 "문서가 있는가"다. 예전에는 `content`가 채워졌는지를 봤는데, 그
        # 컬럼은 나중에 ALTER로 추가돼 기존 행이 전부 비었고 증분 재사용이 그 상태를
        # 계속 물려줬다 — 조건이 늘 거짓이라 매번 build_index() 전체 실행(5.6초)으로
        # 떨어졌다. DB 읽기는 0.6초다. 본문은 chunks에 있고 요약은 summary가 갖는다.
        if docs:
            status = read_json(DATA_DIR / "index.json", {})
            return {
                "generatedAt": status.get("generatedAt", ""),
                "inbox": str(INBOX_DIR),
                "count": len(docs),
                "documents": docs,
                "incremental": status.get("incremental", {}),
                "sqlite": status.get("sqlite", {}),
            }
    # Legacy JSON fallback (pre-migration or SQLite not yet populated)
    idx = read_json(DATA_DIR / "index.json", None)
    if idx and idx.get("documents"):
        return idx
    return build_index()


def load_index():
    """캐시된 인덱스. 낡았으면 **옛 값을 주고 뒤에서 갈아 끼운다**.

    만료될 때마다 다음 요청이 5.9초를 뒤집어쓰면, 앱을 켜 두고 쓰는 사람은 5분마다
    한 번씩 멈추는 화면을 본다 — 실제로 워치리스트에 종목을 추가하면 9.3초가 걸렸고
    그중 6.2초가 이 재로딩이었다. 문서를 쓰는 곳은 `build_index()` 하나뿐이고 그
    경로가 캐시를 직접 버리므로, TTL이 지난 값이 잠깐 더 쓰이는 것은 안전하다.
    """
    global _INDEX_CACHE
    with _INDEX_CACHE_LOCK:
        cached = _INDEX_CACHE
    if cached is not None:
        if (time.monotonic() - cached[0]) >= INDEX_CACHE_TTL_SECONDS:
            _refresh_index_cache_async()
        return cached[1]

    index = _read_index_from_store()
    with _INDEX_CACHE_LOCK:
        _INDEX_CACHE = (time.monotonic(), index)
    return index


def warm_index_cache() -> None:
    """서버가 뜬 직후 백그라운드에서 한 번 읽어 둔다.

    첫 사용자가 6초를 기다리는 대신 시작 직후 조용히 치른다. 실패해도 무시한다 —
    예열은 편의이고, 진짜로 필요할 때 `load_index()`가 다시 읽는다.
    """

    def _worker() -> None:
        try:
            load_index()
        except Exception:  # noqa: BLE001 - 예열 실패가 서버 시작을 막지 않는다
            return
        # 인덱스를 읽어 온 김에 대시보드가 쓰는 집계도 채운다. 기본 탭이라 첫 사용자가
        # 가장 먼저 여는 화면이고, 인덱스만 데워도 여기서 5.7초가 남는다.
        try:
            from features.dashboard.story_share import warm_story_share_cache

            warm_story_share_cache()
        except Exception:  # noqa: BLE001
            pass
        # 판올림한 DB의 옛 JSON 임베딩을 blob으로 바꾼다. 예열이 끝난 뒤에 시작해
        # 첫 화면과 디스크를 다투지 않는다. batch마다 잠깐씩만 잠그며, 중간에 서버가
        # 꺼져도 다음 시작이 남은 것을 이어서 한다.
        try:
            from features.common.research_library.indexing.research_index import migrate_embeddings

            # 캐시는 문서를 들고 있고 임베딩은 검색이 그때그때 DB에서 읽는다.
            # 바꾼다고 캐시가 낡지 않으므로 6초짜리 재로딩을 부르지 않는다.
            migrate_embeddings(RESEARCH_DB_PATH)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_worker, name="folio-index-warm", daemon=True).start()
