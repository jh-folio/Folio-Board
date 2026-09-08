# 투자 리뷰 (Investment Review)

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### 투자 리뷰 (Investment Review)

- 로직은 `features/investment_review/`에 둔다. Portfolio의 `투자 리뷰` 하위 탭이 읽는 날짜별 v2 저장 산출물이며, 새 `portfolio_report`나 Canonical `ReportKind`는 만들지 않는다.
- 권위 저장소는 `data/investment-review/{date}.json`이다. `schemaVersion=2`, 단조 증가 `reviewRevision`, `reviewState=draft|reviewed|stale|due`, `inputBasis`와 이전 날짜 비교를 보존한다. legacy v1은 파일을 고치지 않고 읽을 때 `legacy_unknown`/`stale`로 정규화한다.
- 화면은 오늘의 판단 요약, 지난 리뷰 이후 변화, 우선 검토할 포지션, 공동 위험, 자료·입력 기준, 이력을 순서로 읽는다. 규칙 기반 `오늘 리뷰 갱신`, `검토 완료`, `이 리뷰의 가장 약한 전제를 찾아줘`는 서로 분리된 action이다.
- 화면 자동 로드는 저장본과 freshness만 읽는다. `검토 완료`는 review state/timestamp만 바꾸며 Portfolio·Thesis·checkpoint를 자동 변경하지 않는다. 매수/매도/보유, 목표주가, 권장 비중 또는 포지션 크기 지침, 진입·청산·주문 지침을 생성하지 않는다.
- 현재 API는 `GET /api/investment-review`, `GET /api/investment-review/history`, `GET /api/investment-review/{date}`, `POST /api/investment-review/generate`, `POST /api/investment-review/{date}/reviewed` 5개다. 종목별 Investment Context는 별도 읽기 전용 API다.

