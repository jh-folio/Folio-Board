# Pixel Office

> **보류 (0.3.0)** — 이 기능은 실행되는 앱에 배선되어 있지 않습니다. `app.py`의
> `GET /api/pixel-office` 라우트와 React 라우트를 모두 제거했고, 릴리즈 패키지에서도
> 제외합니다. 아래 문서는 재개할 때를 위한 설계 기록입니다. 재개하려면 라우트 등록,
> React 배선, `scripts/package_release.py`의 제외 규칙 해제를 함께 되돌려야 합니다.

Pixel Office는 Folio Board의 기존 리서치 데이터와 Agent 작업 상태를 장면 오브젝트 단위로 요약하는 Home 기능이다. 이 폴더는 UI가 소비하는 최소 read-only 계약만 소유하며, 보고서 생성·시장 분석·포트폴리오 계산 로직을 복제하지 않는다.

## 사용자 화면

- `#/office`: 기본 Home인 Pixel Office
- `#/home`: 기존 텍스트 중심 Agent Home
- 첫 실행 시 두 Home 중 하나를 선택하고, 이후 각 Home의 전환 버튼이나 Settings > 화면에서 바꾼다.
- 두 Home은 `agentWorkspace/`의 같은 대화, 모델 선택, proposal, 최근 작업 상태를 사용한다.
- Pixel Office와 Agent Home에서는 중복되는 전역 Agent Dock을 표시하지 않는다.

데스크톱 장면은 lazy-loaded PixiJS Canvas가 `560×315` 논리 픽셀의 3/4 top-down 방, 캐릭터, 개체별 깊이 레이어를 렌더링하고 React DOM이 아래 7개 오브젝트의 접근 가능한 버튼과 상태 텍스트를 소유한다. 980px 이하에서는 같은 정보와 동작을 Agent 미니 장면, 상태 카드, 접근 가능한 하단 상세 시트로 제공한다.

방은 가구가 없는 `room-shell-modern-v2.png`와 `scene_object` 레이어로 분리한다. 모든 `scene_object`는 7개 semantic id 중 하나를 `objectId`로 가져야 한다. 하나의 논리 개체가 의자·러그·테이블처럼 서로 다른 Y-depth를 필요로 하면 같은 `objectId` 아래 여러 투명 PNG를 둘 수 있다. 시각 레이어와 클릭 버튼은 같은 scene manifest 좌표를 공유하므로 개체를 다시 그려도 API·상세 패널 계약은 바뀌지 않는다.

| 오브젝트 | 연결 화면/동작 |
|---|---|
| 뉴스 데스크 | RSS Feed |
| 시장 상황판 | Market Memory |
| 리서치 책상 | Deep Research 저장 자료 |
| 보고서 서가 | 저장 보고서 링크 |
| 메모 보드 | Native Investment Notes 요약 |
| 포트폴리오 모니터 | 보유·관심 항목의 redacted 요약 |
| Agent 자리 | Agent Home과 공유하는 대화·작업 패널 |

## API

```text
GET /api/pixel-office
```

응답은 버전, 생성 시각, 고정된 7개 오브젝트 상태, redacted Agent 요약으로 구성된다. 오브젝트 상태는 `loading`, `ready`, `busy`, `attention`, `empty`, `stale`, `unavailable`, `error` enum만 허용한다.

고정 오브젝트:

```text
news_desk
market_board
research_desk
report_shelf
memo_board
portfolio_monitor
agent_seat
```

## 개인정보와 오류 경계

- 작업의 `traceback`, `error`, `result`, label 같은 raw 필드는 반환하지 않는다.
- 투자 노트 본문·요약, 포트폴리오 position 상세, watchlist 항목 원문은 반환하지 않는다.
- 한 소스의 예외는 해당 오브젝트의 일반화된 `error` 상태로 격리한다. 예외 메시지나 로컬 경로를 응답에 넣지 않는다.
- Canonical 보고서와 Personal Overlay를 수정하지 않는다.

## Agent 캐릭터와 상태

0.3.0은 프로젝트 전용 원본 이미지인 `Classic Analyst`와 `Economics Student` 두 preset만 제공한다. 설정은 브라우저의 버전된 UI preference에 저장하고, 이미지 로딩 실패 시 텍스트를 유지하는 CSS 실루엣으로 대체한다.

Classic Pixi 캐릭터는 sprite-gen 공식 출력인 `sprite-sheet-alpha.png`와 `manifest.json`을 함께 사용한다. 런타임은 고정 grid를 추정하지 않고 `manifest.json.frame_layout`의 `down/side/up × idle/walk` 좌표와 `durations_ms`를 검증한 뒤 그대로 재생한다. 서쪽 이동은 오른쪽 옆모습 행을 발 기준점에서 반전한다. `neutral-front-v3.png`는 아틀라스 초기화 전/실패 경계의 정적 identity asset으로 유지한다.

활동 상태는 최근 job에서 결정한다. 실패/승인 대기 → 실행 중 → 대기열 → 최근 완료 → ambient 순서이며, 알려진 RSS·분석·보고서 작업은 대응하는 오브젝트까지 authored waypoint를 따라 실제로 이동한다. 경로 상태는 `idle → route_pending → walking → arriving → working|waiting|complete|error`로 제한한다. 알 수 없는 작업은 일반 작업으로 표시하고, 취소된 작업은 실행 중으로 남기지 않는다. 탭이 숨겨지면 Pixi ticker를 멈춘다. 움직임 줄이기에서는 걷기 행 대신 방향별 idle 행을 표시하고 이동 시간을 단축한다.

완료·실패·승인 대기는 12시간 범위의 in-app attention으로 표시한다. 사용자가 확인한 항목 id만 브라우저에 저장하므로 서버 재시작 후 같은 알림이 반복되지 않는다. 알림에는 raw 오류, traceback, 결과 본문을 넣지 않는다.

## 접근성과 fallback

- 모든 오브젝트는 상태가 포함된 이름을 가진 `<button>`이다.
- 상세 패널/시트는 dialog, Escape 닫기, focus trap, 원래 버튼 focus 복귀를 지원한다.
- 모바일 카드에는 데스크톱과 같은 7개 진입 동작이 있다.
- API 전체 실패 시 registry 기반 일반화 상태를 유지하고 새로고침 동작을 제공한다.
- Canvas/asset 초기화 실패나 React 렌더 오류 시 기존 CSS 장면으로 복귀하며 오브젝트 동작을 잃지 않는다.
- 캐릭터는 장식이 아니라 현재 Agent 상태를 읽는 접근 가능한 이미지 이름을 제공한다.
- 200% 확대 등가 폭과 390px 화면에서 문서 가로 스크롤을 만들지 않는다.

## 0.3.0 범위 밖

다크 테마, My Desk 개인 배치, 포트폴리오/워치리스트 전용 가구, 확장 온보딩은 0.3.0에 포함하지 않는다. 구현되지 않은 캐릭터 preset이나 테마 옵션을 설정에 선노출하지 않는다.

## 구현 파일

```text
schema.py   # object id/state enum과 strict payload validator
service.py  # 기존 feature service를 호출하는 요약·freshness·redaction 계층
tests/      # clean workspace, partial failure, enum, redaction 계약
../../web/src/app/pixelOffice/  # scene, registry, panels, character/activity/attention
../../web/src/app/pixelOffice/game/  # Pixi scene, strict scene/asset/animation manifests, route/movement, DOM overlay, fallback
../../public/pixel-office/scenes/classic/  # 560×315 empty room shell, semantic object layers, public manifests
../../public/pixel-office/characters/classic/  # Classic static identity, official alpha atlas, frame-layout manifest
```

## 씬 배치 (0.3.0 재개)

방과 가구는 이미지 한 장이 아니라 **빈 건축 셸 + 오브젝트별 전체 캔버스 레이어**다.
`room-shell-modern-v2.png`가 바닥·창·벽만 담고, 가구는 `object-*-v2.png` 13장이 각자
`objectId`와 깊이를 들고 같은 560×315 좌표계 위에 놓인다.

- **깊이는 발 위치에서 파생한다**: `depth = 알파 bbox 하단 y × 100`. 화면 아래에 있는 것이
  나중에 그려지므로 빼놓은 의자는 항상 자기 책상 앞에 온다. 이 규칙을 손으로 매기던 이전
  배치에서는 순서가 뒤집혀 의자가 책상에 먹혔다. 러그만 바닥 장식이라 고정 깊이(200)를 쓴다.
- **정차 지점은 가구 앞이어야 한다**: 씬 검증기가 모든 경로 간선이 `collisionBounds`를
  통과하지 않는지 확인한다. 좌표를 손으로 고르면 이 조건을 맞추기 어려워서, 배치를 바꿀 때는
  가구 박스 위에서 정차 지점과 허브를 함께 푸는 방식이 안전하다.
- **겹침 0을 목표로 삼지 않는다**: 알파 겹침을 0으로 만들려던 이전 시도(v4)는 검사에는
  통과했지만 뉴스 워크스테이션을 공간적으로 말이 안 되는 위치로 밀어냈다. 의자가 읽히는지,
  중앙 통로가 열려 있는지는 사람이 판단한다.

배치를 바꾸면 `assets.json`과 `web/src/app/pixelOffice/game/assetManifest.ts`,
`scene.json`과 `classicScene.ts`를 함께 갱신해야 한다. TypeScript 사본은 마운트 전에
검증하는 용도라 JSON과 어긋나면 안 된다.
