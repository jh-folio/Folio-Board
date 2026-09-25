# 공통 Research Schema / Market Tape Lite

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### 공통 Research Schema / Market Tape Lite

- 공통 구조는 `features/common/research_schema/`에 둔다: `checkpoints.py`, `evidence.py`, `source_ledger.py`, `data_gaps.py`, `service.py`.
- 시장 수치 freshness/status 정규화는 `features/common/market_data/tape.py`에 둔다. Step 6에서는 새 provider를 추가하지 않고 기존 snapshot/provider 산출물을 감싼다.
- read API는 `/api/research-data/checkpoints|evidence|source-ledger|data-gaps|market-tape`를 사용한다.
- `user_note` evidence type은 hypothesis 연결용일 뿐 evidence 집계에서 제외한다.
- 구조화 필드는 항상 보고서 JSON의 별도 필드로 저장하고 Canonical markdown은 바꾸지 않는다.

