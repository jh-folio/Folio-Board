import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { getJson, postJson, putJson } from "../api";
import { AgentCliSetup, type AgentCliSettings } from "./AgentCliSetup";
import { FolioWordmark } from "./FolioWordmark";
import { useThemePreference, type ThemePreference } from "./themePreference";

/** 첫 실행 안내.
 *
 *  Folio Board는 자료를 모으고 읽는 도구라 첫 화면이 비어 있다. 무엇을 먼저 해야 하는지
 *  모르면 빈 화면만 보고 닫는다. 그래서 **켠 뒤 바로 쓸 수 있게 되는 것 두 가지**만
 *  묻는다 — 어느 시장을 볼지, AI를 쓸지. 둘 다 나중에 설정에서 바꿀 수 있고, 전부
 *  건너뛰어도 앱은 규칙 기반으로 동작한다.
 *
 *  판정은 서버가 한다(`/api/onboarding`). 안내 파일 유무만 보면 쓰던 사람이 새 버전으로
 *  올릴 때 처음 쓰는 사람 취급을 받는다 — 그 파일은 배포 zip에 없다.
 *
 *  디자인은 이 화면에만 쓰는 언어다(2026-08-08 사용자 결정). 색면이 뒤에서 흐르고
 *  카드는 불투명하다 — 유리를 카드에 쓰면 안쪽 면과 깊이 체계가 겹쳐 둘 다 죽는다.
 *  상세는 `features/frontend_ui/README.md`의 "첫 실행 안내 화면"을 본다.
 */

type MarketScopeState = {
  readonly selected: ReadonlyArray<string>;
  readonly markets: ReadonlyArray<{ readonly id: string; readonly label: string }>;
};

type WorkspaceLocation = { readonly path: string; readonly outsideAppFolder: boolean };

type StepId = "welcome" | "theme" | "engine" | "markets" | "done";

/** 튜토리얼은 여기 없다. 선택이지 절차가 아니라서 진행 막대의 단계로 세지 않는다. */
const STEPS: ReadonlyArray<StepId> = ["welcome", "theme", "engine", "markets", "done"];

const THEME_CHOICES: ReadonlyArray<{ id: ThemePreference; label: string }> = [
  { id: "light", label: "라이트" },
  { id: "dark", label: "다크" },
  { id: "system", label: "시스템" },
];



/** 서버는 한국어 이름을 주지만 화면은 다른 곳과 같은 코드를 쓴다(`EUROPE` → `EU`). */
const MARKET_CODES: Record<string, string> = { US: "US", KR: "KR", EUROPE: "EU", JP: "JP" };

const ICONS: Record<StepId, ReactNode> = {
  welcome: <path d="M3 7.5 12 3l9 4.5-9 4.5zM3 12l9 4.5 9-4.5M3 16.5 12 21l9-4.5" />,
  theme: (
    <>
      <circle cx="12" cy="12" r="8.6" />
      <path d="M12 3.4a8.6 8.6 0 0 0 0 17.2z" fill="currentColor" stroke="none" />
    </>
  ),
  engine: (
    <>
      <path d="M12 3.5v3M12 17.5v3M5.4 5.4l2.1 2.1M16.5 16.5l2.1 2.1M3.5 12h3M17.5 12h3M5.4 18.6l2.1-2.1M16.5 7.5l2.1-2.1" />
      <circle cx="12" cy="12" r="3.2" />
    </>
  ),
  markets: (
    <>
      <circle cx="12" cy="12" r="8.6" />
      <path d="M3.4 12h17.2M12 3.4c2.5 2.6 3.8 5.5 3.8 8.6S14.5 18 12 20.6C9.5 18 8.2 15.1 8.2 12S9.5 6 12 3.4z" />
    </>
  ),
  done: <path d="M5 12.6 9.6 17 19 7.6" />,
};

const EYEBROWS: Record<StepId, string> = {
  welcome: "환영합니다",
  theme: "화면",
  engine: "선택 사항",
  markets: "수집 범위",
  done: "준비 완료",
};

function StepIcon({ step }: { step: StepId }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">{ICONS[step]}</svg>
  );
}

export function WelcomeWizard({ onFinish }: { onFinish: (startTour: boolean) => void }) {
  const theme = useThemePreference();
  const [step, setStep] = useState<StepId>("welcome");
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");

  // 단계를 넘기면 안내 문구를 지운다. 남겨두면 이전 단계의 "저장했습니다"가 다음
  // 단계 아래에 그대로 붙어, 아직 저장하지 않은 것을 저장했다고 읽힌다.
  const goto = useCallback((next: StepId) => { setNote(""); setStep(next); }, []);

  // **지금 설정에서 시작한다.** 늘 `none`으로 두면, 안내를 다시 열어 아무것도 고르지
  // 않고 다음만 눌러도 쓰던 사람의 AI가 꺼진다 — 저장이 `enabled: false`를 쓴다.
  // 실제로 그렇게 꺼진 뒤 다음 날 예약 브리핑이 규칙 기반으로 떨어진 적이 있다.
  const [engine, setEngine] = useState<"none" | "cli">("none");
  const [engineTouched, setEngineTouched] = useState(false);
  const [cli, setCli] = useState<AgentCliSettings | null>(null);

  // 완료 화면에서 둘러보기를 하겠다고 답했는가. 둘러보기 자체는 앱 전체를 돌아야 하므로
  // 이 카드가 아니라 App이 띄운다 — 카드를 덮어쓰면 정작 보여줄 화면이 가려진다.
  const [wantsTour, setWantsTour] = useState<boolean | null>(null);

  const [scope, setScope] = useState<MarketScopeState | null>(null);
  const [markets, setMarkets] = useState<string[]>([]);
  const [collecting, setCollecting] = useState(false);

  const [location, setLocation] = useState<WorkspaceLocation | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const payload = await getJson<MarketScopeState>("/api/market-scope");
        if (cancelled) return;
        setScope(payload);
        setMarkets([...payload.selected]);
      } catch {
        /* 안내를 못 띄울 이유는 아니다. 이 단계는 건너뛸 수 있다. */
      }
      try {
        const where = await getJson<WorkspaceLocation>("/api/workspace");
        if (!cancelled) setLocation(where);
      } catch {
        /* 위와 같다. */
      }
      try {
        // 지금 설정을 읽어 그 값에서 시작한다. 처음 쓰는 사람은 어차피 기본값이고,
        // 쓰던 사람이 안내를 다시 열었을 때 자기 설정이 이미 선택돼 있어야 한다.
        const current = await getJson<{ agent?: { enabled?: boolean; mode?: string } }>("/api/settings");
        if (!cancelled && current.agent?.enabled) {
          setEngine(current.agent.mode === "cli" ? "cli" : "none");
        }
      } catch {
        /* 못 읽으면 기본값에서 시작한다. 저장은 고른 적이 있을 때만 한다. */
      }
      try {
        // CLI를 고르는 순간 목록이 비어 있으면 화면이 멈춘 것처럼 보인다. 미리 읽어 둔다.
        // `refresh`는 하지 않는다 — 모델 목록까지 다시 물으면 안내가 뜨는 데만 수십 초다.
        const bridge = await getJson<AgentCliSettings>("/api/agent-bridge/settings");
        if (!cancelled) setCli(bridge);
      } catch {
        /* CLI를 못 읽어도 나머지 단계는 그대로 쓴다. */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const pickEngine = useCallback((next: "none" | "cli") => {
    setEngineTouched(true);
    setEngine(next);
  }, []);

  const finish = useCallback(async (skipped: boolean) => {
    setBusy("finish");
    try {
      await postJson("/api/onboarding/complete", { skipped });
    } catch {
      /* 기록에 실패해도 앱은 써야 한다. 다음 실행에 안내가 한 번 더 뜰 뿐이다. */
    } finally {
      setBusy("");
      // 건너뛰면 둘러보기도 안 한다. 건너뛰기는 "지금은 됐다"는 뜻이다.
      onFinish(!skipped && wantsTour === true);
    }
  }, [onFinish, wantsTour]);

  const saveEngine = async () => {
    // 고르지 않고 지나가면 아무것도 쓰지 않는다. 지나가는 것은 선택이 아니다.
    if (!engineTouched) { goto("markets"); return; }
    setBusy("engine");
    setNote("");
    try {
      await postJson("/api/settings", {
        agent: { enabled: engine !== "none", mode: "cli" },

      });
      // 성공 문구는 두지 않는다. 다음 단계로 넘어가는 것이 이미 확인이고, 문구를
      // 남기면 다음 단계 아래에 붙어 그 단계를 저장했다고 읽힌다.
      goto("markets");
    } catch (err) {
      setNote(err instanceof Error ? err.message : "저장하지 못했습니다.");
    } finally {
      setBusy("");
    }
  };

  const saveMarkets = async () => {
    if (!scope || !markets.length) { goto("done"); return; }
    setBusy("markets");
    setNote("");
    try {
      const payload = await putJson<{ newlyEnabled?: string[] }>("/api/market-scope", { selected: markets });
      setCollecting(!!payload.newlyEnabled?.length);
      goto("done");
    } catch (err) {
      setNote(err instanceof Error ? err.message : "저장하지 못했습니다.");
    } finally {
      setBusy("");
    }
  };

  const toggleMarket = (id: string) => {
    setMarkets((current) => {
      const next = current.includes(id) ? current.filter((v) => v !== id) : [...current, id];
      // 전부 끄면 남는 화면이 없다. 마지막 하나는 끄지 않는다.
      return next.length ? next : current;
    });
  };

  // `aria-modal="true"`는 뒤 화면이 없는 셈 친다고 선언하는 것이다. Tab이 뒤로
  // 빠져나가면 스크린리더가 읽지 않는 곳에 포커스가 놓여 어디 있는지 알 수 없게 된다.
  const shellRef = useRef<HTMLDivElement | null>(null);

  const focusables = () => Array.from(
    shellRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
    ) ?? [],
  );

  useEffect(() => {
    // 단계가 바뀌면 새 내용의 처음으로 포커스를 옮긴다. 그러지 않으면 이전 단계에서
    // 누른 버튼이 사라진 자리에 포커스가 남아 body로 떨어진다.
    shellRef.current?.querySelector<HTMLElement>("h1")?.focus();
  }, [step]);

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      void finish(true);
      return;
    }
    if (event.key !== "Tab") return;
    const items = focusables();
    if (!items.length) return;
    const [first, last] = [items[0], items[items.length - 1]];
    const active = document.activeElement;
    // 단계 제목 h1은 `tabIndex={-1}`이라 focusables()에 들어오지 않는다. 카드가
    // 열린 직후와 단계 전환 직후에는 포커스가 바로 거기 있고, 그 앞에는 포커스
    // 가능한 요소가 하나도 없다 — 이 상태를 첫 요소로 쳐 주지 않으면 Shift+Tab이
    // `aria-modal="true"`를 선언한 카드 밖으로 빠져나간다.
    const title = shellRef.current?.querySelector<HTMLElement>("h1") ?? null;
    if (event.shiftKey && (active === first || active === title || !shellRef.current?.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const index = STEPS.indexOf(step);

  return (
    <div
      className="welcome-shell"
      role="dialog"
      aria-modal="true"
      aria-labelledby="welcomeTitle"
      ref={shellRef}
      onKeyDown={onKeyDown}
    >
      {/* 배경은 뒤에 떠 있는 앱을 블러 처리한 것이다(CSS `backdrop-filter`). 별도
          레이어를 두지 않는다 — 앱이 비쳐야 "건너뛰면 바로 이거"가 눈에 보인다. */}
      <div className="welcome-card">
        <header className="welcome-head">
          <FolioWordmark />
          <p className="welcome-count">단계 <b>{index + 1}</b> / {STEPS.length}</p>
        </header>

        <div
          className="welcome-rule"
          role="progressbar"
          aria-label="진행 단계"
          aria-valuemin={1}
          aria-valuemax={STEPS.length}
          aria-valuenow={index + 1}
          style={{ ["--welcome-fill" as string]: `${((index + 1) / STEPS.length) * 100}%` }}
        />

        <section className="welcome-body">
          {/* 튜토리얼은 자기 장 표시를 갖는다. 단계 eyebrow까지 남기면 `준비 완료` 위에
              `1 / 3`이 겹쳐 붙어 무엇을 세는 숫자인지 알 수 없다. */}
          <p className="welcome-eyebrow"><StepIcon step={step} />{EYEBROWS[step]}</p>

          {step === "welcome" && (
            <>
              <h1 id="welcomeTitle" tabIndex={-1}>내 PC 안의 투자 리서치 작업실</h1>
              <p>
                뉴스·공시·리포트를 이 컴퓨터에 모아 읽고, 매일 브리핑과 기업 분석을 만듭니다.{" "}
                <strong>자료와 보고서는 전부 이 컴퓨터에만 저장됩니다.</strong>
              </p>
              <p className="welcome-muted">
                몇 가지만 정하면 바로 쓸 수 있습니다. 전부 나중에 설정에서 바꿀 수 있고, 건너뛰어도
                앱은 그대로 동작합니다.
              </p>
            </>
          )}

          {step === "theme" && (
            <>
              <h1 id="welcomeTitle" tabIndex={-1}>어떤 화면으로 보시겠어요?</h1>
              <p>
                고르는 즉시 바뀝니다. <strong>시스템</strong>을 고르면 이 컴퓨터의 밝게·어둡게 설정을
                따라갑니다.
              </p>
              <div className="welcome-choices" role="group" aria-label="화면 테마">
                {THEME_CHOICES.map((choice) => (
                  <button
                    type="button"
                    key={choice.id}
                    aria-pressed={theme.preference === choice.id}
                    onClick={() => theme.setPreference(choice.id)}
                  >
                    {choice.label}
                  </button>
                ))}
              </div>
              <p className="welcome-muted">
                이 설정은 이 브라우저에만 저장됩니다. 상단바의 테마 버튼으로 언제든 바꿀 수 있습니다.
              </p>
            </>
          )}

          {step === "engine" && (
            <>
              <h1 id="welcomeTitle" tabIndex={-1}>AI를 쓰시겠어요?</h1>
              <p>
                브리핑·기업 분석·테마 분석의 문장을 AI가 씁니다.{" "}
                <strong>AI가 없어도 앱은 그대로 동작합니다</strong> — 자료 수집·검색·차트는 모두
                규칙으로 만들고, 보고서도 규칙 기반으로 나옵니다.
              </p>
              {/* 순서는 부담이 적은 것부터다. 라벨은 짧게 두고 설명이 무게를 진다 —
                  CLI의 설치·인증 의미를 설명한다. */}
              <div className="welcome-choices" role="group" aria-label="생성 방식">
                <button type="button" aria-pressed={engine === "none"} onClick={() => pickEngine("none")}>AI 없이</button>
                <button type="button" aria-pressed={engine === "cli"} onClick={() => pickEngine("cli")}>CLI</button>
              </div>

              {engine === "none" && (
                <p className="welcome-muted">
                  규칙으로 보고서를 만듭니다. 자료 수집·검색·차트는 그대로 동작합니다. 나중에 설정에서
                  언제든 켤 수 있습니다.
                </p>
              )}

              {engine === "cli" && (
                <>
                  <p className="welcome-muted">
                    <b>내 컴퓨터에 설치해서 쓰는 AI 프로그램</b>입니다(Codex·Claude Code·Antigravity).
                    이용 조건과 사용 한도는 연결한 CLI 계정을 따릅니다. 아래에서 바로
                    설치하고 로그인할 수 있습니다.
                  </p>
                  <AgentCliSetup
                    adapters={cli?.adapters ?? []}
                    onSettings={setCli}
                    disabled={!!busy}
                  />
                </>
              )}
            </>
          )}

          {step === "markets" && (
            <>
              <h1 id="welcomeTitle" tabIndex={-1}>어느 시장을 보시겠어요?</h1>
              <p>
                여기서 끈 시장은 자료 수집이 멈추고 화면 전체에서 숨습니다. 유가·달러 같은 글로벌
                자료는 항상 보입니다.
              </p>
              <p className="welcome-muted">
                US 뉴욕·나스닥 · KR 코스피·코스닥 · EU 런던·프랑크푸르트 · JP 도쿄
              </p>
              {scope ? (
                <div className="welcome-markets" role="group" aria-label="수집·표시할 시장">
                  {scope.markets.map((market) => {
                    const code = MARKET_CODES[market.id] ?? market.id;
                    return (
                      <button
                        type="button"
                        key={market.id}
                        data-code={code}
                        aria-label={`${code} ${market.label}`}
                        aria-pressed={markets.includes(market.id)}
                        onClick={() => toggleMarket(market.id)}
                      >
                        {code}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <p className="welcome-muted">관심 시장 설정을 읽지 못했습니다. 설정 탭에서 정할 수 있습니다.</p>
              )}
              <p className="welcome-muted">
                저장하면 고른 시장의 뉴스를 바로 모으기 시작합니다. 몇 분 걸리고, 그동안에도 다른
                화면을 쓸 수 있습니다.
              </p>
            </>
          )}

          {step === "done" && (
            <>
              <h1 id="welcomeTitle" tabIndex={-1}>이제 시작할 수 있습니다</h1>
              {collecting && <p>뉴스를 모으고 있습니다. 상단 진행 표시에서 상태를 볼 수 있습니다.</p>}
              {/* 각 항목은 아이템 하나여야 한다. `<strong>`과 뒤 문장을 형제로 두면 둘 다
                  grid 아이템이 되어 번호·굵은 글씨·문장이 세 칸으로 흩어진다. */}
              <ol className="welcome-next">
                <li><span><strong>워치리스트</strong>에 관심 종목을 넣으면 그 종목 뉴스가 모입니다.</span></li>
                <li><span><strong>브리핑</strong>에서 오늘의 시장을 정리합니다. 자료가 쌓일수록 좋아집니다.</span></li>
                <li><span><strong>기업 분석</strong>에 티커를 넣으면 공시와 숫자로 보고서를 만듭니다.</span></li>
              </ol>
              {location && (
                <>
                  <p className="welcome-path"><b>자료 저장 위치</b> · {location.path}</p>
                  {!location.outsideAppFolder && (
                    <p className="welcome-muted">
                      새 버전은 새 폴더로 풀립니다. 설정 &gt; 자료 위치에서 옮겨두면 업데이트할 때
                      그대로 이어집니다.
                    </p>
                  )}
                </>
              )}
              <div className="welcome-ask">
                <p className="welcome-ask-q">둘러보기를 진행할까요?</p>
                <p className="welcome-muted">
                  RSS 피드 · 시장 내러티브 · 브리핑을 차례로 열어, 자료가 어떻게 결과물이 되는지
                  실제 화면에서 보여드립니다. 30초면 끝나고 언제든 멈출 수 있습니다.
                </p>
                <div className="welcome-choices" role="group" aria-label="둘러보기">
                  <button type="button" aria-pressed={wantsTour === true} onClick={() => setWantsTour(true)}>
                    둘러보기
                  </button>
                  <button type="button" aria-pressed={wantsTour === false} onClick={() => setWantsTour(false)}>
                    바로 시작
                  </button>
                </div>
              </div>
            </>
          )}

          {note && <p className="react-dashboard-warning" role="status">{note}</p>}
        </section>

        <footer className="welcome-actions">
          <button className="welcome-skip" type="button" onClick={() => void finish(step !== "done")} disabled={!!busy}>
            {step === "done" ? "닫기" : "건너뛰기"}
          </button>
          <div className="welcome-acts">
            {index > 0 && step !== "done" && (
              <button className="welcome-btn" type="button" onClick={() => goto(STEPS[index - 1])} disabled={!!busy}>
                이전
              </button>
            )}
            {step === "welcome" && (
              <button className="welcome-btn welcome-btn--go" type="button" onClick={() => goto("theme")}>다음</button>
            )}
            {step === "theme" && (
              <button className="welcome-btn welcome-btn--go" type="button" onClick={() => goto("engine")}>다음</button>
            )}
            {step === "engine" && (
              <button className="welcome-btn welcome-btn--go" type="button" onClick={() => void saveEngine()} disabled={!!busy}>
                {busy === "engine" ? "저장 중" : "저장하고 다음"}
              </button>
            )}
            {step === "markets" && (
              <button className="welcome-btn welcome-btn--go" type="button" onClick={() => void saveMarkets()} disabled={!!busy}>
                {busy === "markets" ? "저장 중" : "저장하고 시작"}
              </button>
            )}
            {step === "done" && (
              <button className="welcome-btn welcome-btn--go" type="button" onClick={() => void finish(false)} disabled={!!busy}>
                {wantsTour ? "둘러보기 시작" : "시작하기"}
              </button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}
