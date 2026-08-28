"""Strict structural and evidence-boundary validation for Deep Research."""
from __future__ import annotations

import re
from collections import Counter

from features.common.report_prose import (
    HEDGE_DENSITY_LIMIT,
    HEDGE_PHRASES,
    HEDGE_REPEAT_DENSITY,
    HEDGE_REPEAT_MIN,
    SOURCE_ID_RE as _SOURCE_ID_RE,
    SPEAKER_ROLE_WORDS,
    defect as _defect,
    sections_citing,
    split_sections,
    unattributed_speech,
    visible_character_count,
    visible_markdown,
)
from features.common import report_prose as _prose
from features.topic_report.section_sources import (
    SOURCE_TAG_NAMES,
    _INLINE_CITATION,
    apply_section_usage,
    canonical_heading,
)
from features.topic_report.topic_schema import (
    EXPECTED_SECTIONS_V2,
    REPORT_HEAD_SECTIONS,
    REPORT_TAIL_SECTIONS,
)


_SENTENCE = re.compile(r"(?:다\.|[.!?。！？])\s+|[\r\n]+")
# 설명 단계를 소제목으로 굳힌 흔적. 초심자 서술을 4단계로 지시했더니 모델이 모든 본문
# 섹션에 같은 `###` 소제목 네 개를 달아 보고서가 서식이 됐다.
_STEP_HEADING = re.compile(
    r"^###\s*(?:개념|작동\s*원리|실제로\s*지금\s*어떤가|그래서\s*이\s*질문에는)\s*$",
    re.MULTILINE,
)

_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)

_SOURCE_EXEMPT = frozenset({"질문 정의와 분석 범위", "Source & Data Notes"})


def _source_required(sections: list[str]) -> list[str]:
    """근거 연결을 요구할 섹션. 범위 설명과 데이터 메모는 근거를 인용하는 자리가 아니다."""
    return [heading for heading in sections if heading not in _SOURCE_EXEMPT]




# 질문을 구별짓는 말. 연도·사건명처럼 다른 말로 바꾸기 어려운 것을 고른다.
_QUESTION_STOPWORDS = frozenset({
    "영향", "분석", "전망", "관련", "대한", "대해", "어떻게", "무엇", "무엇인가", "있는", "인가",
    "그리고", "하지만", "어떤", "이런", "그런", "가운데", "위해", "따라", "통해", "각각",
    "시장", "경제", "지표", "국면", "상황", "가능성", "경우", "때문", "정도", "수준",
    # 의문사·활용 꼬리. 두 글자 내용어를 살리면 이것들이 키워드로 남는데, 잘 쓴 글은
    # 질문의 활용형을 그대로 반복하지 않으므로 대조 기준이 될 수 없다.
    "무엇인", "어떠한", "어디에", "누구인", "되는가", "하는가", "인가요", "실제",
})
_QUESTION_TOKEN = re.compile(r"[A-Za-z가-힣0-9]{2,}")
_PARTICLES = "이가은는을를와과에의로서도만"
# 연도만 고른다. `10년물`·`P500` 같은 용어는 숫자를 품었을 뿐 답의 대상이 아니다.
_YEAR_TOKEN = re.compile(r"^(?:19|20)\d{2}년?$")


def question_keywords(question: str, limit: int = 8) -> list[str]:
    """질문에서 본문 대조에 쓸 말. 숫자가 든 말(연도)을 가장 먼저 본다."""
    tokens: list[str] = []
    for raw in _QUESTION_TOKEN.findall(str(question or "")):
        token = raw.strip()
        # 조사를 떼지 않으면 "기간프리미엄은"이 본문의 "기간프리미엄이"와 안 맞아
        # 답한 질문을 못 답했다고 잡는다.
        if len(token) >= 3 and token[-1] in _PARTICLES:
            token = token[:-1]
        if len(token) < 2 or token.lower() in _QUESTION_STOPWORDS or token in tokens:
            continue
        tokens.append(token)
    years = [token for token in tokens if _YEAR_TOKEN.match(token)]
    if years:
        # 연도가 든 질문은 그 연도가 답의 대상이다. 다른 낱말이 겹친다고 답한 것이 아니다 —
        # 실측으로 "2021~2022년 인플레이션 국면" 질문이 본문에 2021도 2022도 없이
        # 인플레이션·정책 같은 일반어만으로 통과했다.
        #
        # **연도만 골라낸다.** 예전에는 "숫자가 든 4자 이상 토큰"으로 물어서 `10년물`,
        # `P500`, `5y5y` 같은 용어가 걸렸고, 그러면 내용어를 전부 버린 채 그 한 토큰의
        # 문자열 일치만 요구했다 — "미국 10년물 금리…" 질문은 본문이 "10년 만기 국채
        # 금리"라고 제대로 답해도 미답으로 잡혀 `question_unanswered`(심각도 70)가
        # 붙고 품질이 69점으로 눌렸다.
        return years[:limit]
    # 두 글자를 버리지 않는다. 한국어 내용어는 대부분 두 글자라(물가·금리·환율·경로)
    # 세 글자 하한을 두면 동사 활용형과 의문사만 남아 답한 질문을 못 답했다고 잡는다.
    return tokens[:limit]


def unanswered_questions(text: str, research_questions) -> list[str]:
    """본문에 흔적이 하나도 없는 질문.

    비교는 **공백을 지우고** 한다. 한국어 복합어의 띄어쓰기는 글쓴이마다 다르고,
    실측으로 질문의 "기간프리미엄"이 본문의 "기간 프리미엄"과 맞지 않아 8번이나
    다룬 주제를 다루지 않았다고 잡았다.
    """
    body = re.sub(r"\s+", "", str(text or ""))
    missing: list[str] = []
    for question in research_questions or []:
        keywords = [re.sub(r"\s+", "", keyword) for keyword in question_keywords(question)]
        keywords = [keyword for keyword in keywords if keyword]
        if not keywords:
            continue
        if not any(keyword in body for keyword in keywords):
            missing.append(str(question))
    return missing


# 유보가 있어야 마땅한 자리는 세지 않는다. 데이터 한계 서술이 그 섹션의 일이다.
_HEDGE_EXEMPT_SECTIONS = ("Source & Data Notes",)


def hedge_stats(markdown: str) -> dict:
    """딥 리서치의 면제 섹션을 적용한 유보 통계."""
    return _prose.hedge_stats(markdown, exempt=_HEDGE_EXEMPT_SECTIONS)


def hedgiest_section(markdown: str) -> str:
    """유보 표현이 가장 몰린 섹션. 보수가 손댈 자리를 가리킨다."""
    return _prose.hedgiest_section(markdown, exempt=_HEDGE_EXEMPT_SECTIONS)


def validate_deep_report(
    markdown: str,
    *,
    source_ledger: list[dict],
    depth_policy: dict,
    material_resolution: dict | None = None,
    internal_score: int = 0,
    expected_sections: list[str] | None = None,
    research_questions: list[str] | None = None,
    quote_sources: list[dict] | None = None,
) -> dict:
    text = str(markdown or "").strip()
    defects = []
    sections = split_sections(text)
    headings = [row["heading"] for row in sections]
    expected = [str(item).strip() for item in (expected_sections or depth_policy.get("sections") or EXPECTED_SECTIONS_V2)]
    head, tail = list(REPORT_HEAD_SECTIONS), list(REPORT_TAIL_SECTIONS)
    if not text:
        defects.append(_defect("blocking", "empty_body", 100, fixable=False))
    # 차단은 **필수 요소**가 없을 때다. 꼬리의 반론·시나리오·체크포인트·Source Notes는
    # 확증편향 방지와 추적성의 집행 장치라 빠지면 보고서로 성립하지 않는다.
    # 본문 구성이 계획과 다른 것은 결함이지만 결과물을 버릴 이유는 아니다 — 예전에는
    # 전체 목록 정확 일치를 차단으로 두어, 주제에 맞는 구성을 아예 만들 수 없었다.
    if len(headings) < len(head) + len(tail) or headings[: len(head)] != head or headings[-len(tail):] != tail:
        defects.append(_defect("blocking", "required_sections_missing", 100))
    elif headings != expected:
        defects.append(_defect("structure", "body_sections_differ", 45))
    # 근거 태그로 읽히지 않는 주석. 모델이 태그 이름을 새로 만들면 연결이 조용히
    # 무너지므로(실측: 한 보고서에서 `<!-- sources: -->` 22개, linkage 1.00 → 0.38)
    # 결함으로 남긴다.
    # 질문에 답했는가. 근거가 모였는지가 아니라 본문이 다뤘는지를 본다.
    # 유보 표현 — 오류 위험은 낮추지만 독자는 지금 가장 타당한 판단이 무엇인지 알 수 없다.
    hedges = hedge_stats(text)
    if hedges["per1000"] > HEDGE_DENSITY_LIMIT:
        defects.append(_defect("style", "hedge_overuse", 40, section=hedgiest_section(text)))
    if hedges["topCount"] >= HEDGE_REPEAT_MIN and hedges["topPer1000"] > HEDGE_REPEAT_DENSITY:
        defects.append(_defect("style", "hedge_repetition", 35, section=hedgiest_section(text)))
    # 발언은 누가 언제 말했는지가 곧 근거다. 기관 이름으로 뭉개면 인용이 아니다.
    unattributed = unattributed_speech(text, quote_sources)
    citing = sections_citing(text, unattributed)
    for source_id in unattributed[:3]:
        defects.append(_defect("evidence", "speech_unattributed", 40, section=citing.get(source_id, "")))
    missing_questions = unanswered_questions(text, research_questions)
    if missing_questions:
        body_target = next(
            (heading for heading in headings if heading not in REPORT_HEAD_SECTIONS and heading not in REPORT_TAIL_SECTIONS),
            "결론",
        )
        for question in missing_questions[:3]:
            defects.append(_defect("coverage", "question_unanswered", 70, section=body_target))
    if _INLINE_CITATION.search(text):
        # 정본은 숨김 주석이다. 본문에 ID가 보이면 독자가 읽을 것이 아닌 내부 식별자를
        # 보게 된다(실측 18곳).
        defects.append(_defect("evidence", "visible_source_id", 40))
    step_headings = _STEP_HEADING.findall(text)
    if len(step_headings) >= 3:
        defects.append(_defect("structure", "templated_step_headings", 40))
    unknown_comments = [
        comment for comment in _COMMENT.findall(text)
        if not any(name in comment.lower() for name in SOURCE_TAG_NAMES)
    ]
    if unknown_comments:
        defects.append(_defect("evidence", "unknown_comment_tag", 40))
    projected_ledger, source_result = apply_section_usage(text, source_ledger)
    for code, values, category, severity in (
        # 태그는 숨은 주석이고, 모르는 id는 usage에서 이미 제외된다. 차단으로 두면
        # 모델이 id 하나를 잘못 베낀 것만으로 다 만든 보고서가 통째로 버려진다 —
        # 근거 연결이 줄어드는 것은 linkage 점수가 이미 벌한다.
        ("malformed_source_tag", source_result["malformedSourceIds"], "major", 60),
        ("unknown_source_tag", source_result["unknownSourceIds"], "major", 60),
        # 자기참조 근거만은 계속 차단이다(§5 원칙 5) — 위 둘과 달리 내용 오염이다.
        ("forbidden_source_tag", source_result["forbiddenSourceIds"], "blocking", 100),
    ):
        if values:
            defects.append(_defect(category, code, severity))
    usage = source_result["sectionUsage"]
    source_required = _source_required(headings or expected)
    linked_required = sum(bool(usage.get(heading)) for heading in source_required)
    linkage_ratio = linked_required / max(1, len(source_required))
    for heading in source_required:
        if not usage.get(heading):
            defects.append(_defect("evidence", "unlinked_section", 35, section=heading))
    if linkage_ratio < 0.7:
        defects.append(_defect("evidence", "low_source_linkage", 70))
    material_missing = [
        row for category in ("market", "macro")
        for row in (material_resolution or {}).get(category, [])
        if row.get("status") != "available"
    ]
    if material_missing:
        defects.append(_defect("non_fixable", "required_material_unavailable", 60, fixable=False))
    count = visible_character_count(text)
    recommended_min = int(depth_policy.get("recommendedMinChars") or 0)
    safety_max = int(depth_policy.get("safetyMaxChars") or 18_000)
    if count < recommended_min:
        defects.append(_defect("depth", "below_recommended_length", 45))
    if count > safety_max:
        defects.append(_defect("depth", "above_safety_length", 80))
    budgets = depth_policy.get("sectionBudgets") or {}
    for section in sections:
        target = int(budgets.get(section["heading"]) or 0)
        if target and len(section["body"]) < max(180, int(target * 0.35)):
            defects.append(_defect("depth", "thin_section", 35, section=section["heading"]))
    sentences = [re.sub(r"\s+", " ", row).strip() for row in _SENTENCE.split(text)]
    repeats = Counter(row for row in sentences if len(row) >= 40)
    if any(count >= 3 for count in repeats.values()):
        defects.append(_defect("depth", "repeated_sentence", 55))
    if "시나리오" in headings:
        scenario = next((row["body"] for row in sections if row["heading"] == "시나리오"), "")
        if not any(term in scenario for term in ("조건", "이상", "이하", "상회", "하회", "경우")):
            defects.append(_defect("reasoning", "unconditional_scenarios", 45, section="시나리오"))
    blocking = [row for row in defects if row["category"] == "blocking"]
    fixable = [row for row in defects if row["fixable"]]
    return {
        "valid": not blocking,
        "defects": defects,
        "metrics": {
            "characterCount": count,
            "sourceLinkageRatio": round(linkage_ratio, 4),
            "requiredSectionCount": len(headings),
            "unansweredQuestionCount": len(missing_questions),
            "blockingCount": len(blocking),
            "fixableSeverity": sum(int(row["severity"]) for row in fixable),
            "fixableCount": len(fixable),
            "internalScore": int(internal_score),
        },
        "sourceLedger": projected_ledger,
        "sourceResult": source_result,
    }


# 이 모듈이 계약의 창구다. 공용 도구(`common/report_prose.py`)에서 온 이름도 여기서
# 함께 내보내, 소비자가 어느 쪽에서 가져올지 헷갈리지 않게 한다.
__all__ = [
    "HEDGE_DENSITY_LIMIT",
    "HEDGE_PHRASES",
    "HEDGE_REPEAT_DENSITY",
    "HEDGE_REPEAT_MIN",
    "SPEAKER_ROLE_WORDS",
    "canonical_heading",
    "hedge_stats",
    "hedgiest_section",
    "question_keywords",
    "sections_citing",
    "split_sections",
    "unanswered_questions",
    "unattributed_speech",
    "validate_deep_report",
]
