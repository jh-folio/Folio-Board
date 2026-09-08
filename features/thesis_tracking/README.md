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

## Thesis를 만드는 경로 (0.6 Stage B)

Obsidian 없이 앱 안에서 Thesis를 만들고 고칠 수 있습니다. Obsidian 경로는 그대로 유지됩니다.

| 경로 | 무엇을 하는가 | `source` |
|---|---|---|
| `POST /api/theses` | 직접 입력·수정. **보낸 키만 덮습니다**(부분 갱신) | `manual` |
| 네이티브 `company_thesis` 노트 저장 | thesis가 없는 종목이면 **자동 등록** | `native_note` |
| `POST /api/investment-notes/{note_id}/thesis` | `이 노트로 Thesis 만들기/갱신` — 이미 있는 thesis를 노트 내용으로 덮는 유일한 경로 | `native_note` |
| Vault 동기화(`sync_theses_from_vault`) | Vault의 `company_thesis` 노트 반영 | `obsidian` |

- **빈자리만 자동, 갱신은 명시적입니다**(계획 §8.2). 노트를 저장할 때마다 thesis가 덮이면 공들여 쓴 Thesis가 지나가는 메모에 조용히 사라집니다. 노트 저장 훅은 빈자리만 채우고, 덮는 것은 사용자가 누른 승격 action뿐입니다.
- **자동 등록은 명시 승격보다 엄격합니다**(`native_notes.auto_register_block`). `agent_assisted` 태그 노트는 자동 등록하지 않고(Agent 자유 텍스트가 확인 없이 hypothesis 정본이 되면 §3.13 위반), 본문 없이 생각 한 줄뿐인 노트도 등록하지 않습니다(지나가는 한 줄이 빈자리를 선점하면 나중의 공들인 노트·Vault 노트가 전부 막힙니다). 명시 승격은 생각 fallback을 그대로 씁니다 — 사용자가 그것을 골랐으므로.
- **노트 저장은 검토가 아닙니다.** 자동 등록·승격이 `last_reviewed_at`을 찍지 않습니다 — 찍으면 검토한 적 없는 thesis가 "최근 검토: 오늘"이 되고 Delta의 `since_last_review` 창이 0일로 접힙니다.
- **Vault 동기화는 자기가 만든 thesis만 덮습니다**(`store.VAULT_OWNED_SOURCES`). 이 동기화는 thesis를 열 때마다 도는 경로(`thesis_detail_payload(sync=True)`)라, 소유자를 보지 않으면 앱에서 만든 Thesis가 같은 티커의 옛 Vault 노트로 매 조회마다 되돌아갑니다. 빈자리는 예전처럼 자동으로 채웁니다. **부분 갱신은 소유권을 옮기지 않습니다** — `upsert_manual_thesis`가 기존 `source`를 보존하므로 확신도 한 칸을 고쳤다고 Vault 동기화가 끊기지 않습니다. 소유권 이전은 명시적 승격뿐이며, 그때의 "Vault에서 더 이상 갱신되지 않음" 표시는 Stage C 몫입니다.
- **덮겠다는 의사는 요청이 싣습니다.** 승격 API의 `overwrite` 기본은 False — 기존 행을 만나면 `skipped_existing`으로 돌아가고 화면이 최신 상태를 보여준 뒤 재확인합니다(화면 캐시가 낡은 사이 다른 경로가 만든 thesis를 확인 없이 덮지 않습니다). 승격도 부분 보존입니다 — 노트가 값을 주지 않는 필드(핵심 지표·신호·이탈 조건)는 기존을 유지합니다.
- **부분 갱신은 손실 방지 장치입니다.** 명시적 action이라고 손실 없는 action은 아닙니다 — 전체 폼을 통째로 받는 API로 두면 한 칸만 고치는 호출자가 나머지를 빈 값으로 지웁니다. `note_path`·`created_at`·`last_reviewed_at`도 보존합니다.
- **티커 정규화는 `model.normalize_ticker` 하나입니다**(노트 색인과 동일 규칙 — `.KS/.KQ` 제거·`.`→`-`). thesis PK와 노트 색인 티커가 join 키라 정규화가 갈리면 같은 회사가 두 행으로 갈라져 카드가 영영 Thesis를 못 찾습니다.
- 노트 본문이 `## 핵심 Thesis` 같은 템플릿 형식이면 섹션 파서가 각 필드를 채우고, 자유 형식이면 첫 문단이 `core_thesis`가 됩니다 — 노트 쓰는 방식을 강요하지 않습니다.
- 노트 승격이 실패해도 노트 저장은 되돌아가지 않습니다. 등록은 노트의 부가물입니다.
- 저장된 구조화 체크포인트는 어느 경로로 갱신해도 보존됩니다(`store.upsert_thesis`의 병합).
- 로직은 `features/thesis_tracking/native_notes.py`이며, 노트 색인과 thesis 레지스트리는 **같은 DB**(`market-memory.sqlite3`)입니다 — 저장 훅은 호출자가 준 DB 경로를 그대로 씁니다.

## 저장 위치

`thesis` 테이블 — `data/market-memory.sqlite3` (지식그래프 DB 확장, 별도 파일 없음).
**키 정책: ticker 1개당 thesis 1개(PK=ticker)** — 같은 ticker 노트가 여럿이면 마지막 동기화가 이긴다.

`thesis_delta` 테이블 — 같은 DB의 시계열 Delta 저장소. `ticker`, `generated_at`, `period`, `verdict`, `analysis_json`, `evidence_json`을 저장한다.

## 사용 예

```python
from features.thesis_tracking.service import sync_theses_from_vault, list_theses, get_thesis, upsert_manual_thesis, run_thesis_delta

sync_theses_from_vault()        # Vault의 company_thesis 노트 → 레지스트리 동기화(자기 것만 덮음)
list_theses(status="active")    # 등록된 thesis 목록
get_thesis("LRCX")              # 티커별 조회
upsert_manual_thesis({"ticker": "NVDA", "core_thesis": "..."})  # UI 직접 입력(보낸 키만 덮음)
promote_note_to_thesis("note-id")                                # 네이티브 노트 → Thesis(명시적 갱신)
run_thesis_delta("LRCX", {"period": "90d", "useLlm": False})     # Delta 생성/저장
```

## 체크포인트 판정 (0.6 Stage A)

`next_checkpoints`에는 문자열(노트에서 읽은 문장)과 구조화 체크포인트(dict)가 함께 삽니다. 스키마는 `features/common/research_schema/tracked_checkpoints.py`가 소유하고 내러티브와 공용입니다(자세한 규칙은 `features/market_memory/README.md`).

- 판정은 `features/thesis_tracking/checkpoint_verdicts.py`가 하며 RSS 수집·시장 메모리 갱신과 같은 자리에서 규칙 기반으로 돕니다. **LLM을 부르지 않습니다.**
- 근거 풀은 **연구 인덱스 문서를 직접 훑어** 그 회사 태그가 붙은 뉴스만 **날짜순**으로 모읍니다(컷오프 이후만, 안전판 상한 500은 가장 오래된 쪽을 자름). `search_documents` 브라우즈의 관련도순 상한 200을 쓰지 않습니다 — 보도가 많은 종목(실측 GOOGL 9,387건 태그)에서 이번 주 기사가 상한 밖으로 잘려 판정이 영영 `no_signal`이 됩니다(워치리스트가 문서화한 "AMD 297건인데 69건" 버그와 동일). `market_memory` 행을 섞지 않습니다.
- **구조화 체크포인트를 가진 thesis가 하나도 없으면 인덱스를 열지 않습니다**(`load_index()` 실측 4.7초).
- 문서 풀에는 supporting/challenging 분류가 없으므로 체크포인트의 `direction`이 판정 방향을 정하고(enum 밖 direction은 판정하지 않음), 근거 사본은 `{docId, date, title}`입니다(`role` 없음, **docId는 URL 우선** — 파일 경로는 보관 기간 정리가 지웁니다). **회사명·티커는 매칭 재료가 아닙니다** — 풀이 이미 그 종목이라, 행에 matchedTerms를 싣지 않고(haystack = 제목+요약) validator 금지어에 티커·회사명을 넘깁니다. **keyword가 방향을 담아야 합니다**("가이던스 상향").
- 판정 이력은 체크포인트 dict의 `history` 배열(상한 20)이며 새 테이블을 만들지 않습니다. thesis 하나가 실패해도 나머지 판정은 계속됩니다(결과 행에 오류 코드만 남음).
- 쓰기는 `store.save_thesis_checkpoints`가 `next_checkpoints_json`만 제자리 교체합니다. **`last_reviewed_at`도 `updated_at`도 바뀌지 않습니다** — Delta의 `since_last_review`가 `updated_at`으로 물러나는 폴백이 있어, 올리면 기계 판정이 사용자 검토로 읽힙니다. `upsert_thesis`(노트 동기화)는 문자열 목록만 갈아끼우고 저장된 dict를 보존하므로 판정 status와 이력이 재동기화에 살아남습니다.
- **판정이 Thesis verdict(6값 enum)를 자동으로 바꾸지 않습니다.** 체크포인트 판정은 "이 확인 항목에 신호가 왔는가"이고, verdict는 명시적 `최신 근거로 검토` action이 소유합니다.

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

## 화면 — Watchlist 상세가 주 표면이다 (0.6 Stage C.2)

종목 Thesis의 주 표면은 **Watchlist 상세**입니다. 기업 분석 reader의 `가설 검토 상태` 카드는 만들기·검토 진입점으로 남고 정본을 따로 두지 않습니다.

- payload는 `GET /api/theses/{ticker}/workspace`(`workspace_view.py`)이며 **읽기 전용 projection**입니다. 화면 진입이 Agent를 실행하지 않습니다.
- 순서·경계·소유권 표시·연결 내러티브 경고(A.3)의 규칙은 `features/watchlist_notes/README.md`의 "종목 Thesis workspace" 절이 갖습니다.
- **판정 두 층을 섞지 않습니다**(계획 §3.2). `thesis_delta`의 6값 verdict와 구조화 체크포인트의 3값 판정은 payload에서도 서로 다른 키에 담깁니다.
- thesis 체크포인트의 근거 사본은 `{docId, date, title}`이고 **role이 없습니다** — 문서 풀에는 supporting/challenging 분류가 없으므로 화면도 없는 분류를 만들어 내지 않습니다.
- `이 Thesis를 반박해줘`는 만들기/수정과 최신 검토와 분리된 0.6 Stage D action입니다. 명시적으로 눌렀을 때만 ticker가 붙은 새 Agent 대화와 첫 질문을 만들며, 서버가 해당 Thesis·검증·최근 90일 근거를 다시 읽습니다. 대화 결과는 verdict나 체크포인트를 자동 갱신하지 않습니다.

## API

```text
GET  /api/theses
POST /api/theses                                  # 직접 입력·수정(부분 갱신)
GET  /api/theses/{ticker}
GET  /api/theses/{ticker}/workspace               # Watchlist 상세용 읽기 projection
POST /api/theses/{ticker}/delta
POST /api/investment-notes/{note_id}/thesis       # 이 노트로 Thesis 만들기/갱신
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
