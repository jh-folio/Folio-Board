"""RSS feed configuration loader.

The loader accepts the small YAML subset used by ``config/rss_feeds.yaml`` and
uses PyYAML when available. Keeping the fallback local lets Folio OS run without
an extra dependency.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path

from features.common.config_bootstrap import resolve_config
from features.common.markets import MarketCode


class FeedConfigError(ValueError):
    """Raised when an enabled feed violates the checked config contract."""


# 모든 피드가 언어를 선언한다. 예전에는 유럽·일본 전용이었고 나머지 36개 피드는 선언이
# **금지**돼 있었다(`country_language_only_supported_for_europe_japan`). 그래서 화면의 언어
# 필터에 영어도 한국어도 뜨지 않았다.
#
# `country`는 없앴다. 태그된 17개 피드에서 language와 정확히 1:1이었고(DE↔de, FR↔fr, IT↔it,
# ES↔es, NL↔nl, JP↔ja, GB↔en) 국제 통신사(Reuters·FT·Bloomberg)에서는 정의 자체가 안 됐다.
# 축은 셋으로 정리됐다 — 시장 태그가 "무엇에 대한 기사인가", 언어가 "읽을 수 있는가",
# 출처 필터가 "어느 매체인가"를 맡는다.
FEED_LANGUAGES = frozenset({"ko", "en", "ja", "de", "fr", "nl", "it", "es"})
TARGET_MARKETS = frozenset({MarketCode.EUROPE.value, MarketCode.JP.value})
DEFAULT_MARKETS = frozenset(
    market.value for market in MarketCode if market is not MarketCode.UNKNOWN
)
SOURCE_TYPES = frozenset({"news", "press_release"})


def _coerce_scalar(value: str):
    text = str(value or "").strip()
    if not text:
        return ""
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    low = text.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in {"null", "none"}:
        return None
    try:
        return int(text)
    except ValueError:
        return text


def _split_inline(text: str) -> list[str]:
    """`"a", "b"`를 항목으로 가른다. 따옴표 안의 쉼표는 구분자가 아니다."""
    parts: list[str] = []
    buffer: list[str] = []
    quote = ""
    for char in text:
        if quote:
            buffer.append(char)
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
            buffer.append(char)
            continue
        if char == ",":
            parts.append("".join(buffer))
            buffer = []
            continue
        buffer.append(char)
    parts.append("".join(buffer))
    return [part.strip() for part in parts if part.strip()]


def _coerce_value(value: str):
    """스칼라 또는 인라인 시퀀스(`["finanzen"]`). 설정이 쓰는 두 형태뿐이다."""
    text = str(value or "").strip()
    if text.startswith("[") and text.endswith("]"):
        return [_coerce_scalar(part) for part in _split_inline(text[1:-1])]
    return _coerce_scalar(text)


def _fallback_yaml_feeds(text: str) -> list[dict]:
    """PyYAML 없이 `config/rss_feeds.yaml`을 읽는다. 그 파일이 쓰는 구조만 읽는다.

    **들여쓰기를 본다.** 예전에는 `- `로 시작하면 무조건 새 피드로 봐서 `only_publishers`
    아래의 블록 시퀀스 항목(`- "Reuters"`)이 피드 경계가 됐다. 그 키는 빈 문자열로 남고
    소비자(`feed_item_allowed`, `url_section_allowed`)는 빈 값에서 통과시키므로, 필터가
    통째로 사라져도 유효 피드 수는 그대로라 겉으로는 아무 신호가 없었다.

    받는 구조: 피드 항목의 스칼라 키, 블록 시퀀스(`only_publishers`), 한 단계 중첩
    매핑과 그 안의 인라인 시퀀스(`url_sections: {allow: [...]}`).
    """
    feeds: list[dict] = []
    current: dict | None = None
    in_feeds = False
    item_indent: int | None = None
    # 값이 비어 있는 키 아래로 더 깊은 줄이 오면 그 줄들이 이 키의 값이다.
    nested_key = ""
    nested_indent = 0
    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if not in_feeds:
            in_feeds = stripped == "feeds:"
            continue
        if stripped == "-" or stripped.startswith("- "):
            rest = stripped[1:].strip()
            if item_indent is not None and indent > item_indent:
                if current is not None and nested_key and indent > nested_indent:
                    if not isinstance(current.get(nested_key), list):
                        current[nested_key] = []
                    current[nested_key].append(_coerce_scalar(rest))
                continue
            if current:
                feeds.append(current)
            if item_indent is None:
                item_indent = indent
            current = {}
            nested_key = ""
            if rest and ":" in rest:
                key, value = rest.split(":", 1)
                current[key.strip()] = _coerce_value(value)
            continue
        if current is None or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        if nested_key and indent > nested_indent:
            if not isinstance(current.get(nested_key), dict):
                current[nested_key] = {}
            current[nested_key][key] = _coerce_value(value)
            continue
        current[key] = _coerce_value(value)
        # 값이 비면 다음 줄들이 이 키에 딸린다. 아무것도 안 따라오면 빈 문자열로 남는다.
        nested_key = key if not str(value).strip() else ""
        nested_indent = indent
    if current:
        feeds.append(current)
    return feeds


def _load_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {"feeds": _fallback_yaml_feeds(text)}


def _required_text(row: dict, key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise FeedConfigError(f"missing_{key}")
    return value


def _probe_datetime(row: dict, key: str) -> dt.datetime:
    raw = _required_text(row, key)
    try:
        value = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FeedConfigError(f"invalid_{key}:{raw}") from exc
    if value.tzinfo is None:
        raise FeedConfigError(f"timezone_required_{key}")
    return value.astimezone(dt.timezone.utc)


def _target_metadata(row: dict, default_market: str) -> dict[str, object]:
    """Validate a feed's language, plus the freshness probe Europe/Japan must carry.

    The probe stays scoped to Europe and Japan because those feeds were added by
    hand from outlets nobody here reads daily — a dead one would sit there
    returning stale items with an HTTP 200 and look fine. US/KR feeds get noticed.
    """
    language = _required_text(row, "language").lower()
    if language not in FEED_LANGUAGES:
        raise FeedConfigError(f"invalid_language:{language}")
    if default_market not in TARGET_MARKETS:
        return {
            "language": language,
            "freshness_checked_at": "",
            "freshness_latest_at": "",
            "freshness_item_count": 0,
        }

    checked_at = _probe_datetime(row, "freshness_checked_at")
    latest_at = _probe_datetime(row, "freshness_latest_at")
    try:
        item_count = int(row.get("freshness_item_count") or 0)
    except (TypeError, ValueError) as exc:
        raise FeedConfigError("invalid_freshness_item_count") from exc
    age = checked_at - latest_at
    if item_count <= 0:
        raise FeedConfigError("freshness_probe_has_no_items")
    if age < dt.timedelta(0) or age > dt.timedelta(hours=72):
        raise FeedConfigError("freshness_probe_is_stale")
    return {
        "language": language,
        "freshness_checked_at": checked_at.isoformat().replace("+00:00", "Z"),
        "freshness_latest_at": latest_at.isoformat().replace("+00:00", "Z"),
        "freshness_item_count": item_count,
    }


def _url_sections(raw) -> dict:
    """`{"allow": [...]}` 또는 `{"deny": [...]}`. 둘 다 없으면 거르지 않는다.

    `allow`가 있으면 그 섹션만 받는다(가장 엄격). `deny`는 그 섹션만 뺀다. 둘 다 주면
    `allow`를 먼저 보고 통과한 것에 `deny`를 적용한다.
    """
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key in ("allow", "deny"):
        values = raw.get(key)
        if not isinstance(values, list):
            continue
        cleaned = [str(v).strip().strip("/").lower() for v in values if str(v or "").strip()]
        if cleaned:
            out[key] = cleaned
    return out


def normalize_feed(row: dict) -> dict | None:
    if not isinstance(row, dict):
        return None
    url = str(row.get("url") or "").strip()
    media = str(row.get("media") or "").strip()
    if not url or not media:
        return None
    enabled = row.get("enabled", True)
    if enabled is False or str(enabled).strip().lower() == "false":
        return None
    default_market = str(row.get("default_market") or "").strip().upper()
    if default_market not in DEFAULT_MARKETS:
        raise FeedConfigError(f"invalid_default_market:{default_market or '<empty>'}")
    target_metadata = _target_metadata(row, default_market)
    source_type = str(row.get("source_type") or "news").strip().lower() or "news"
    if source_type not in SOURCE_TYPES:
        raise FeedConfigError(f"invalid_source_type:{source_type}")
    try:
        reliability_tier = int(row.get("reliability_tier") or 2)
    except (TypeError, ValueError) as exc:
        raise FeedConfigError("invalid_reliability_tier") from exc
    if reliability_tier not in {1, 2, 3}:
        raise FeedConfigError(f"invalid_reliability_tier:{reliability_tier}")
    # Aggregating feeds carry many outlets. When set, only items whose feed-declared
    # publisher matches are kept, and the item is re-tagged with that publisher name.
    # 기사 URL의 섹션으로 거른다. 언어와 무관한 **구조적** 신호라, 키워드 표를 여섯 개
    # 언어로 늘리지 않고도 종합 피드에서 투자와 무관한 면을 뺄 수 있다. 실측: Handelsblatt
    # 1,260건 중 politik 421 · karriere 68 · video 31이었고 finanzen은 279뿐이었다.
    url_sections = _url_sections(row.get("url_sections"))
    raw_publishers = row.get("only_publishers")
    only_publishers = [
        str(v).strip() for v in raw_publishers if str(v or "").strip()
    ] if isinstance(raw_publishers, list) else []
    return {
        "url": url,
        "media": media,
        "category": str(row.get("category") or "").strip(),
        "priority": int(row.get("priority") or 3),
        # `allow_full_text`는 여기서 읽히기만 하고 **소비자가 없었다**(0.5.4에 제거).
        # 본문 확보 여부는 수집 시점에 정해진다 — aggregator 리다이렉트는 기사 HTML을
        # 가져오지 않고, 유료벽 문구가 잡히면 요약만 남는다. 그래서 이 플래그와 실제
        # 결과가 어긋나 있었다: 설정이 `false`인 CNBC가 실측 538건 중 538건 전문 확보,
        # `true`인 피드 중에도 0%가 있었다. 없는 신호를 남겨 두면 다음 판단이 그것을 믿는다.
        "reliability_tier": reliability_tier,
        "default_market": default_market,
        **target_metadata,
        "only_publishers": only_publishers,
        "url_sections": url_sections,
        # "news"는 브리핑 입력에 포함되고, "press_release"는 기업 자료 전용으로 분리된다.
        "source_type": source_type,
    }


def load_rss_feeds(path: str | Path) -> list[dict]:
    config_path = Path(path)
    if not config_path.exists():
        return []
    data = _load_yaml(config_path)
    feeds = []
    for row in data.get("feeds") or []:
        feed = normalize_feed(row)
        if feed:
            feeds.append(feed)
    feeds.sort(key=lambda item: (-int(item.get("priority") or 0), item.get("media", ""), item.get("url", "")))
    return feeds


@lru_cache(maxsize=8)
def _feed_identity_index(path_text: str, mtime_ns: int) -> dict[str, dict[str, str]]:
    """Map an unambiguous feed URL to the metadata stored items can be re-read with.

    `default_market` is here because the RSS cache rebuild has to re-tag items it
    reads back from Markdown, and the index used to drop any feed without a
    `country`/`language`. That excluded all 36 US/KR/GLOBAL feeds, so the rebuild
    had no feed hint at all and legacy `UNKNOWN` items could never recover.
    Feeds with no country or language now stay in the index with empty strings,
    which is what the language lookup already saw for them.
    """
    del mtime_ns  # cache key only; the file timestamp invalidates stale mappings
    candidates: dict[str, list[dict[str, str]]] = {}
    for feed in load_rss_feeds(path_text):
        url = str(feed.get("url") or "").strip()
        if not url:
            continue
        candidates.setdefault(url, []).append({
            "language": str(feed.get("language") or ""),
            "default_market": str(feed.get("default_market") or "").strip().upper(),
        })
    return {url: rows[0] for url, rows in candidates.items() if len(rows) == 1}


@lru_cache(maxsize=8)
def _media_index(path_text: str, mtime_ns: int) -> dict[str, dict[str, str]]:
    """Map an outlet name to the fields all of its feeds agree on.

    Measured 2026-08-09: 83% of stored items carry no `query` in their front
    matter — they are legacy line-oriented files — so a feed-URL lookup reaches
    only 17% of them. The outlet name resolves 90%.

    Disagreement means "we cannot tell", because the stored item does not say
    which of that outlet's feeds it arrived through. In practice that only bites
    the market (Reuters is US and GLOBAL, 연합인포맥스 is US, KR and GLOBAL);
    an outlet writes in one language whichever feed you take it from.
    """
    del mtime_ns  # cache key only
    seen: dict[str, dict[str, set[str]]] = {}
    for feed in load_rss_feeds(path_text):
        media = str(feed.get("media") or "").strip()
        if not media:
            continue
        row = seen.setdefault(media, {"market": set(), "language": set()})
        market = str(feed.get("default_market") or "").strip().upper()
        language = str(feed.get("language") or "").strip().lower()
        if market:
            row["market"].add(market)
        if language:
            row["language"].add(language)
    return {
        media: {
            field: next(iter(values)) if len(values) == 1 else ""
            for field, values in fields.items()
        }
        for media, fields in seen.items()
    }


def _config_index_key(config_path: str | Path | None) -> tuple[str, int] | None:
    path = Path(config_path) if config_path is not None else resolve_config("rss_feeds.yaml")
    if not path.exists():
        return None
    return str(path.resolve()), path.stat().st_mtime_ns


def feed_metadata_for_query(query: object, *, config_path: str | Path | None = None) -> dict[str, str]:
    """Return metadata only for an exact, unambiguous configured feed URL."""
    feed_url = str(query or "").strip()
    key = _config_index_key(config_path) if feed_url else None
    if key is None:
        return {}
    row = _feed_identity_index(*key).get(feed_url)
    return dict(row) if row else {}


def _media_field(media: object, field: str, config_path: str | Path | None) -> str:
    name = str(media or "").strip()
    key = _config_index_key(config_path) if name else None
    if key is None:
        return ""
    return _media_index(*key).get(name, {}).get(field, "")


def feed_market_for_media(media: object, *, config_path: str | Path | None = None) -> str:
    """Return the declared market for an outlet, or `""` when its feeds disagree."""
    return _media_field(media, "market", config_path)


def feed_language_for_media(media: object, *, config_path: str | Path | None = None) -> str:
    """Return the language an outlet publishes in, or `""` when its feeds disagree."""
    return _media_field(media, "language", config_path)
