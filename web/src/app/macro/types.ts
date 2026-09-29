export type MacroPoint = {
  period: string;
  value: number | null;
  rawValue?: string | null;
  displayValue: number | null;
  displayUnit: string;
  metadata: { unit: string; frequency: string; adjustment: string };
  metadataId: string;
  availabilityBasis: "official_release" | "provider_vintage" | "local_observed";
  availableAt: string;
  releasedAt: string | null;
  vintageDate: string | null;
  fetchedAt: string;
  firstSeenAt?: string | null;
  calculationGap?: string | null;
  revised?: boolean;
};

/** 개요 한 줄의 머리 숫자. 방향(tone)은 좋고 나쁨이 아니라 늘었다·줄었다다. */
export type MacroHeadline = {
  value: number;
  previous: number | null;
  delta: number | null;
  tone: "up" | "down" | "flat";
  unit: string;
  deltaUnit: string;
  digits: number;
  measure: string;
  period: string;
  shape: "bars" | "line";
  spark: [string, number | null][];
};

export type MacroRelease = {
  date: string;
  sourceUrl: string;
  precision: "date";
  basis: "provider_schedule" | "official_schedule" | "customary_estimate";
};

export type MacroItem = {
  series: {
    id: string; label: string; axis: string; stage: string; frequency: string; sourceUrl: string;
    unit: string; transform: string; methodVersion: string; adjustment: string; provider: string; code: string;
  };
  latest: MacroPoint | null;
  history: MacroPoint[];
  headline?: MacroHeadline | null;
  direction: string;
  quality: string[];
  coverage: { firstAvailableAt: string | null };
  providerStates: { status: string; last_success: string; error_code: string }[];
  latestRevisedComparison: MacroPoint[];
  revisions: MacroPoint[];
  revisionPeriod?: string | null;
  nextRelease?: MacroRelease | null;
  guide?: { heading: string; body: string }[];
};

export type MacroOverview = {
  recent: { seriesId: string; period: string; frequency: string }[];
  upcoming: { date: string; series: { seriesId: string; basis: MacroRelease["basis"] }[] }[];
  collection: { total: number; collected: number; revised: number; lastCollectedAt: string | null };
};

export type MacroSnapshot = {
  view?: "full" | "summary";
  overview?: MacroOverview | null;
  market: "US" | "KR";
  mode: "as_of" | "latest_revised";
  date: string;
  timezone: string;
  cutoff: string | null;
  axes: Record<string, string>;
  items: MacroItem[];
  notes: string[];
};

/** 거시 지도 상태는 URL hash가 소유한다. 새로고침·뒤로가기·Calendar 왕복에서 그대로 복원된다. */
export function readMacroLocation() {
  const params = new URLSearchParams(window.location.hash.split("?")[1] || "");
  const market = params.get("market") === "KR" ? "KR" : "US";
  return {
    market,
    // 한국은 과거 시점 재현을 지원하지 않으므로 URL에 as_of가 있어도 현재 수정치로 읽는다.
    mode: market === "US" && params.get("mode") === "as_of" ? "as_of" : "latest_revised",
    date: params.get("date") || "",
    series: params.get("series") || "",
    period: params.get("period") || "",
    years: params.get("years") === "50" ? "50" : "5",
  };
}

export function lastMacroView() {
  const saved = sessionStorage.getItem("folio.macro.lastView.v1")?.replace("#/market-memory/macro", "#/macro/map");
  return saved?.startsWith("#/macro/map") ? saved : "#/macro/map";
}

export function navigateMacro(patch: Partial<ReturnType<typeof readMacroLocation>>) {
  const current = { ...readMacroLocation(), ...patch };
  if ("series" in patch || "market" in patch) current.period = "";
  if (current.market === "KR") current.mode = "latest_revised";
  const params = new URLSearchParams(Object.entries(current).filter(([, value]) => Boolean(value)));
  window.location.hash = `/macro/map?${params}`;
}

// 화면에 보이는 짧은 이름. 발표 기관은 괄호에 한국어로 남긴다.
const SHORT_LABEL: Record<string, string> = {
  CPIAUCSL: "소비자물가 (CPI)",
  KR_CPI: "소비자물가 (CPI)",
  NFCI: "금융여건지수 (시카고 연준)",
  STLFSI4: "금융스트레스지수 (세인트루이스 연준)",
  KR_IP: "전산업생산",
  KR_SPREAD: "신용 스프레드 (회사채 AA−)",
};
// 요약 카드(최근 자료·다음 발표)에 쓰는 아주 짧은 이름.
const TINY_LABEL: Record<string, string> = {
  GDPC1: "GDP", INDPRO: "산업생산", UNRATE: "실업률", CPIAUCSL: "CPI", PCEPILFE: "근원 PCE", DFF: "연방기금금리",
  KR_GDP: "GDP", KR_IP: "생산", KR_UNRATE: "실업률", KR_CPI: "CPI", KR_RATE: "금통위", KR_CREDIT: "가계신용",
  NFCI: "금융여건지수", STLFSI4: "금융스트레스지수", KR_USDKRW: "원/달러", KR_SPREAD: "신용 스프레드", CFNAIMA3: "CFNAI", ICSA: "신규 실업수당 청구",
};

export function shortLabel(series: { id: string; label: string }): string {
  return SHORT_LABEL[series.id] || series.label;
}

export function tinyLabel(seriesId: string, fallback = ""): string {
  return TINY_LABEL[seriesId] || fallback || seriesId;
}

/** 관측기간을 사람이 읽는 말로. 월 "8월", 분기 "26년 2분기", 주 "9/18 주", 일 "9/24". */
export function periodLabel(period: string, frequency: string): string {
  const [year, month, day] = period.split("-").map(Number);
  if (!year || !month) return period;
  if (frequency === "Q") return `${year % 100}년 ${Math.floor((month - 1) / 3) + 1}분기`;
  if (frequency === "M") return `${month}월`;
  if (frequency === "W") return `${month}/${day} 주`;
  return `${month}/${day}`;
}

/** 차트 x축 눈금. 월 "24.10", 분기 "24.Q4", 일·주 "24.10". */
export function axisLabel(period: string, frequency: string): string {
  const [year, month] = period.split("-").map(Number);
  if (!year || !month) return period;
  const yy = String(year % 100).padStart(2, "0");
  return frequency === "Q" ? `${yy}.Q${Math.floor((month - 1) / 3) + 1}` : `${yy}.${String(month).padStart(2, "0")}`;
}

export function fixed(value: number | null | undefined, digits: number): string {
  if (value == null || !Number.isFinite(value)) return "자료 없음";
  return value.toLocaleString("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** "2026년 9월 27일" — 기준일 배지. */
export function longDate(day: string): string {
  const [year, month, date] = day.split("-").map(Number);
  return year && month && date ? `${year}년 ${month}월 ${date}일` : day;
}

/** "9/27 17:04" — 한국 시간 기준 짧은 시각. */
export function shortKst(value: string | null | undefined): string {
  if (!value) return "기록 없음";
  const parts = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(value));
  const get = (type: string) => parts.find((part) => part.type === type)?.value || "";
  return `${get("month")}/${get("day")} ${get("hour")}:${get("minute")}`;
}
