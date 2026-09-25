# 서버 재시작

> 이 기능을 변경·검토할 때 해당 기능 README와 함께 읽는다. 다른 기능의 상세 문서를 일괄 로드하지 않는다.
> 공통 규칙과 § 번호는 [AGENTS.md](../../AGENTS.md)를 참조한다. 코드 경로 표기는 저장소 루트 기준이다.

### 서버 재시작

- 웹 UI 상단의 `서버 재시작` 버튼은 `POST /api/server/restart`를 호출한다.
- `schedule_server_restart()`는 0.5초 후 `os._exit(RESTART_EXIT_CODE)`로 프로세스를 종료한다. **재시작 신호는 7이다.**
- **3을 쓰지 않는다.** `uvicorn.config.STARTUP_FAILURE`가 3이라, 포트 충돌을 비롯한 모든 uvicorn 시작 실패가 같은 코드로 끝난다. 예전에는 런처가 그것을 재시작 신호로 읽어 무한히 다시 띄웠다 — 시작 → 바인드 실패 → `Restarting...` → 시작 → … (실측: 서버가 이미 떠 있을 때 `py -3 app.py`가 exit 3). 사용자가 `.cmd`를 두 번 실행하면 바로 걸린다.
- `main()`은 uvicorn을 부르기 전에 포트를 직접 잡아 본다(`_port_owner_message()`). 이미 우리 서버가 떠 있으면 그 주소를 안내하고, 다른 프로그램이면 `PORT`를 바꾸라고 말한 뒤 코드 1로 끝낸다. uvicorn의 영어 소켓 오류를 그대로 보여주지 않는다.
- `start.ps1`과 `start.sh`는 종료 코드 7이면 루프를 돌며 `py -3 app.py`(또는 Python 경로)를 재실행한다. 0도 7도 아니면 `start.ps1`은 창을 붙잡아(`Read-Host`) 실패 이유가 사라지지 않게 한다.
- `start-archive.cmd`나 `start.ps1` / `start.sh`로 실행 중일 때만 재시작이 자동으로 동작한다. 터미널에서 `py -3 app.py`를 직접 실행 중이면 서버가 종료만 된다.
- `_RESTART_REQUESTED` 플래그로 동시에 여러 재시작 요청이 들어와도 한 번만 실행한다.
- 재시작 후 `load_jobs()`는 `jobs-v2.json`과 legacy `data/jobs.json` 양쪽의 `queued`/`running`/`cancel_requested` 작업을 `failed_restart`로 변환한다(좀비 잡 방지). **legacy 파일도 실제로 고쳐 쓴다** — API는 `JOBS` 캐시가 아니라 매 요청 `_store().merged()`를 다시 읽고 merged()가 legacy 행을 그대로 싣기 때문에, 캐시만 고치면 구버전에서 남은 `running` 행이 영원히 실행 중으로 보인다.
- **비공개 pack 삭제가 막혀도 기동을 멈추지 않는다.** `recover_startup()`은 실패한 잡을 `cleanup_blocked`에 남겨 잡 조회를 503으로 닫되(fail-closed), 나머지 잡 전환과 orphan 정리를 끝내고 마지막에 알린다. `load_jobs()`는 그 예외를 잡고 계속한다 — 백신이 pack을 수십 밀리초 잡았다고 앱 전체가 안 켜지는 것이 더 나쁘다.

