"""Shared output contract for API-parity Agent CLI briefings."""

from __future__ import annotations

import re
from collections import OrderedDict

# 종류 판정과 허용 집합은 브리핑 계약이 소유한다. `limits`는 의존이 없는 잎 모듈이라
# 여기서 불러도 순환이 생기지 않는다.
from features.daily_briefing.limits import BRIEFING_KINDS, is_weekly, normalize_briefing_kind


# 시장별 제목과 섹션 라벨. 네 시장이 같은 골격을 쓰므로 섹션은 라벨 하나로 만든다.
MARKET_LABELS = {"us": "미국장", "kr": "한국장", "europe": "유럽장", "jp": "일본장"}
TITLE_REQUIREMENTS = {
    "us": "US Market Briefing",
    "kr": "Korea Market Briefing",
    "europe": "Europe Market Briefing",
    "jp": "Japan Market Briefing",
}
SINGLE_MARKETS = tuple(TITLE_REQUIREMENTS)
AGGREGATE_MARKETS = {"both": ("us", "kr"), "all": SINGLE_MARKETS}


def required_sections(market: str) -> tuple[str, ...]:
    label = MARKET_LABELS[market]
    return (
        TITLE_REQUIREMENTS[market],
        f"0. 오늘의 {label} 성격",
        f"1. {label} 시장 흐름",
        f"2. {label}을 움직인 핵심 변수",
        f"3. {label}을 주도한 기업 ①",
        f"4. {label}을 주도한 기업 ②",
        "5. 일반 투자자 관점",
        f"6. 다음 {label} 체크포인트",
        "오늘의 결론",
    )


def weekly_required_sections(market: str) -> tuple[str, ...]:
    """주간 골격. **일간과 겹치는 라벨을 쓰지 않는다.**

    "오늘의 미국장 성격"을 주간에 그대로 쓰면 계약 검사가 통과하더라도 독자가 읽는
    글이 하루짜리로 흐른다. 주간은 한 주 동안 무엇이 달라졌는지를 쓰는 글이라
    섹션 이름부터 그 일을 지시한다.
    """
    label = MARKET_LABELS[market]
    return (
        TITLE_REQUIREMENTS[market],
        f"0. 지난주 {label} 한 줄 요약",
        f"1. 지난주 {label} 흐름",
        f"2. 지난주 {label}을 움직인 핵심 변수",
        f"3. 지난주 {label}을 주도한 기업·업종",
        "4. 이야기의 변화",
        f"5. 다음주 {label} 일정",
        f"6. 다음주 {label} 확인할 것",
        "이번 주 결론",
    )


def section_zero_label(market: str, kind: str = "daily") -> str:
    label = MARKET_LABELS[market]
    if is_weekly(kind):
        return f"## 0. 지난주 {label} 한 줄 요약"
    return f"## 0. 오늘의 {label} 성격"


US_REQUIRED_SECTIONS = required_sections("us")
KR_REQUIRED_SECTIONS = required_sections("kr")


def briefing_output_contract(
    market_scope: str = "both",
    briefing_type: str = "default",
    *,
    expected_titles: dict | None = None,
    markets: "tuple[str, ...] | list[str] | None" = None,
    kind: str = "daily",
    expected_leading_companies: dict[str, list[str]] | None = None,
) -> dict:
    """생성 결과가 지켜야 할 계약. **시장 목록이 곧 계약 대상이다.**

    예전에는 범위 이름(`market_scope`)만 받았고, 아는 이름이 아니면 조용히 `both`로
    되돌아갔다. 시장이 넷으로 늘면서 `market_selection_scope(["kr","jp"])`가 `multi`를
    돌려주는데 이 함수는 그 이름을 모른다. 그래서 한국장+일본장 예약이 **미국장 섹션을
    요구하는 계약**으로 검사됐다 — 프롬프트는 `read_briefing_prompt(requested_markets)`로
    올바르게 한국·일본을 시키는데 검사만 다른 것을 봤다.

    결과는 매번 계약 위반 → 재작성 1회 → 또 위반 → `internal_error`였다. CLI를 두 번
    돌리므로 45분을 쓰고 아무것도 남기지 못했다(2026-08-12 18:00 예약 실측).
    """
    scope = str(market_scope or "both").strip().lower()
    normalized_type = str(briefing_type or "default").strip().lower()
    if normalized_type not in {"default", "market_focused", "concise"}:
        normalized_type = "default"
    if markets:
        resolved = tuple(
            key for key in (str(item or "").strip().lower() for item in markets)
            if key in TITLE_REQUIREMENTS
        )
    else:
        resolved = ()
    if not resolved:
        # 목록이 없으면 예전처럼 범위 이름에서 되짚는다. 다만 모르는 이름을 `both`로
        # 바꾸지 않는다 — 그 조용한 대체가 이 결함의 원인이었다.
        if scope in AGGREGATE_MARKETS:
            resolved = AGGREGATE_MARKETS[scope]
        elif scope in SINGLE_MARKETS:
            resolved = (scope,)
        else:
            resolved = AGGREGATE_MARKETS["both"]
    markets = resolved
    normalized_kind = normalize_briefing_kind(kind)
    if normalized_kind not in BRIEFING_KINDS:
        normalized_kind = "daily"
    scope = scope if scope in {*SINGLE_MARKETS, *AGGREGATE_MARKETS} else "multi"
    build_sections = weekly_required_sections if normalized_kind == "weekly" else required_sections
    sections = [section for market in markets for section in build_sections(market)]
    market_count = len(markets)
    sections.append("Source & Data Notes")
    if normalized_kind == "weekly":
        return {
            "format": "markdown",
            "marketScope": scope,
            "kind": "weekly",
            "requiredMarketTitles": [TITLE_REQUIREMENTS[key] for key in markets],
            "expectedTitles": {
                key: value for key, value in (expected_titles or {}).items() if key in markets
            },
            "titleDatePattern": "주간 — MM.DD~MM.DD",
            "requireImmediateSectionZeroAfterTitle": True,
            # 주간에는 `주도한 기업 ①/②`가 없다. 기업과 업종을 한 섹션에서 다루므로
            # 기업명 헤딩 검사를 켜 두면 무엇을 써도 통과할 수 없다.
            "requireLeadingCompanyNames": False,
            "requiredSections": sections,
            "briefingType": normalized_type,
            "minimumCharacters": (2500 if normalized_type == "concise" else 4000) * market_count,
            "minimumOneLineConclusions": 7 * market_count,
            "minimumMiddleDotBullets": 18 * market_count,
            "retryOnViolation": 1,
        }
    return {
        "format": "markdown",
        "marketScope": scope,
        "kind": "daily",
        "requiredMarketTitles": [TITLE_REQUIREMENTS[key] for key in markets],
        # **만들 시장의 제목만 남긴다.** 프롬프트가 이 값을 전부 펼쳐 "H1은 정확히
        # 이것들이어야 한다"고 지시하므로, 여기 미국·유럽이 섞여 있으면 한국·일본
        # 예약이 네 시장을 다 쓴다. 호출자가 범위 이름으로 만든 넓은 표를 넘겨도
        # 계약이 자기 시장으로 좁힌다.
        "expectedTitles": {
            key: value for key, value in (expected_titles or {}).items() if key in markets
        },
        "expectedLeadingCompanies": {
            key: [str(name).strip() for name in names[:2] if str(name).strip()]
            for key, names in (expected_leading_companies or {}).items()
            if key in markets and isinstance(names, list)
        },
        "titleDatePattern": "YYYY.MM.DD 마감|장중",
        "requireImmediateSectionZeroAfterTitle": True,
        "requireLeadingCompanyNames": True,
        "requiredSections": sections,
        "briefingType": normalized_type,
        "minimumCharacters": (2500 if normalized_type == "concise" else 5000) * market_count,
        "minimumOneLineConclusions": 7 * market_count,
        "minimumMiddleDotBullets": 18 * market_count,
        "retryOnViolation": 1,
    }


def _market_keys_from_contract(contract: dict) -> list[str]:
    scope = str(contract.get("marketScope") or "").strip().lower()
    if scope in SINGLE_MARKETS:
        return [scope]
    if scope in AGGREGATE_MARKETS:
        return list(AGGREGATE_MARKETS[scope])
    required = " ".join(str(section) for section in contract.get("requiredSections") or [])
    if not required:
        return []
    keys = [key for key, title in TITLE_REQUIREMENTS.items() if title in required]
    # 범위도 제목도 없으면 예전 두 시장 계약으로 본다. 네 시장으로 넓히면
    # 만든 적 없는 시장의 섹션까지 요구하게 된다.
    return keys or ["us", "kr"]


def _title_line_match(value: str, title: str, expected_title: str = "", kind: str = "daily"):
    if expected_title:
        return re.search(
            rf"^#\s+{re.escape(expected_title)}\s*$",
            value,
            re.MULTILINE,
        )
    if is_weekly(kind):
        return re.search(
            rf"^#\s+{re.escape(title)}\s+주간\s+[—-]\s+\d{{2}}\.\d{{2}}~\d{{2}}\.\d{{2}}\s*$",
            value,
            re.MULTILINE,
        )
    return re.search(
        rf"^#\s+{re.escape(title)}\s+[—-]\s+\d{{4}}\.\d{{2}}\.\d{{2}}(?:\s+(?:마감|장중))?\s*$",
        value,
        re.MULTILINE,
    )


def _next_non_empty_line(value: str, start: int) -> str:
    for line in value[start:].splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _has_named_leading_company_heading(value: str, fragment: str) -> bool:
    pattern = re.compile(
        rf"^#{{2,6}}\s+{re.escape(fragment)}\s*[—-]\s*(.+?)\s*$",
        re.MULTILINE,
    )
    for match in pattern.finditer(value):
        company = match.group(1).strip()
        placeholder = company.strip("[]").strip()
        if placeholder and placeholder != "기업명":
            return True
    return False


def _leading_company_name(value: str, fragment: str) -> str:
    match = re.search(
        rf"^#{{2,6}}\s+{re.escape(fragment)}\s*[—-]\s*(.+?)\s*$",
        value,
        re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def briefing_contract_violations(markdown: str, contract: dict) -> list[str]:
    value = str(markdown or "").strip()
    headings = [
        match.group(1).strip()
        for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", value, re.MULTILINE)
    ]
    normalized_headings = [heading.casefold() for heading in headings]
    required_counts = OrderedDict()
    for required in contract.get("requiredSections") or []:
        key = str(required).casefold()
        required_counts.setdefault(key, {"label": str(required), "count": 0})
        required_counts[key]["count"] += 1
    missing = []
    for fragment, item in required_counts.items():
        actual = sum(fragment in heading for heading in normalized_headings)
        if actual < item["count"]:
            missing.append(f"{item['label']} ({actual}/{item['count']}회)")
    violations = []
    if missing:
        violations.append(f"필수 제목 누락: {', '.join(missing)}")

    kind = str(contract.get("kind") or "daily").strip().lower()
    for key in _market_keys_from_contract(contract):
        title = TITLE_REQUIREMENTS[key]
        expected_title = str((contract.get("expectedTitles") or {}).get(key) or "").strip()
        match = _title_line_match(value, title, expected_title, kind)
        if not match:
            if expected_title:
                violations.append(f"시장별 제목 불일치: '# {expected_title}' 필요")
            elif kind == "weekly":
                violations.append(f"시장별 제목 구간 누락: '# {title} 주간 — MM.DD~MM.DD' 형식 필요")
            else:
                violations.append(f"시장별 제목 날짜 누락: '# {title} — YYYY.MM.DD 마감|장중' 형식 필요")
            continue
        if contract.get("requireImmediateSectionZeroAfterTitle", True):
            next_line = _next_non_empty_line(value, match.end())
            # **라벨은 시장마다 다르다.** 예전에는 `us가 아니면 한국장`이라 일본장·유럽장
            # 제목 뒤에 `0. 오늘의 한국장 성격`을 요구했다 — 같은 계약의 필수 섹션 목록은
            # `0. 오늘의 일본장 성격`을 요구하므로 **계약이 자기 자신과 모순됐다.**
            # 18:00 한국·일본 예약은 무엇을 써도 통과할 수 없었고, 위반 → 재작성 →
            # 또 위반으로 CLI를 두 번 돌린 뒤 45분을 버리고 실패했다(실측).
            expected = section_zero_label(key, kind)
            if not next_line.startswith(expected):
                violations.append(f"제목 다음 프리앰블 금지: '# {title}' 다음은 바로 '{expected}'이어야 함")

    if contract.get("requireLeadingCompanyNames", True):
        for key in _market_keys_from_contract(contract):
            # 위와 같은 이유로 라벨을 시장에서 가져온다. 이쪽은 문서 전체를 훑어서 다른
            # 시장의 헤딩이 대신 걸리면 통과해 버렸다 — 조용히 검사를 건너뛴 셈이다.
            prefix = MARKET_LABELS[key]
            for ordinal in ("①", "②"):
                fragment = f"{3 if ordinal == '①' else 4}. {prefix}을 주도한 기업 {ordinal}"
                if not _has_named_leading_company_heading(value, fragment):
                    violations.append(f"주도 기업명 누락: '## {fragment} — [실제 기업명]' 형식 필요")
            expected_companies = (contract.get("expectedLeadingCompanies") or {}).get(key) or []
            for index, expected in enumerate(expected_companies[:2]):
                ordinal = "①" if index == 0 else "②"
                fragment = f"{3 if index == 0 else 4}. {prefix}을 주도한 기업 {ordinal}"
                actual = _leading_company_name(value, fragment)
                if actual != str(expected):
                    violations.append(f"주도 기업 불일치: '{fragment} — {expected}' 필요 (현재: {actual or '없음'})")

    minimum_characters = int(contract.get("minimumCharacters") or 0)
    if len(value) < minimum_characters:
        violations.append(f"최소 분량 미달: {len(value)}자 / {minimum_characters}자")

    conclusion_count = len(re.findall(r"\*\*\s*한 줄 결론\s*:\s*\*\*", value))
    minimum_conclusions = int(contract.get("minimumOneLineConclusions") or 0)
    if conclusion_count < minimum_conclusions:
        violations.append(f"한 줄 결론 부족: {conclusion_count}개 / {minimum_conclusions}개")

    bullet_count = len(re.findall(r"^\s*·\s+\S", value, re.MULTILINE))
    minimum_bullets = int(contract.get("minimumMiddleDotBullets") or 0)
    if bullet_count < minimum_bullets:
        violations.append(f"가운뎃점 요약 부족: {bullet_count}개 / {minimum_bullets}개")
    return violations
