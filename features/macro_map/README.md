# 거시 지도

시장 내러티브의 `거시 지도` 하위 보기에서 미국 8개·한국 8개 지표를 경기·물가·금융여건·위험 네 축으로 읽습니다. 자동 경기 판정, 투자 추천, AI 해설은 만들지 않습니다.

- 처음에는 최근 5년을 표시합니다. 시장·자료 기준·기준일·표시 기간·상세 지표·수정 비교 관측기간을 URL에 보존하며, Calendar 왕복과 새로고침에서도 유지합니다.
- 미국의 `과거 시점 재현`은 America/Chicago의 선택 날짜 마감에 알려진 FRED 보관판을 사용합니다. 지표별 실제 지원 시작일 이전은 빈칸입니다. 현재 수정치는 명시적으로 전환하거나 상세의 점선으로 비교합니다.
- 한국은 현재 수정치의 과거 추이와 수집을 시작한 뒤 확인한 변경 이력을 제공합니다. `처음 확인한 시각`은 Folio Board의 관측이며 공식 최초 발표일이 아닙니다.
- 상승·하락은 화면에 표시된 값의 직전 관측 대비 방향입니다. 좋고 나쁨이나 투자 신호를 뜻하지 않습니다. 회사채 스프레드는 같은 날짜의 두 금리만 뺍니다. 기준기간 자료도 같은 과거 시점의 판을 사용합니다.
- 상세에는 원값·단위·조정·출처·보관판·수집 시각·계산 방식·수정 이력이 있습니다. 공식 발표시각을 확인하지 못하면 그대로 밝힙니다. FRED Calendar의 다음 일정은 **날짜**만 연결하며, Calendar의 합성 시각을 발표 근거로 승격하지 않습니다.
- 원천 확인 실패·부분 수집·관측기간 노후·정의 변경·자료 부족은 함께 표시할 수 있습니다. 같은 원천 보관판의 값 불일치는 확정값을 고르지 않습니다. 별도 교차 검증 경로가 없으면 `비교 경로 없음`입니다. 확인된 공식 발표시각 연결이 없는 지표에 발표 지연 판정을 만들지 않습니다.

## 수집과 저장

설정의 기존 FRED/BOK 키를 사용합니다. `공식 자료 갱신`은 `macro_refresh` SharedJob이며 AI/내러티브 생성 작업을 호출하지 않습니다. 초기 수집 목표는 2000년이고 원천의 실제 지원 범위가 우선합니다. 키 없는 원천은 미연결 상태로 남습니다.

자동 갱신은 기본 OFF입니다. 사용자가 켜면 서버가 실행되는 동안 09:00·21:00 KST에 갱신합니다. 종료 중 놓친 회차는 재기동 후 한 번으로 모읍니다. 수동 갱신과 예약은 실행 중인 작업을 공유합니다. 취소·서버 재시작·실패 시 이미 저장한 페이지는 남기고 cursor에서 재개합니다. 일부 원천 실패를 전체 완료로 표시하지 않습니다.

`market-memory.sqlite3`에 공통 거시 원장을 추가하며, 첫 migration 전에 SQLite backup API로 기존 DB를 백업합니다. 기존 내러티브·노트·보고서는 수정하지 않습니다. 설정과 마지막 작업 ID는 `macro-settings.json` / `macro-refresh-state.json`에 원자 저장합니다. GET은 수집·migration을 실행하지 않습니다.

## API와 경계

| API | 역할 |
| --- | --- |
| `GET /api/macro?market=US&mode=as_of&date=2020-03-31&years=5` | 당시 자료 지도. `series` 상세, `period` 수정 비교 관측기간 선택 가능 |
| `GET/POST /api/macro/settings` | `enabled`, `startYear`와 고정 갱신 일정 |
| `POST /api/macro/refresh` / `GET /api/macro/refresh` | 수집 요청 / 마지막 SharedJob 조회 |
| `POST /api/jobs/{id}/cancel` | 기존 작업 취소 계약 |

공통 registry·provider·저장·변환은 [macro_data](../common/macro_data/README.md)가 소유합니다. 라우터는 이 폴더에서 조립하고 `app.py`는 등록만 합니다. UI는 `web/src/app/macro/`와 기존 `FolioChart`를 사용합니다.

0.8은 이 조회 결과의 `availabilityBasis`, `availableAt`, `metadataId`, `quality`, 원천 지원 범위를 입력 계약으로 삼아야 합니다. 현재 수정치·한국 로컬 관측·FRED 날짜를 과거 공식 발표시각으로 바꾸지 않습니다. 사용자 가설과 Portfolio 상태는 이 원장의 근거가 아닙니다.

검증: `py -3 -X utf8 -m pytest features/common/macro_data/tests features/market_calendar/tests -q`, `web`에서 `npm run typecheck`, `npm test`, `npm run test:ui -- macro-map.spec.ts`, `npm run build`.
