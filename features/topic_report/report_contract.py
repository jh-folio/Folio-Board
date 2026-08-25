"""Strict structural and evidence-boundary validation for Deep Research."""
from __future__ import annotations

import re
from collections import Counter

from features.topic_report.depth_policy import visible_character_count, visible_markdown
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


_HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
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


def split_sections(markdown: str) -> list[dict]:
    text = str(markdown or "")
    matches = list(_HEADING.finditer(text))
    rows = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        rows.append({
            "heading": canonical_heading(match.group(1)),
            "rawHeading": match.group(1).strip(),
            "body": text[match.end():end].strip(),
        })
    return rows


def _defect(category: str, code: str, severity: int, *, section: str = "", fixable: bool = True) -> dict:
    return {"category": category, "code": code, "severity": severity, "section": section, "fixable": fixable}


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
    numeric = [token for token in tokens if any(ch.isdigit() for ch in token) and len(token) >= 4]
    if numeric:
        # 연도가 든 질문은 그 연도가 답의 대상이다. 다른 낱말이 겹친다고 답한 것이 아니다 —
        # 실측으로 "2021~2022년 인플레이션 국면" 질문이 본문에 2021도 2022도 없이
        # 인플레이션·정책 같은 일반어만으로 통과했다.
        return numeric[:limit]
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


# 유보 표현. 제안서 §13 Rule 3의 목록에 실측에서 실제로 나온 것을 더했다.
HEDGE_PHRASES = (
    "수 있다", "수 있으", "수 있는", "가능성이 있다", "가능성을 배제",
    "단정하기 어렵", "판단하기 어렵", "확인하기 어렵",
    "함께 봐야", "함께 볼", "점검해야", "구분해야", "주의해야",
    "것으로 보인다", "보이지만",
)
# 유보가 있어야 마땅한 자리는 세지 않는다. 데이터 한계 서술이 그 섹션의 일이다.
_HEDGE_EXEMPT_SECTIONS = ("Source & Data Notes",)
# 이 밀도를 넘으면 판단이 아니라 회피다. 실측 기준: 문제로 지적된 보고서가
# 천자당 3.07~3.34회였고 그중 `수 있다` 하나가 23회였다.
HEDGE_DENSITY_LIMIT = 2.5
HEDGE_REPEAT_MIN = 10
HEDGE_REPEAT_DENSITY = 1.5
# 발언에 붙는 직함. 사람 이름은 원문이 영문이고 본문은 한국어라 대조할 수 없다
# ("Jerome H. Powell" vs "파월"). 직함은 두 표기에 함께 남는다.
SPEAKER_ROLE_WORDS = ("의장", "총재", "이사", "장관", "위원", "대표", "사장", "CEO")


_SOURCE_ID_RE = re.compile(r"(?:ev|market|macro|web)_[A-Za-z0-9_.\-]+")


def hedge_stats(markdown: str) -> dict:
    """유보 표현의 밀도와 한 표현의 쏠림. 둘 다 봐야 한다 —
    총량이 적어도 한 표현만 스무 번 나오면 글이 같은 자리에서 계속 멈춘다."""
    body = "".join(
        str(row.get("body") or "")
        for row in split_sections(visible_markdown(markdown))
        if not any(name in str(row.get("heading") or "") for name in _HEDGE_EXEMPT_SECTIONS)
    )
    length = len(body)
    counts = {phrase: body.count(phrase) for phrase in HEDGE_PHRASES}
    counts = {phrase: count for phrase, count in counts.items() if count}
    total = sum(counts.values())
    top = max(counts.items(), key=lambda row: row[1], default=("", 0))
    per_1000 = (total / length * 1000) if length else 0.0
    return {
        "chars": length,
        "total": total,
        "per1000": round(per_1000, 2),
        "topPhrase": top[0],
        "topCount": top[1],
        "topPer1000": round(top[1] / length * 1000, 2) if length else 0.0,
    }


def hedgiest_section(markdown: str) -> str:
    """유보 표현이 가장 몰린 섹션. 보수가 손댈 자리를 가리킨다."""
    best, best_count = "", 0
    for row in split_sections(visible_markdown(markdown)):
        heading = str(row.get("heading") or "")
        if any(name in heading for name in _HEDGE_EXEMPT_SECTIONS):
            continue
        body = str(row.get("body") or "")
        count = sum(body.count(phrase) for phrase in HEDGE_PHRASES)
        if count > best_count:
            best, best_count = heading, count
    return best


def sections_citing(markdown: str, source_ids) -> dict:
    """근거 ID별로 그것을 인용한 첫 섹션."""
    wanted = {str(source_id) for source_id in source_ids or []}
    out: dict = {}
    for row in split_sections(str(markdown or "")):
        found = set(_SOURCE_ID_RE.findall(str(row.get("body") or "")))
        for source_id in wanted & found:
            out.setdefault(source_id, str(row.get("heading") or ""))
    return out


def unattributed_speech(markdown: str, quote_sources) -> list[str]:
    """인용한 발언 근거 중 본문이 화자를 밝히지 않은 것.

    실측: 파월·월러 발언 4건을 찾아 원장에 올렸고 본문이 그 태그를 달았는데,
    문장은 전부 "연준은 ~라고 설명했다"였고 이름은 0회였다. 누가 말했는지가 사라지면
    그것은 발언이 아니라 기관 입장이다.
    """
    rows = [row for row in quote_sources or [] if isinstance(row, dict) and row.get("sourceId")]
    if not rows:
        return []
    visible = visible_markdown(markdown)
    tagged = set()
    for match in re.finditer(r"<!--(.*?)-->", markdown or "", re.DOTALL):
        tagged.update(_SOURCE_ID_RE.findall(match.group(1)))
    missing = []
    for row in rows:
        source_id = str(row.get("sourceId") or "")
        role = str(row.get("role") or "")
        if source_id not in tagged or not role:
            continue
        if role not in visible:
            missing.append(source_id)
    return missing


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


__all__ = ["canonical_heading", "split_sections", "validate_deep_report"]
