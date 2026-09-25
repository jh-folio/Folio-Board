# 0.6 검증 루프 — 권위·판정·Agent 경계

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### 0.6 검증 루프 — 권위·판정·Agent 경계

Watchlist 상세의 Thesis와 Portfolio `투자 리뷰`는 개인 판단의 주 표면이지만, 별도 Canonical 보고서나 투자 조언을 만들지 않는다. Canonical markdown은 이 루프로 바뀌지 않는다.

| 대상 | 권위 저장소/역할 | 화면·경계 |
|---|---|---|
| 외부 자료·Canonical 보고서 | `research-index.sqlite3`와 보고서 JSON | evidence/source-grounded의 근거·보편 보고서 |
| Thesis·Thesis Delta | `market-memory.sqlite3`의 `thesis`·`thesis_delta` | 종목별 가설과 최신 검토 이력; Watchlist는 이를 투영한다 |
| Watchlist | metadata + hypothesis | 화면 표면이며 Thesis/Delta의 별도 권위 저장소가 아니다 |
| Portfolio 투자 리뷰 | `data/investment-review/{date}.json` | 날짜별 v2 점검·입력 기준·상태·이력의 권위 산출물 |
| Agent 대화 | scope가 붙은 `data/agent-threads/` | hypothesis process record, `reuseAsEvidence=false`; evidence나 verdict 권위가 아니다 |

- **판정은 두 층으로 분리한다.** 내러티브 구조화 checkpoint의 규칙 판정은 `confirmed|challenged|no_signal`이며, Thesis Delta의 최신 근거 검토 결과는 `strengthened|maintained|weakened|at_risk|broken|insufficient_evidence`다. 어느 층도 다른 층의 상태를 자동 변경하지 않는다.
- **Agent 반박은 정확한 scope의 명시 action뿐이다.** 내러티브는 `stateId`, Thesis는 `ticker`로 정확한 권위 객체와 최근 90일 근거를 다시 읽는다. 투자 리뷰는 `date + reviewRevision`의 저장된 구조화 리뷰만 다시 읽고, 일반 Portfolio 맥락이나 새 근거 조회로 넓히지 않는다. stale/missing ID는 넓은 컨텍스트로 대체하지 않는다.
- **자동 쓰기와 조언을 금지한다.** 화면 로드·규칙 판정·Agent 답변은 Thesis verdict, checkpoint, Portfolio, review state를 자동으로 바꾸지 않는다. 구조화 변경은 preview와 명시적 확인 후에만 저장한다. 이 표면은 매수/매도/보유, 목표주가, 권장 비중 또는 포지션 크기 지침, 진입·청산·주문 지침을 제공하지 않는다.

