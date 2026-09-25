"""Generation-time quality targets shared by report builders."""
from __future__ import annotations

from typing import Any


QUALITY_TARGETS = {
    "briefing": {
        "goal": "미국장과 한국장의 날짜 정합성, 가격 반응, 핵심 변수, 반론/확인 조건을 근거 중심으로 연결한 일일 브리핑",
        "minimumSources": 6,
        "evidenceMix": [
            "research-inbox/articles 또는 research-inbox/rss의 시장 기사",
            "미국장 마감/정규장 기준일 확인 자료",
            "한국장 지수·수급·업종 흐름 자료",
            "marketTape 또는 시장 가격 스냅샷",
        ],
        "collectionRoutes": [
            "로컬 articles/rss에서 브리핑 대상 시장창 자료를 우선 사용",
            "KOSPI/KOSDAQ·투자자별 수급은 provider chain 또는 한국 market-data CSV로 보강",
            "미국장 결과 수치는 정규장 기준일이 맞는 마감 기사 또는 market snapshot으로 교차 확인",
            "자료가 부족하면 수치를 추정하지 말고 dataGap과 다음 확인 경로를 남김",
        ],
        "requiredOutputs": [
            "오늘 시장 성격과 핵심 변수 3개 이하",
            "미국장/한국장 날짜와 반영 시차 구분",
            "반론 또는 판단이 틀릴 조건",
            "다음 거래일 체크포인트",
            "참고자료 또는 Source & Data Notes",
        ],
    },
    "company_analysis": {
        "goal": "공식 숫자와 공시 문단을 우선 사용해 투자 포인트, 재무 품질, 밸류에이션, 리스크를 조건부로 설명한 기업 분석",
        "minimumSources": 4,
        "evidenceMix": [
            "SEC companyfacts 또는 DART Open API 공식 숫자",
            "SEC 10-K/10-Q HTML 문단 또는 DART/로컬 filings",
            "IR·실적발표·컨퍼런스콜·증권사 리포트",
            "시장 가격·밸류에이션 데이터",
        ],
        "collectionRoutes": [
            "미국 기업은 SEC companyfacts와 10-K/10-Q HTML 문단을 최우선",
            "국내 기업은 DART 재무제표와 공시 목록을 최우선",
            "공식 자료가 부족하면 로컬 filings/reports/articles/rss 순서로 보조",
            "웹 검색 허용 시 회사 IR, earnings release, transcript, SEC/EDGAR 또는 DART를 먼저 확인",
        ],
        "requiredOutputs": [
            "핵심 판단과 3~5개 투자 포인트",
            "공식 숫자 기반 Financial Summary",
            "재무 품질과 밸류에이션",
            "리스크와 반증조건",
            "Sources Used와 데이터 한계",
        ],
    },
    "topic_report": {
        "goal": "질문에 직접 답하고 Evidence Pack의 supporting/challenging/data point를 균형 있게 사용한 투자 주제 보고서",
        "minimumSources": 6,
        "evidenceMix": [
            "topic planner의 분석축별 Evidence Pack",
            "시장 데이터와 macro data",
            "시장 내러티브 기록",
            "반대 방향 또는 약화 조건을 보여주는 challenging evidence",
        ],
        "collectionRoutes": [
            "Topic Plan의 searchQueries와 analysisAxes를 기준으로 축별 검색",
            "Evidence Pack이 빈 축은 dataGap으로 남기고 Source & Data Notes에 표시",
            "시장 데이터와 FRED/BOK는 있으면 수치 근거로 사용하고 없으면 한계를 명시",
            "userContext와 Obsidian 노트는 관심 방향/hypothesis로만 사용",
        ],
        "requiredOutputs": [
            "질문 정의와 핵심 요약을 하나로 묶은 Executive Summary",
            "작동 경로",
            "반론과 리스크",
            "앞으로 확인할 체크포인트",
            "질문에 대한 직접적인 답과 판단이 흔들리는 조건(제목은 자유, 내용은 필수)",
            "Source & Data Notes",
        ],
    },
}


def quality_target_for(artifact_type: str) -> dict[str, Any]:
    return dict(QUALITY_TARGETS.get(str(artifact_type or ""), QUALITY_TARGETS["topic_report"]))


def render_quality_target_context(
    artifact_type: str,
    *,
    preflight: dict | None = None,
    context: dict | None = None,
) -> str:
    """Render generation requirements for LLM/rule contexts.

    This is intentionally phrased as report-writing guidance, not as a hidden
    scoring rubric. The model sees the same source boundaries the evaluator uses.
    """
    target = quality_target_for(artifact_type)
    context = context or {}
    preflight = preflight or {}
    required_inputs = preflight.get("requiredInputs") or {}
    risks = preflight.get("risks") or []

    lines = [
        "## 생성 품질 목표",
        target["goal"],
        "",
        f"- 최소 근거 목표: {target['minimumSources']}건 이상. 부족하면 단정하지 말고 데이터 한계로 표시.",
        "- 핵심 주장은 수치·출처·자료 유형 중 하나 이상으로 뒷받침.",
        "- supporting evidence와 challenging evidence를 구분하고, 판단이 틀릴 조건을 반드시 포함.",
        "- 체크포인트는 사용자가 직접 확인 가능한 지표/일정/공시/가격 조건으로 작성.",
        "- 사용자 노트나 userContext는 hypothesis/관심 방향이며 evidence로 쓰지 않음.",
        "",
        "### 필요한 근거 믹스",
        *[f"- {item}" for item in target["evidenceMix"]],
        "",
        "### 자료 수집·보강 루트",
        *[f"- {item}" for item in target["collectionRoutes"]],
        "",
        "### 필수 산출 요소",
        *[f"- {item}" for item in target["requiredOutputs"]],
    ]
    if required_inputs:
        lines += [
            "",
            "### 현재 입력 상태",
            *[f"- {key}: {value}" for key, value in required_inputs.items()],
        ]
    if risks:
        lines += [
            "",
            "### 생성 전 주의할 품질 리스크",
            *[f"- {risk}" for risk in risks[:8]],
        ]
    if context.get("extraRoutes"):
        lines += [
            "",
            "### 추가 보강 루트",
            *[f"- {route}" for route in context.get("extraRoutes", [])[:8]],
        ]
    return "\n".join(lines)
