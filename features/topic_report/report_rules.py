"""Rule-based fallback report when LLM is unavailable."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

try:
    KST = ZoneInfo("Asia/Seoul")
except Exception:
    KST = dt.timezone(dt.timedelta(hours=9))


def _pct_str(v):
    if v is None:
        return "-"
    return f"{v:+.2f}%"


def _fmt(v, digits=2):
    if v is None:
        return "-"
    return f"{v:.{digits}f}"


def build_rule_report(
    topic: dict,
    market_data: dict,
    macro_data: dict,
    docs: list,
    memories: list,
    user_context: str = "",
    topic_plan: dict | None = None,
    data_gaps: list | None = None,
    as_of: str = "",
) -> str:
    label = topic.get("label", "시장")
    # 제목 날짜는 호출자가 정한 보고서 기준일이다. 여기서 실행 시각을 다시 읽으면
    # 자정을 넘겨 끝난 생성에서 JSON `date`/`title`과 본문 H1만 하루 어긋난다.
    today = str(as_of or "").strip() or dt.datetime.now(tz=KST).strftime("%Y-%m-%d")
    sections = []

    sections.append(f"# {label} 분석 리포트 — {today}")
    sections.append(f"\n> **규칙 기반 보고서**: LLM을 사용할 수 없어 수집된 데이터를 구조화한 요약입니다.\n")

    # --- Topic Plan summary (v2) ---
    if topic_plan:
        from features.topic_report.topic_schema import REPORT_TYPE_LABELS
        rtype = topic_plan.get("reportType", "")
        sections.append("## 리서치 계획 요약\n")
        plan_lines = [f"- **보고서 유형**: {REPORT_TYPE_LABELS.get(rtype, rtype)} (`{rtype}`)"]
        if topic_plan.get("regions"):
            plan_lines.append(f"- **지역**: {', '.join(topic_plan['regions'])}")
        if topic_plan.get("assetClasses"):
            plan_lines.append(f"- **자산군**: {', '.join(topic_plan['assetClasses'])}")
        if topic_plan.get("researchQuestions"):
            plan_lines.append("- **리서치 질문**:")
            plan_lines += [f"  - {q}" for q in topic_plan["researchQuestions"][:4]]
        if topic_plan.get("analysisAxes"):
            plan_lines.append("- **분석 축**:")
            plan_lines += [f"  - {a.get('label', '')}" for a in topic_plan["analysisAxes"]]
        sections.append("\n".join(plan_lines))
        deep = topic_plan.get("deepResearch") or {}
        if deep.get("enabled"):
            sections.append("\n## 심층 리서치 커버리지\n")
            coverage_lines = [
                f"- **라운드 상한**: {deep.get('maxRounds', 2)}회",
                "- **하위 질문**:",
            ]
            for question in (deep.get("subQuestions") or [])[:12]:
                coverage_lines.append(
                    f"  - R{question.get('round', 1)} · {question.get('question', '')}"
                )
            if data_gaps:
                coverage_lines.append("- **남은 갭**:")
                coverage_lines += [f"  - {gap}" for gap in data_gaps[:5]]
            sections.append("\n".join(coverage_lines))

    # --- Market data table ---
    sections.append("## 핵심 지표 현황\n")
    tickers = market_data.get("tickers", {})
    if tickers:
        rows = [
            "| 지표 | 현재값 | 1D | 1W | 1M | 3M | 1Y | 기간 내 백분위 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for sym, d in tickers.items():
            if d.get("error"):
                continue
            ch = d.get("changes", {})
            st = d.get("stats", {})
            prank = f"{st.get('pctRankInPeriod')}%" if st.get("pctRankInPeriod") is not None else "-"
            rows.append(
                f"| {sym} {d.get('label', '')} | {_fmt(d.get('last'), 4)} "
                f"| {_pct_str(ch.get('1d'))} | {_pct_str(ch.get('1w'))} | {_pct_str(ch.get('1m'))} "
                f"| {_pct_str(ch.get('3m'))} | {_pct_str(ch.get('1y'))} | {prank} |"
            )
        sections.append("\n".join(rows))
    else:
        sections.append("시장 데이터를 불러오지 못했습니다.")

    # --- Correlations ---
    corrs = market_data.get("correlations", [])
    if corrs:
        sections.append("\n**주요 상관관계 (일별 수익률 기준)**\n")
        rows = ["| 지표 쌍 | 상관계수 |", "| --- | ---: |"]
        for c in corrs[:5]:
            rows.append(f"| {c.get('labelA', '')} / {c.get('labelB', '')} | {c.get('corr', 0):+.3f} |")
        sections.append("\n".join(rows))

    # --- Macro data ---
    if macro_data and macro_data.get("ok"):
        from features.topic_report.macro_data import macro_data_to_markdown
        sections.append("\n## 경제 지표 (FRED + BOK ECOS)\n")
        sections.append(macro_data_to_markdown(macro_data))

    # --- User context (관심 방향 — 근거 아님) ---
    if user_context and user_context.strip():
        sections.append("\n## 사용자 관심 방향 (사실/근거 아님)\n")
        sections.append("> 아래는 사용자가 입력한 관심 방향입니다. 보고서의 근거로 사용되지 않았습니다.\n")
        sections.append(user_context.strip())

    # --- Memories ---
    if memories:
        sections.append("\n## 관련 시장 내러티브\n")
        for mem in memories[:5]:
            title = mem.get("title", "")
            summary = mem.get("summary", "") or mem.get("storyThesis", "")
            date = mem.get("date", "")
            bias = mem.get("stateBias", "") or mem.get("bias", "")
            sections.append(f"- **{title}** ({date}, {bias}): {summary[:200]}")

    # --- Related docs ---
    if docs:
        sections.append("\n## 관련 뉴스·자료\n")
        for d in docs[:8]:
            title = d.get("title", "")
            source = d.get("source", "")
            date = d.get("date", "")
            url = d.get("url", "")
            summary = d.get("summary") or d.get("searchSnippet") or ""
            if url:
                sections.append(f"- [{title}]({url}) — {source}, {date}")
            else:
                sections.append(f"- **{title}** — {source}, {date}")
            if summary:
                sections.append(f"  {summary[:180]}")

    # --- Data gaps (v2) ---
    if data_gaps:
        sections.append("\n## 데이터 부족 경고\n")
        for gap in data_gaps[:8]:
            sections.append(f"- {gap}")

    if topic_plan and (topic_plan.get("deepResearch") or {}).get("enabled"):
        sections.append("\n## 정량 근거표\n")
        rows = [
            "| 근거 항목 | 현재 확인 상태 | 해석 |",
            "| --- | --- | --- |",
        ]
        tickers = (market_data.get("tickers") or {})
        for sym, d in list(tickers.items())[:6]:
            if d.get("error"):
                continue
            ch = d.get("changes", {})
            rows.append(f"| {sym} | 1D {_pct_str(ch.get('1d'))}, 1M {_pct_str(ch.get('1m'))} | 가격 반응이 주제의 작동 경로와 같은 방향인지 확인 |")
        if macro_data and macro_data.get("ok"):
            rows.append("| FRED/BOK 지표 | 사용 가능 | 금리·환율·경기 전제가 유지되는지 확인 |")
        if len(rows) == 2:
            rows.append("| 로컬 정량 근거 | 부족 | 시장 데이터/API 키 또는 사용자가 저장한 자료 보강 필요 |")
        sections.append("\n".join(rows))

    sections.append("\n## 반론과 리스크\n")
    risk_lines = [
        "- 수집 자료가 특정 방향의 뉴스에 치우쳤을 수 있어, 반대 방향 가격 반응과 후속 지표 확인이 필요합니다.",
        "- 시장이 이미 해당 이슈를 가격에 반영했을 경우, 추가 뉴스가 나와도 영향은 제한될 수 있습니다.",
    ]
    if data_gaps:
        risk_lines.append("- 데이터 부족 항목이 남아 있으므로, 확인되지 않은 수치나 일정은 단정하지 않았습니다.")
    if user_context and user_context.strip():
        risk_lines.append("- 사용자 관심 방향은 hypothesis로만 사용했으며, 외부 자료와 충돌하는 경우에는 외부 자료 확인을 우선해야 합니다.")
    sections.append("\n".join(risk_lines))

    if topic_plan and (topic_plan.get("deepResearch") or {}).get("enabled"):
        sections.append("\n## 시나리오\n")
        sections.append("\n".join([
            "| 시나리오 | 조건 | 시장 영향 | 확인 지표 |",
            "| --- | --- | --- | --- |",
            "| 기본 | 현재 확인된 가격·뉴스 흐름이 유지 | 관련 자산의 차별화가 완만하게 지속 | 후보 티커 1D/1W/1M 추세, 핵심 거시 지표 |",
            "| 우호 | 수요·정책·수급 근거가 추가로 확인 | 수혜 자산/기업의 상대강도 확대 | 거래량 동반 상승, 실적/가이던스 개선 |",
            "| 악화 | 반대 지표나 정책 변화가 확인 | 기존 thesis 약화, 리스크 프리미엄 확대 | 금리·환율 급변, 관련 기업 하락 전환 |",
        ]))

        triggers = (topic_plan.get("deepResearch") or {}).get("falsificationTriggers") or []
        sections.append("\n## 반증 조건\n")
        sections.append("\n".join(f"- {trigger}" for trigger in triggers[:5]) or "- 핵심 가격·지표가 기본 시나리오와 반대로 확인될 때")

    # --- Checkpoints (v2): 계획의 시장 데이터/축 기반 점검 목록 ---
    sections.append("\n## 앞으로 확인할 체크포인트\n")
    checkpoints = []
    if topic_plan:
        for ticker, name in list(topic_plan.get("candidateTickers", {}).items())[:6]:
            checkpoints.append(f"- {name}({ticker}) 가격·추세 변화")
        for axis in topic_plan.get("analysisAxes", [])[:4]:
            checkpoints.append(f"- {axis.get('label', '')} 관련 신규 뉴스/지표")
    for sym, d in list((market_data.get("tickers") or {}).items())[:4]:
        if not d.get("error"):
            checkpoints.append(f"- {sym} 가격·거래량과 1D/1W 변화가 같은 방향으로 이어지는지 확인")
    if macro_data and macro_data.get("ok"):
        checkpoints.append("- FRED/BOK 주요 지표의 다음 발표에서 현재 방향이 유지되는지 확인")
    sections.append("\n".join(checkpoints[:8]) if checkpoints else "- 핵심 지표 추적 목록을 만들 데이터가 부족합니다.")

    # --- Sections placeholder ---
    report_sections = topic.get("report_sections", [])
    if report_sections:
        sections.append("\n## 분석 섹션 (LLM 필요)\n")
        sections.append("아래 섹션은 LLM 분석이 활성화되면 자동으로 채워집니다:\n")
        for s in report_sections:
            sections.append(f"- {s}")

    sections.append("\n## 결론\n")
    sections.append(
        "현재 자료만으로는 방향성을 단정하기보다, 가격 반응·공식 지표·반대 근거가 같은 방향으로 확인되는지를 우선 점검해야 합니다. "
        "지금 당장 가장 먼저 확인해야 할 것은 체크포인트에 적은 가격/지표 변화가 후속 자료에서도 반복되는지입니다."
    )

    sections.append("\n---\n\n## Source & Data Notes\n")
    sections.append(f"- 시장 데이터: yfinance ({market_data.get('period', '')} 히스토리, {market_data.get('asOf', '')} 기준)")
    sections.append(f"- 경제 지표: {'FRED/BOK 데이터 포함' if macro_data and macro_data.get('ok') else 'FRED/BOK 키 없음 (설정에서 입력)'}")
    sections.append(f"- 로컬 자료: {len(docs)}건 검색됨")
    sections.append(f"- 시장 내러티브: {len(memories)}건 참조")
    sections.append("- 본 보고서는 규칙 기반 요약이며 LLM 분석을 포함하지 않습니다.")

    return "\n\n".join(sections)
