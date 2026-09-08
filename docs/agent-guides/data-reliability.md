# Data Source Reliability

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### Data Source Reliability

- 로직은 `features/common/data_reliability/`에 둔다. 공식자료 우선순위, source reliability, provider status, 한국 market-data CSV 보강 경로를 담당한다.
- 기업분석/Thesis Delta source priority는 `SEC/DART filings > companyfacts/XBRL > 10-K/10-Q 문단 > IR/실적자료 > 리포트 > 기사 > RSS` 순서를 따른다.
- Thesis Delta는 기존 로컬 뉴스 evidence에 `company_analysis materials` 기반 SEC companyfacts/DART, SEC 10-K/10-Q 상위 문단, 로컬 filings/reports evidence를 보강한다.
- 한국 데이터 보강 MVP 경로는 `research-inbox/market-data/krx_foreign_flows.csv`, `sector_performance.csv`, `bok_macro.csv`다. 자동 연동이 부족하면 `dataGaps.suggestedAction`으로 이 경로를 안내한다.
- provider status는 `ok/degraded/failed/unknown`으로 기록하며, Market Tape에는 `providerStatus` 요약이 포함된다. API는 `/api/data-reliability/provider-status`, `/api/data-reliability/market-data-files`를 사용한다.
- 사용자 노트는 계속 hypothesis이며 source reliability나 evidence count에 포함하지 않는다.

