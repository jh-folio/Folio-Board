import { useEffect, useRef, useState } from "react";
// React 19가 전역 JSX 네임스페이스를 없애 React.JSX로 옮겼다.
import type { JSX } from "react";
import { getJson, postJson } from "../api";
import { AgentHome } from "./AgentHome";
import { BriefingRoute } from "./BriefingRoute";
import { CommandPalette } from "./CommandPalette";
import { CompanyAnalysisRoute } from "./CompanyAnalysisRoute";
import { Dashboard } from "./Dashboard";
import { DeepResearchRoute } from "./DeepResearchRoute";
import { MarketMemoryRoute } from "./MarketMemoryRoute";
import { PortfolioRoute } from "./PortfolioRoute";
import { ReactAgentDock } from "./ReactAgentDock";
import { RssRoute } from "./RssRoute";
import { SettingsRoute } from "./SettingsRoute";
import { WatchlistRoute } from "./WatchlistRoute";
import { preferredHomeRoute, useUiPreferences } from "./homePreference";
import { NAV_ROUTES, parseHashRoute, routeById, ROUTES, toHash, type RouteId } from "./routes";
import { activateReactAgentContextScope } from "./agentContext";
import { FolioWordmark } from "./FolioWordmark";
import { useThemePreference, type ThemePreference } from "./themePreference";

/** 상단바 테마 전환 — 라이트 → 다크 → 시스템 순서로 한 칸씩 돈다.
 *
 *  설정에 있는 세 버튼과 같은 값을 쓴다(`window.FolioTheme`가 한 저장소를 갖는다).
 *  여기 둔 이유는 테마가 하루에도 여러 번 바뀌는 설정인데 지금은 설정 화면을 열고
 *  두 번 더 눌러야 닿기 때문이다. 아이콘 하나로 두되, 무엇이 켜져 있고 누르면
 *  무엇이 되는지는 접근성 이름이 말한다 — 아이콘만으로는 시스템 모드를 구분할 수 없다.
 */
const THEME_CYCLE: ThemePreference[] = ["light", "dark", "system"];
const THEME_LABELS: Record<ThemePreference, string> = {
  light: "라이트",
  dark: "다크",
  system: "시스템",
};

function ThemeIcon({ preference }: { preference: ThemePreference }) {
  if (preference === "light") {
    return (
      <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <circle cx="8" cy="8" r="3.1" stroke="currentColor" strokeWidth="1.4" />
        <path
          d="M8 1.4v1.6M8 13v1.6M14.6 8H13M3 8H1.4M12.66 3.34l-1.13 1.13M4.47 11.53l-1.13 1.13M12.66 12.66l-1.13-1.13M4.47 4.47 3.34 3.34"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (preference === "dark") {
    return (
      <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <path
          d="M13.2 9.6A5.6 5.6 0 0 1 6.4 2.8a5.6 5.6 0 1 0 6.8 6.8Z"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="1.8" y="2.6" width="12.4" height="8.6" rx="1.4" stroke="currentColor" strokeWidth="1.4" />
      <path d="M5.6 13.9h4.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function ThemeToggle() {
  const theme = useThemePreference();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const current = theme.preference === "system"
    ? `시스템 (${THEME_LABELS[theme.resolved]})`
    : THEME_LABELS[theme.preference];

  // 열려 있는 동안 바깥을 누르거나 Escape를 누르면 닫는다. 닫을 때 포커스를
  // 트리거로 되돌려야 키보드 사용자가 상단바로 돌아온다.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const index = Math.max(0, THEME_CYCLE.indexOf(theme.preference));
    itemRefs.current[index]?.focus();
  }, [open, theme.preference]);

  const moveFocus = (from: number, delta: number) => {
    const next = (from + delta + THEME_CYCLE.length) % THEME_CYCLE.length;
    itemRefs.current[next]?.focus();
  };

  return (
    <div className="theme-menu" ref={wrapRef}>
      <button
        className="btn btn--icon"
        type="button"
        ref={triggerRef}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`화면 테마: ${current}`}
        // 툴팁은 기본이 위쪽인데 상단바에서는 화면 밖으로 나가 잘린다.
        data-tooltip={open ? "" : `테마: ${current}`}
        data-tooltip-pos="bottom"
        onClick={() => setOpen((value) => !value)}
      >
        <ThemeIcon preference={theme.preference} />
      </button>
      {open && (
        <div className="theme-menu-list" role="menu" aria-label="화면 테마">
          {THEME_CYCLE.map((value, index) => (
            <button
              key={value}
              type="button"
              role="menuitemradio"
              aria-checked={theme.preference === value}
              ref={(node) => { itemRefs.current[index] = node; }}
              onClick={() => {
                theme.setPreference(value);
                setOpen(false);
                triggerRef.current?.focus();
              }}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown") { event.preventDefault(); moveFocus(index, 1); }
                if (event.key === "ArrowUp") { event.preventDefault(); moveFocus(index, -1); }
              }}
            >
              <ThemeIcon preference={value} />
              {THEME_LABELS[value]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

type AgentAdapterRow = { id: string; label?: string; available?: boolean; installed?: boolean; bridgeSupported?: boolean };
type AgentBridgeSettings = { provider?: string; adapters?: AgentAdapterRow[] };

const AGENT_PROVIDERS = ["codex", "claude", "antigravity"] as const;

function adapterState(row: AgentAdapterRow | undefined) {
  if (!row) return "확인 중";
  if (row.bridgeSupported === false) return "지원 안 됨";
  if (!row.installed) return "미설치";
  return row.available ? "사용 가능" : "로그인 필요";
}

/** 전역 Agent CLI. 예약 브리핑·기업분석처럼 도크 밖에서 도는 작업이 이 값을 쓴다.
 *
 *  설정 탭에도 같은 선택이 있고 둘은 같은 값을 본다 — 여기서 바꾸면 설정 탭도 따라
 *  바뀐다. 도크의 선택은 **그 대화에만** 적용되는 다른 값이라 여기서 다루지 않는다.
 */
function AgentProviderMenu() {
  const [settings, setSettings] = useState<AgentBridgeSettings | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const payload = await getJson<AgentBridgeSettings>("/api/agent-bridge/settings");
        if (alive) setSettings(payload);
      } catch {
        if (alive) setSettings(null);
      }
    })();
    // 설정 탭에서 바꾼 값이 이 버튼에도 즉시 보여야 한다. 두 화면이 같은 값을 다르게
    // 말하면 어느 쪽이 진짜인지 알 수 없다.
    const onUpdated = (event: Event) => setSettings((event as CustomEvent).detail as AgentBridgeSettings);
    window.addEventListener("folio:agent-settings-updated", onUpdated);
    return () => { alive = false; window.removeEventListener("folio:agent-settings-updated", onUpdated); };
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: PointerEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); triggerRef.current?.focus(); }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [open]);

  const rows = AGENT_PROVIDERS.map((id) => ({
    id,
    row: settings?.adapters?.find((item) => item.id === id),
  }));
  const current = settings?.provider && AGENT_PROVIDERS.includes(settings.provider as typeof AGENT_PROVIDERS[number])
    ? settings.provider
    : "";
  const currentLabel = rows.find((item) => item.id === current)?.row?.label || "선택 안 됨";

  async function choose(id: string) {
    setBusy(true);
    try {
      const models = Object.fromEntries((settings?.adapters || []).map((item) => [item.id, (item as { model?: string }).model || ""]));
      const payload = await postJson<AgentBridgeSettings>("/api/agent-bridge/settings", { provider: id, models });
      setSettings(payload);
      window.dispatchEvent(new CustomEvent("folio:agent-settings-updated", { detail: payload }));
    } catch {
      // 실패해도 메뉴만 닫는다. 저장 결과는 설정 탭이 자세히 말한다.
    } finally {
      setBusy(false);
      setOpen(false);
      triggerRef.current?.focus();
    }
  }

  return (
    <div className="theme-menu" ref={wrapRef}>
      <button
        className="btn btn--icon"
        type="button"
        ref={triggerRef}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Agent CLI: ${currentLabel}`}
        data-tooltip={open ? "" : `Agent CLI: ${currentLabel}`}
        data-tooltip-pos="bottom"
        onClick={() => setOpen((value) => !value)}
      >
        <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" width="16" height="16">
          <path d="M4 5.5 L6.5 8 L4 10.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M8.5 11 H12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <div className="theme-menu-list agent-provider-menu" role="menu" aria-label="Agent CLI">
          <p className="agent-provider-menu__note">
            전역 기본입니다. 예약 브리핑과 기업분석이 이 CLI로 돕니다.
          </p>
          {rows.map(({ id, row }) => (
            <button
              key={id}
              type="button"
              role="menuitemradio"
              aria-checked={current === id}
              disabled={busy || row?.bridgeSupported === false}
              onClick={() => void choose(id)}
            >
              <span>{row?.label || id}</span>
              <small>{adapterState(row)}</small>
            </button>
          ))}
          <p className="agent-provider-menu__note">
            도크에서 고르는 CLI는 그 대화에만 적용되며 이 값을 바꾸지 않습니다.
          </p>
        </div>
      )}
    </div>
  );
}

// 아침에 앱을 여는 순서를 따른다 — 시장 흐름(홈·대시보드)을 보고, 읽고(뉴스),
// 그게 내 것에 무슨 의미인지 보고(투자), 필요하면 파고든다(리서치).
// 설정은 제목 없이 맨 아래다. 항목 하나를 위해 제목 한 줄을 쓰지 않는다.
const NAV_GROUPS: Array<{ id: string; title: string; routes: RouteId[] }> = [
  { id: "home", title: "홈", routes: ["home", "dashboard"] },
  { id: "news", title: "뉴스", routes: ["briefing", "market-memory", "rss"] },
  { id: "portfolio", title: "투자", routes: ["watchlist", "portfolio"] },
  { id: "research", title: "리서치", routes: ["analysis", "deep-research"] },
  { id: "system", title: "", routes: ["settings"] },
];

const ROUTE_ICONS: Record<RouteId, JSX.Element> = {
  home: (
    <svg className="react-left-nav-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V21h5v-6h4v6h5V9.5" />
    </svg>
  ),
  dashboard: (
    <svg className="react-left-nav-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="7" height="8" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="15" width="7" height="6" rx="1.5" />
    </svg>
  ),
  briefing: (
    // Newspaper (기존 RSS 피드가 쓰던 아이콘)
    <svg className="react-left-nav-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 5h12.5v14H5.5A1.5 1.5 0 0 1 4 17.5z" />
      <path d="M16.5 8H20v9a2 2 0 0 1-2 2h-1.5" />
      <path d="M7.5 9h6" />
      <path d="M7.5 13h6" />
      <path d="M7.5 16.5h3.5" />
    </svg>
  ),
  rss: (
    // Material Icons — dynamic_feed
    <svg className="react-left-nav-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path fill="currentColor" stroke="none" d="M8 8H6v7c0 1.1.9 2 2 2h9v-2H8V8z" />
      <path
        fill="currentColor"
        stroke="none"
        d="M20 3h-8c-1.1 0-2 .9-2 2v6c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 8h-8V7h8v4z"
      />
      <path fill="currentColor" stroke="none" d="M4 12H2v7c0 1.1.9 2 2 2h9v-2H4v-7z" />
    </svg>
  ),
  "market-memory": (
    <svg className="react-left-nav-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M22 12h-4l-3 8-6-16-3 8H2" />
    </svg>
  ),
  analysis: (
    // Report (outline) — 문서 + 막대 그래프
    <svg className="react-left-nav-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
      <path d="M14 3v6h6" />
      <path d="M8 17v-3" />
      <path d="M12 17v-6" />
      <path d="M16 17v-4" />
    </svg>
  ),
  "deep-research": (
    // Untitled UI icons — file-search-02
    <svg className="react-left-nav-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M14 11H8m2 4H8m8-8H8m12 3.5V6.8c0-1.68 0-2.52-.327-3.162a3 3 0 0 0-1.311-1.311C17.72 2 16.88 2 15.2 2H8.8c-1.68 0-2.52 0-3.162.327a3 3 0 0 0-1.311 1.311C4 4.28 4 5.12 4 6.8v10.4c0 1.68 0 2.52.327 3.162a3 3 0 0 0 1.311 1.311C6.28 22 7.12 22 8.8 22h2.7M22 22l-1.5-1.5m1-2.5a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0" />
    </svg>
  ),
  watchlist: (
    // Untitled UI icons — bookmark-add
    <svg className="react-left-nav-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 13V7m-3 3h6m4 11V7.8c0-1.68 0-2.52-.327-3.162a3 3 0 0 0-1.311-1.311C16.72 3 15.88 3 14.2 3H9.8c-1.68 0-2.52 0-3.162.327a3 3 0 0 0-1.311 1.311C5 5.28 5 6.12 5 7.8V21l7-4z" />
    </svg>
  ),
  portfolio: (
    <svg className="react-left-nav-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M3 7.5h18v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <path d="M8 7.5V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2.5" />
      <path d="M3 12h18M10 12v2h4v-2" />
    </svg>
  ),
  settings: (
    <svg className="react-left-nav-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-.4-1.1 1.7 1.7 0 0 0-1-.6 1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.1-.4 1.7 1.7 0 0 0 .6-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06A2 2 0 1 1 7.22 3.43l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 .4 1.1 1.7 1.7 0 0 0 1 .6 1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.2.34.4.7.6 1a1.7 1.7 0 0 0 1.1.4H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.1.4c-.17.14-.31.28-.41.2Z" />
    </svg>
  ),
};

const NARROW_VIEWPORT_QUERY = "(max-width: 1024px)";

function isNarrowViewport() {
  return typeof window !== "undefined" && window.matchMedia(NARROW_VIEWPORT_QUERY).matches;
}

function currentHash() {
  // Pixel Office 보류: 코드는 남기지만 사용자가 도달할 수 있는 입구는 두지 않는다.
  // 오래된 북마크나 직접 입력으로 미완성 화면에 들어가는 일이 없어야 한다.
  const hash = window.location.hash || toHash(preferredHomeRoute());
  if (/^#\/?office(?:\/|$)/.test(hash)) {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/home`);
    return toHash("home");
  }
  return hash;
}

function useRouteState(): { hash: string; routeId: RouteId } {
  const [hash, setHash] = useState(() => currentHash());

  useEffect(() => {
    const handleHashChange = () => setHash(currentHash());
    window.addEventListener("hashchange", handleHashChange);
    handleHashChange();
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  return { hash, routeId: parseHashRoute(hash) };
}

async function waitForServerAndReload(setStatus: (value: string) => void) {
  // 재시작 신호를 보낸 직후에는 이전 프로세스가 아직 살아 있을 수 있어
  // 잠시 기다렸다가 서버가 완전히 내려간 뒤 다시 뜨는 시점을 감지한다.
  await new Promise((resolve) => window.setTimeout(resolve, 1500));
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch("/api/dashboard", { cache: "no-store" });
      if (response.ok) {
        setStatus("재시작 완료 · 새로고침 중");
        window.location.reload();
        return;
      }
    } catch {
      // 서버가 아직 내려가 있거나 재기동 중이면 계속 폴링한다.
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  // 60초 안에 살아나지 못하면 수동 새로고침을 안내한다.
  setStatus("재시작 확인 실패 · 수동 새로고침 필요");
}

export function AppShell() {
  const { hash, routeId } = useRouteState();
  const active = routeById(routeId);
  const uiPreferences = useUiPreferences();
  const preferredHome = preferredHomeRoute(uiPreferences.preferences);
  const [navCollapsed, setNavCollapsed] = useState(() => localStorage.getItem("folio.react.navCollapsed") === "1");
  // 좁은 화면에서 도크는 본문 대부분을 덮으므로, 저장된 열림 선호보다 뷰포트를 우선한다.
  const agentViewportForcedRef = useRef(false);
  const [agentOpen, setAgentOpen] = useState(() => {
    const stored = localStorage.getItem("folio.react.agentClosed");
    const preferred = stored === null ? true : stored !== "1";
    if (preferred && isNarrowViewport()) {
      agentViewportForcedRef.current = true;
      return false;
    }
    return preferred;
  });
  const [visitedRoutes, setVisitedRoutes] = useState<Set<RouteId>>(() => new Set([routeId]));
  const [routeHashes, setRouteHashes] = useState<Record<string, string>>(() => ({ [routeId]: currentHash() }));
  const [restartStatus, setRestartStatus] = useState("");
  const [restarting, setRestarting] = useState(false);
  const routeHostRef = useRef<HTMLElement | null>(null);
  const previousRouteRef = useRef<RouteId>(routeId);
  const routeFocusReadyRef = useRef(false);
  const scrollByRouteRef = useRef<Record<string, number>>({});
  const agentVisible = active.id !== "home";
  const shellAgentClass = agentVisible && agentOpen ? " is-agent-open" : " is-agent-closed";

  useEffect(() => {
    activateReactAgentContextScope(active.id, { surface: `react_${active.id}`, viewId: active.id });
  }, [active.id]);

  useEffect(() => {
    localStorage.setItem("folio.react.navCollapsed", navCollapsed ? "1" : "0");
  }, [navCollapsed]);

  useEffect(() => {
    // 뷰포트 때문에 강제로 닫은 경우에는 데스크톱 선호를 덮어쓰지 않는다.
    if (agentViewportForcedRef.current) {
      agentViewportForcedRef.current = false;
      return;
    }
    localStorage.setItem("folio.react.agentClosed", agentOpen ? "0" : "1");
  }, [agentOpen]);

  useEffect(() => {
    const query = window.matchMedia(NARROW_VIEWPORT_QUERY);
    const handleChange = (event: MediaQueryListEvent) => {
      if (!event.matches) return;
      setAgentOpen((open) => {
        if (!open) return open;
        agentViewportForcedRef.current = true;
        return false;
      });
    };
    query.addEventListener("change", handleChange);
    return () => query.removeEventListener("change", handleChange);
  }, []);

  useEffect(() => {
    setVisitedRoutes((current) => {
      if (current.has(routeId)) return current;
      const next = new Set(current);
      next.add(routeId);
      return next;
    });
  }, [routeId]);

  useEffect(() => {
    setRouteHashes((current) => (
      current[routeId] === hash ? current : { ...current, [routeId]: hash }
    ));
  }, [hash, routeId]);

  useEffect(() => {
    if (!routeFocusReadyRef.current) {
      routeFocusReadyRef.current = true;
      previousRouteRef.current = routeId;
      return;
    }
    const host = routeHostRef.current;
    const previousRoute = previousRouteRef.current;
    if (host) {
      scrollByRouteRef.current[previousRoute] = host.scrollTop;
      window.requestAnimationFrame(() => {
        host.scrollTop = scrollByRouteRef.current[routeId] || 0;
        host.focus({ preventScroll: true });
      });
    }
    previousRouteRef.current = routeId;
  }, [routeId]);

  useEffect(() => {
    const bridge = window.FolioBridge ?? {};
    const previousOpenAgentDock = bridge.openAgentDock;
    window.FolioBridge = {
      ...bridge,
      openAgentDock(context = {}) {
        setAgentOpen(true);
        window.dispatchEvent(new CustomEvent("folio:react-agent-request", { detail: context }));
      },
    };
    return () => {
      if (!window.FolioBridge) return;
      window.FolioBridge.openAgentDock = previousOpenAgentDock;
    };
  }, []);

  async function restartServer() {
    if (restarting) return;
    setRestarting(true);
    setRestartStatus("재시작 요청 중");
    try {
      await fetch("/api/server/restart", { method: "POST", body: "{}" });
    } catch {
      // 서버가 응답 전에 종료될 수 있어도 재시작 요청 자체는 정상 흐름이다.
    }
    setRestartStatus("서버 재시작 중");
    // 서버가 os._exit(3) 후 start 스크립트로 재기동될 때까지 폴링하고,
    // 다시 응답하면 최신 코드로 화면을 새로고침한다.
    // 성공 시 reload로 페이지가 다시 로드되고, 실패(타임아웃) 시에만 아래로 돌아온다.
    await waitForServerAndReload(setRestartStatus);
    setRestarting(false);
  }

  function navigateToRoute(nextRouteId: RouteId) {
    const nextHash = routeHashes[nextRouteId] || toHash(nextRouteId);
    if (window.location.hash === nextHash) return;
    window.location.hash = nextHash;
  }

  function renderRoutePane(paneRouteId: RouteId) {
    const route = routeById(paneRouteId);
    if (route.id === "home") return <AgentHome />;
    if (route.id === "dashboard") return <Dashboard />;
    if (route.id === "briefing") return <BriefingRoute />;
    if (route.id === "rss") return <RssRoute />;
    if (route.id === "market-memory") return <MarketMemoryRoute />;
    if (route.id === "analysis") return <CompanyAnalysisRoute />;
    if (route.id === "deep-research") return <DeepResearchRoute />;
    if (route.id === "watchlist") return <WatchlistRoute />;
    if (route.id === "portfolio") return <PortfolioRoute />;
    if (route.id === "settings") return <SettingsRoute />;
    return null;
  }

  return (
    <div className={`react-shell${navCollapsed ? " is-nav-collapsed" : ""}${shellAgentClass}${agentVisible ? "" : " is-agent-suppressed"}`}>
      <a
        className="react-skip-link"
        href="#folio-main-content"
        onClick={(event) => {
          event.preventDefault();
          window.requestAnimationFrame(() => routeHostRef.current?.focus({ preventScroll: true }));
        }}
      >
        본문으로 건너뛰기
      </a>
      <header className="react-shell-topbar">
        <button
          type="button"
          className="react-shell-brand"
          onClick={() => {
            navigateToRoute(preferredHome);
          }}
          aria-label="홈으로 이동"
        >
          <FolioWordmark />
          <small>Investment Workspace</small>
        </button>
        <div className="react-shell-status" aria-live="polite">
          {/* 재시작 진행만 남긴다. 예전에는 작업 상태와 job id도 여기 실렸지만
              그 저장소는 상수를 돌려주고 있어서 "준비됨" 말고는 나올 수 없었고,
              그 상수를 1초마다 다시 읽고 있었다. 비면 `span:empty`가 자리를 접는다. */}
          <span>{restartStatus}</span>
          <ThemeToggle />
          <AgentProviderMenu />
          <button className="btn btn--sm" type="button" onClick={restartServer} disabled={restarting}>
            {restarting ? "재시작 중" : "재시작"}
          </button>
        </div>
      </header>

      <aside className="react-shell-nav" aria-label="주요 화면 탐색">
        <button
          className="react-shell-nav-toggle"
          type="button"
          aria-label={navCollapsed ? "좌측 사이드바 펼치기" : "좌측 사이드바 접기"}
          aria-expanded={!navCollapsed}
          onClick={() => setNavCollapsed((value) => !value)}
        >
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M10 3.5 L5.5 8 L10 12.5" />
          </svg>
        </button>
        <nav className="react-left-nav" aria-label="Folio OS 화면">
          <div className="react-left-nav-title">Navigate</div>
          {NAV_GROUPS.map((group) => (
            <section className="react-left-nav-group" data-nav-group={group.id} key={group.id}>
              {group.title && <h3>{group.title}</h3>}
              <div className="react-left-nav-items">
                {group.routes.map((routeIdValue) => {
                  const resolvedRouteId = group.title === "Home" ? preferredHome : routeIdValue;
                  const route = NAV_ROUTES.find((item) => item.id === resolvedRouteId);
                  if (!route) return null;
                  return (
                    <span className="react-left-nav-entry" key={route.id}>
                      <button
                        type="button"
                        data-tooltip={route.label}
                        aria-label={route.label}
                        data-qa={route.id === "deep-research" ? "nav-deep-research" : undefined}
                        // 둘러보기가 이 버튼을 찾아 조명하는 앵커다. 클래스는 여럿이
                        // 공유하므로 화면 순서에 기대지 않을 이름이 필요하다.
                        data-route={route.id}
                        className="react-left-nav-item"
                        aria-current={route.id === active.id ? "page" : undefined}
                        onClick={() => {
                          navigateToRoute(route.id);
                        }}
                      >
                        <span className="react-left-nav-icon" aria-hidden="true">{ROUTE_ICONS[route.id]}</span>
                        <span className="react-left-nav-label">{route.label}</span>
                      </button>
                    </span>
                  );
                })}
              </div>
            </section>
          ))}
        </nav>
      </aside>

      <main className="react-shell-main" id="folio-main-content">
        <section className="react-route-host" data-route={active.id} ref={routeHostRef} tabIndex={-1}>
          {ROUTES.filter((route) => visitedRoutes.has(route.id)).map((route) => (
            <div
              className="react-route-pane"
              data-route-pane={route.id}
              hidden={route.id !== active.id}
              key={route.id}
            >
              {renderRoutePane(route.id)}
            </div>
          ))}
        </section>
      </main>

      {agentVisible && (
        <ReactAgentDock
          surface={`react_${active.id}`}
          open={agentOpen}
          onOpen={() => setAgentOpen(true)}
          onClose={() => setAgentOpen(false)}
        />
      )}
      <CommandPalette />
    </div>
  );
}
