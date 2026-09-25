# React SPA Browser Smoke Test

Folio Board의 기본 프론트엔드는 React SPA다. 자동/수동 브라우저 smoke test는 빌드 산출물과 실제 서버 화면의 최소 계약을 확인한다.

## 실행 전 조건

- `npm run build`가 성공해야 한다.
- FastAPI 서버를 `start.ps1` 또는 `py -3 app.py`로 실행한다.
- 테스트 대상 URL은 기본적으로 `http://127.0.0.1:8787/`이다.

## 자동화 체크리스트

Playwright 또는 Codex browser smoke에서 다음 항목을 확인한다.

1. `/` 진입 시 `#folioReactRoot .react-shell`이 존재한다.
2. 홈 화면에는 전역 Agent Dock이 없고, 홈 입력창과 빠른 실행 버튼이 보인다.
3. `#/dashboard`, `#/briefing`, `#/rss`, `#/market-memory`, `#/analysis`, `#/deep-research`, `#/watchlist`, `#/settings`로 이동해 각 route root가 표시된다.
4. 좌측 사이드바 접기/펴기 버튼은 같은 위치와 크기를 유지한다.
5. Agent Dock이 열려 있는 route에서 닫기 버튼을 누르면 floating `AI` pill로 접힌다.
6. 브리핑/기업분석/딥리서치 저장 카드가 있으면 reader를 열고 breadcrumb, action rail, Folio Note panel, Agent proposal surface가 보이는지 확인한다.
7. 대시보드 Current Market 위젯 메뉴에서 수정/삭제 메뉴가 열리는지 확인한다. 실제 삭제는 테스트 데이터가 아닐 때 실행하지 않는다.
8. 브라우저 console에 uncaught error가 없어야 한다.
9. 1440px desktop과 390px mobile viewport에서 가로 스크롤이 없어야 한다.

## Codex Browser Smoke 예시

```text
open http://127.0.0.1:8787/
assert visible "#folioReactRoot .react-shell"
click "브리핑"
assert visible "[data-briefing-route]"
click "AI Agent 닫기"
assert visible ".react-agent-dock.is-closed"
check console errors
```

## 회귀 기준

- React route가 legacy DOM fallback 없이 자체 route root를 렌더해야 한다.
- `public/app.js`는 bridge-only 역할만 수행해야 한다.
- 보고서 본문 렌더링과 TradingView/briefing visuals wrapper는 유지되어야 한다.
