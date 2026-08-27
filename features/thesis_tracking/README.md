# Thesis Tracking

기업 투자 **thesis(투자 논리)를 추적**하고, 최신 자료 대비 강화/유지/약화/이탈을 판정한다(Thesis Delta).
Folio OS Personal Overlay 계층의 기업 단위 적용(개선안 02).

> 로컬 계획문서 `IMPLEMENTATION_PLAN.md` Step 3 기반.
> 현재 구현은 company_thesis 노트 파싱/저장/조회, Delta 생성/저장/API/UI/Obsidian export에 더해
> Step 9 Data Source Reliability에서 SEC/DART·company_analysis materials를 공식자료 evidence로 보강한다.

## 핵심 원칙

- thesis는 사용자의 **가설(hypothesis)** 이다. evidence가 아니다(3계층 위계). Obsidian `company_thesis` 노트 또는 UI 직접 입력에서 온다.
- Thesis Delta는 thesis를 최신 외부 자료와 대조해 **검증**한다 — 옹호가 아니다. 강화/반대 근거를 균형 있게, 충돌은 명시.
- 판정 결론은 **verdict enum**으로만 통제한다(자유 텍스트 결론 금지).

## verdict enum (개선안 02 §5)

`strengthened(강화)` · `maintained(유지)` · `weakened(약화)` · `at_risk(이탈 위험)` · `broken(이탈)` · `insufficient_evidence(판단 보류)`

## company_thesis 노트 형식

```yaml
---
type: company_thesis
ticker: LRCX
company: Lam Research
status: active           # active | watch | closed
review_cycle: quarterly  # weekly | monthly | quarterly | event_driven
conviction: medium_high  # low | medium | medium_high | high
source_layer: user_synthesis
reuse_as_hypothesis: true
linked_regimes: [AI 반도체 공급망, 메모리 capex 회복]
key_metrics: [WFE outlook, gross margin]
---
# LRCX 투자 Thesis
## 핵심 Thesis      → core_thesis (문단)
## 핵심 가정         → key_assumptions (bullets)
## 강화 신호         → supporting_signals
## 약화 신호         → weakening_signals
## 이탈 조건         → falsification_triggers
## 다음 리뷰 체크포인트 → next_checkpoints
```

헤딩은 키워드(한/영)로 매칭하며, 문서 H1 제목이 키워드에 걸려도 **내용 있는 섹션을 우선**한다.

## 저장 위치

`thesis` 테이블 — `data/market-memory.sqlite3` (지식그래프 DB 확장, 별도 파일 없음).
**키 정책: ticker 1개당 thesis 1개(PK=ticker)** — 같은 ticker 노트가 여럿이면 마지막 동기화가 이긴다.

`thesis_delta` 테이블 — 같은 DB의 시계열 Delta 저장소. `ticker`, `generated_at`, `period`, `verdict`, `analysis_json`, `evidence_json`을 저장한다.

## 사용 예

```python
from features.thesis_tracking.service import sync_theses_from_vault, list_theses, get_thesis, upsert_manual_thesis, run_thesis_delta

sync_theses_from_vault()        # Vault의 company_thesis 노트 → 레지스트리 동기화
list_theses(status="active")    # 등록된 thesis 목록
get_thesis("LRCX")              # 티커별 조회
upsert_manual_thesis({"ticker": "NVDA", "core_thesis": "..."})  # UI 직접 입력
run_thesis_delta("LRCX", {"period": "90d", "useLlm": False})     # Delta 생성/저장
```

## Thesis Delta

- evidence 소스: `research-index.sqlite3`의 로컬 뉴스 인덱스(`articles/rss`)를 `hybrid_search()` 경로로 검색하고, Step 9 이후 `company_analysis materials`를 재사용해 SEC companyfacts/DART, SEC 10-K/10-Q 상위 문단, 로컬 filings/reports를 공식자료 evidence로 보강한다.
- 분석 기간: `30d`, `90d`, `since_last_review`, `since_last_note`, `last_earnings`를 받는다. `last_earnings`는 아직 실적일 자동 식별 대신 90일 창과 uncertainty를 사용한다.
- LLM 경로: `delta_prompt.md` + `json_mode`로 verdict enum JSON을 요청한다.
- fallback 경로: LLM 꺼짐/키 없음/오류/근거 부족 시 규칙 기반 판정으로 서비스가 계속 동작한다.
- 편향방지: `counterEvidence`, `contradictions`, `uncertainties`를 항상 보장한다.
- Step 6 Data Foundation Lite 이후 저장된 Delta에는 공통 `checkpoints`, `evidenceItems`, `sourceLedger` 필드가 함께 들어간다. `checkpoints`는 기존 `nextCheckpoints`를 구조화한 별도 필드이며, thesis/user note는 계속 hypothesis로만 취급한다.
- Step 7 Research Quality 이후 저장된 Delta에는 공통 `quality` 필드가 함께 들어간다. 평가는 반대 근거, 체크포인트, sourceGrounding, personalBiasRisk를 규칙 기반으로 점검한다.
- Step 9 Data Source Reliability 이후 저장된 Delta에는 `dataGaps`와 `officialMaterials` 메타가 함께 들어갈 수 있다. 공식자료가 부족하면 `suggestedAction`으로 SEC/DART 설정 확인 또는 `research-inbox/filings/` 보강 경로를 안내한다.
- Obsidian export: `type: thesis_delta`, `generated_by: Folio OS`, `source_layer: primary_processed`, `reuse_as_evidence: false` frontmatter로 `Thesis Delta/` 폴더에 저장한다.

## API

```text
GET  /api/theses
GET  /api/theses/{ticker}
POST /api/theses/{ticker}/delta
```

`POST /api/theses/{ticker}/delta` body:

```json
{
  "period": "90d",
  "useLlm": true,
  "exportObsidian": false,
  "reuseLatest": false
}
```

## 관련 코드

- `model.py` — `Thesis`, enum(conviction/review_cycle/status/verdict) + 정규화, `parse_company_thesis`/`parse_thesis_text`
- `store.py` — `thesis`/`thesis_delta` 스키마, `upsert_thesis`/`list_theses`/`get_thesis`, Delta 저장/조회
- `delta.py` — 로컬/공식자료 evidence 수집, LLM json_mode, 규칙 fallback, Delta 정규화/Markdown
- `delta_prompt.md` — LLM Thesis Delta JSON 출력 프롬프트
- `service.py` — `sync_theses_from_vault`(Obsidian importer 재사용), thesis 조회, `run_thesis_delta`, Obsidian export
- `tests/test_thesis_model.py` — 13/13 (enum·파싱·store·delta fallback·service 저장)

## 테스트

```powershell
py -3 features\thesis_tracking\tests\test_thesis_model.py
```

## 다음

- 마지막 실적일 자동 식별을 구현해 `last_earnings` 기간을 실제 실적 window로 전환.
- UI 직접 thesis 입력/수정 화면을 추가할지 결정.

## Review State와 명시적 검토 (0.2.1)

- `thesis_review_state`는 최근/다음 검토 시각, 최신 Delta ID, freshness,
  최대 20개 체크포인트와 revision만 저장한다.
- Direct, Agent, durable CLI 경로는 모두 기존 Delta 정규화 후 같은 review
  state 갱신을 수행한다. raw prompt/provider 출력은 review state에 저장하지 않는다.
- Agent context는 hypothesis/evidence/Market State 레이어와 writeback target을
  서버가 고정하며 evidence는 최대 12개로 제한한다.
- LLM 비활성 또는 자료 부족 시 기존 rules fallback이 계속 동작한다.
