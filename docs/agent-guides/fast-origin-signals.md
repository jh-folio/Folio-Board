# Fast-Origin Signals (빠른 시장 신호)

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### Fast-Origin Signals (빠른 시장 신호)

- 로직은 `features/common/research_library/signals/`에 둔다. 수집 단위는 metadata-only lead(제목/URL/시각/티커/신뢰 등급)이며 본문·이미지·provider raw response·비밀값을 저장하지 않는다.
- provider allowlist는 **기존 한국 RSS 하나**(`APPROVED_PROVIDERS = {"kr_existing"}`)다. 새 provider는 별도 계획 변경 없이 추가하지 않는다. 0.4.5에서 제외 확정: Benzinga(공개 피드 목록이 비어 있거나 404, 응답하는 피드도 시장 속보가 아님), FinancialJuice(한 줄짜리 지표 속보라 브리핑·기업분석 어느 쪽에도 쓰임 없음), Investing.com(공개 피드 주소 없음, 약관상 사전 승인 필요). 셋 다 어댑터·설정·env 키·UI·런타임을 모두 제거했다.
- **fast-origin 경로에 자격증명·사용자 설정이 없다.** `promote_kr_rss_leads()`는 이미 수집된 `evidence_items` 행을 다시 읽을 뿐 네트워크를 쓰지 않으므로 **RSS 수집 작업에 함께 실린다**. 대상 매체는 연합인포맥스·연합뉴스이며 매일경제는 일반 RSS로만 분류한다.
- provider 켜고 끄는 설정 화면과 `signal-provider-settings.json` 오버레이는 없다. 설정할 provider가 없기 때문이며, 다시 필요해지면 계획 변경으로 되살린다.
- lead끼리의 교차 확인(`corroborated`)은 독립 provider가 둘 이상일 때만 성립하므로 현재 도달하지 않는 경로다. 확인은 공식 자료 경로(`confirm_signal`)가 담당한다.
- **별도 `signals` 자동화는 0.5에서 삭제했다.** 승인 provider가 하나뿐이라 lead를 보여주는 화면이 없고, 하는 일이 RSS 수집과 겹쳤다. 설정 항목(`저지연 리드 수집`)과 스케줄 kind를 모두 없앴으며 승격은 RSS 수집이 계속한다.
- `evidence_items.intake_stage=lead`는 `is_countable_evidence()`에서 항상 제외되고 source ledger에 들어가지 않는다. corroboration/공식 확인 후 승격된 row만 evidence가 된다.
- retention 기본값: 일반 lead 3일, 티커가 연결된 lead 14일, corroborated 30일(`normalize_signal`은 `related_tickers`가 비었는지만 본다 — 워치리스트·포트폴리오 보유 여부를 따로 확인하지 않는다). **집행은 두 곳이다** — `promote_kr_rss_leads()`가 승격 전에 `purge_expired()`를 부르고(RSS 수집·`지금 수집` 버튼과 함께 돈다), `query_signals()`가 아직 지워지지 않은 만료 lead를 결과에서 뺀다. 승격만 남기고 purge 호출부를 없애면 보존 계약이 집행되지 않는다 — lead 행은 `markdown_path`가 비어 있어 `prune_orphan_evidence()`도 걷어내지 못한다.
- 상시 WebSocket 연결은 두지 않는다(`start_signal_runtime`은 lifespan 호환용 no-op).
- run log에는 provider/count/status/error code만 남기고 headline/raw payload를 남기지 않는다.
- **0.4.8부터 lead를 보여주는 화면이 없다.** 워치리스트 상세의 `빠른 시장 신호` 레일은 승인 provider가 하나만 남아 교차 확인이 불가능해졌고 lead 티커가 워치리스트 종목과 맞는 경우가 없어 제거했다. 승격·retention 런타임은 그대로 남아 대화 context(`sourceContext.fastSignals`)가 계속 읽는다.

