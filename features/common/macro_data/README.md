# 공통 거시 원장

16개 표시 지표의 17개 원천 시계열과 국면 계산 전용 4계열을 allowlist로 관리합니다. 전체 FRED 10개, ECOS 11개이며 한국 회사채 AA−·국고채 3년을 같은 날짜에 연결해 스프레드 하나로 표시합니다. [거시 지도](../../macro_map/README.md)가 첫 소비자이고 Calendar는 FRED vintage parser를 공유합니다.

국면 전용 입력은 `ICSA`(주간, 선행, 노후 기준 14일), `CFNAIMA3`(월간, 동행, 60일), `KR_LEADING`·`KR_COINCIDENT`(ECOS `901Y067`의 `I16E`·`I16D`, 월간, 70일)입니다. 기존 지도 표시 지표에는 추가하지 않습니다. 2000년 시작 계산에 필요한 관측은 UNRATE 1998-05, INDPRO 1998-07, GDPC1 1999Q1, ICSA 1999-04까지 수집 범위를 넓혀 추가합니다. 요청 시작일이 더 이르면 그 날짜를 유지합니다. 화면의 시작 범위는 바꾸지 않습니다.

## 공식 미발표 사실 등록

일반 결측은 공식 미발표 사실로 변환하지 않습니다. UNRATE의 공식 미발표 월만 관리자가 BLS 원문을 확인한 뒤 `publication_facts`의 별도 명시 경로로 등록합니다. JSON 입력 필드는 `seriesId`, `observationMonth`(`YYYY-MM`), `sourceUrl`(BLS HTTPS 원문), `availableAt`(시간대 포함)입니다. 공개 시각과 실제 기록 시각 `recordedAt`을 분리합니다. 원문 내용의 확인 책임은 관리자에게 있으며 URL 형태 검사만으로 사실 여부를 판정하지 않습니다.

```powershell
py -3 -X utf8 -m features.common.macro_data.publication_facts --input "fact.json"
# 내용을 확인한 뒤 출력된 confirmationToken을 명시해야 저장됩니다.
py -3 -X utf8 -m features.common.macro_data.publication_facts --input "fact.json" --database "path/market-memory.sqlite3" --confirm "확인한 토큰"
```

미리보기와 조회는 파일·테이블을 만들지 않습니다. 같은 사실의 재등록은 멱등이며 최초 `recordedAt`을 보존합니다. 사실은 schema v2의 `macro_publication_facts`에 저장하고 `availableAt <= cutoff`인 행만 조회합니다. 수집·화면 조회에서 등록 함수를 호출하지 않습니다. v1→v2는 SQLite backup API 사본 생성 후 트랜잭션으로 테이블만 추가하며 기존 관측은 수정하지 않습니다.

## 시간·값 계약

`period`는 관측기간, `vintageDate`는 FRED 보관판 날짜, `releasedAt`은 정확한 값·판과 연결한 공식 시각, `fetchedAt`은 응답 수집 시각입니다. `availableAt`은 조회에 쓸 수 있는 보수적인 시각입니다.

- `provider_vintage`: 원천 현지 날짜 마감에 가용한 것으로 처리합니다. 나중에 다운로드했어도 지원되는 당시 날짜로 조회할 수 있습니다. 현재 연결은 이 근거이며 공식 발표시각을 주장하지 않습니다.
- `local_observed`: 다운로드 이전으로 소급하지 않습니다. 한국의 과거 추이는 현재 수정치이며 당시 알려진 값 재현은 지원하지 않습니다.
- `official_release`: 정확한 발표 근거 URL과 시각이 필요합니다. 현재 FRED/ECOS 수집기는 이 근거를 만들지 않습니다.

숫자는 유한한 Decimal 문자열로 정규화하고 0·결측·철회를 구분합니다. 같은 값·메타데이터 재수집은 멱등이며, 값이 달라졌다가 돌아온 이력은 남깁니다. 같은 보관판에서 다른 값이 오면 둘 다 보관하고 해당 판의 주 조회값은 null로 만듭니다. 이는 다른 provider 간 교차 검증 성공을 뜻하지 않습니다.

변화율의 기준기간도 같은 cutoff에서 고릅니다. 단위·주기·계절조정·정의 버전이 다르면 계산을 중지합니다. 전분기비는 비연율이며 금리·실업률 차이는 %p입니다. NFCI와 STLFSI4는 공통 입력이 있어 독립 신호로 합산하지 않습니다. 산업생산(INDPRO·전산업생산)은 `macro-2`부터 전년비입니다(이전 `macro-1`은 전월비). 관측기간 노후 기준은 일간 7일, 주간 21일, 월간 60일, GDP 150일, 가계신용 180일입니다. 월간·분기는 해당 관측기간의 마지막 날부터, 일간·주간은 원천 관측일로부터 계산합니다. 이는 공식 발표 지연 판정과 별개입니다.

## 수집·복구

- FRED metadata의 유효기간별 단위·정의를 보존합니다. 월·분기는 `output_type=3`의 모든 관측기간·개정값을 파싱합니다. 정의만 바뀌는 날짜에는 `output_type=1` 당일 snapshot을 받아 메타데이터 변경도 남깁니다.
- 일·주간은 넓은 vintage 열 행렬의 timeout을 피하도록 `output_type=1` 장형 구간을 사용합니다. 최대 2년 단위이며 정의 변경일에서도 구간을 자릅니다. 반복 경계의 같은 값은 저장 시 제거합니다. 요청당 vintage 2,000개 제한과 observations 페이지 10,000행을 지킵니다.
- 빈 최근 vintage 구간에 FRED가 오류를 내는 경우를 피하도록 전체 지원 날짜 목록을 페이지별로 읽고 증분 범위를 고릅니다. 완료 이후 7일을 겹쳐 재조회합니다. 시작 연도를 넓히면 전체 수집으로 전환합니다.
- ECOS는 표·주기·모든 차원·단위를 검증하고 1,000행씩 수집합니다. 원천이 주지 않는 수정판·공표일·계절조정을 추정하지 않습니다.
- `ProviderFetchRuntime`의 cache/circuit breaker를 재사용합니다. 키에 series·차원·기간·vintage·metadata 버전을 넣으며 stale 응답을 정상 수집으로 적재하지 않습니다. 인증정보가 들어간 URL은 오류·로그에 남기지 않습니다.
- 재생성 가능한 `macro-cache` 응답은 128MiB/7일을 기준으로 오래된 것부터 정리합니다. 방금 쓴 1시간 이내 응답은 보호하므로 초기 수집 중에는 일시 초과할 수 있습니다. 해당 cache의 엄격한 파일명 패턴만 다루고 원장·백업·사용자 파일·다른 cache는 삭제하지 않습니다.
- 페이지의 값·metadata·cursor는 같은 SQLite transaction에서 저장합니다. `fred`, `fred_metadata`, `ecos` cursor를 재개하며, 네트워크 오류·잘못된 응답·취소 시 완료 cursor로 진행하지 않습니다. 메모리 전체 복제 대신 변경 이력만 저장합니다.
- ECOS cursor에는 전체 행 수도 함께 저장합니다. 마지막 페이지 저장 직후 중단되어도 범위 밖 요청 없이 완료 처리를 재개합니다. 전체 행 수가 없는 이전 cursor는 첫 페이지부터 멱등 재수집합니다. 충돌한 보관판 다음의 정상 보관판은 같은 숫자라도 남기며, 과거 충돌을 소급해서 지우지 않습니다.

## 저장·읽기

기존 knowledge DB의 `macro_schema`, `macro_metadata`, `macro_observations`, `macro_collection_state`를 사용합니다. 첫 적용은 기존 SQLite의 일관된 backup을 만들고 DDL transaction을 실행합니다. 원장 조회는 read-only이며 없는 DB를 만들지 않습니다. 최신/과거 조회는 지표·관측기간·가용시각 인덱스에서 후보를 집계한 뒤 metadata를 연결합니다.

원천: [FRED observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html), [FRED vintage dates](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html), [한국은행 ECOS](https://ecos.bok.or.kr/).
