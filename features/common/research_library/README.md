# Research Library

Research Library는 Folio OS가 자료를 읽고 찾는 공통 기반입니다. 사용자가 넣은 기사·RSS·리포트·공시·PDF를 스캔해 `research-index.sqlite3`에 저장하고, 브리핑·RSS 피드·뉴스 검색·기업분석·0.2 Deep Research·Thesis Delta가 같은 자료 기반을 읽도록 해줍니다.

## 사용 흐름

```text
research-inbox/에 자료 저장
→ RSS 수집/가져오기 또는 자료 폴더 다시 읽기
→ 증분 인덱싱으로 SQLite/FTS/청크 갱신
→ 브리핑, 검색, 기업분석, 테마분석, 워치리스트에서 재사용
```

## 폴더 역할

| 하위 폴더 | 역할 |
| --- | --- |
| `ingestion/` | `research-inbox` 폴더 계약과 PDF 추출 보조 코드 |
| `rss/` | 공개 RSS 수집, RSSArchive Markdown 저장, RSS 피드 캐시/API payload |
| `signals/` | fast-origin 출처의 metadata-only lead 수집, provider health, TTL/cursor query |
| `indexing/` | 파일 스캔, PDF 본문 추출, 태깅, `research-index.sqlite3` 동기화 |
| `search/` | RSS/기사 검색, 워치리스트 관련 뉴스 검색, hybrid search 호출 |

## 자료를 넣는 곳

```text
research-inbox/
  articles/   # 직접 저장한 기사, 웹페이지, txt, md, html
  rss/        # RSS 수집 결과. RSS 저장 위치는 오직 여기
  reports/    # 기업분석용 증권사 리포트, IR 자료
  filings/    # 기업분석용 SEC/DART 공시, 10-K/10-Q PDF
  links/      # URL 목록 txt/md/csv/json
```

지원 형식은 `.txt`, `.md`, `.html`, `.htm`, `.json`, `.csv`, `.pdf`입니다. PDF는 인덱싱 중 본문 추출을 시도하고 결과를 `data/pdf-cache/`에 저장합니다. 이미지 스캔 PDF는 OCR을 하지 않아 추출이 제한될 수 있습니다.

## 기능별 자료 범위

| 기능 | 사용하는 자료 |
| --- | --- |
| 브리핑 | `articles`, `rss`만 사용 |
| RSS 피드 | `rss` 파일과 `rss_feed_items` 캐시 |
| 뉴스 검색 | 기본 `articles`, `rss`; `scope=all`일 때 전체 검색 |
| 기업 분석 | `filings > reports > articles > rss > 기타` 순서 |
| Deep Research | 승인 계획에 따라 RSS/기사 외부 근거를 live resolve; Smart Collection/Market State/userContext 자체는 evidence가 아님 |
| Thesis Delta | 로컬 뉴스 검색 + 공식자료 보강 |

## Evidence Intake / RSS 수집

RSS 피드 탭의 `RSS 수집/가져오기`는 공개 RSS를 읽어 `research-inbox/rss/`에 Markdown으로 저장합니다.
내부 수집기는 Folio OS Evidence Intake 경로를 사용하며, RSS는 `collector=rss`인 입력원입니다.

수집 범위는 설정의 **관심 시장**(`features/common/market_scope.py`, `data/market-scope.json`, 기본 US/KR)이
정합니다. 범위 밖 시장 전용 피드는 수집에서 제외되고(GLOBAL 피드는 항상 수집), 시장을 다시 켜면
그 시장 피드만 즉시 나이 제한 없이 수집합니다(`--only-markets`, `--max-age-days 0`). RSS는 피드가
내어주는 최근 항목까지만 받을 수 있으므로 꺼져 있던 기간의 공백은 남습니다. 목록 API도 같은 범위를
지키며, GLOBAL/UNKNOWN 태그 항목은 어떤 범위에서도 보입니다.
신규 Markdown은 YAML front matter에 `collector`, `source_type`, `normalized_url`, `collection_status`,
`query_source`, `reliability_tier`, `language`, `country`를 저장하고, 기존 list-style RSSArchive Markdown은 계속 읽기 호환합니다.

기본 소스:

- 미국: Bloomberg, Dow Jones, Reuters, WSJ, Financial Times
- 한국: 한국경제, 연합인포맥스(증권, IB/기업, 채권/외환, 해외주식, 국제뉴스), 연합뉴스(경제, 산업/마켓), 매일경제(경제, 증권)

유료 본문 우회 수집은 하지 않습니다. 공개 RSS의 제목·요약·링크·발행일을 사용하고, 접근 가능한 공개 본문만 추출을 시도합니다. 수집 파일에는 `Collection Status`가 남아 `full_text`, `summary_only`, `fetch_failed`, `needs_manual_save` 상태를 구분합니다.

본문/요약 추출 규칙:

- 기사 페이지 요청은 표준 브라우저 User-Agent를 사용합니다(일부 무료 매체가 도구 UA에 403을 반환). 유료벽 감지는 그대로 유지되며 우회하지 않습니다.
- paywall 판정은 "구독 후 이용", "subscribe to continue" 같은 게이트 문구 기준입니다. 한국 뉴스 페이지 공통 푸터의 "구독"/"로그인" 단어만으로는 유료벽으로 판정하지 않으며, 충분한 길이의 공개 본문이 추출되면 페이지 다른 곳의 구독 배너가 `full_text` 판정을 막지 않습니다.
- `news.google.com` 리다이렉트 링크(Google News 검색 RSS)는 기사 HTML이 아니므로 페이지를 가져와 요약을 덮어쓰지 않고, RSS 요약을 유지한 `summary_only`로 저장합니다.
- **본문 확보 여부는 피드 설정이 정하지 않습니다.** 위 규칙(aggregator 리다이렉트 · 유료벽 문구 · 추출 결과)이 수집 시점에 정합니다. 예전 `config/rss_feeds.yaml`의 `allow_full_text` 항목은 읽히기만 하고 소비자가 없었고, 실제와 어긋나 있었습니다 — 설정이 `false`인 CNBC는 실측 538건 전부 본문이 확보됐습니다. 0.5.4에서 설정과 코드 양쪽에서 제거했습니다. 없는 신호를 남겨 두면 다음 판단이 그것을 믿습니다.
- 실측 본문 확보율(저장된 evidence 행 기준): CNBC·한국경제·매일경제 100%, 연합뉴스 99.9%, Handelsblatt 99%, 연합인포맥스 89.9%, Financial Times 49%, Reuters 7%, WSJ 0.8%, Bloomberg 0.1%. 낮은 쪽은 전부 유료벽 매체이며 우회하지 않습니다.

브리핑의 한국장 출처 다양성을 위해 `config/rss_feeds.yaml`에는 연합뉴스 경제·산업/마켓과 매일경제 경제·증권의 공식 공개 RSS가 포함됩니다. 포털 aggregator는 사용하지 않으며, 같은 매체의 여러 feed는 브리핑 이슈 확산도에서 하나의 publisher vote로 정규화됩니다.
CLI 기본 실행에서는 기사 전문을 Markdown에 저장하지 않습니다. 로컬/비공개 archive에 전문을 저장하려면 CLI에서 `--save-full-text`를 명시해야 하며, `--public-mode`에서는 전문 저장이 비활성화됩니다.
웹 앱에서 실행되는 수집(RSS 수집 버튼, 자동화 루틴)은 설정 탭 자동화 > RSS 수집의 `기사 전문 저장` 옵션(`automation-settings.json`의 `rss.saveFullText`, 기본 켜짐)에 따라 `--save-full-text`를 전달합니다. 저장된 전문은 인덱싱을 거쳐 하이브리드 검색과 브리핑 근거로 사용됩니다.
동일 기사 중복 제거는 원본 URL이 아니라 tracking query를 제거한 `normalized_url` 기준입니다.

설정 파일:

```text
config/rss_feeds.yaml          # RSS/Atom feed 목록, 시장/국가/언어, source type, reliability, freshness probe
config/evidence_sources.yaml   # 공식자료 adapter 설정
```

0.5 유럽/일본 feed는 canonical `default_market`(`EUROPE | JP`)과 고정 국가
universe(`GB | DE | FR | NL | IT | ES | JP`), 원문 `language`, 실제 최신 item
시각을 확인한 freshness probe를 함께 기록합니다. 지원하지 않는 enum이나 72시간보다
이미 오래된 probe는 로더가 거부합니다. 현지어 제목·요약은 번역하지 않습니다.

CLI 예시:

```bash
python -m features.common.research_library.rss.rss_archive --collectors rss --dry-run
python -m features.common.research_library.rss.rss_archive --collectors rss --save-full-text
```

공식자료 collector는 fake data를 만들지 않는 adapter stub으로 시작하며, 기존 공식자료 모듈 output을 EvidenceItem으로 연결하는 확장 지점입니다.
수집된 EvidenceItem metadata는 Markdown과 함께 `data/research-index.sqlite3`의 `evidence_items` 테이블에도 저장됩니다.
`language`/`country`는 RSS cache와 indexed document/search-hit metadata에도 additive하게 전파됩니다.
기존 Markdown에 두 필드가 없으면 `query`가 현재 feed URL과 정확히 하나만 일치할 때만 읽기 시점에
보완하며, source명이나 본문을 보고 추측하거나 파일을 다시 쓰지 않습니다.

## Fast-origin lead

기존 연합인포맥스·연합뉴스 RSS의 제목·링크·발행/수신 시각만 `intake_stage=lead`로 저장할 수 있습니다. lead는 빠른 알림용이며 확인 전에는 evidence count와 Canonical source ledger에서 제외됩니다. provider가 stale/unhealthy/disabled/unauthorized이면 headline을 노출하지 않습니다.

기사 본문·HTML·이미지·raw response·인증 URL/token은 signal 저장소와 run log에 남기지 않습니다. 수집만으로 Agent나 Change Intelligence가 실행되지 않습니다. 상세 계약은 [signals/README.md](signals/README.md)를 봅니다.

RSS 피드 화면은 Markdown 파일 전체를 매번 읽지 않고 `data/research-index.sqlite3`의 `rss_feed_items` 캐시에서 `LIMIT/OFFSET`으로 읽습니다. 캐시는 파일 크기와 `mtime_ns` 기준으로 증분 갱신하며 기본 TTL은 `RSS_CACHE_REFRESH_TTL_SECONDS=30`초입니다.
각 RSS 항목은 `markets` 태그를 함께 저장합니다. 값은 `US`, `KR`, `GLOBAL`, `UNKNOWN`이며, `US,KR,GLOBAL`처럼 복수 태그가 가능합니다. RSS 목록과 병합 다운로드는 `market=US|KR|GLOBAL|UNKNOWN` 필터를 지원합니다.

출처·언어 선택지는 필터를 적용하지 않은 별도 질의에서 만듭니다. 지금 보이는 목록에서 뽑으면 언어를 하나 고른 순간 선택지가 그 하나로 줄어 다른 언어로 돌아갈 방법이 사라집니다.

## 보관 기간 (Retention)

설정 탭 > 자동화 > RSS 수집에서 보관 기간을 고릅니다(30/60/90/180일/1년/계속 보관). 기간이 지난 `research-inbox/rss/*.md`는 다음 수집 때 함께 지워집니다.

**기본값은 설치 상태에 따라 다릅니다.** 새 설치는 90일로 시작해 아카이브가 처음부터 묶이고, 이 기능 이전에 만들어진 설정 파일이 있으면 `계속 보관`입니다 — 반년치를 모아 둔 사람이 새 버전을 받는 것만으로 석 달치를 잃으면 안 됩니다. 줄이는 것은 화면에서 고르며, 고를 때 몇 건이 지워지는지 먼저 보여줍니다.

RSS는 하루 300건씩 들어오고 한 건이 파일로 끝나지 않습니다. 색인 문서 하나와 청크 3~4개가 따라붙고 그 임베딩이 자리를 대부분 차지합니다 — 실측으로 2.5개월치 22,609건에 `research-index.sqlite3`가 728MB였고 그중 342MB가 `chunks.embedding_json`이었습니다. 인덱스된 문서는 100%가 RSS이므로 보관 기간이 곧 검색 DB 크기입니다.

`retention.py`는 **파일만 지웁니다.** 나머지 행은 이미 있는 경로가 걷어냅니다 — `refresh_rss_feed_cache()`가 `rss_feed_items`를, `build_index(incremental=True)`가 `documents`/`chunks`/FTS/`file_manifest`를 정리합니다. 같은 일을 하는 삭제 SQL을 따로 쓰면 인덱서가 바뀔 때마다 조용히 어긋납니다. 어느 쪽도 손대지 않는 `evidence_items`만 재색인 뒤에 정리합니다.

- 날짜는 파일명 접두(`2026-05-28 15-44-47 - ...`)로 읽습니다. 날짜를 못 읽는 파일과 `.state.json`은 건드리지 않습니다.
- evidence 행과 파일을 맞출 때 **대소문자는 무시합니다.** Windows 파일 시스템이 구분하지 않으므로, 매체가 제목의 대문자만 바꿔도(`Lost its` → `Lost Its`) 저장된 이름과 디스크의 이름이 갈립니다. 구분해서 비교하면 파일이 멀쩡히 있는 근거를 고아로 보고 지웁니다.
- 보관 기간은 `RETENTION_CHOICES`의 값만 받습니다. 임의의 숫자로 자료가 지워지지 않습니다.
- `GET /api/rss/retention?days=`는 저장 전에 몇 건이 지워지는지 세어 화면에 보여줍니다. 되돌릴 수 없는 설정이라 고르기 전에 비용을 먼저 말합니다.
- **VACUUM은 `지금 정리` 버튼에서만** 합니다. 실측 728MB 기준 29초 동안 DB를 통째로 잠그므로, 매시간 도는 수집이 파일 하나를 지웠다고 매번 물릴 수 없습니다. 자동 수집은 지운 자리를 SQLite가 재사용하게 두어 크기를 묶어 두고, 파일을 실제로 줄이는 일은 사용자가 부를 때 합니다.
- **자료 위치를 옮긴 뒤 재시작 전까지는 수집도 정리도 쉽니다.** 표지가 쓰인 순간부터 이 프로세스는 두 워크스페이스를 동시에 봅니다 — 모듈 상수는 옛 폴더, 수집 서브프로세스와 호출 시점에 판정하는 경로는 새 폴더입니다. 그대로 두면 새 기사는 옛 폴더에 파일로, 새 폴더에 근거 행으로 갈려 재시작 뒤 사라지고, 정리는 방금 복사한 사본을 지웁니다. 작업 결과에 `skipped: "workspace_moved"`와 재시작 안내가 함께 나옵니다.

## 인덱싱과 검색

핵심 산출물:

```text
data/research-index.sqlite3   # documents, file_manifest, chunks, chunks_fts, rss_feed_items
#   chunks.embedding: float32 + zlib blob (JSON 텍스트 대비 14.85배 작고 디코드 9배 빠름)
data/index.json               # generatedAt/count/incremental/sqlite 등 상태 요약
data/pdf-cache/               # PDF 본문 추출 캐시
```

`build_index(incremental=True)`는 `file_manifest`의 파일 크기/수정시각을 보고 바뀌지 않은 파일을 건너뜁니다. 시장 관련 없는 파일도 manifest에 기록해 다음 실행 때 재처리하지 않습니다.

텍스트 쿼리가 있으면 검색은 항상 hybrid search 경로를 탑니다.

1. FTS5 BM25로 최대 120개 청크 후보 추출
2. 후보에 한해 해시 임베딩 코사인 유사도 계산
3. RRF(k=60)로 FTS 랭크와 벡터 랭크 통합
4. 같은 문서의 여러 청크는 최고 점수 청크로 중복 제거
5. 기업/범위 필터는 결과에 post-filter 적용

일본어처럼 unicode61이 부분어를 놓치는 질의는 trigram 보조 인덱스(`chunks_cjk`)에서 후보를 보탭니다. 이 보조 경로도 1단계와 같은 범위·허용 문서 제한을 집니다 — 제한 없이 후보를 보태면 허용 밖 문서가 후보 정원을 먹어 정작 찾아야 할 문서가 밀려납니다.

쿼리 없이 회사/범위 필터만 있을 때는 인메모리 문서 목록을 필터링합니다.

### 임베딩 저장 형식

`chunks.embedding`은 float32 + zlib blob입니다. JSON 텍스트로 저장하면 값 하나가 `-0.05922199384805114,` 같은 20여 글자가 되어, 실측으로 청크 42,471개의 임베딩이 342MB를 차지했습니다(검색 DB 728MB의 절반 가까이). 같은 표본에서 이 형식은 **14.85배 작고 디코드가 9배 빠릅니다**(후보 120개 기준 13.0ms → 1.4ms). 실제 DB에서 변환 + VACUUM 후 **728MB → 380MB**였습니다.

float32로 줄이면 성분 오차가 최대 1.4e-08입니다. 코사인 값은 RRF에서 **순위로만** 쓰이므로 이 오차로는 순서가 바뀌지 않습니다 — 실제 질의 8개(한국어 포함)로 변환 전후 상위 20위가 완전히 같음을 확인했습니다.

- 판올림한 DB는 시작 직후 배경에서 변환합니다(`migrate_embeddings()`). batch 500개가 곧 한 트랜잭션이라 그동안 검색이 멈추지 않고, 중간에 꺼져도 다음 시작이 이어서 합니다(`typeof(embedding)='text'`로 고름).
- `parse_embedding()`은 blob과 옛 JSON을 모두 읽습니다. 변환이 도는 동안에도 검색이 그대로 동작해야 합니다.
- 칸 이름은 `embedding_json` → `embedding`으로 바뀝니다. SQLite 3.25+의 `RENAME COLUMN`은 메타데이터만 바꿔 728MB DB에서도 즉시 끝납니다.
- 변환해도 파일은 줄지 않습니다(빈 페이지로 남음). 설정의 `지금 정리`가 `PRAGMA freelist_count`로 회수량을 재서 50MB 이상일 때 VACUUM합니다.

## 태깅

기업 태깅 우선순위:

1. `config/company_master.json`
2. `config/company_aliases.json`
3. `features/common/company_lookup.py`의 seed
4. 문서 안의 패턴(`NASDAQ:NVDA`, `005930.KS`, `Uber Technologies, Inc. (UBER)` 등)

섹터/영향 태그는 `indexing/service.py`의 `SECTOR_TERMS`, `IMPACT_TERMS`로 찾고 `features/common/taxonomy.py`의 `normalize_tag()`로 정규화합니다. 새 태그를 추가할 때는 taxonomy와 indexing 키워드가 함께 맞아야 합니다.

## API

```text
POST /api/index
GET  /api/index/documents
POST /api/rssarchive/import
GET  /api/rss/retention?days=90
POST /api/rss/retention/run
GET  /api/rss/items
GET  /api/rss/merge
GET  /api/signals
GET  /api/signals/providers
GET  /api/search?query=NVDA&limit=30
```

`/api/index`와 `/api/rssarchive/import`는 오래 걸릴 수 있어 job을 만들고 `/api/jobs/{job_id}`로 진행 상황을 조회합니다.

## 관련 코드

- `ingestion/extract_pdf.py`: PDF 추출 보조
- `rss/rss_archive.py`: Evidence Intake CLI entrypoint과 얇은 orchestration
- `rss/fetch.py`: feed/article HTTP 수집(retry/backoff)
- `rss/parser.py`: RSS/Atom XML → raw item 파싱
- `rss/article.py`: 공개 기사 본문/요약 추출, paywall 감지
- `rss/relevance.py`: 시장 관련성 게이트(NOISY/term 필터, `should_archive_item`, `canonical_media`)
- `rss/normalizer.py`: raw item → `IntakeEvidenceItem`
- `rss/policy.py`: normalized URL dedupe/retry/relevance score/full-text/paywall 정책
- `rss/collectors.py`: official collector adapter
- `rss/writer.py`: YAML front matter Markdown 아카이브 IO, legacy 업그레이드, `.state.json`
- `rss/store.py`: `research-index.sqlite3::evidence_items` 저장
- `rss/retention.py`: 보관 기간 판정·기간 지난 파일 삭제·orphan evidence 정리·VACUUM
- `rss/service.py`: RSS import/feed/merge/cache payload, `run_retention_now()`
- `signals/`: approved provider adapter, metadata-only 저장/조회, health와 retention
- `indexing/service.py`: `build_index()`, `load_index()`, `build_document()`, `market_relevance()`
- `indexing/research_index.py`: SQLite schema, FTS, manifest, `hybrid_search()`
- `search/service.py`: `search_documents()`, `group_docs()`, `list_companies()`

## 주의점

- `research-inbox/rss/` 외의 예전 `archive/` 폴더를 다시 만들지 않습니다.
- `data/`, `research-inbox/`, `config/`는 사용자 개인 자료가 들어갈 수 있으므로 명시 요청 없이 삭제하거나 초기화하지 않습니다.
- 검색/태깅 변경은 브리핑, 워치리스트, 기업분석, 테마분석, thesis tracking에 함께 영향을 줍니다.
