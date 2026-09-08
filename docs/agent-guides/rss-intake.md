# RSS와 뉴스 검색 (Evidence Intake)

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### RSS와 뉴스 검색 (Evidence Intake)

- 수집은 RSS 단독이 아니라 Folio OS Evidence Intake 경로다. 최종 단위는 `IntakeEvidenceItem`이고 RSS는 `collector=rss` 입력원 중 하나다.
- 모듈 경계(단방향 DAG): `rss_archive.py`(얇은 CLI/orchestration) → `fetch.py`(HTTP retry/backoff) → `parser.py`(RSS/Atom→raw item) → `article.py`(본문/요약 추출) → `relevance.py`(시장 관련성 게이트) → `normalizer.py`(raw→EvidenceItem) → `policy.py`(dedupe/retry/relevance score/full-text/paywall) → `collectors.py`(official adapter) → `writer.py`(YAML front matter Markdown 아카이브 IO + state) → `store.py`(`research-index.sqlite3::evidence_items`). `rss_archive.py`에는 run-level orchestration만 둔다(parse/fetch/write 로직 추가 금지).
- 설정 파일로 분리: `config/rss_feeds.yaml`, `config/evidence_sources.yaml`. 코드 수정 없이 feed enable/disable이 가능하다.
- **피드는 정기적으로 죽는다.** 매체가 호스트를 옮기면 기존 URL이 200 OK와 옛 항목을 계속 반환해 정상처럼 보인다(2026-08 확인: WSJ `feeds.a.dj.com` 3개가 553일, MarketWatch `feeds.marketwatch.com`이 396일 정체 상태로 응답 중이었고 `feeds.content.dowjones.io`가 현행 호스트다). 커버리지가 이상하면 건수가 아니라 **최신 항목 시각**을 먼저 확인한다.
- `only_publishers`를 지정하면 aggregating 피드에서 해당 발행처 항목만 남기고 저장 시 **원 발행처 이름으로 태그**한다(Yahoo Finance→Reuters). 발행처는 RSS `<source>`에서 읽는다.
- feed의 `source_type`이 소비 경로를 가른다. 기본 `news`만 사용자에게 보이는 뉴스 경로에 들어간다. **`press_release`(PR Newswire·GlobeNewswire 같은 보도자료 와이어)는 브리핑과 RSS 피드 화면 양쪽에서 제외한다.** 브리핑은 `is_news_document()`가, RSS 화면은 `_HIDE_PRESS_RELEASE_SQL`이 담당하며 목록과 출처 드롭다운이 같은 조건을 공유한다(출처를 직접 골라도 보이지 않는다). 이야기 비중 패널도 `news_documents()`를 거치므로 함께 제외된다. 같은 문서는 인덱스에 그대로 남아 워치리스트 종목 뉴스와 기업분석 보조자료로 쓰인다. 브리핑은 교차 보도량(`publisherCount`)으로 이슈를 고르는데 보도자료는 발행처가 1곳뿐이라 이슈로 뜨지 않으면서 클러스터링만 흐리고, RSS 화면에서는 발행량이 많아 뉴스를 밀어내기 때문이다.
- feed는 **직접 피드**와 **aggregator 경유**로 성격이 다르다. 직접 피드(CNBC·Yahoo Finance·The Guardian·BBC·한국 매체)는 본문까지 확보되지만, `news.google.com` 검색 경유(Reuters·Bloomberg·WSJ·Barron's 등)는 `AGGREGATOR_REDIRECT_HOSTS` 정책상 기사 HTML을 가져오지 않아 **제목·링크만 남는다**. 커버리지 논의에서 수집 건수와 실제 사용 가능한 본문 수를 구분한다. Reuters·AP·Bloomberg 등은 공개 RSS를 종료했거나 라이선스 전용이라(2026-08 확인: Reuters 401·도메인 소멸, AP 401/404) 제목 신호로만 유지하며, 제3자 RSS 변환기나 scraping으로 우회하지 않는다.
- 신규 Markdown은 YAML front matter(`collector`/`source_type`/`normalized_url`/`collection_status`/`reliability_tier`/`query` 등) + body section 포맷이다. legacy line-oriented Markdown은 읽기 호환을 유지한다.
- CLI 기본 실행은 기사 전문을 저장하지 않는다. `--save-full-text` 명시 시에만 `Full Text` 섹션에 전문을 쓴다. 웹 앱이 실행하는 수집(RSS 수집 버튼/자동화)은 설정 탭의 `rss.saveFullText`(automation-settings, 기본 켜짐)에 따라 이 플래그를 전달한다. 유료 본문 우회는 금지한다.
- paywall 판정은 게이트 문구("구독 후 이용", "subscribe to continue" 등) 기준이다. 한국 뉴스 푸터의 "구독"/"로그인" 단어만으로 유료벽 판정하지 않으며, 충분한 공개 본문이 추출되면 페이지 내 구독 배너가 full_text 판정을 막지 않는다. `news.google.com` 리다이렉트 링크는 기사 HTML을 가져오지 않고 RSS 요약을 유지한 `summary_only`로 저장한다(aggregator 페이지 요약으로 덮어쓰기 금지). 기사 페이지 요청은 표준 브라우저 UA를 사용한다.
- normalized URL 기준 dedupe를 사용한다. `summary_only`/`needs_manual_save`/`legacy_rss`/`fetch_failed`는 기본적으로 반복 재수집하지 않는다(`--retry-failed`/`--retry-summary-only`로만).
- 공식자료(SEC/OpenDART/FRED/BOK)는 `source_type=official_filing|macro_data|official_release`, `reliability_tier=1`로 구분한다. 현재 adapter는 fake data 없는 stub이며 브리핑 직접 근거로 쓰지 않는다.
- 외부 검색 API 기반 추가 수집은 사용하지 않는다. RSS 수집 버튼(`/api/rssarchive/import`)은 RSS collector만 실행한다.
- **임베딩은 `chunks.embedding`에 float32 + zlib blob으로 담는다.** JSON 텍스트는 값 하나가 20여 글자라 청크 42,471개가 342MB였다(실측). 이 형식은 14.85배 작고 디코드가 9배 빠르며, 변환+VACUUM 후 DB가 728MB → 380MB가 됐다. float32 오차는 최대 1.4e-08이고 코사인은 RRF에서 순위로만 쓰여 한국어 포함 8개 질의의 상위 20위가 완전히 같았다.
- 판올림한 DB는 시작 직후 배경에서 batch 500개씩 변환한다(`migrate_embeddings()`). 전부를 한 트랜잭션으로 밀면 그동안 검색이 멈춘다. `parse_embedding()`이 blob과 옛 JSON을 모두 읽으므로 변환 중에도 검색이 동작한다. 변환해도 파일은 줄지 않으며 회수는 `지금 정리`가 한다.
- **보관 기간이 곧 검색 DB 크기다.** 인덱스된 문서는 100%가 RSS이고, 한 건이 파일 3.5KB로 끝나지 않는다 — 문서 하나와 청크 3~4개가 따라붙어 실측 2.5개월치 22,609건에 `research-index.sqlite3`가 728MB였다(그중 342MB가 `chunks.embedding_json`). 설정은 `automation-settings.json`의 `rss.retentionDays`(기본 90일)이고 로직은 `features/common/research_library/rss/retention.py`다.
- 정리는 **파일만 지운다.** 나머지 행은 이미 있는 경로가 걷어낸다 — `refresh_rss_feed_cache()`가 `rss_feed_items`를, `build_index(incremental=True)`가 `documents`/`chunks`/FTS/`file_manifest`를 정리한다. 같은 일을 하는 삭제 SQL을 따로 쓰면 인덱서가 바뀔 때마다 조용히 어긋난다. 어느 쪽도 손대지 않는 `evidence_items`만 재색인 뒤에 정리한다.
- **기본값은 설치 상태에 따라 다르다.** 새 설치는 90일, 이 기능 이전에 만들어진 설정 파일이 있으면 `계속 보관`(0)이다(`schema.py::_retention_for`). 쓰던 설정에 90일을 먹이면 반년치를 모아 둔 사람이 판올림만으로 석 달치를 잃는다 — 지우겠다고 말한 적이 없는데 지워진다(§6 절대 규칙 2). 줄이는 것은 화면에서 고르고, 그때는 몇 건이 지워지는지 먼저 보여준다.
- 날짜는 파일명 접두로 읽고, 날짜를 못 읽는 파일과 `.state.json`은 건드리지 않는다. 기간은 `RETENTION_CHOICES` 값만 받는다 — 임의의 숫자로 자료가 지워지지 않는다.
- **VACUUM은 `지금 정리` 버튼에서만** 한다(`run_retention_now()`). 실측 728MB 기준 29초 동안 DB를 통째로 잠그므로 매시간 도는 수집에 물릴 수 없다. 자동 수집은 지운 자리를 SQLite가 재사용하게 두어 크기를 묶어 두고, 파일을 실제로 줄이는 일은 사용자가 부를 때 한다.
- **수집 서브프로세스 상한은 `RSS_COLLECT_TIMEOUT_SECONDS`(기본 1800초)다.** 300초이던 시절 매시 자동 수집이 전부 상한에서 잘려 **한 건도 쓰지 못한 채 `done`으로 기록**됐다(실측 2026-08-14~24 열흘, 매 실행 307초). 잘린 실행은 파일을 남기지 않아 다음 실행이 같은 backlog를 다시 시도하므로 스스로 회복되지 않는다. 실측으로 열흘 공백을 메우는 실행에 8~10분이 걸렸다.
- **수집 실패는 실패로 기록한다.** 예전에는 예외를 통째로 삼켜 이유 없는 `RSS collection failed.` 한 줄만 남기고 자동화 실행 기록에는 `done`으로 적었다 — 자동 수집이 도는 줄 알고 열흘을 보낸다. 이제 결과에 `collection: {ok, error}`가 실리고 `run_automation_once()`가 그것을 보고 상태를 `failed`로 남긴다. 예외 종류는 코드 식별자라 기록하되 원문 메시지는 담지 않는다.
- RSS API: `app.py::rss_feed_payload()`, `rss_merge_payload()`. import 경로는 `service.py::import_rssarchive()`.
- 출처 필터 드롭다운은 **현재 `config/rss_feeds.yaml`에서 수집 중인 매체만** 노출한다(`_selectable_sources()`). 피드를 지웠거나 aggregating 피드가 원 발행처로 재태그해서 더는 새 항목이 들어오지 않는 매체는 고를 수 있어도 결과가 늘지 않아 사용자를 오도한다. 과거 수집분은 목록에 그대로 보이며 필터 대상에서만 빠진다. 설정을 읽지 못하면 전부 노출하는 기존 동작으로 되돌아간다.
- 화면: RSS 피드 탭. 한 페이지 20개 표시. 시간, 소스, 시장 필터를 제공한다.
- RSS 피드 목록은 Markdown 파일 전체를 매 요청마다 읽지 않고 `data/research-index.sqlite3`의 `rss_feed_items` 캐시 테이블에서 `LIMIT/OFFSET`으로 읽는다. 캐시는 파일 `mtime_ns`/크기 기준으로 증분 갱신하며 기본 TTL은 `RSS_CACHE_REFRESH_TTL_SECONDS=30`초다. RSS 수집 직후에는 강제 갱신한다. 캐시는 각 항목의 `markets` 태그를 `US`, `KR`, `GLOBAL`, `UNKNOWN` 중 하나 이상으로 저장하며, `/api/rss/items`와 `/api/rss/merge`는 `market=US|KR|GLOBAL|UNKNOWN` 필터를 지원한다.
- 인덱싱은 front matter metadata(`collector`/`sourceType`/`reliabilityTier`/`query`/`relatedTickers`/`narrativeIds` 등)를 문서/chunk metadata로 보존해 briefing/topic/market_memory 소비자가 읽을 수 있게 한다. 단, 브리핑 입력 범위는 계속 `articles/rss` 원칙을 지킨다.
- 별도 뉴스 검색 탭은 없다. RSS 피드 탭 안에서 `articles/rss` 자료를 검색한다.

