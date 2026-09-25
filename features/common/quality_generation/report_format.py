"""Report format guardrails for LLM section rewrite output."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FormatGuardResult:
    markdown: str
    mode: str
    warnings: list[str]
    issues: list[str]


def unwrap_markdown_payload(value: object) -> str:
    """Return Markdown, unwrapping accidental JSON-with-markdown payloads."""
    text = str(value or "").strip()
    for _ in range(3):
        candidate = text.strip()
        if not (candidate.startswith("{") and "markdown" in candidate[:300]):
            break
        try:
            payload = json.loads(candidate)
        except Exception:
            break
        if not isinstance(payload, dict) or "markdown" not in payload:
            break
        next_text = str(payload.get("markdown") or "").strip()
        if not next_text or next_text == text:
            break
        text = next_text
    malformed = _unwrap_malformed_markdown_json(text)
    if malformed:
        return malformed
    return text


def _unwrap_malformed_markdown_json(text: str) -> str:
    """Best-effort recovery for truncated {"markdown": "..."} responses."""
    match = re.match(r'^\{\s*"markdown"\s*:\s*"', str(text or "").strip(), flags=re.S)
    if not match:
        return ""
    body = str(text or "").strip()[match.end():]
    if not body:
        return ""
    for suffix in ['"\n}', '"}', '",\n  "changedSections"', '", "changedSections"']:
        idx = body.find(suffix)
        if idx >= 0:
            body = body[:idx]
            break
    body = body.replace("\\n", "\n")
    body = body.replace('\\"', '"')
    body = body.replace("\\/", "/")
    body = body.replace("\\\\", "\\")
    return body.strip()


def _norm_heading(line: str) -> str:
    text = re.sub(r"^#{1,6}\s+", "", str(line or "").strip())
    text = re.sub(r"\s+", " ", text)
    return text.strip().casefold()


def _main_sections(markdown: str) -> list[dict]:
    matches: list[dict] = []
    offset = 0
    for line in str(markdown or "").splitlines(keepends=True):
        content = line.rstrip("\r\n")
        level = len(content) - len(content.lstrip("#"))
        if (
            1 <= level <= 2
            and len(content) > level
            and content[level].isspace()
            and content[level:].strip()
        ):
            matches.append(
                {
                    "start": offset,
                    "end": offset + len(content),
                    "full": content.strip(),
                    "level": level,
                }
            )
        offset += len(line)
    sections: list[dict] = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1]["start"] if idx + 1 < len(matches) else len(markdown)
        full = match["full"]
        body_start = match["end"]
        sections.append({
            "heading": full,
            "norm": _norm_heading(full),
            "level": match["level"],
            "start": match["start"],
            "body_start": body_start,
            "end": end,
            "text": markdown[match["start"]:end].strip(),
            "body": markdown[body_start:end].strip(),
        })
    return sections


def _contains_heading_prefix(markdown: str, prefix: str) -> bool:
    prefix_norm = _norm_heading(prefix)
    for section in _main_sections(markdown):
        if section["norm"].startswith(prefix_norm):
            return True
    return False


def _ordered_prefixes_present(markdown: str, prefixes: list[str]) -> tuple[bool, list[str]]:
    sections = _main_sections(markdown)
    norms = [s["norm"] for s in sections]
    missing: list[str] = []
    cursor = 0
    for prefix in prefixes:
        prefix_norm = _norm_heading(prefix)
        found_at = -1
        for idx in range(cursor, len(norms)):
            if norms[idx].startswith(prefix_norm):
                found_at = idx
                break
        if found_at < 0:
            missing.append(prefix)
        else:
            cursor = found_at + 1
    return not missing, missing


def _required_prefixes(artifact_type: str, original: str) -> list[str]:
    if artifact_type == "briefing":
        market_prefixes: list[str] = []
        if _contains_heading_prefix(original, "# US Market Briefing"):
            market_prefixes.extend([
                "# US Market Briefing",
                "## 0. 오늘의 미국장 성격",
                "## 1. 미국장 시장 흐름",
                "## 2. 미국장을 움직인 핵심 변수",
                "## 3. 미국장을 주도한 기업 ①",
                "## 4. 미국장을 주도한 기업 ②",
                "## 5. 일반 투자자 관점",
                "## 6. 다음 미국장 체크포인트",
                "## 오늘의 결론",
            ])
        if _contains_heading_prefix(original, "# Korea Market Briefing"):
            market_prefixes.extend([
                "# Korea Market Briefing",
                "## 0. 오늘의 한국장 성격",
                "## 1. 한국장 시장 흐름",
                "## 2. 한국장을 움직인 핵심 변수",
                "## 3. 한국장을 주도한 기업 ①",
                "## 4. 한국장을 주도한 기업 ②",
                "## 5. 일반 투자자 관점",
                "## 6. 다음 한국장 체크포인트",
                "## 오늘의 결론",
            ])
        if market_prefixes:
            return [
                *market_prefixes,
                "## 참고자료",
                "## Source & Data Notes",
            ]
        return [
            "# Daily Market Briefing",
            "## 0. 오늘의 시장 성격",
            "## 1. 시장 흐름",
            "## 2. 시장을 움직인 핵심 변수",
            "## 3. 시장을 주도한 기업 ①",
            "## 4. 시장을 주도한 기업 ②",
            "## 5. 일반 투자자 관점",
            "## 6. 내일 확인할 체크포인트",
            "## 오늘의 결론",
            "## 참고자료",
            "## Source & Data Notes",
        ]
    if artifact_type == "topic_report":
        # 머리 1개(Executive Summary)·꼬리 3개만 이름이 고정이다(0.6 Phase 1,
        # 2026-09-13). 본문 섹션 이름은 분석축이 정하므로 여기서 미리 알 수 없어
        # 목록에 넣지 않는다 — 예전 "현재 상황/작동 경로/수혜·피해" 같은 기본값을
        # 넣어 두면 실제로는 다른 축 이름을 쓰는 대부분의 보고서에서 항상 불일치로
        # 잡혔다. "시나리오"·"결론"도 이제 이름을 강제하지 않으므로 뺐다.
        return [
            "## Executive Summary",
            "## 반론과 리스크",
            "## 앞으로 확인할 체크포인트",
            "## Source & Data Notes",
        ]
    if artifact_type == "company_analysis":
        return [
            "섹션 0",
            "섹션 1",
            "섹션 2",
            "섹션 3",
            "섹션 4",
            "섹션 5",
            "섹션 6",
            "섹션 7",
            "섹션 8",
        ]
    return []


def _original_heading_issues(original: str, candidate: str) -> list[str]:
    original_sections = [s for s in _main_sections(original) if s["level"] <= 2]
    candidate_norms = {s["norm"] for s in _main_sections(candidate) if s["level"] <= 2}
    if len(original_sections) < 4:
        return []
    missing = [s["heading"] for s in original_sections if s["norm"] not in candidate_norms]
    allowed_missing = max(1, len(original_sections) // 5)
    if len(missing) > allowed_missing:
        return [f"원본 주요 헤더 {len(missing)}개가 후보에서 누락됨: {', '.join(missing[:5])}"]
    return []


def detect_report_format_issues(artifact_type: str, original: str, candidate: str) -> list[str]:
    candidate = unwrap_markdown_payload(candidate)
    issues: list[str] = []
    if not candidate.strip():
        return ["후보 Markdown이 비어 있음"]
    if candidate.lstrip().startswith("{") and '"markdown"' in candidate[:300]:
        issues.append("후보가 Markdown이 아니라 JSON 객체 문자열로 보임")
    if not _main_sections(candidate):
        issues.append("후보에 Markdown 헤더가 없음")
    prefixes = _required_prefixes(artifact_type, original)
    if prefixes:
        ok, missing = _ordered_prefixes_present(candidate, prefixes)
        original_has_spec = sum(1 for prefix in prefixes if _contains_heading_prefix(original, prefix))
        if artifact_type == "company_analysis" and original_has_spec < 5:
            missing = []
            ok = True
        # topic_report는 이제 고정 이름이 4개뿐이라(위 _required_prefixes) 옛 11개
        # 기준의 "5개 미만이면 건너뛴다" 문턱을 그대로 두면 항상 건너뛰게 된다.
        # 목록 크기에 비례해 2로 낮춘다.
        if artifact_type == "topic_report" and original_has_spec < 2:
            missing = []
            ok = True
        if not ok:
            issues.append(f"필수 보고서 헤더 누락 또는 순서 변경: {', '.join(missing[:6])}")
    issues.extend(_original_heading_issues(original, candidate))
    return issues


def _allowed_replace_keys(artifact_type: str, original_sections: list[dict]) -> set[str]:
    keys = {s["norm"] for s in original_sections if s["level"] == 2}
    if artifact_type == "briefing":
        disallowed_prefixes = [
            _norm_heading("# Daily Market Briefing"),
            _norm_heading("## 참고자료"),
        ]
        return {
            s["norm"]
            for s in original_sections
            if s["level"] == 2 and not any(s["norm"].startswith(p) for p in disallowed_prefixes)
        }
    return keys


def _merge_matching_sections(original: str, candidate: str, artifact_type: str) -> str:
    original_sections = _main_sections(original)
    candidate_sections = _main_sections(candidate)
    if not original_sections or not candidate_sections:
        return original
    candidate_by_norm = {s["norm"]: s for s in candidate_sections}
    allowed = _allowed_replace_keys(artifact_type, original_sections)
    pieces: list[str] = []
    cursor = 0
    changed = False
    for section in original_sections:
        pieces.append(original[cursor:section["start"]])
        replacement = candidate_by_norm.get(section["norm"])
        if replacement and section["norm"] in allowed and replacement["body"]:
            pieces.append(f"{section['heading']}\n\n{replacement['body'].strip()}\n")
            changed = True
        else:
            pieces.append(original[section["start"]:section["end"]])
        cursor = section["end"]
    pieces.append(original[cursor:])
    return "".join(pieces).strip() if changed else original


def enforce_report_format(artifact_type: str, original: str, candidate: str) -> FormatGuardResult:
    original = str(original or "")
    candidate = unwrap_markdown_payload(candidate)
    issues = detect_report_format_issues(artifact_type, original, candidate)
    if not issues:
        return FormatGuardResult(candidate, "full_markdown", [], [])

    merged = _merge_matching_sections(original, candidate, artifact_type)
    if merged != original:
        merged_issues = detect_report_format_issues(artifact_type, original, merged)
        if not merged_issues:
            return FormatGuardResult(
                merged,
                "section_merge",
                ["LLM 출력의 보고서 형식이 맞지 않아 원본 섹션 골격에 동일 헤더 본문만 병합했습니다."],
                issues,
            )

    return FormatGuardResult(
        original,
        "rejected",
        ["LLM 섹션 개선 결과가 보고서 형식을 깨뜨려 적용하지 않았습니다."],
        issues,
    )
