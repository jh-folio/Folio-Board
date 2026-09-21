# 브리핑 주도 기업 본문·차트 정합성 설계

## 문제

가격 snapshot은 본문 작성 전에 기사 그룹에서 고른 기업으로 생성되고, CLI는 본문에서 별도의 주도 기업을 선택한다. 프론트는 기업명이 아니라 시장별 ①·② 순번으로 차트를 삽입하므로 NVIDIA 본문 아래 Microsoft 차트가 표시될 수 있다.

## 목표

- CLI·규칙 기반 브리핑 모두 본문 제목의 주도 기업과 같은 ticker의 차트만 표시한다.
- 생성 당시 snapshot 불변성과 시장별 ①·② 순서를 유지한다.
- 기업 해석이나 시세 수집에 실패하면 다른 기업 차트를 대신 표시하지 않는다.

## 설계

`features/daily_briefing/visuals.py`가 `## 3/4. 미국장/한국장을 주도한 기업 ①/② — 기업명` 제목을 파싱하고 기존 company master·aliases로 ticker를 해석한다. 결과는 시장별 ordinal 순서의 명시적 leader subject 목록이다.

`collect_briefing_visuals()`는 선택적 `leader_subjects`를 받는다. 값이 있으면 기사 그룹의 첫 기업 대신 본문에서 파싱한 기업만 수집한다. 규칙 경로는 Markdown 완성 뒤 이 목록을 전달한다.

CLI context pack은 기존처럼 시장·히트맵 snapshot을 준비한다. writeback 시 완성 Markdown에서 leader subject를 파싱하고 회사 차트만 다시 수집한 뒤, draft의 기존 `role=leading_company` 추천·snapshot을 제거하고 새 결과로 교체한다. heatmap sidecar와 지수 snapshot은 다시 수집하거나 변경하지 않는다.

프론트는 placement ordinal을 계속 사용하지만, 저장된 추천 자체가 본문 ordinal과 같은 ticker를 가진다. 해석 실패·시세 실패 시 해당 ordinal 추천을 만들지 않으므로 잘못된 차트가 표시되지 않는다.

## 테스트

- 영문·한글·하이픈·em dash 제목에서 시장/ordinal/기업 ticker를 파싱한다.
- 본문 leader override가 그룹 후보보다 우선한다.
- CLI writeback이 기존 회사 차트를 본문 회사 차트로 교체한다.
- 해석 실패 시 기존의 불일치 차트가 제거되고 다른 기업 차트가 붙지 않는다.
- 전체 Python·프론트 회귀를 실행한다.

## 구현 결과

2026-06-21 구현 완료. Python 전체 회귀 277개와 프론트 24개, Python·JavaScript 문법 검사가 통과했다. 문제 저장본의 최종 제목은 미국 `NVDA·GOOGL`, 한국 `000660·005930`으로 경고 없이 해석된다. 기존 immutable 보고서는 수정하지 않으며 재생성부터 최종 본문 기업 snapshot을 저장한다.
