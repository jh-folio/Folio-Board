# Automation

Automation stores local settings for RSS collection, Market Memory digest updates, briefing prerequisites, and scheduled briefing generation.

0.2에서 Automation은 Deep Research 계획 승인이나 실행을 자동으로 시작하지 않으며 Smart Collection을 materialize하지 않습니다. Deep Research는 사용자가 화면에서 질문·계획·자료 부족 경고를 확인하고 명시적으로 승인하는 흐름입니다.

Automation is local-only: it runs while the Folio OS server is running. If the PC is asleep, shut down, or the server is stopped, scheduled work may be skipped according to the missed-run setting.

Settings live in `data/automation-settings.json`. Recent run summaries live in `data/automation-runs.json`.

The service exposes manual run endpoints and a single scheduler loop. `app.py` only starts that loop during FastAPI lifespan startup; all timing, due checks, and run dispatch stay in `features/automation/service.py`.

Run kinds:

- `rss`: collect RSS evidence into `research-inbox/rss/`.
- `marketMemory`: summarize RSS short-term memory into Market Memory, then run the rules-based regime trend refresh (`refresh_all_regimes`) for active/watch states. 화면의 수동 `추세 갱신` 버튼을 없앤 대신 이 경로가 momentum/confidence/근거 카운트를 자동으로 갱신한다.
- `briefingPrerequisites`: run RSS and Market Memory together.
- `briefing`: optionally run prerequisites, then generate a saved daily briefing using the selected generation mode. 예약마다 독립된 job이며 실행 기록에 `scheduleId`가 붙는다.

## 브리핑 예약 (0.5.2)

`briefingSchedules`는 목록이다. 예전에는 **하나만** 등록할 수 있었는데, 시장이 넷이 되면서
마감 시각이 전부 달라져(유럽 01:30 · 미국 05~06 · 일본 15:00 · 한국 15:30 KST) 시각 하나로는
구조적으로 안 된다 — 08:00 한 번이면 미국 마감은 담지만 한국·일본은 개장 전이다.

```json
{ "id": "…", "enabled": true, "time": "18:00", "markets": ["kr", "jp"],
  "briefingType": "concise", "qualityMode": "diagnose_only", "runPrerequisites": false }
```

- **상한 5개.** 없으면 24개를 만들어 하루 종일 LLM을 돌릴 수 있다. 화면과 서버가 같은 값으로 자른다.
- `markets`는 `build_briefing(markets=[...])`에 그대로 넘어간다. 엔진은 이미 시장 집합을 받고 있었고 자동화만 옛 단일 문자열에 갇혀 있었다.
- **관심 시장과는 실행 시점에 교집합**을 낸다(`markets_in_scope`). 선택 자체를 막지 않는 이유는 시장을 잠깐 껐다 켜는 동안 예약이 파괴되면 안 되기 때문이다. 전부 꺼져 있으면 건너뛰고 `markets_out_of_scope`를 실행 기록에 남긴다. 범위를 못 읽으면 요청대로 돌린다 — 설정 파일 하나 때문에 브리핑이 멈추는 쪽이 더 나쁘다.
- 같은 주기에 같은 시장 집합이 두 번 만들어지지 않는다(시각이 가까운 예약 둘이 같은 시장을 볼 때).
- **예약마다 도는 요일을 고른다**(`days`, 0=월 … 6=일). 예전에는 요일을 보지 않아 08:00 예약이 토·일에도 돌았고, 장이 열리지 않은 날 금요일 자료로 만든 브리핑이 매주 두 건씩 쌓였다.
  - 거래일 판정으로 대신하지 않는다. 그러면 발행일이 곧 거래일이 되어 **주말 브리핑을 만들 길이 막힌다** — 주간 요약과 다음주 프리뷰는 토·일에 내는 것이 맞다. 판정 대상이 당일이 아니라 직전 세션이라 공휴일이 끼면 꼬일 여지도 크다. 언제 낼지는 사용자가 고르고 코드는 그 선택을 지킨다(2026-08-10 사용자 결정).
  - 새 예약은 평일(월~금)로 시작한다. **이 항목이 없는 저장된 예약은 매일로 읽는다** — 판올림만으로 토·일 브리핑이 사라지는 것도 사용자가 정한 적 없는 변화다. 화면의 요일 칩을 한 번 눌러 정하면 된다.
  - **마지막 하나를 끄는 것도 선택이다.** 예전에는 그 클릭을 무시해서 눌러도 아무 일이 없는 버튼으로 보였고, 서버는 빈 목록을 기본값으로 되돌려 끄겠다는 선택이 정반대로 저장됐다(시장을 비우면 네 시장이 살아났다). 이제 비울 수 있고, **만들 시장이나 돌 날이 없어진 예약은 스스로 꺼진다** — 켠 채로 두면 화면은 켜졌다고 말하는데 아무 일도 일어나지 않는다. 다시 고르면 성립하고, 켜는 것은 사용자가 정한다(2026-08-10 사용자 결정).
  - 빈 목록과 **읽을 수 없는 값**은 다르다. `marketScope: "bad"`나 `days: [9, "x"]`처럼 값이 있는데 하나도 알아볼 수 없으면 고장이므로 기본값으로 되돌린다. 둘을 같이 다루면 설정 파일이 깨진 것과 사용자가 끈 것이 구분되지 않는다.
  - 요일 판정은 따라잡기 창보다 앞선다. 금요일 23:00 예약이 토요일 새벽에 실행되지 않는다.
- 저장된 `briefing` 싱글톤은 읽을 때 예약 하나로 승격한다. `marketScope: both` → `markets: ["us","kr"]`.
- **예약마다 만드는 브리핑 종류를 고른다**(`kind ∈ {daily, weekly}`, 0.5.4). 이 항목이 없는 저장된 예약은 일간이다. 발행 요일은 자유 선택이며 기존 요일 칩을 그대로 쓴다 — 주간 예약을 추가할 때의 **제안**만 일요일이다(2026-08-20 사용자 결정).
- **중복 억제 키에 종류가 들어간다.** `produced`가 시장 집합만 보던 시절에는, 같은 시장의 일간 예약과 주간 예약이 한 주기에 걸리면(일요일 아침이 정확히 그 경우다) 뒤에 오는 쪽이 조용히 스킵돼 사용자가 주간 예약을 켜 두고도 아무것도 받지 못했다.
- 주간 예약은 `briefingType`(편집 강조점)을 적용하지 않는다. 세 값이 모두 "기존 섹션 구성을 유지하라"는 지시라 골격이 다른 주간에 성립하지 않으며, 화면도 주간을 고르면 그 선택지를 감춘다.
- **사전작업(`runPrerequisites`)은 예약별로 정한다.** 브리핑 전에 RSS 수집과 시장 메모리 갱신을 돌릴지다. 예약이 여럿일 때 매번 모으면 같은 자료를 하루에 여러 번 수집하고, 하나도 안 모으면 어제 자료로 브리핑을 만든다. 값이 없으면 켠 것으로 읽는다.
- **사전작업은 화면이 보여주는 내러티브까지 만든다.** 예전에는 `run_rss_market_memory_update()`만 불렀는데, 그것은 `market_memory` 행과 regime 카운트를 규칙으로 갱신할 뿐 **`market_state_snapshots`를 만들지 않는다.** 시장 내러티브 탭의 `시장 해석`·`판단 및 투자 행동`이 바로 그 스냅샷이라, 사전작업이 도는 날에도 화면은 며칠 전 해석 그대로였다. 실측으로 스냅샷 이력이 08-12·08-07·08-06으로 띄엄띄엄했고 그 시각에는 자동화 기록이 없었다 — 전부 사용자가 버튼을 누른 것이었다.
- 스냅샷 생성은 `_refresh_market_state_snapshot()`이며 버튼과 **같은 경로**를 쓴다: CLI 모드는 `run_market_memory_update_task`(중기 메모리 → 스냅샷 2단계, `job_id` 없이 부르면 동기), API 모드는 `create_market_state_service(DATA_DIR).run_manual(...)`. 따로 만들면 버튼과 예약이 서로 다른 스냅샷을 만들게 된다.
  - **API 모드는 attempt/watermark 라이프사이클을 탄다**(0.5.4). 예전에는 `run_llm_market_state_snapshot()`으로 바로 저장해서 자동 스냅샷에만 `updateAttemptRef`가 없었고, reconcile이 중단된 갱신을 복구할 근거를 잃었다. 조립은 `features/market_memory/http_runtime.py::create_market_state_service()` 하나이며 라우터도 같은 것을 쓴다.
  - **scope는 GLOBAL 고정이다**(`PREREQUISITE_SNAPSHOT_SCOPE`). 예약이 고른 시장 집합과 무관하다 — 화면의 시장 내러티브는 시장별 보고서가 아니라 하나의 해석이고, 그 안에서 `marketViews`로 미국장·한국장을 나눈다.
- **실패해도 올리지 않는다.** 브리핑이 오늘의 결과물이고 스냅샷은 그 앞의 준비다 — 스냅샷을 못 만들었다고 브리핑까지 없어지면 손해가 더 크다. 왜 못 만들었는지만 `marketMemory.stateSnapshot`에 남긴다.
- 규칙 모드에서는 만들 수 없다(`reason: rules_mode`). LLM이 시장 해석 문장을 쓰는 산출물이라 규칙으로 대신할 수 있는 것이 아니다.
- **신선도는 둘을 따로 본다**(0.5.4). 규칙 갱신 신선도는 `market_memory_recently_run()`(자동화 실행 기록), 화면 스냅샷 신선도는 `market_state_snapshot_recently_run()`(스냅샷의 `as_of` 열)이다. 예전에는 한 덩어리로 스킵해서, 규칙 갱신이 12시간 안에 돌았으면 스냅샷이 며칠 전이어도 건너뛰었다. 스냅샷만 다시 만든 경우는 자동화 기록을 남기지 않는다 — 남기면 규칙 갱신 가드까지 연장된다. 스냅샷은 자기 `as_of`로 신선도를 말한다.
- **신선도 가드는 예약 경로에만 적용한다.** 사용자가 직접 부르는 `briefingPrerequisites`는 `force=True`라 12시간 안에 돌았어도 다시 만든다 — 눌러도 아무 일이 없는 버튼이 되면 안 된다.
- 사전작업의 정의는 `run_briefing_prerequisites()` 하나다. 경로마다 따로 조립하면 예약만 스냅샷을 만들고 수동 실행은 안 만드는 식으로 갈라진다.
  - 0.5.2에서 예약을 목록으로 바꾸며 화면 토글이 사라지고 값만 `true`로 박혀 있었다. 백엔드는 계속 실행하고 있었지만 사용자가 끌 방법이 없었다. RSS 자동 수집을 끄고 브리핑 직전에만 모으는 구성에서는 이 항목이 **유일한 수집 경로**다.
- 손으로 만드는 브리핑은 어느 예약에도 속하지 않으므로, 켜 둔 예약 중 하나라도 원하면 사전 수집을 한다(`wants_prerequisites`).

## 놓친 실행과 재시도

- `missedRuns.catchUpHours` (0·1·3·6·24, 기본 3). 예전 `onStartup`은 `skip`/`catch_up` 둘뿐이었고 둘 다 나빴다 — 앞의 것은 10분 창이 전부라 08:15에 PC를 켜면 그날 브리핑이 없었고, 뒤의 것은 상한이 없어 23:50에 켜도 아침 브리핑을 만들었다. 저장된 값은 읽을 때 옮긴다(`skip`→0, `catch_up`→24)므로 기존 사용자의 동작은 바뀌지 않는다.
- 0시간을 골라도 스케줄러가 1분마다 도므로 10분 창은 바닥으로 남는다.
- **성공한 실행만 "오늘 했다"로 친다.** 예전에는 상태를 보지 않아 LLM이 한 번 타임아웃 나면 그날 브리핑이 아예 없었다. 실패하면 30분 뒤 재시도하고 하루 3회에서 멈춘다. 상한은 **예약별**이라 아침이 세 번 실패해도 저녁은 돈다.
- **CLI 모드 제출은 완료가 아니다.** `submit_agent_task`는 job을 띄우고 바로 돌아오므로 그 시점을 `done`으로 적으면 job이 실패해도 그날 '성공'이 남아 위 재시도 규칙이 죽는다(실측: 실패한 예약이 화면에 성공으로 남고 재시도가 한 번도 돌지 않았다). 그래서 제출은 `submitted`로 적고, 스케줄러가 매 주기 `_reconcile_submitted_briefings()`로 job 종결 상태를 실행 기록에 되돌려 적는다 — job이 도는 동안은 성공처럼 취급해 중복 제출을 막고, 실패로 끝나면 `failed`로 바뀌어 재시도가 되살아난다. 재시도 30분 간격은 제출 시각이 아니라 job의 실제 종료 시각부터 센다.

## 실패 기록

실패한 실행은 `errorType`(예외 클래스 이름)과 `errorReason`(분류된 한국어 원인)을 남긴다.
**예외 원문은 담지 않는다** — 반환값과 실행 기록이 모두 HTTP로 나가고 메시지에는 요청 URL,
헤더, 프롬프트 조각이 실릴 수 있다. 키 패턴만 지우는 방식으로는 모르는 형태를 막지 못한다.
`tests/test_security_alert_regressions.py`가 이 경계를 지킨다.
