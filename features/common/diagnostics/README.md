# common/diagnostics

브리핑 저장 준비·규칙 대체·최종 검사·시간 제한의 허용된 코드 위치를 관측합니다. 일반 worker 위치 대신 가장 안쪽의 허용 위치 한 개를 남기며, 최종 검사 예외는 일반 오류와 구별합니다. 예외 메시지·보고서·지역 변수·전체 traceback은 저장하지 않습니다.

0.6 L1a의 실행별 안전 진단 core입니다. 이 패키지는 job, commit, retry, 결과 본문을 소유하지 않는 관측 문서만 다룹니다. import만으로 workspace를 찾거나 파일을 만들지 않습니다.

## 사용 경계

생산자는 기존 권위 저장이 성공한 뒤, 그 저장과 같은 data root를 주입해 best-effort로 사용합니다.

```python
from features.common.diagnostics import DiagnosticsStore, new_context

store = DiagnosticsStore(data_root=jobs.data_root())
context = new_context(
    feature_code="jobs", route_code="shared_worker",
    authority_kind="shared_job", job_id=job.id, app_version="0.5.4",
)
recorder = store.start(context)
if recorder is not None:
    stage = recorder.start_stage("generate")
    if stage:
        recorder.end_stage(stage, "generate")
    recorder.finish("succeeded")
store.close()
```

`start`, `event`, `failure`, `finish`, `resume`는 진단 문제를 원래 작업 예외로 바꾸지 않습니다. 실패하면 `None`/`False`를 반환합니다. 조회는 `store.read(run_id)`이고 완료 시 `store.close()`를 부릅니다. 새 observer는 context를 명시 전달하고 `bind_context()`는 같은 실행의 편의 접근으로만 사용합니다. subprocess는 이 store를 직접 import하거나 쓰지 않습니다.

## 보안과 저장

- 위치는 주입한 `<data root>/diagnostics/runs/<validated runId>.json`입니다.
- schema v1은 closed allow-list입니다. 자유 metadata, exception text/args/body, traceback, stdout/stderr, URL/query, prompt/본문은 받을 수 없습니다.
- frames는 producer가 선언한 source registry와 실제 배포 AST의 module/function/line 모두 일치해야 읽거나 쓸 수 있습니다.
- UTF-8 128 KiB/run, events 200, errors 16(terminal slot 예약), total 50 MiB, files 4096입니다. quota/scan/lease failure는 diagnostics만 partial 또는 unavailable로 만듭니다.
- 동일 workspace의 writer는 Windows byte lock/POSIX flock advisory lease 하나입니다. lease가 없으면 reader만 동작하고 기존 product writer 계약은 바뀌지 않습니다.

L1b에서는 SharedJob 제출·worker·기존 private terminal/recovery 권위 뒤에만 observer가 연결됩니다. `GET /api/diagnostics/runs/{runId}`와 `GET /api/diagnostics/jobs/{jobId}`는 headless v1 상세이며, 기존 jobs/private-cleanup 503을 우회하지 않습니다. HTTP는 모든 요청에 서버 생성 request ID header를 붙이고 unhandled 500에서만 별도 direct diagnostic run을 best-effort로 기록합니다.

L1c는 automation/RSS/index, report CLI bridge, durable JSON/SQL commit, approved topic worker, consultation worker, 그리고 지원되는 direct personal-judgment 경계에 observer를 연결합니다. 각 producer는 실제 권위 경계와 저장 proof만 기록합니다. 기존 one-shot `chat_cli`와 consultation worker는 이 범위에 포함되며, 미사용 route code를 신규 실행 경로로 활성화하지 않습니다. provider protocol·parser 소비자·UI/Work Log·standalone/manual CLI는 이 단계의 보장 대상이 아닙니다.

`requiredProducerCoverage`는 `complete|partial` closed enum입니다. L1c에서 `complete`를 주장할 수 있는 경로는 실제 SharedJob authority terminal 뒤에 observer가 끝까지 연결되고, 모든 stage가 닫히며, drop/issue/recovery gap이 없는 감사된 `index/index_build`와 `rss/rss_collect`뿐입니다. 상세 projection도 현재 authority가 `matched`일 때만 `diagnosticQuality=complete`로 보이며, 현재 authority가 changed/unavailable이거나 그 밖의 모든 경로는 `partial`입니다.

## Headless run list v1

`GET /api/diagnostics/runs`는 기존 Work Log와 합쳐 표시할 수 있는 privacy-safe 실행
요약만 반환합니다. query는 `version=1`, `limit`(기본20, 최대100), `cursor`, `feature`,
`outcome`, `fallback`, `from`, `to`만 허용하며 각각 중복·미지 파라미터를 거부합니다.
`feature`는 feature code enum, `outcome`은 `all|succeeded|failed|cancelled|running|unknown`,
`fallback`은 `all|observed`입니다. `from`/`to`는 Z UTC timestamp의 반열린
`[from,to)` 구간입니다.

요약은 `runId`, `createdAt`, `finishedAt`, 관측 상태/결과, feature/route/task,
authority state/status, adapter/engine/fallback code, failure stage/reason,
`diagnosticQuality`, 그리고 현재 보이는 Work Log job일 때만 기존 `workLogId`를 포함합니다.
본문·메시지·prompt·예외 문자열·경로·private result는 목록에 들어가지 않습니다.
`outcome=failed`는 현재 권위와 일치하는 failed family만 뜻합니다. direct 또는 changed/
unavailable 관측의 실패는 `observedOutcome=failed`로 남지만 확정 실패가 아니며,
`outcome=unknown`은 확정 권위가 없는 관측도 포함합니다. fallback이 관측되지 않은
경우 `fallbackObserved`는 `null`이며 부정 증거로 해석하지 않습니다.

목록은 diagnostics writer lease/quota/recovery cache를 건드리지 않는 250ms cooperative
bounded scan을 사용합니다. 최대 4096개의 검증된 header와 5000 filesystem entries를
넘지 않으며, cold scan이 끝나지 않으면 `truncated=true`와 `scan.complete=false`를
반환하고 다음 새 요청에서 스캔을 이어갑니다. corrupt header는 빈 성공으로 숨기지 않고
code-only `errors`로 표시합니다. authority/control 저장소 손상·private lifecycle 차단·
reparse/읽기 장애는 503입니다.

`nextCursor`는 서버 메모리의 immutable snapshot/index를 가리키는 랜덤 opaque token입니다.
cursor 요청은 query shape와 현재 job/Work Log visibility revision을 다시 확인하며,
만료·재시작·query mismatch·hidden/pruned job 변화는 409입니다. 새 diagnostics run은
이미 발급한 snapshot의 순서나 page를 바꾸지 않습니다. Work Log clear/migration 범위는
확장하지 않고, 진단 자체 삭제·숨기기·export/retention은 이 버전의 책임이 아닙니다.

`snapshotAt`은 같은 페이지 묶음이 공유하는 UTC 조회 기준 시각입니다. cursor의 결과는
그 시점의 관측/권위 projection이며, 현재 상태를 매 페이지 새로 계산한 결과가 아닙니다.
프로세스당 snapshot은 최대8개/5분, cursor token은 최대4096개로 제한합니다. 반복해서
같은 페이지를 읽어도 token이 계속 늘어나지 않습니다. `scan.complete=true`여도 `errors`가
있으면 읽지 못한 기록이 있는 부분 목록이므로 오류를 함께 표시해야 합니다.

권위 파일은 파일당2MiB, 자동화 기록은 최대200행 안에서 엄격히 읽습니다. 손상/누락된
main을 이전 backup으로 대체해 현재 상태라고 표시하지 않고 503을 반환합니다. 조회는
복원·migration·삭제를 수행하지 않습니다. job/control snapshot은 scan 뒤에 읽고,
자동화는 잠금 역전을 피하도록 별도로 읽습니다. 숨기기와 겹친 요청의 기준점은
job/control snapshot 읽기이며 HTTP 전송 완료까지 잠근다는 보장은 하지 않습니다.

## 기존 화면의 목록 조회

Work Log의 접힌 진단 조회에서 모든 실행 또는 실패/대체/기간 조건으로 공통 목록을
조회합니다. 기존 작업 기록과 진단 목록은 동시에 중복 표시하지 않으며, 연결된 Work Log
항목은 원래 작업 기록으로 돌아가 기존 결과/승인 동작을 확인합니다. 진단 행 상세는
선택한 `runId`로 조회합니다. 조건 변경은 이전 응답을 무효화하고, 같은 조건의 전체
새로고침은 열린 상세와 기존 snapshot 표시를 유지합니다. 기간의 UTC 시작 경계는
같은 페이지 묶음 안에서 고정하며 새로운 조회에서 다시 계산합니다.

빈 검사 진행 상태에도 계속 확인 경로를 제공하고, 일부 기록을 읽지 못한 결과를
확정적인 빈 목록으로 표시하지 않습니다. 현재 권위가 확인되지 않은 결과는 관측과
미확정을 함께 표시합니다. 이 화면 연결은 진단 자체 삭제/내보내기 권한을 추가하지 않습니다.

## 선택 실행 내보내기와 보존 관리

개발 상태(2026-09-08): 아래 D4 경로는 구현·로컬 수용을 완료했습니다. 내보내기·보존 안전성과
격리 HTTP 통합, desktop/mobile × Light/Dark 화면·접근성을 검증했습니다.
운영 서버 재시작·실제 진단 삭제·자동 삭제 설정 활성화는 수행하지 않았습니다.

내보내기는 선택한 실행과 선택적으로 직접 부모·자식만 대상으로 합니다. 미리보기에서
허용된 진단 JSON과 읽을 수 있는 요약을 먼저 확인하고 로컬 파일로 다운로드합니다.
전체 자료 폴더를 묶거나 외부 서비스로 전송하지 않습니다. 최대 20개 실행·1MiB로 제한하며,
기존 schema/source 검증을 다시 거쳐 임의 필드·본문·원문 예외·비밀값을 포함하지 않습니다.
`POST /api/diagnostics/runs/{runId}/export/preview`는 미리보기를,
`POST /api/diagnostics/runs/{runId}/export/download`는 확인한 token에 해당하는 파일을 제공합니다.

설정의 진단 보존 관리는 `GET /api/diagnostics/retention`으로 사용량·상한·현재 설정을
읽습니다. 자동 삭제 기본값은 off이며 보존 기간은 7/30/90/180/365일(기본30일) 중 선택합니다.
기간을 선택하는 것만으로 삭제되지 않습니다. `/retention/preview`의 대상 건수·용량·기간을
확인하고 `/retention/confirm`에 일회용 token과 `confirm:true`를 보내야 정리합니다.
설정 변경도 `/retention/settings/preview` → `/retention/settings/confirm`으로 별도 확인합니다.
화면 조회·미리보기는 원래 작업 실행이나 기록 복구를 시작하지 않습니다.

정리는 검증된 `diagnostics/runs/{runId}.json`만 대상으로 하며 현재 실행 중·권위 불명·
복구·비공개 정리 차단·변경된 기록과 symlink/reparse 경로를 제외합니다. 확인 시 대상과
현재 상태를 다시 검사하고 writer 소유권을 지킵니다. 기존 Work Log 요약, jobs/자동화 원장,
보고서·노트·포트폴리오·원천 자료는 삭제하지 않습니다. 자동 삭제는 사용자가 명시적으로
활성화한 경우에만 기존 실행 종료 흐름의 제한된 내부 정리 경로에서 동작합니다.

만료된 상세는 최소 허용 metadata만 담은 `diagnostics/expired.json`으로 식별합니다.
정확한 만료 표식이 있을 때만 `availabilityReason=expired`이며 상세 `record`는 null입니다.
파일이 없다는 이유만으로 만료를 추정하지 않습니다. 표식은 최대4096건·256KiB로 제한되므로
오래된 표식이 사라진 경우는 `missing_unknown`으로 남습니다. 작업 요약의 보존과 상세 진단의
보존은 별개이며, 기존 상세가 남아 있으면 만료 표식보다 실제 상세가 우선합니다.
