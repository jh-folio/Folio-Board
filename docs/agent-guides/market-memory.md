# 시장 내러티브 메모리

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### 시장 내러티브 메모리

- 브리핑 생성 시 주요 흐름을 중기 내러티브로 누적한다.
- 최소 온톨로지와 상태(`active/watch/resolved/overridden`)를 유지한다.
- taxonomy 테이블로 category, region, importance, entry_mode, story, family, relation, tag, industry, ticker, subject, subject_type, event_kind, state_key, net_effect 사용량을 추적한다.
- story link graph로 개별 branch가 어떤 큰 family에서 분기되는지 기록한다.
- `AI 반도체 공급망`, `AI 데이터센터 전력 병목`, `금리·달러 유동성`, `중동 에너지 리스크`처럼 큰 story family를 우선 재사용한다.
- 모든 이슈를 바로 현재 상태로 올리지 않는다. `issue` 메모 중 반복 근거가 있거나, 중요도가 높고 복수 출처가 있을 때만 active/watch 상태 후보가 된다.
- 시장 내러티브 탭의 기본 UI는 Market State Dashboard v3(`GET /api/memory/state-dashboard`) 하나다. 상단은 `시장 해석`과 `판단 및 투자 행동` 두 개의 큰 본문으로 보여주고, 스냅샷에 `marketViews.overall/us/kr`가 있으면 `종합 / 미국장 / 한국장` 세그먼트로 전환한다. 드라이버 카드는 짧은 판단 요약과 방향 칩만 먼저 보여준다. 세부 근거는 카드 안 `근거 보기` 접기에 `근거 요약`, `시장 영향`, `다음 확인`만 간결하게 표시한다. taxonomy·story map·audit·패밀리 제안·개별 기록 목록 UI는 제거되었고 API로만 접근한다.
- Market State Snapshot context는 `rssCandidates`, `shortTermDigest`, `existingStates`에 더해 yfinance 기반 `marketTape`와 FRED/BOK ECOS 기반 `macroSnapshot`을 포함할 수 있다. 이 값은 LLM이 시장 판단을 작성하기 위한 structured evidence이며, 코드는 provider/freshness/결측을 정리할 뿐 시장 결론을 규칙으로 확정하지 않는다.
- **확인은 해석이 아니다.** 지수가 얼마 내렸는지 적는 문장은 옆의 드라이버와 차트가 이미 보여주는 것을 되풀이한다 — 모든 문장이 주장을 하나씩 지고 등락은 그 주장 안에 숫자 하나로 들어간다. 첫 문장은 그 시장이 어떤 상태이고 왜 그런지다. **규칙이 서로 반대를 말하면 모델은 뒤엣것을 따른다** — `판단으로 시작하라`와 `무슨 일이 있었는지에서 시작하라`가 같은 프롬프트에 있었고, `퍼센트 나열로 열지 말 것`이 함께 적힌 채로 `파리가 1.6%, 밀라노가 1.17%, 마드리드가 0.9%, 런던이 0.7% 내렸습니다`가 나왔다. 뒤엣것은 이제 첫 문장이 아니라 근거의 출처를 말한다(뉴스 흐름이 1차, marketTape·macroSnapshot은 확인·반박).
- **계약을 지켰는지 재서 남긴다**(`interpretationAudit`). 같은 금지가 프롬프트에 있는 채로 두 번 깨졌고, 프롬프트는 부탁이라 지켜졌는지 아무도 모르면 다음 판단이 눈대중이 된다. **재는 것과 되돌리는 것은 다른 결정이다** — 자르면 결론이 사라지고 재생성은 수십 초짜리 CLI 호출이라 감사는 기록만 하고 산출물을 막지 않는다.
- **뷰의 `headline`도 계약을 갖는다.** 최상위 `headline`에만 "short Korean title"이 적혀 있고 `marketViews[].headline`은 필드 이름만 나열돼 계약이 없었다 — 시장 해석과 같은 구멍이다. 그래서 사건도 판단도 없는 분류 라벨이 나왔다(`기후발 공급 충격이 지역 비용·성장 위험을 높임`, `에너지 경로의 지정학 위험을 점검하는 유럽`). 20~40자 한 줄로 판단을 말하고, **시장 이름으로 끝내지 않으며**(화면이 이미 어느 시장인지 말한다), 그 뷰 `marketInterpretation`이 지배적이라고 본 원인을 빠뜨리지 않고(두 힘이 끌면 하나만 쓴 제목은 짧은 것이 아니라 틀린 것이다), 다른 시장과의 비교만으로 쓰지 않고 전달 경로를 지목한다. 비면 `_view_label`이 `EUROPE`가 아니라 `유럽`을 낸다 — 한국어 문장 사이의 영문 코드는 값이 빠진 티가 아니라 고장으로 읽힌다.
- **시장 해석(`marketInterpretation`)은 3~4문장·300자 안팎이고 문장마다 출처를 붙이지 않는다.** 이 필드만 크기 지시가 없고 상한이 1600자여서 엔진의 기본 장황함이 그대로 화면에 나왔다(실측 저장본 11건: 다른 필드는 편차 2배 안쪽, 이 필드만 79~823자). **문장 수만 걸면 계약이 되지 않는다** — 3~5문장으로 제한했더니 정확히 5문장에 526자가 나왔고, 한 문장이 쉼표로 네 항목을 이어 붙이면 문단이다(실측 문장당 155·116·125·102자). 그래서 문장 수·총 글자 수·문장당 한 가지 생각을 함께 걸고 **나열을 금지한다**(가장 긴 문장이 4개 종목의 등락을 각각 적은 것이었는데 그것은 옆의 `keyDrivers`가 이미 보여주는 목록이다). 상한(800자)은 폭주 방지용이며 계약 값까지 낮춰 자르지 않는다 — 마지막 문장이 결론이라 뒤를 자르면 판단이 사라진다. 문장마다 붙는 `(Bloomberg, 연합뉴스)`는 프롬프트로 금지하되 `_REF_DROP_KEYS`가 함께 지운다(다른 필드는 계속 매체명으로 살린다). 출처는 그 뷰의 `sourceRefs`가 갖는다.
- **시장 해석 문장은 뉴스 흐름에서 시작한다.** `rssCandidates`가 1차 근거 풀이고 `marketTape`/`macroSnapshot`은 그 이야기를 확인·반박하는 맥락이다. 해석을 지수 레벨이나 퍼센트 나열로 열지 않는다(프롬프트 규칙으로 강제, `snapshot.py`). 수치가 앞장서면 근거 위계가 뒤집힌다.
- audit, story-map, family-review, narrative-report는 API로 유지되므로 품질 저하나 잘못 묶인 패밀리는 API 응답으로 점검한다.
- active/watch 상태의 추세·근거 카운트 갱신은 `run_rss_market_memory_update()`가 규칙 기반 `refresh_all_regimes`로 자동 수행한다(RSS/Market Memory 자동화 실행 시 포함). 화면에는 상태별 수동 갱신 버튼이 없다.
- LLM 기반 정리는 사용자가 `시장 메모리 업데이트` 버튼을 눌렀을 때만 실행한다. 이 버튼은 `/api/memory/llm`으로 기존 중기 내러티브 row를 누적한 뒤 `/api/memory/state-snapshot`으로 화면용 현재 시장 상태 스냅샷을 이어 생성한다. 자동 브리핑 생성 과정에서는 규칙 기반 후보 저장을 유지한다.
- LLM에는 전체 원문을 보내지 말고 후보 이슈, 상위 자료 요약, 기존 memory/state/taxonomy/story-links의 압축본만 보낸다.
- LLM 결과는 JSON으로 받고, 코드에서 enum/길이/출처를 검증한 뒤 `upsert_memory()`로 저장한다.
- 기사 링크 나열이 아니라 요약, 중요성, 포트폴리오 연결, 체크포인트 중심이어야 한다.
- Regime 추적 v2는 위 상태에 momentum/confidence/evidence window/thesis 연결을 더한다.
- Regime 추세 갱신은 `next_checkpoints_json`과 `falsification_triggers_json`을 채워 Step 8 대시보드가 구조화 checkpoint를 읽을 수 있게 한다.
- `momentum` enum은 `strengthening/stable/fading/turning/conflicted`, evidence role은 `supporting/challenging/neutral`만 허용한다.
- Regime 근거는 기존 `market_memory` 엔트리를 상태별로 분류해 `market_regime_evidence`에 저장하고, 변화는 `market_regime_changes`에 남긴다.
- Thesis/Obsidian 노트는 hypothesis다. `linked_regimes`, ticker overlap 등은 `market_regime_thesis_links` 연결 정보로만 쓰며 evidence로 승격하지 않는다.
- 기존 active/watch/resolved 호환성과 기본 브리핑 markdown 불변을 최우선으로 유지한다.

