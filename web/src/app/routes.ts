export type RouteId =
  | "home"
  | "dashboard"
  | "briefing"
  | "rss"
  | "market-memory"
  | "macro"
  | "analysis"
  | "deep-research"
  | "watchlist"
  | "portfolio"
  | "settings";

export type AppRoute = {
  id: RouteId;
  label: string;
  group: "home" | "research" | "portfolio" | "system";
  visibleInNav?: boolean;
};

export const ROUTES: AppRoute[] = [
  { id: "home", label: "홈", group: "home" },
  { id: "dashboard", label: "대시보드", group: "home" },
  { id: "briefing", label: "브리핑", group: "research" },
  { id: "rss", label: "RSS 피드", group: "research" },
  { id: "market-memory", label: "시장 내러티브", group: "research" },
  { id: "macro", label: "시장·거시", group: "research" },
  { id: "analysis", label: "기업 분석", group: "research" },
  { id: "deep-research", label: "딥 리서치", group: "research" },
  { id: "watchlist", label: "워치리스트", group: "home" },
  { id: "portfolio", label: "포트폴리오", group: "portfolio" },
  { id: "settings", label: "설정", group: "system" },
];

export const NAV_ROUTES = ROUTES.filter((route) => route.visibleInNav !== false);

const DEFAULT_ROUTE: RouteId = "home";

export function parseHashRoute(hash: string): RouteId {
  if (hash.startsWith("#/market-memory/macro")) return "macro";
  const cleaned = hash.replace(/^#\/?/, "").split("?")[0].split("/")[0];
  return ROUTES.some((route) => route.id === cleaned) ? (cleaned as RouteId) : DEFAULT_ROUTE;
}

export function toHash(routeId: RouteId): string {
  return `#/${routeId}`;
}

export function routeById(routeId: RouteId): AppRoute {
  return ROUTES.find((route) => route.id === routeId) ?? ROUTES[0];
}
