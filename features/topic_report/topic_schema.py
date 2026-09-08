"""Topic Report v2 스키마 — report_type/evidenceRole enum과 TopicPlan 정규화.

설계 원칙 4(결론은 enum으로 통제): LLM이 무엇을 돌려주든 최종 reportType과
evidenceRole은 코드에서 검증한다. 자유 텍스트 분류를 그대로 신뢰하지 않는다.
"""
from __future__ import annotations

import re

# 주제 라벨 상한. planner._SUBJECT_MAX와 같은 값이며, 넘을 때만 주제어 추출로 줄인다.
_TOPIC_LABEL_MAX = 40

REPORT_TYPE_CHOICES = {
    "macro_analysis",
    "cross_asset_analysis",
    "industry_theme",
    "supply_chain_theme",
    "policy_regulation",
    "geopolitical_risk",
    "earnings_theme",
    "factor_style",
    "company_basket",
    "country_market",
    "portfolio_implication",
    "custom_research",
}
REPORT_TYPE_DEFAULT = "custom_research"

REPORT_TYPE_LABELS = {
    "macro_analysis": "거시 분석",
    "cross_asset_analysis": "크로스에셋 분석",
    "industry_theme": "산업 테마",
    "supply_chain_theme": "공급망 테마",
    "policy_regulation": "정책·규제",
    "geopolitical_risk": "지정학 리스크",
    "earnings_theme": "실적 테마",
    "factor_style": "팩터·스타일",
    "company_basket": "기업군 비교",
    "country_market": "국가 시장",
    "portfolio_implication": "포트폴리오 영향",
    "custom_research": "자유 리서치",
}

# 기존 프리셋의 legacy report_type → v2 enum 매핑 (backward compat)
LEGACY_REPORT_TYPE_MAP = {
    "macro_analysis": "macro_analysis",
    "earnings_analysis": "earnings_theme",
    "weekly_summary": "cross_asset_analysis",
    "industry_analysis": "industry_theme",
    "custom": "custom_research",
}

EVIDENCE_ROLE_CHOICES = {"supporting", "challenging", "neutral", "background", "data_point"}
EVIDENCE_ROLE_DEFAULT = "neutral"

TIME_HORIZON_DEFAULT = "1~2 quarters"

# 설계 §9 보고서 구조 (v2 공통 섹션)
# 딥리서치 하위 질문 상한. 라운드1은 "연구질문 + 분석축 전체"를 담아야 한다 —
# 6으로 두면 축이 5개일 때 첫 축만 질문을 받고 나머지 축은 질문 없이 남는다.
# 이 값을 계획 생성기(planner)와 승인 계약(approved_plan_schema)이 함께 읽는다.
DEEP_MAX_QUESTIONS = 12
DEEP_MAX_ROUND_1_QUESTIONS = 10
DEEP_MAX_ROUND_2_QUESTIONS = 6

# 보고서 골격은 **머리·꼬리 고정 + 본문 자유**다.
#
# 예전에는 11개 섹션 전체가 고정이었고 헤딩이 하나만 달라도 보고서를 통째로 버렸다.
# 그런데 유형별 템플릿 9개는 전부 같은 골격 안에서 강조점만 바꿀 뿐이고, 계획이 다른
# 구성을 선언할 통로도 없었다(승인 계약이 정확 일치를 요구했다). 그 결과 주제와 맞지
# 않는 섹션은 건너뛸 수 없어 얇게 채워졌고(실측: 결론이 예산의 24%), 분석축 5개가
# 가중치 15%짜리 섹션 하나에 밀려 들어가 축당 400자를 받았다.
#
# 머리와 꼬리는 서식이 아니라 계약이다 — 꼬리의 반론·시나리오·체크포인트는 §5 원칙 3
# (확증편향 방지)의 집행 장치이고, 체크포인트 추출·품질 평가·리더가 **이름으로** 찾는다.
# 가운데는 주제가 정한다: 계획의 분석축이 그대로 본문 섹션이 된다.
REPORT_HEAD_SECTIONS = (
    "Executive Summary",
    "질문 정의와 분석 범위",
    "핵심 데이터 대시보드",
)
REPORT_TAIL_SECTIONS = (
    "반론과 리스크",
    "시나리오",
    "앞으로 확인할 체크포인트",
    "결론",
    "Source & Data Notes",
)
BODY_SECTION_MIN = 2
BODY_SECTION_MAX = 8
BODY_SECTION_MAX_LENGTH = 40
DEFAULT_BODY_SECTIONS = ("현재 상황", "작동 경로", "수혜/피해 자산과 기업")
_RESERVED_SECTIONS = frozenset(REPORT_HEAD_SECTIONS) | frozenset(REPORT_TAIL_SECTIONS)


def compose_sections(body_sections) -> list[str]:
    """머리 + 본문 + 꼬리."""
    return [*REPORT_HEAD_SECTIONS, *normalize_body_sections(body_sections), *REPORT_TAIL_SECTIONS]


def body_sections(sections) -> list[str]:
    """전체 섹션 목록에서 가운데(본문)만 떼어낸다."""
    rows = [str(item or "").strip() for item in sections or []]
    return [row for row in rows if row and row not in _RESERVED_SECTIONS]


def normalize_body_sections(values, fallback=DEFAULT_BODY_SECTIONS) -> list[str]:
    """본문 섹션 이름 위생. 예약 이름·중복·과한 길이를 걸러낸다.

    이름이 곧 헤딩이므로 번호 접두(`1. `)와 `#`은 떼어낸다 — 계획이 그대로 헤딩이
    되면 `## 1. 1. 현재 상황`이 된다.
    """
    out: list[str] = []
    for raw in values or []:
        label = re.sub(r"^#+\s*", "", str(raw or "")).strip()
        label = re.sub(r"^\d+\.\s*", "", label).strip()
        if not label or len(label) > BODY_SECTION_MAX_LENGTH:
            continue
        if label in _RESERVED_SECTIONS or label in out:
            continue
        out.append(label)
        if len(out) >= BODY_SECTION_MAX:
            break
    if len(out) < BODY_SECTION_MIN:
        return list(fallback)
    return out


# 기존 소비자 호환 기본값. 계획이 본문을 정하지 않았을 때의 골격이다.
EXPECTED_SECTIONS_V2 = compose_sections(DEFAULT_BODY_SECTIONS)


def normalize_report_type(value, default: str = REPORT_TYPE_DEFAULT) -> str:
    value = str(value or "").strip().lower()
    if value in REPORT_TYPE_CHOICES:
        return value
    return LEGACY_REPORT_TYPE_MAP.get(value, default)


def normalize_evidence_role(value, default: str = EVIDENCE_ROLE_DEFAULT) -> str:
    value = str(value or "").strip().lower()
    return value if value in EVIDENCE_ROLE_CHOICES else default


def _str_list(value, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


# yfinance 형식 심볼. 승인 계약(`normalize_tickers`)이 20자·비어 있지 않음을 요구하므로
# 그 안쪽으로 좁게 잡는다. 밑줄과 공백은 심볼에 오지 않는다 — 그게 온 것은 티커가 아니라
# 모델이 만든 그룹 이름이다.
# 선행 `^`는 지수 심볼이다(`^GSPC`·`^KS11`). 빼면 대표지수가 조용히 사라진다.
_TICKER_SYMBOL = re.compile(r"[A-Z0-9^][A-Z0-9.^=-]{0,19}")
_LABEL_MAX = 160


def _harvest_symbols(value) -> list[str]:
    """리스트 모양의 값에서 심볼만 건져 낸다.

    실측으로 플래너가 `{"cloud_and_compute": "['AMZN', 'NVDA']"}`처럼 **그룹 이름 → 티커
    목록**을 돌려줬다. 계약은 `{티커: 표시명}`이라 그대로 두면 승인 단계가 통째로 422가
    되고, 60초짜리 계획 호출이 버려진다. 산문 라벨에서 대문자 낱말을 티커로 오인하지
    않도록 **리스트 모양일 때만** 건진다.
    """
    if isinstance(value, (list, tuple, set)):
        items = [str(item or "") for item in value]
    else:
        text = str(value or "").strip()
        if not (text.startswith("[") or text.startswith("(")):
            return []
        items = [text]
    found: list[str] = []
    for item in items:
        for match in _TICKER_SYMBOL.finditer(item.upper()):
            symbol = match.group(0)
            if symbol not in found:
                found.append(symbol)
    return found


def _ticker_map(value, limit: int = 14) -> dict[str, str]:
    """`{티커: 표시명}`으로 강제한다.

    티커 위생은 검색어 위생과 같은 이유로 **코드가 정한다**(planner의 `_clean_queries`).
    프롬프트로 형식을 부탁한 것과 모델이 지킨 것은 다르고, 여기서 새는 값은 곧 승인
    단계의 실패다. 못 읽는 항목은 버리되 요청 전체를 죽이지 않는다.
    """
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}

    def _add(symbol: str, label: str) -> None:
        if len(out) >= limit or symbol in out:
            return
        if not any(char.isalnum() for char in symbol):
            return
        out[symbol] = (label.strip() or symbol)[:_LABEL_MAX]

    for key, label in value.items():
        if len(out) >= limit:
            break
        # **값이 목록이면 키는 그룹 이름이다.** 키 모양으로 먼저 가르면 `payments`·`group`
        # 처럼 밑줄 없는 그룹 이름이 티커 패턴을 통과해 목록 문자열을 표시명으로 달고
        # 들어온다. 그룹 이름은 표시명으로 남겨 모델이 왜 묶었는지를 잃지 않는다.
        symbols = _harvest_symbols(label)
        if symbols:
            for symbol in symbols:
                _add(symbol, str(key or symbol))
            continue
        ticker = str(key or "").strip().upper()
        if ticker and _TICKER_SYMBOL.fullmatch(ticker):
            _add(ticker, str(label or ticker))
    return out


def normalize_axis(value, index: int = 0) -> dict | None:
    if not isinstance(value, dict):
        return None
    label = str(value.get("label") or "").strip()
    if not label:
        return None
    key = str(value.get("key") or "").strip() or f"axis_{index + 1}"
    return {
        "key": key[:60],
        "label": label[:160],
        "questions": _str_list(value.get("questions"), limit=4),
        "requiredData": _str_list(value.get("requiredData"), limit=8),
        "searchQueries": _str_list(value.get("searchQueries"), limit=6),
    }


def _normalized_label(value: str) -> str:
    """주제 라벨은 40자 주제어다. 코드가 정한다 — 프롬프트는 부탁이지 제한이 아니다.

    LLM이 배경 문단을 통째로 topicLabel에 넣어도 여기서 첫 구획으로 끊는다.
    검색어에는 `_clean_queries()` 게이트가 있는데 제목에는 없어 200자가 그대로
    보고서 제목·저장 라벨이 됐다.

    이 게이트는 **상한이지 무조건 절단이 아니다**. 40자 이내면 그대로 둔다 —
    `AI 데이터센터: 전력 병목`처럼 짧고 변별력 있는 라벨까지 첫 구획에서 자르면
    planHash로 파일이 갈린 같은 날 두 보고서가 화면에서 글자까지 같은 카드가 된다.
    """
    # planner가 topic_schema를 import하므로 순환을 피해 호출 시점에 가져온다.
    from features.topic_report.planner import topic_subject

    # 라벨은 한 줄이다. 예전에는 topic_subject()가 줄바꿈에서 끊어 주었으므로,
    # 짧은 라벨을 그대로 두는 지금은 여기서 공백을 접어야 제목이 여러 줄이 되지 않는다.
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(value) <= _TOPIC_LABEL_MAX:
        return value
    return topic_subject(value) or value[:_TOPIC_LABEL_MAX]


def _expected_sections(plan: dict, axes: list) -> list[str]:
    """본문 섹션은 계획이 정한다. 없으면 분석축 라벨에서, 그것도 없으면 기본 골격."""
    declared = body_sections(_str_list(plan.get("expectedSections"), limit=16))
    if declared:
        return compose_sections(declared)
    return compose_sections(str((axis or {}).get("label") or "") for axis in axes or [])


def normalize_topic_plan(plan: dict | None, *, topic: str = "", topic_label: str = "") -> dict:
    """TopicPlan을 스키마에 맞게 강제 정규화한다. 누락 필드는 빈 값으로 보장."""
    plan = plan if isinstance(plan, dict) else {}
    axes = []
    for i, axis in enumerate(plan.get("analysisAxes") or []):
        normalized = normalize_axis(axis, i)
        if normalized:
            axes.append(normalized)
        if len(axes) >= 6:
            break
    return {
        "topic": str(plan.get("topic") or topic or "").strip()[:300],
        "topicLabel": _normalized_label(str(plan.get("topicLabel") or topic_label or topic or "").strip()),
        "reportType": normalize_report_type(plan.get("reportType")),
        "regions": _str_list(plan.get("regions"), limit=6),
        "assetClasses": _str_list(plan.get("assetClasses"), limit=6),
        "timeHorizon": str(plan.get("timeHorizon") or TIME_HORIZON_DEFAULT).strip()[:60],
        "userIntent": str(plan.get("userIntent") or "investment implication").strip()[:120],
        "researchQuestions": _str_list(plan.get("researchQuestions"), limit=6),
        "analysisAxes": axes,
        "requiredMarketData": _str_list(plan.get("requiredMarketData"), limit=14),
        "requiredMacroData": _str_list(plan.get("requiredMacroData"), limit=10),
        "searchQueries": _str_list(plan.get("searchQueries"), limit=12),
        "memoryQueries": _str_list(plan.get("memoryQueries"), limit=10),
        "candidateTickers": _ticker_map(plan.get("candidateTickers")),
        "expectedSections": _expected_sections(plan, axes),
        "dataGapsLikely": _str_list(plan.get("dataGapsLikely"), limit=8),
    }
