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
FLEXIBLE_LEADER_MARKETS = {"us", "kr"}
FLEXIBLE_LEADER_MODES = {"qualified_zero_to_two", "optional_zero_to_two"}


def contract_reason_codes(violations: list[str]) -> list[str]:
    """Closed diagnostic codes, never headings, names or response excerpts."""
    prefixes = {
        "필수 제목 누락": "contract_missing_heading",
        "시장별 제목": "contract_title_mismatch",
        "제목 다음 프리앰블": "contract_preamble",
        "최소 분량": "contract_too_short",
        "한 줄 결론": "contract_missing_conclusions",
        "가운뎃점 요약": "contract_missing_bullets",
        "주도 기업": "contract_leader_section",
        "기업 신호": "contract_leader_section",
    }
    return sorted({next((code for prefix, code in prefixes.items() if text.startswith(prefix)),
                        "contract_other") for text in violations})


class BriefingOutputContractError(ValueError):
    def __init__(self, violations: list[str]):
        super().__init__(f"CLI 브리핑 출력 계약 위반: {'; '.join(violations)}")
        self.reason_codes = contract_reason_codes(violations)


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
    leader_section_modes: dict[str, str] | None = None,
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
    # **Notes는 시장마다 하나다.** 합본에 하나만 요구하면 모델이 모든 시장을 합친
    # 공통 꼬리를 쓰고, 시장별 분리가 그 꼬리를 마지막 시장 파일에 통째로 준다 —
    # 실측(2026-08-24 kr+jp): 일본장 파일의 Notes에 한국장 문장이 들어가고 한국장
    # 파일에는 Notes가 아예 없었다. 필수 섹션 위반 검사는 이미 개수를 세므로
    # 시장 수만큼 넣으면 그대로 강제된다.
    sections = []
    # A flexible daily market with no authoritative concentration result may
    # legitimately omit both company slots.  Its stable body then has five
    # numbered sections (0, 1, 2, 5, 6) plus the conclusion, rather than the
    # seven conclusion/bullet-bearing sections used by the fixed two-company
    # shape.  Keep the quantitative gate aligned with that allowed shape;
    # headings, title/date, minimum characters, and bounded slot validation
    # remain unchanged.
    minimum_conclusions = 0
    minimum_bullets = 0
    for market in markets:
        requested_mode = str((leader_section_modes or {}).get(market) or "fixed_two")
        mode = (
            requested_mode
            if normalized_kind == "daily" and market in FLEXIBLE_LEADER_MARKETS
            and requested_mode in {"fixed_two", *FLEXIBLE_LEADER_MODES}
            else "fixed_two"
        )
        expected_by_market = expected_leading_companies or {}
        # A present list is an authoritative concentration result, including an
        # intentionally empty finalPair.  An absent key means ordinary optional
        # slots: do not infer zero companies merely because no whitelist was
        # supplied.
        has_authoritative_names = (
            market in expected_by_market
            and isinstance(expected_by_market.get(market), list)
        )
        flexible_mode = (
            normalized_kind == "daily"
            and market in FLEXIBLE_LEADER_MARKETS
            and mode in FLEXIBLE_LEADER_MODES
        )
        if flexible_mode and not has_authoritative_names:
            minimum_conclusions += 6
            minimum_bullets += 15
        else:
            minimum_conclusions += 7
            minimum_bullets += 18
        if flexible_mode and has_authoritative_names:
            label = MARKET_LABELS[market]
            count = min(2, len(expected_by_market.get(market) or []))
            sections.extend((
                TITLE_REQUIREMENTS[market],
                f"0. 오늘의 {label} 성격",
                f"1. {label} 시장 흐름",
                f"2. {label}을 움직인 핵심 변수",
            ))
            if count == 0:
                sections.append("3. 오늘의 기업 신호")
            if count >= 1:
                sections.append(f"3. {label}을 주도한 기업 ①")
            if count >= 2:
                sections.append(f"4. {label}을 주도한 기업 ②")
            sections.extend(("5. 일반 투자자 관점", f"6. 다음 {label} 체크포인트", "오늘의 결론"))
        elif flexible_mode:
            # The author may include zero, one, or two concrete company
            # sections based on the supplied facts.  Since the count is not
            # known at contract construction time, only the stable surrounding
            # sections are required; the validator checks the bounded optional
            # alternatives below.
            label = MARKET_LABELS[market]
            sections.extend((
                TITLE_REQUIREMENTS[market],
                f"0. 오늘의 {label} 성격",
                f"1. {label} 시장 흐름",
                f"2. {label}을 움직인 핵심 변수",
                "5. 일반 투자자 관점",
                f"6. 다음 {label} 체크포인트",
                "오늘의 결론",
            ))
        else:
            sections.extend(build_sections(market))
        sections.append("Source & Data Notes")
    market_count = len(markets)
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
            # A full second Agent run roughly doubles latency/tokens and can still
            # time out with no artifact.  Contract failure leaves the previous
            # saved artifact untouched; bounded section repair happens later.
            "retryOnViolation": 0,
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
        "leaderSectionModes": {
            key: (
                str(value)
                if normalized_kind == "daily" and key in FLEXIBLE_LEADER_MARKETS
                and str(value) in {"fixed_two", *FLEXIBLE_LEADER_MODES}
                else "fixed_two"
            )
            for key, value in (leader_section_modes or {}).items()
            if key in markets and (
                str(value) in {"fixed_two", *FLEXIBLE_LEADER_MODES}
            )
        },
        "titleDatePattern": "YYYY.MM.DD 마감|장중",
        "requireImmediateSectionZeroAfterTitle": True,
        "requireLeadingCompanyNames": True,
        "requiredSections": sections,
        "briefingType": normalized_type,
        "minimumCharacters": (2500 if normalized_type == "concise" else 5000) * market_count,
        "minimumOneLineConclusions": minimum_conclusions,
        "minimumMiddleDotBullets": minimum_bullets,
        "retryOnViolation": 0,
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


def _optional_leading_company_violations(
    value: str, prefix: str, market_title: str = ""
) -> list[str]:
    """Validate the un-whitelisted US/KR daily 0–2 company alternatives.

    This deliberately does not select or rank companies.  It only makes an
    optional author choice bounded and structurally safe: a concrete first
    section may be followed by a concrete second section, or the generic
    signal section may stand alone when no company has enough direct evidence.
    """
    violations: list[str] = []
    scoped_value = value
    if market_title:
        # A combined US+KR report can legitimately contain one generic
        # ``오늘의 기업 신호`` heading in each market block.  Scope the
        # alternative check to its own H1 so one market cannot count the
        # other market's zero-company fallback.
        block = re.search(
            rf"^#\s+{re.escape(market_title)}\b.*?(?=^#\s+|\Z)",
            value,
            re.MULTILINE | re.DOTALL,
        )
        if block:
            scoped_value = block.group(0)
    matches: dict[str, list[re.Match[str]]] = {}
    for ordinal, number in (("①", 3), ("②", 4)):
        pattern = re.compile(
            rf"^#{{2,6}}\s+{number}\.\s+{re.escape(prefix)}을 주도한 기업 {ordinal}(?:\s*[—-].*)?$",
            re.MULTILINE,
        )
        matches[ordinal] = list(pattern.finditer(scoped_value))
        if len(matches[ordinal]) > 1:
            violations.append(f"주도 기업 슬롯 중복: {prefix} {ordinal}이 여러 번 나옴")
        if matches[ordinal] and not _has_named_leading_company_heading(
            scoped_value, f"{number}. {prefix}을 주도한 기업 {ordinal}"
        ):
            violations.append(f"주도 기업명 누락: '## {number}. {prefix}을 주도한 기업 {ordinal} — [실제 기업명]' 형식 필요")

    first = bool(matches["①"])
    second = bool(matches["②"])
    if second and not first:
        violations.append(f"주도 기업 슬롯 순서 불일치: {prefix} 기업 ② 전에 기업 ①이 필요")

    generic_pattern = re.compile(r"^#{2,6}\s+3\.\s+오늘의 기업 신호\s*$", re.MULTILINE)
    generic_count = len(generic_pattern.findall(scoped_value))
    if generic_count > 1:
        violations.append(f"기업 신호 섹션 중복: {prefix} {generic_count}개")
    if generic_count and (first or second):
        violations.append(f"기업 신호 섹션 혼용: {prefix} 구체 기업 절과 일반 신호를 함께 쓸 수 없음")
    return violations


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
            mode = str((contract.get("leaderSectionModes") or {}).get(key) or "fixed_two")
            if kind == "daily" and key not in FLEXIBLE_LEADER_MARKETS:
                mode = "fixed_two"
            expected_map = contract.get("expectedLeadingCompanies") or {}
            has_authoritative_names = key in expected_map and isinstance(expected_map.get(key), list)
            expected_companies = expected_map.get(key) if has_authoritative_names else []
            if (
                kind == "daily"
                and key in FLEXIBLE_LEADER_MARKETS
                and mode in FLEXIBLE_LEADER_MODES
                and not has_authoritative_names
            ):
                violations.extend(_optional_leading_company_violations(
                    value, MARKET_LABELS[key], TITLE_REQUIREMENTS[key],
                ))
                continue
            required_ordinals = (
                ("①", "②") if mode == "fixed_two"
                else tuple(("①", "②")[: min(2, len(expected_companies))])
            )
            for ordinal in required_ordinals:
                fragment = f"{3 if ordinal == '①' else 4}. {prefix}을 주도한 기업 {ordinal}"
                if not _has_named_leading_company_heading(value, fragment):
                    violations.append(f"주도 기업명 누락: '## {fragment} — [실제 기업명]' 형식 필요")
            for index, expected in enumerate(expected_companies[:2]):
                ordinal = "①" if index == 0 else "②"
                fragment = f"{3 if index == 0 else 4}. {prefix}을 주도한 기업 {ordinal}"
                actual = _leading_company_name(value, fragment)
                # 정확 문자열 비교는 띄어쓰기("SK 하이닉스")나 티커 부기 하나로 위반이
                # 되고, 재작성 한 번 뒤 잡 전체가 실패한다 — 공백 제거·대소문자 무시
                # 후 어느 한쪽 포함이면 같은 회사로 본다.
                wanted = str(expected).replace(" ", "").casefold()
                got = actual.replace(" ", "").casefold()
                if not wanted or (wanted not in got and got not in wanted):
                    violations.append(f"주도 기업 불일치: '{fragment} — {expected}' 필요 (현재: {actual or '없음'})")
            if mode in FLEXIBLE_LEADER_MODES:
                actual_count = sum(
                    bool(_has_named_leading_company_heading(
                        value, f"{3 if ordinal == '①' else 4}. {prefix}을 주도한 기업 {ordinal}",
                    ))
                    for ordinal in ("①", "②")
                )
                if actual_count != len(expected_companies[:2]):
                    violations.append(
                        f"주도 기업 슬롯 수 불일치: {prefix} {actual_count}개 / 근거 충족 {len(expected_companies[:2])}개"
                    )

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
