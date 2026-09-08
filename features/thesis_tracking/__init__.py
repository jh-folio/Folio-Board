"""Thesis Tracking — 기업 투자 thesis를 추적하고, 최신 자료 대비 강화/유지/약화/이탈을 판정한다.

Folio Board Personal Overlay 계층의 기업 단위 적용(개선안 02).

- thesis는 사용자의 가설(hypothesis)이다. Obsidian `company_thesis` 노트 또는 UI 직접 입력에서 온다.
- Thesis Delta는 thesis를 최신 외부 자료와 대조해 verdict(enum)로 판정한다 — 옹호가 아니라 검증.
- thesis 노트는 기준점이지 evidence가 아니다(3계층 위계). 외부 자료와 충돌하면 충돌을 명시한다.

이 패키지는 단계적으로 구현된다(IMPLEMENTATION_PLAN Step 3):
  1) 레지스트리 — company_thesis 파싱 + 저장 + 조회   ← 현재
  2) Thesis Delta 엔진 (LLM + fallback, verdict enum)
  3) API / UI / Obsidian export
"""
