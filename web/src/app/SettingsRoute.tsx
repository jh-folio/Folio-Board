import { useCallback, useEffect, useMemo, useState } from "react";
import { getJson, postJson, putJson } from "../api";
import { AgentCliSetup } from "./AgentCliSetup";
import { checkedAtLabel } from "./aiConnectionStatus";
import { setReactAgentContextScope } from "./agentContext";
import { useUiPreferences } from "./homePreference";
import { RouteHero } from "./RouteHero";
import { useThemePreference, type ThemePreference } from "./themePreference";
import { WorkLogMigrationControl } from "./WorkLogMigration";

type ProviderId = "openai" | "gemini" | "claude";
type SettingsTab = "integrations" | "admin";

const SETTINGS_TABS: ReadonlyArray<{ id: SettingsTab; label: string }> = [
  { id: "admin", label: "관리" },
  { id: "integrations", label: "연동" },
];

type ModelChoice = { value: string; label: string };

type LlmProvider = {
  label?: string;
  hasApiKey?: boolean;
  apiKeyMasked?: string;
  model?: string;
  modelChoices?: ModelChoice[];
  setupUrl?: string;
};

type SettingsPayload = {
  agent?: {
    enabled?: boolean;
    mode?: "cli" | "api";
  };
  llm?: {
    provider?: ProviderId;
    providers?: Record<string, LlmProvider>;
  };
  dart?: { hasApiKey?: boolean; apiKeyMasked?: string };
  fred?: { hasApiKey?: boolean; apiKeyMasked?: string };
  bok?: { hasApiKey?: boolean; apiKeyMasked?: string };
  notion?: { hasToken?: boolean; tokenMasked?: string; hasDb?: boolean; dbIdMasked?: string; dbId?: string };
};

type AgentAdapter = {
  id: string;
  label?: string;
  installed?: boolean;
  available?: boolean;
  authenticated?: boolean;
  bridgeSupported?: boolean;
  error?: string;
  model?: string;
  modelChoices?: ModelChoice[];
  docsUrl?: string;
  installSupported?: boolean;
  loginSupported?: boolean;
};

type AgentSettings = {
  provider?: string;
  selectedAdapter?: string;
  adapters?: AgentAdapter[];
};

type BriefingSchedule = {
  id: string;
  enabled: boolean;
  time: string;
  markets: string[];
  briefingType: string;
  // 브리핑 종류. `briefingType`(편집 강조점)과 직교하며, 없으면 일간이다.
  kind?: string;
  qualityMode?: string;
  runPrerequisites: boolean;
  days?: number[];
};

type AutomationSettings = {
  rss?: { enabled?: boolean; intervalMinutes?: number | string; saveFullText?: boolean; retentionDays?: number | string };
  marketMemory?: { enabled?: boolean; intervalMinutes?: number | string; runAfterRss?: boolean };
  briefingSchedules?: BriefingSchedule[];
  missedRuns?: { catchUpHours?: number | string };
};

type AutomationRun = {
  kind?: string;
  status?: string;
  startedAt?: string;
  finishedAt?: string;
  errorType?: string;
  errorReason?: string;
  scheduleId?: string;
};

type LlmTestResult = {
  label?: string;
  status?: string;
  available?: boolean;
  message?: string;
  /** `check_provider()`가 함께 준다. 언제 확인한 값인지 모르면 상태를 믿을 수 없다. */
  checkedAt?: string;
};


type ObsidianSettings = { vaultPath?: string };
type CacheStats = {
  stats?: Array<{ directory?: string; files?: number; total_mb?: number; stale_files?: number; stale_mb?: number; max_age_days?: number }>;
  total_mb?: number;
  stale_mb?: number;
};
type CacheCleanup = {
  deleted?: number;
  freed_mb?: number;
  details?: Array<{ path?: string; age_days?: number }>;
};

const API_PROVIDERS: ProviderId[] = ["openai", "gemini", "claude"];

const PROVIDER_LABELS: Record<ProviderId, { name: string; key: string; model: string }> = {
  openai: { name: "OpenAI", key: "sk-...", model: "gpt-5.5" },
  gemini: { name: "Gemini", key: "AIza...", model: "gemini-3.5-flash" },
  claude: { name: "Claude", key: "sk-ant-...", model: "claude-sonnet-5" },
};

function providerOrDefault(value?: string): ProviderId {
  return API_PROVIDERS.includes(value as ProviderId) ? (value as ProviderId) : "openai";
}

/** loadAll이 저장된 모델을 선택지 목록에 맞춰 정규화하는 것과 같은 규칙.
 *  dirty 판정 기준선도 같은 규칙으로 계산해야 "불러오자마자 dirty"가 되지 않는다. */
function normalizedChoice(model: string | undefined, choices: ModelChoice[] | undefined): string {
  const list = choices || [];
  return list.some((choice) => choice.value === model) ? String(model || "") : list[0]?.value || "";
}

function statusText(hasValue: boolean | undefined, masked: string | undefined, emptyText: string, label: string) {
  return hasValue ? `${label} 저장됨: ${masked || "저장됨"}` : emptyText;
}

// 어댑터 상태 문구·클래스는 `AgentCliSetup`이 소유한다. 여기 사본을 두면 같은 상태를
// 두 화면이 다르게 말하게 된다.

function ToggleSwitch({
  checked,
  onChange,
  label,
  ariaLabel,
  compact = false,
  disabled = false,
  title,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  ariaLabel?: string;
  compact?: boolean;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <label
      className={`settings-switch${compact ? " settings-switch-compact" : ""}${checked ? " is-on" : ""}${disabled ? " is-disabled" : ""}`}
      title={title}
    >
      <input
        aria-label={ariaLabel || label || "설정 전환"}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.currentTarget.checked)}
        type="checkbox"
      />
      <span className="settings-switch-track" aria-hidden="true"><span className="settings-switch-thumb" /></span>
      {label ? (
        <span className="settings-switch-copy">
          <strong>{label}</strong>
          <small>{checked ? "ON" : "OFF"}</small>
        </span>
      ) : (
        <span className="settings-switch-state" aria-hidden="true">{checked ? "ON" : "OFF"}</span>
      )}
    </label>
  );
}

function buildAutomationPayload(form: AutomationSettings): AutomationSettings {
  return {
    rss: {
      enabled: Boolean(form.rss?.enabled),
      intervalMinutes: form.rss?.intervalMinutes || 60,
      saveFullText: form.rss?.saveFullText !== false,
      retentionDays: form.rss?.retentionDays ?? DEFAULT_RETENTION_DAYS,
    },
    marketMemory: {
      enabled: Boolean(form.marketMemory?.enabled),
      intervalMinutes: form.marketMemory?.intervalMinutes || 1440,
      runAfterRss: Boolean(form.marketMemory?.runAfterRss),
    },
    briefingSchedules: (form.briefingSchedules || []).slice(0, MAX_SCHEDULES).map((row) => ({
      id: row.id,
      enabled: Boolean(row.enabled),
      time: row.time || "08:00",
      markets: [...(row.markets || [])],
      briefingType: row.briefingType || "default",
      kind: row.kind === "weekly" ? "weekly" : "daily",
      qualityMode: row.qualityMode || "diagnose_only",
      runPrerequisites: Boolean(row.runPrerequisites),
      // 요일을 고른 적 없는 예약은 키를 보내지 않는다. 서버가 `매일`로 읽어 판올림
      // 이전 동작을 지킨다 — 빈 배열을 보내면 영영 안 도는 예약이 된다.
      ...(row.days ? { days: [...row.days] } : {}),
    })),
    missedRuns: { catchUpHours: form.missedRuns?.catchUpHours ?? 3 },
  };
}

// 상한이 없으면 24개를 만들어 하루 종일 LLM을 돌릴 수 있다. 서버도 같은 값으로 자른다.
const MAX_SCHEDULES = 5;
// 서버의 WEEKDAYS와 짝. 0=월 … 6=일(`datetime.weekday()`).
const WEEKDAY_CODES: ReadonlyArray<{ id: number; label: string }> = [
  { id: 0, label: "월" }, { id: 1, label: "화" }, { id: 2, label: "수" }, { id: 3, label: "목" },
  { id: 4, label: "금" }, { id: 5, label: "토" }, { id: 6, label: "일" },
];
const WEEKDAYS_ALL = WEEKDAY_CODES.map((day) => day.id);
// 예약이 만들어졌을 때 요일을 고를 수 없었으면 매일이다. 판올림만으로 토·일 브리핑이
// 사라지는 것도 사용자가 정한 적 없는 변화라, 서버와 같은 규칙을 화면도 따른다.
function scheduleDays(row: BriefingSchedule) {
  return row.days ?? WEEKDAYS_ALL;
}
const MARKET_CODES: Array<{ id: string; label: string }> = [
  { id: "us", label: "US" },
  { id: "kr", label: "KR" },
  { id: "europe", label: "EU" },
  { id: "jp", label: "JP" },
];

// 시장 계약은 소문자(`us`)인데 `/api/market-scope`는 대문자(`US`)로 돌려준다.
// 둘 다 같은 코드를 찾도록 양쪽 키를 만든다.
const MARKET_CODE_BY_ID: Record<string, string> = Object.fromEntries(
  MARKET_CODES.flatMap((market) => [[market.id, market.label], [market.id.toUpperCase(), market.label]]),
);

// 마감 시각이 전부 다르다 — 유럽 01:30 · 미국 05~06 · 일본 15:00 · 한국 15:30 (KST).
// 사용자가 그걸 알아야 하는 화면은 만들지 않는다. 관심 시장에서 켠 것만 넣어 제안한다.
const SCHEDULE_PROPOSALS: Array<{
  label: string; time: string; markets: string[]; hint: string; kind?: string; days?: number[];
}> = [
  { label: "아침", time: "08:00", markets: ["us", "europe"], hint: "밤사이 해외장" },
  { label: "저녁", time: "18:00", markets: ["kr", "jp"], hint: "오늘 국내장" },
  // 발행 요일은 자유 선택이다. 제안만 일요일이며 사용자가 요일 칩으로 옮길 수 있다.
  {
    label: "주말", time: "09:00", markets: ["us", "kr", "europe", "jp"],
    hint: "지난주 요약과 다음주 일정", kind: "weekly", days: [6],
  },
];

// 예약이 만드는 브리핑의 종류. 화면 용어는 생성 화면(BriefingRoute)과 같아야 한다.
const AUTOMATION_BRIEFING_KINDS: Record<string, string> = {
  daily: "일간",
  weekly: "주간 요약",
};

function scheduleKind(row: BriefingSchedule) {
  return row.kind === "weekly" ? "weekly" : "daily";
}

function newScheduleId() {
  return `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

// 놓친 실행을 몇 시간까지 따라잡을지. 예전에는 `건너뛴다`/`따라잡는다` 둘뿐이었고 둘 다
// 나빴다 — 앞의 것은 10분 창이 전부라 08:15에 PC를 켜면 그날 브리핑이 없었고, 뒤의 것은
// 상한이 없어 23:50에 켜도 아침 브리핑을 만들었다.
const CATCH_UP_CHOICES: Array<{ value: string; label: string }> = [
  { value: "0", label: "정시에만" },
  { value: "1", label: "1시간 안이면" },
  { value: "3", label: "3시간 안이면" },
  { value: "6", label: "6시간 안이면" },
  { value: "24", label: "그날 안이면 언제든" },
];

// 서버의 RETENTION_CHOICES와 짝이다. 여기 없는 값을 보내면 서버가 기본값으로 되돌린다.
const DEFAULT_RETENTION_DAYS = 90;
const RETENTION_CHOICES: Array<{ value: string; label: string }> = [
  { value: "30", label: "30일" },
  { value: "60", label: "60일" },
  { value: "90", label: "90일" },
  { value: "180", label: "180일" },
  { value: "365", label: "1년" },
  { value: "0", label: "계속 보관" },
];

type RetentionPreview = {
  days: number; cutoff: string; files: number; fileBytes: number; estimatedIndexBytes: number;
  reclaimableBytes?: number;
};

/** 그 패널이 방금 한 일의 결과. 누른 버튼 바로 아래에 뜬다. */
function PanelNote({ note, panel }: { note: { panel: string; text: string; tone: "ok" | "error" } | null; panel: string }) {
  if (!note || note.panel !== panel) return null;
  return (
    <p className={note.tone === "error" ? "react-dashboard-error" : "react-dashboard-warning"} role="status">
      {note.text}
    </p>
  );
}

export function megabytes(bytes: number) {
  return `${Math.max(bytes / 1e6, 0).toFixed(bytes >= 1e8 ? 0 : 1)}MB`;
}

// 서버의 RECLAIM_THRESHOLD_BYTES와 짝이다. 이만큼 아래면 12~29초를 기다릴 값을 못 한다.
const RECLAIM_THRESHOLD_BYTES = 50e6;

/** `지금 정리` 버튼 옆 설명.
 *
 *  VACUUM은 도는 동안 검색을 멈춘다. 돌려받는 양을 먼저 말해야 누를지 정할 수 있다.
 *  임베딩을 blob으로 바꾸고 나면 지울 자료가 없어도 수백 MB가 빈 페이지로 남는다.
 */
export function reclaimHint(reclaimableBytes: number | undefined) {
  return (reclaimableBytes || 0) >= RECLAIM_THRESHOLD_BYTES
    ? `검색 색인에서 약 ${megabytes(reclaimableBytes!)}를 돌려받습니다. 그동안 검색이 잠시 멈춥니다.`
    : "정리 후 검색 색인을 다시 만들고 파일 크기를 줄입니다. 몇 분 걸릴 수 있습니다.";
}

/** 지우기 전에 무엇이 지워지는지 말한다.
 *
 *  보관 기간은 되돌릴 수 없는 설정이라, 고른 값이 지금 몇 건을 없애는지 보이지 않으면
 *  고를 수 없다. 서버가 세는 값이고 화면은 그대로 옮긴다.
 */
function RetentionNote({ preview, days }: { preview: RetentionPreview | null; days: number }) {
  if (days <= 0) return <p className="settings-hint">모든 자료를 계속 보관합니다. 수집이 쌓이는 만큼 검색 색인이 커집니다.</p>;
  if (!preview || preview.days !== days) return <p className="settings-hint">정리 대상을 확인하는 중입니다.</p>;
  if (!preview.files) return <p className="settings-hint">지금은 {preview.cutoff}보다 오래된 자료가 없어 지워지는 것이 없습니다.</p>;
  return (
    <p className="settings-hint">
      {preview.cutoff}보다 오래된 <strong>{preview.files.toLocaleString()}건</strong>이 지워집니다
      {" "}(자료 {megabytes(preview.fileBytes)}, 검색 색인 약 {megabytes(preview.estimatedIndexBytes)}).
    </p>
  );
}

function runOutcome(run: AutomationRun | undefined) {
  if (!run) return { tone: "", text: "아직 실행된 적 없습니다" };
  const at = run.finishedAt ? new Date(run.finishedAt) : null;
  const when = at && !Number.isNaN(at.getTime())
    ? at.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : "";
  if (run.status === "failed") {
    // 예외 원문이 아니라 분류된 원인이다. 메시지에는 요청 URL·헤더·프롬프트 조각이
    // 실릴 수 있어 화면으로 내보내지 않는다.
    const reason = run.errorReason || "";
    return { tone: "is-failed", text: `${when} 실패${reason ? ` — ${reason}` : ""}` };
  }
  // CLI 제출은 완료가 아니라 제출이다. 아직 도는 job을 완료로 그리면, 뒤이어 실패로
  // 바뀌는 행이 화면에서는 성공으로 남는다.
  if (run.status === "submitted") return { tone: "", text: `${when} 제출됨 — 생성 중` };
  return { tone: "is-done", text: `${when} 완료` };
}

/** 브리핑 예약 목록.
 *
 *  예전에는 하나만 등록할 수 있었다. 시장이 넷이 되면서 마감 시각이 전부 달라져
 *  시각 하나로는 구조적으로 안 된다 — 08:00 한 번이면 미국 마감은 담지만 한국·일본은
 *  개장 전이다. 목록이되, 비어 있을 때는 마감 시각에서 나온 제안을 눌러 넣게 한다.
 */
function BriefingSchedules({
  schedules, watched, runsById, onChange,
}: {
  schedules: BriefingSchedule[];
  watched: string[];
  runsById: Record<string, AutomationRun>;
  onChange: (next: BriefingSchedule[]) => void;
}) {
  const patch = (id: string, changes: Partial<BriefingSchedule>) =>
    onChange(schedules.map((row) => (row.id === id ? { ...row, ...changes } : row)));

  // 마지막 하나를 끄는 것도 선택이다. 예전에는 그 클릭을 그냥 무시해서, 눌러도 아무
  // 일이 없는 버튼으로 보였다. 이제 끄게 두고 — 만들 것이 없어진 예약은 스스로 꺼진다.
  const toggleMarket = (row: BriefingSchedule, market: string) => {
    const next = row.markets.includes(market)
      ? row.markets.filter((m) => m !== market)
      : MARKET_CODES.map((m) => m.id).filter((m) => m === market || row.markets.includes(m));
    patch(row.id, { markets: next, ...(next.length ? {} : { enabled: false }) });
  };

  const toggleDay = (row: BriefingSchedule, day: number) => {
    const current = scheduleDays(row);
    const next = current.includes(day)
      ? current.filter((value) => value !== day)
      : WEEKDAYS_ALL.filter((value) => value === day || current.includes(value));
    patch(row.id, { days: next, ...(next.length ? {} : { enabled: false }) });
  };

  const add = (markets: string[], time: string, kind = "daily", days = [0, 1, 2, 3, 4]) => {
    if (schedules.length >= MAX_SCHEDULES) return;
    onChange([...schedules, {
      id: newScheduleId(), enabled: true, time, markets,
      briefingType: "default", kind, qualityMode: "diagnose_only", runPrerequisites: true,
      // 새 일간 예약은 장이 서는 평일만. 주말 발행은 고르는 것이지 기본값이 아니다.
      days: [...days],
    }]);
  };

  const proposals = SCHEDULE_PROPOSALS
    .map((row) => ({ ...row, markets: row.markets.filter((m) => watched.includes(m)) }))
    .filter((row) => row.markets.length);

  return (
    <div className="schedule-list">
      {schedules.map((row) => {
        const offScope = row.markets.filter((m) => !watched.includes(m));
        return (
          <div className="schedule-row" key={row.id}>
            <div className="schedule-row-head">
              <input
                type="time"
                aria-label="브리핑 시각"
                value={row.time}
                onChange={(event) => patch(row.id, { time: event.currentTarget.value })}
              />
              <select
                aria-label="브리핑 종류"
                value={scheduleKind(row)}
                onChange={(event) => patch(row.id, { kind: event.currentTarget.value })}
              >
                {Object.entries(AUTOMATION_BRIEFING_KINDS).map(([value, label]) => (
                  <option value={value} key={value}>{label}</option>
                ))}
              </select>
              {/* 편집 강조점은 일간 골격 위에서만 뜻이 있다. 주간은 섹션 구성이 달라
                  이 셋("기존 섹션 구성을 유지")이 성립하지 않는다. */}
              {scheduleKind(row) === "daily" && (
                <select
                  aria-label="브리핑 유형"
                  value={row.briefingType}
                  onChange={(event) => patch(row.id, { briefingType: event.currentTarget.value })}
                >
                  {Object.entries(AUTOMATION_BRIEFING_TYPES).map(([value, label]) => (
                    <option value={value} key={value}>{label}</option>
                  ))}
                </select>
              )}
              <ToggleSwitch
                ariaLabel={`${row.time} 예약 사용`}
                checked={row.enabled}
                onChange={(checked) => patch(row.id, { enabled: checked })}
                // 만들 시장도 돌 날도 없으면 켜 봐야 아무 일도 일어나지 않는다.
                // 켤 수 있게 두면 화면은 켜졌다고 말하는데 브리핑은 나오지 않는다.
                disabled={!row.markets.length || !scheduleDays(row).length}
                title={
                  !row.markets.length
                    ? "시장을 하나 이상 골라야 켤 수 있습니다."
                    : !scheduleDays(row).length
                      ? "요일을 하나 이상 골라야 켤 수 있습니다."
                      : undefined
                }
                compact
              />
              <button
                className="btn btn--quiet"
                type="button"
                onClick={() => onChange(schedules.filter((item) => item.id !== row.id))}
              >
                삭제
              </button>
            </div>
            <div className="settings-theme-options" role="group" aria-label={`${row.time} 예약의 시장`}>
              {MARKET_CODES.map((market) => (
                <button
                  type="button"
                  key={market.id}
                  aria-pressed={row.markets.includes(market.id)}
                  onClick={() => toggleMarket(row, market.id)}
                >
                  {market.label}
                </button>
              ))}
            </div>
            {scheduleKind(row) === "weekly" && (
              <p className="settings-hint">
                고른 요일에 그 날짜까지의 지난 7일을 요약하고 다음주 일정을 붙입니다.
              </p>
            )}
            <div className="settings-theme-options" role="group" aria-label={`${row.time} 예약이 도는 요일`}>
              {WEEKDAY_CODES.map((day) => (
                <button
                  type="button"
                  key={day.id}
                  aria-pressed={scheduleDays(row).includes(day.id)}
                  onClick={() => toggleDay(row, day.id)}
                >
                  {day.label}
                </button>
              ))}
            </div>
            {/* 예약별로 정한다. 예약이 여럿일 때 매번 모으면 같은 자료를 하루에 여러 번
                수집하고, 하나도 안 모으면 어제 자료로 브리핑을 만든다. */}
            <div className="automation-inline-switch">
              <span>브리핑 전에 RSS 수집과 시장 메모리 갱신</span>
              <ToggleSwitch
                ariaLabel={`${row.time} 예약: 브리핑 전 RSS 수집과 시장 메모리 갱신`}
                checked={row.runPrerequisites !== false}
                onChange={(checked) => patch(row.id, { runPrerequisites: checked })}
                compact
              />
            </div>
            {offScope.length > 0 && (
              // 선택 자체를 막지 않는다. 시장을 잠깐 껐다 켜는 동안 예약이 파괴되면 안 된다.
              <p className="settings-hint">
                관심 시장에서 꺼둔 {offScope.map((m) => MARKET_CODES.find((c) => c.id === m)?.label || m).join(" · ")}은(는) 빼고 생성합니다.
              </p>
            )}
            <LastRun run={runsById[row.id]} />
          </div>
        );
      })}

      {!schedules.length && proposals.length > 0 && (
        <div className="schedule-proposals">
          <p className="settings-hint">아직 예약이 없습니다. 관심 시장의 마감 시각에 맞춰 제안합니다.</p>
          {proposals.map((row) => (
            <button
              className="btn"
              type="button"
              key={`${row.time}-${row.kind || "daily"}`}
              onClick={() => add(row.markets, row.time, row.kind || "daily", row.days || [0, 1, 2, 3, 4])}
            >
              {row.label} {row.time} — {row.markets.map((m) => MARKET_CODES.find((c) => c.id === m)?.label).join(" · ")}
              <span>{row.hint}</span>
            </button>
          ))}
        </div>
      )}

      <div className="schedule-actions">
        <button
          className="btn"
          type="button"
          disabled={schedules.length >= MAX_SCHEDULES}
          onClick={() => add(watched.length ? [...watched] : MARKET_CODES.map((m) => m.id), "08:00")}
        >
          예약 추가
        </button>
        {schedules.length >= MAX_SCHEDULES && <span className="settings-hint">최대 {MAX_SCHEDULES}개까지 만들 수 있습니다.</span>}
      </div>
    </div>
  );
}

function LastRun({ run }: { run?: AutomationRun }) {
  const { tone, text } = runOutcome(run);
  return (
    <p className={`automation-last-run ${tone}`.trim()}>
      <span>마지막 실행</span>
      {text}
    </p>
  );
}

// 수동 생성 화면(BriefingRoute)과 같은 문구를 쓴다. 두 화면이 다른 이름으로
// 같은 유형을 부르면 자동 브리핑이 무엇으로 나오는지 알 수 없다.
const AUTOMATION_BRIEFING_TYPES: Record<string, string> = {
  default: "기본",
  market_focused: "시황 중심",
  concise: "요약",
};

type MarketScopeState = {
  readonly selected: readonly string[];
  readonly markets: ReadonlyArray<{ readonly id: string; readonly label: string }>;
  readonly enabledAt: Readonly<Record<string, string>>;
};

/** 관심 시장 — 필터가 아니라 제품의 바깥 테두리.
 *
 *  여기서 끈 시장은 RSS 수집이 멈추고, 목록·브리핑 선택지·캘린더·내러티브
 *  세그먼트에서 사라진다. 다시 켜면 그 시장 피드를 즉시 수집하지만, RSS는
 *  피드가 내어주는 최근 항목까지만 받을 수 있어 꺼져 있던 기간의 공백이
 *  남을 수 있다 — 그 한계를 화면이 먼저 말한다.
 */
function MarketScopePanel() {
  const [scope, setScope] = useState<MarketScopeState | null>(null);
  const [draft, setDraft] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const payload = await getJson<MarketScopeState>("/api/market-scope");
        if (cancelled) return;
        setScope(payload);
        setDraft([...payload.selected]);
      } catch {
        if (!cancelled) setNote("관심 시장 설정을 불러오지 못했습니다.");
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (!scope) return null;

  const toggle = (id: string) => {
    setDraft((current) => {
      const next = current.includes(id) ? current.filter((v) => v !== id) : [...current, id];
      // 전부 끄면 남는 화면이 없다. 마지막 하나는 끄지 않는다.
      return next.length ? scope.markets.map((m) => m.id).filter((m) => next.includes(m)) : current;
    });
  };

  const dirty = JSON.stringify(draft) !== JSON.stringify([...scope.selected]);

  const save = async () => {
    if (!dirty) {
      setNote("변경 사항이 없습니다.");
      return;
    }
    setBusy(true);
    setNote("");
    try {
      const payload = await putJson<MarketScopeState & { newlyEnabled?: string[]; collectionJob?: unknown }>(
        "/api/market-scope",
        { selected: draft },
      );
      setScope(payload);
      setDraft([...payload.selected]);
      const enabled = payload.newlyEnabled || [];
      setNote(enabled.length
        ? "저장했습니다. 방금 켠 시장의 자료 수집을 시작했습니다 — 꺼져 있던 기간의 기사는 피드가 아직 내어주는 범위까지만 들어옵니다."
        : "저장했습니다.");
    } catch (err) {
      setNote(err instanceof Error ? err.message : "저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="settings-panel input-panel" data-qa="market-scope-panel">
      <div className="input-panel-header">
        <div>
          <h3>관심 시장</h3>
          <p>여기서 끈 시장은 자료 수집이 멈추고 화면 전체(RSS·브리핑·캘린더·내러티브)에서 숨습니다. 유가·달러 같은 글로벌 자료는 항상 보입니다.</p>
        </div>
      </div>
      <div className="field">
        <span id="marketScopeLabel">수집·표시할 시장</span>
        <div className="settings-theme-options" role="group" aria-labelledby="marketScopeLabel">
          {scope.markets.map((market) => (
            <button
              type="button"
              key={market.id}
              aria-pressed={draft.includes(market.id)}
              disabled={busy}
              onClick={() => toggle(market.id)}
              // 버튼에는 짧은 코드를 쓰고 전체 이름은 접근성 이름으로 남긴다. 서버는 계속
              // 한국어 라벨을 주고 화면이 코드로 바꾼다 — 첫 실행 안내와 예약 화면이
              // 이미 같은 방식이라, 라벨을 서버에서 바꾸면 산문(작업 이름)까지 끌려간다.
              aria-label={market.label}
            >
              {MARKET_CODE_BY_ID[market.id] || market.label}
            </button>
          ))}
        </div>
      </div>
      <div className="settings-actions">
        {dirty && !busy && <span className="settings-dirty-hint">저장 안 된 변경</span>}
        <button className={dirty && !busy ? "btn btn--primary" : "btn"} type="button" onClick={() => void save()} disabled={busy}>
          {busy ? "저장 중" : "저장"}
        </button>
      </div>
      {note && <p className="react-dashboard-warning" role="status">{note}</p>}
    </section>
  );
}

type WorkspaceState = {
  readonly path: string;
  readonly appFolder: string;
  readonly outsideAppFolder: boolean;
  readonly fileCount: number;
  readonly totalBytes: number;
  readonly documentsPath: string;
  readonly documentsAvailable: boolean;
  readonly documentsIsOneDrive: boolean;
  readonly envPinned: boolean;
  readonly canMoveToDocuments: boolean;
  readonly canMoveToAppFolder: boolean;
};

function humanBytes(size: number): string {
  const units = ["B", "KB", "MB", "GB"];
  let value = Math.max(0, size);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return unit === 0 ? `${Math.round(value)} B` : `${value.toFixed(1)} ${units[unit]}`;
}

/** 자료 위치 — 새 버전을 받았을 때 자료가 따라오게 하는 설정.
 *
 *  배포 zip은 버전이 박힌 폴더로 풀리고 `data/`는 빈 채로 나온다. 그래서 새 버전을
 *  받으면 이전 자료는 옛 폴더에 남는다. 자료를 앱 폴더 밖으로 옮겨두면 새 버전이
 *  그 폴더를 다시 찾는다. **옮겨도 원본은 지우지 않는다.**
 */
function WorkspacePanel() {
  const [state, setState] = useState<WorkspaceState | null>(null);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState<"documents" | "app" | "">("");

  const load = useCallback(async () => {
    try {
      setState(await getJson<WorkspaceState>("/api/workspace"));
    } catch {
      setNote("자료 위치를 읽지 못했습니다.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (!state) return null;

  const move = async (destination: "documents" | "app", merge: boolean) => {
    setBusy(destination);
    setNote("");
    try {
      const result = await postJson<{ path: string; previousPath: string; fileCount: number }>(
        "/api/workspace/move",
        { destination, merge },
      );
      setConfirming("");
      await load();
      setNote(
        `자료 ${result.fileCount}개를 ${result.path}(으)로 복사했습니다. ` +
        `서버를 재시작해야 새 위치를 사용합니다. 원본은 ${result.previousPath}에 그대로 있으니 ` +
        "새 위치에서 자료가 잘 보이는지 확인한 뒤 지우세요. " +
        // 서버가 collectionPausedUntilRestart로 알리는 사실이다. 말하지 않으면 그 창에서
        // 수집 버튼이 아무것도 모으지 않는 이유를 알 길이 없다.
        "재시작 전까지는 RSS 수집과 보관 기간 정리가 일시정지됩니다.",
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "옮기지 못했습니다.";
      if (message.includes("이미 자료")) setConfirming(destination);
      setNote(message);
    } finally {
      setBusy("");
    }
  };

  const reveal = async () => {
    setBusy("reveal");
    try {
      await postJson("/api/workspace/reveal", {});
    } catch (err) {
      setNote(err instanceof Error ? err.message : "폴더를 열지 못했습니다.");
    } finally {
      setBusy("");
    }
  };

  return (
    <section className="settings-panel input-panel" data-qa="workspace-panel">
      <div className="input-panel-header">
        <div>
          <h3>자료 위치</h3>
          <p>
            보고서·수집 자료·설정이 저장되는 폴더입니다. 새 버전은 버전 이름이 붙은 새 폴더로
            풀리기 때문에, 자료가 앱 폴더 안에 있으면 업데이트할 때 직접 옮겨야 합니다.
          </p>
        </div>
      </div>

      <div className="field">
        <span id="workspacePathLabel">지금 쓰는 폴더</span>
        <p className="workspace-path" aria-labelledby="workspacePathLabel">{state.path}</p>
        <p className="settings-hint">
          자료 {state.fileCount.toLocaleString()}개 · {humanBytes(state.totalBytes)}
          {state.outsideAppFolder
            ? " · 앱 폴더 밖에 있어 새 버전을 받아도 그대로 이어집니다."
            : " · 앱 폴더 안에 있습니다."}
        </p>
      </div>

      {state.envPinned && (
        <p className="settings-hint">
          FOLIO_HOME 환경변수가 이 위치를 정하고 있습니다. 여기서 옮기려면 환경변수를 먼저 지우세요.
        </p>
      )}

      {state.documentsIsOneDrive && state.canMoveToDocuments && (
        <p className="react-dashboard-warning" role="status">
          문서 폴더가 OneDrive와 동기화됩니다. 자료에는 700MB가 넘는 검색 인덱스가 있어 저장할
          때마다 업로드가 돌고, 두 PC에서 함께 쓰면 충돌 사본이 생길 수 있습니다.
        </p>
      )}

      <div className="settings-actions">
        <button
          className="btn"
          type="button"
          onClick={() => window.dispatchEvent(new CustomEvent("folio:show-welcome"))}
        >
          첫 실행 안내 다시 보기
        </button>
        <button className="btn" type="button" onClick={() => void reveal()} disabled={!!busy}>
          {busy === "reveal" ? "여는 중" : "폴더 열기"}
        </button>
        {state.canMoveToDocuments && state.documentsAvailable && (
          <button
            className="btn btn--primary"
            type="button"
            onClick={() => void move("documents", confirming === "documents")}
            disabled={!!busy}
          >
            {busy === "documents"
              ? "복사 중"
              : confirming === "documents"
                ? "그래도 합치기"
                : "문서 폴더로 옮기기"}
          </button>
        )}
        {state.canMoveToAppFolder && (
          <button
            className="btn"
            type="button"
            onClick={() => void move("app", confirming === "app")}
            disabled={!!busy}
          >
            {busy === "app" ? "복사 중" : confirming === "app" ? "그래도 합치기" : "앱 폴더로 되돌리기"}
          </button>
        )}
      </div>

      {state.canMoveToDocuments && state.documentsAvailable && (
        <p className="settings-hint">
          옮길 위치: {state.documentsPath} · 복사만 하고 원본은 지우지 않습니다.
        </p>
      )}
      {note && <p className="react-dashboard-warning" role="status">{note}</p>}
    </section>
  );
}

export function SettingsRoute() {
  const theme = useThemePreference();
  const uiPreferences = useUiPreferences();
  // 관리(화면·관심 시장·자동화)가 먼저다. 연동은 한 번 설정하면 다시 열 일이 적다.
  const [tab, setTab] = useState<SettingsTab>("admin");
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [agentSettings, setAgentSettings] = useState<AgentSettings | null>(null);
  const [automation, setAutomation] = useState<AutomationSettings>({});
  // 자동화 폼은 서버 응답을 그대로 편집하므로, dirty 판정용 기준선을 따로 든다.
  const [automationSaved, setAutomationSaved] = useState<AutomationSettings>({});
  const [automationRuns, setAutomationRuns] = useState<AutomationRun[]>([]);
  const [retentionPreview, setRetentionPreview] = useState<RetentionPreview | null>(null);
  // 예약 제안은 관심 시장에서 켠 것만 넣는다. 못 읽으면 네 시장을 다 보여주고,
  // 실행할 때 서버가 어차피 교집합을 낸다.
  const [watchedMarkets, setWatchedMarkets] = useState<string[]>(MARKET_CODES.map((m) => m.id));
  const [obsidian, setObsidian] = useState<ObsidianSettings>({});
  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [provider, setProvider] = useState<ProviderId>("openai");
  const [providerApiKey, setProviderApiKey] = useState("");
  const [providerModel, setProviderModel] = useState("");
  const [agentEnabled, setAgentEnabled] = useState(true);
  const [agentMode, setAgentMode] = useState<"cli" | "api">("cli");
  const [agentProvider, setAgentProvider] = useState("codex");
  const [agentModel, setAgentModel] = useState("");
  const [apiDraft, setApiDraft] = useState({ fred: "", bok: "", dart: "" });
  const [notionDraft, setNotionDraft] = useState({ token: "", dbId: "" });
  const [vaultPath, setVaultPath] = useState("");
  const [llmStatus, setLlmStatus] = useState<Record<string, LlmTestResult & { checking?: boolean }>>({});
  const [busy, setBusy] = useState("");
  // 결과는 누른 버튼 옆에 뜬다. 예전에는 한 곳(화면 맨 위)에 모아서, 문서상 1,991px에 있는
  // 자동화 저장을 눌러도 메시지가 54px에 떠 두 화면 반 위에 있었다 — 보이지 않는 확인이다.
  const [note, setNote] = useState<{ panel: string; text: string; tone: "ok" | "error" } | null>(null);
  const say = useCallback((panel: string, text: string) => setNote({ panel, text, tone: "ok" }), []);
  const fail = useCallback((panel: string, text: string) => setNote({ panel, text, tone: "error" }), []);
  // 화면 전체를 못 불러온 것은 어느 패널의 일도 아니라 위에 남긴다.
  const [error, setError] = useState("");

  const providers = settings?.llm?.providers || {};
  const selectedProvider = providers[provider] || {};
  const selectedProviderMeta = PROVIDER_LABELS[provider];
  const providerChoices = selectedProvider.modelChoices || [];
  const agentAdapters = agentSettings?.adapters || [];
  const selectedAgent = agentAdapters.find((adapter) => adapter.id === agentProvider) || agentAdapters[0];
  const selectedAgentChoices = selectedAgent?.modelChoices || [];

  // dirty→primary (2026-08-08 확정): 변경이 생긴 패널의 저장 버튼만 진해지고,
  // 진한 버튼이 곧 "저장 안 된 변경"의 신호다. disabled로 잠그지 않는다.
  const baselineAgentProvider = ["codex", "claude", "antigravity"].includes(agentSettings?.provider || "")
    ? String(agentSettings?.provider)
    : String(agentSettings?.selectedAdapter || agentAdapters[0]?.id || "codex");
  const baselineAdapter = agentAdapters.find((adapter) => adapter.id === baselineAgentProvider) || agentAdapters[0];
  const agentDirty =
    agentEnabled !== (settings?.agent?.enabled !== false) ||
    agentMode !== (settings?.agent?.mode === "api" ? "api" : "cli") ||
    agentProvider !== baselineAgentProvider ||
    agentModel !== normalizedChoice(baselineAdapter?.model, baselineAdapter?.modelChoices) ||
    provider !== providerOrDefault(settings?.llm?.provider) ||
    providerModel !== normalizedChoice(selectedProvider.model, selectedProvider.modelChoices) ||
    providerApiKey.trim() !== "";
  const apiDirty = Boolean(apiDraft.fred.trim() || apiDraft.bok.trim() || apiDraft.dart.trim());
  const notionDirty =
    Boolean(notionDraft.token.trim()) || notionDraft.dbId.trim() !== String(settings?.notion?.dbId || "").trim();
  const obsidianDirty = vaultPath.trim() !== String(obsidian.vaultPath || "").trim();
  const automationDirty =
    JSON.stringify(buildAutomationPayload(automation)) !== JSON.stringify(buildAutomationPayload(automationSaved));
  // 기록은 최신순으로 오므로 종류별 첫 행이 마지막 실행이다.
  const lastRunByKind = useMemo(() => {
    const map: Record<string, AutomationRun> = {};
    for (const run of automationRuns) {
      const kind = String(run.kind || "");
      if (kind && !map[kind]) map[kind] = run;
    }
    return map;
  }, [automationRuns]);
  // 브리핑은 예약마다 따로 본다. 아침이 실패했는지 저녁이 실패했는지 구분되어야 한다.
  const lastBriefingRunById = useMemo(() => {
    const map: Record<string, AutomationRun> = {};
    for (const run of automationRuns) {
      if (run.kind !== "briefing") continue;
      const id = String(run.scheduleId || "");
      if (id && !map[id]) map[id] = run;
    }
    return map;
  }, [automationRuns]);

  const loadAll = useCallback(async (refreshAgent = false) => {
    setError("");
    setBusy("load");
    try {
      const [settingsPayload, agentPayload, automationPayload, obsidianPayload, runsPayload, scopePayload] = await Promise.all([
        getJson<SettingsPayload>(`/api/settings${refreshAgent ? "?refresh=true" : ""}`),
        getJson<AgentSettings>(`/api/agent-bridge/settings${refreshAgent ? "?refresh=true" : ""}`),
        getJson<AutomationSettings>("/api/automation/settings"),
        getJson<ObsidianSettings>("/api/obsidian/settings"),
        // 실행 기록은 있었는데 부르는 화면이 없었다. 자동화가 돌았는지 실패했는지
        // 볼 방법이 없으면 켜 둔 채로 몇 주가 지나도 모른다.
        getJson<{ items?: AutomationRun[] }>("/api/automation/runs?limit=50").catch(() => ({ items: [] })),
        getJson<MarketScopeState>("/api/market-scope").catch(() => null),
      ]);
      setAutomationRuns(runsPayload.items || []);
      if (scopePayload?.selected) {
        setWatchedMarkets(scopePayload.selected.map((code) => String(code).toLowerCase()));
      }
      setSettings(settingsPayload);
      setAgentEnabled(settingsPayload.agent?.enabled !== false);
      setAgentMode(settingsPayload.agent?.mode === "api" ? "api" : "cli");
      const nextProvider = providerOrDefault(settingsPayload.llm?.provider);
      setProvider(nextProvider);
      const nextProviderData = settingsPayload.llm?.providers?.[nextProvider] || {};
      const nextProviderChoices = nextProviderData.modelChoices || [];
      setProviderModel(nextProviderChoices.some((choice) => choice.value === nextProviderData.model)
        ? String(nextProviderData.model || "")
        : nextProviderChoices[0]?.value || "");
      setNotionDraft({ token: "", dbId: settingsPayload.notion?.dbId || "" });

      setAgentSettings(agentPayload);
      const nextAgentProvider = ["codex", "claude", "antigravity"].includes(agentPayload.provider || "")
        ? String(agentPayload.provider)
        : String(agentPayload.selectedAdapter || agentPayload.adapters?.[0]?.id || "codex");
      const nextAgent = agentPayload.adapters?.find((adapter) => adapter.id === nextAgentProvider) || agentPayload.adapters?.[0];
      setAgentProvider(nextAgentProvider);
      const nextAgentChoices = nextAgent?.modelChoices || [];
      setAgentModel(nextAgentChoices.some((choice) => choice.value === nextAgent?.model)
        ? String(nextAgent?.model || "")
        : nextAgentChoices[0]?.value || "");
      window.dispatchEvent(new CustomEvent("folio:agent-settings-updated", { detail: agentPayload }));

      setAutomation(buildAutomationPayload(automationPayload));
      setAutomationSaved(buildAutomationPayload(automationPayload));
      setObsidian(obsidianPayload);
      setVaultPath(obsidianPayload.vaultPath || "");
      setReactAgentContextScope("settings", { surface: "settings", viewId: "settings", reportKind: "", reportId: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "설정을 불러오지 못했습니다.");
    } finally {
      setBusy("");
    }
  }, []);

  const loadCacheStats = useCallback(async () => {
    setBusy("cache");
    setNote(null);
    try {
      const payload = await getJson<CacheStats>("/api/cache/stats");
      setCacheStats(payload);
      say("cache", "캐시 상태를 불러왔습니다.");
    } catch (err) {
      fail("cache", err instanceof Error ? err.message : "캐시 상태를 불러오지 못했습니다.");
    } finally {
      setBusy("");
    }
  }, []);

  async function cleanupCache() {
    setBusy("cache-cleanup");
    fail("cache", "");
    say("cache", "오래된 기업 데이터 캐시를 정리하는 중입니다.");
    try {
      const result = await postJson<CacheCleanup>("/api/cache/cleanup", {});
      const statsPayload = await getJson<CacheStats>("/api/cache/stats");
      setCacheStats(statsPayload);
      // 0개 삭제만 적으면 고장인지 지울 게 없는 것인지 알 수 없다.
      say("cache", result.deleted
        ? `캐시 정리 완료: ${result.deleted}개 삭제, ${result.freed_mb || 0}MB 확보`
        : "정리할 오래된 캐시가 없습니다. 보관 기간이 지난 파일만 지웁니다.");
    } catch (err) {
      fail("cache", err instanceof Error ? err.message : "캐시 정리에 실패했습니다.");
    } finally {
      setBusy("");
    }
  }

  // 고른 기간이 지금 몇 건을 없애는지 서버에 물어본다. 저장한 값이 아니라 **고른 값**을
  // 물어야 한다 — 저장 후에야 알 수 있다면 되돌릴 수 없는 설정을 눈감고 고르는 셈이다.
  const retentionDays = Number(automation.rss?.retentionDays ?? DEFAULT_RETENTION_DAYS);
  useEffect(() => {
    if (retentionDays <= 0) return undefined;
    let alive = true;
    // 실패해도 화면이 뜨는 편이 낫다. 미리보기가 없으면 안내 문장만 빠진다.
    getJson<RetentionPreview>(`/api/rss/retention?days=${retentionDays}`)
      .then((payload) => { if (alive) setRetentionPreview(payload); })
      .catch(() => { if (alive) setRetentionPreview(null); });
    return () => { alive = false; };
  }, [retentionDays]);

  async function runRetentionNow() {
    setBusy("retention");
    fail("automation", "");
    try {
      // 백그라운드 작업이라 여기서는 접수만 확인한다. 진행률은 상단 작업 표시가 맡는다.
      await postJson("/api/rss/retention/run", {});
      say("automation", "정리 작업을 시작했습니다. 진행 상황은 상단 작업 표시에서 확인합니다.");
    } catch (err) {
      fail("automation", err instanceof Error ? err.message : "정리를 시작하지 못했습니다.");
    } finally {
      setBusy("");
    }
  }

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    const current = providers[provider] || {};
    const choices = current.modelChoices || [];
    setProviderModel((previous) => choices.some((choice) => choice.value === previous)
      ? previous
      : choices.some((choice) => choice.value === current.model)
        ? String(current.model || "")
        : choices[0]?.value || "");
    setProviderApiKey("");
  }, [provider, providers]);

  useEffect(() => {
    const adapter = agentAdapters.find((item) => item.id === agentProvider) || agentAdapters[0];
    const choices = adapter?.modelChoices || [];
    setAgentModel((previous) => choices.some((choice) => choice.value === previous)
      ? previous
      : choices.some((choice) => choice.value === adapter?.model)
        ? String(adapter?.model || "")
        : choices[0]?.value || "");
  }, [agentProvider, agentAdapters]);

  async function saveAiAgentSettings() {
    if (!agentDirty) {
      say("agent", "변경 사항이 없습니다.");
      return;
    }
    setBusy("agent");
    say("agent", "AI Agent 설정을 저장하는 중입니다.");
    try {
      const models = Object.fromEntries(agentAdapters.map((adapter) => [adapter.id, adapter.model || ""]));
      models[agentProvider] = agentModel;
      const [agentPayload, settingsPayload] = await Promise.all([
        postJson<AgentSettings>("/api/agent-bridge/settings", { provider: agentProvider, models }),
        postJson<SettingsPayload>("/api/settings", {
          agent: { enabled: agentEnabled, mode: agentMode },
          llm: {
            provider,
            providers: {
              [provider]: { apiKey: providerApiKey.trim(), model: providerModel },
            },
          },
        }),
      ]);
      setAgentSettings(agentPayload);
      setSettings(settingsPayload);
      setProviderApiKey("");
      setLlmStatus((current) => {
        const next = { ...current };
        delete next[provider];
        return next;
      });
      window.dispatchEvent(new CustomEvent("folio:agent-settings-updated", { detail: agentPayload }));
      say("agent", agentEnabled
        ? `AI Agent를 ${agentMode === "cli" ? "LLM CLI" : "LLM API"} 모드로 저장했습니다.`
        : "AI Agent 생성을 비활성화했습니다.");
    } catch (err) {
      fail("agent", err instanceof Error ? err.message : "AI Agent 설정 저장에 실패했습니다.");
    } finally {
      setBusy("");
    }
  }

  async function testProvider(providerId: ProviderId) {
    // 키 없이 눌러도 버튼은 눌리게 두고, 빠진 것을 그 자리에서 말한다(§4 disabled 금지).
    if (!providers[providerId]?.hasApiKey) {
      setLlmStatus((current) => ({
        ...current,
        [providerId]: { status: "missing_key", available: false, message: "API 키를 먼저 입력하세요" },
      }));
      return;
    }
    setLlmStatus((current) => ({ ...current, [providerId]: { checking: true } }));
    try {
      const result = await postJson<LlmTestResult>(`/api/settings/llm/test/${encodeURIComponent(providerId)}`, {});
      setLlmStatus((current) => ({ ...current, [providerId]: result }));
    } catch (err) {
      setLlmStatus((current) => ({
        ...current,
        [providerId]: { status: "network_error", available: false, message: err instanceof Error ? err.message : "연결 확인 실패" },
      }));
    }
  }

  async function saveApiSettings() {
    if (!apiDirty) {
      say("api", "변경 사항이 없습니다.");
      return;
    }
    setBusy("api");
    say("api", "외부 데이터 API 설정을 저장하는 중입니다.");
    try {
      const payload = await postJson<SettingsPayload>("/api/settings", {
        fred: { apiKey: apiDraft.fred.trim() },
        bok: { apiKey: apiDraft.bok.trim() },
        dart: { apiKey: apiDraft.dart.trim() },
      });
      setSettings(payload);
      setApiDraft({
        fred: "",
        bok: "",
        dart: "",
      });
      say("api", "외부 데이터 API 설정을 저장했습니다.");
    } catch (err) {
      fail("api", err instanceof Error ? err.message : "API 설정 저장에 실패했습니다.");
    } finally {
      setBusy("");
    }
  }

  async function saveNotionSettings() {
    if (!notionDirty) {
      say("notion", "변경 사항이 없습니다.");
      return;
    }
    setBusy("notion");
    say("notion", "Notion 설정을 저장하는 중입니다.");
    try {
      const payload = await postJson<SettingsPayload>("/api/settings", {
        notion: { token: notionDraft.token.trim(), dbId: notionDraft.dbId.trim() },
      });
      setSettings(payload);
      setNotionDraft({ token: "", dbId: payload.notion?.dbId || "" });
      say("notion", "Notion 설정을 저장했습니다.");
    } catch (err) {
      fail("notion", err instanceof Error ? err.message : "Notion 설정 저장에 실패했습니다.");
    } finally {
      setBusy("");
    }
  }

  async function saveObsidianSettings() {
    if (!obsidianDirty) {
      say("obsidian", "변경 사항이 없습니다.");
      return;
    }
    setBusy("obsidian");
    say("obsidian", "Obsidian 경로를 저장하는 중입니다.");
    try {
      const payload = await postJson<ObsidianSettings>("/api/obsidian/settings", { vaultPath: vaultPath.trim() });
      setObsidian(payload);
      setVaultPath(payload.vaultPath || vaultPath);
      say("obsidian", payload.vaultPath ? "Obsidian 경로를 저장했습니다." : "Vault 경로를 입력하세요.");
    } catch (err) {
      fail("obsidian", err instanceof Error ? err.message : "Obsidian 설정 저장에 실패했습니다.");
    } finally {
      setBusy("");
    }
  }

  async function saveAutomationSettings() {
    if (!automationDirty) {
      say("automation", "변경 사항이 없습니다.");
      return;
    }
    setBusy("automation");
    say("automation", "자동화 설정을 저장하는 중입니다.");
    try {
      const payload = await postJson<AutomationSettings>("/api/automation/settings", buildAutomationPayload(automation));
      setAutomation(buildAutomationPayload(payload));
      setAutomationSaved(buildAutomationPayload(payload));
      say("automation", "자동화 설정을 저장했습니다.");
    } catch (err) {
      fail("automation", err instanceof Error ? err.message : "자동화 설정 저장에 실패했습니다.");
    } finally {
      setBusy("");
    }
  }

  const providerRows = useMemo(() => API_PROVIDERS.map((providerId) => {
    const row = providers[providerId] || {};
    const result = llmStatus[providerId];
    const checking = result?.checking;
    const label = checking ? "확인 중" : result?.available ? "사용 가능" : result ? "확인 실패" : row.hasApiKey ? "확인 필요" : "키 없음";
    const className = result?.available ? "ready" : checking || result ? "warn" : "";
    const detail = result?.message || `${row.model || "모델 미설정"} · ${row.hasApiKey ? "저장된 키가 있습니다." : "API Key를 저장하세요."}`;
    const checkedAt = checkedAtLabel(result?.checkedAt);
    return { providerId, row, label, className, detail, checkedAt };
  }), [llmStatus, providers]);

  return (
    <div className="react-settings-route" data-settings-route>
      <RouteHero
        eyebrow="Settings"
        title="설정"
        description="화면, 관심 시장, 자동화와 LLM·외부 데이터·내보내기 연동을 관리합니다."
        actions={(
        <button className="btn" type="button" onClick={() => loadAll(true)} disabled={busy === "load"}>
          {busy === "load" ? "불러오는 중" : "새로고침"}
        </button>
        )}
      />

      {/* 포트폴리오의 하위 탭과 같은 프리미티브다. 선택 상태는 `aria-pressed`가 소유하고,
          화면 전용 클래스는 여백만 갖는다(§UI 프리미티브 우선). */}
      <div className="segment settings-tabs" role="group" aria-label="설정 하위 탭">
        {SETTINGS_TABS.map((item) => (
          <button type="button" key={item.id} aria-pressed={tab === item.id} onClick={() => setTab(item.id)}>
            {item.label}
          </button>
        ))}
      </div>

      {error && <p className="react-dashboard-error">{error}</p>}

      {tab === "integrations" ? (
        <div id="settings-integrations" className="sub-tab-panel active">
          <section className="settings-panel input-panel">
            <div className="input-panel-header settings-agent-header">
              <div>
                <h3>AI Agent 설정</h3>
                <p>보고서와 시장 내러티브 생성에 사용할 Agent 경로를 선택합니다. 비활성화하면 규칙 기반으로 생성합니다.</p>
              </div>
            </div>
            <div className="settings-grid">
              <div className="field">
                <span>실행 방식</span>
                <div className="settings-agent-mode-row">
                  <ToggleSwitch ariaLabel="AI Agent 사용" checked={agentEnabled} onChange={setAgentEnabled} compact />
                  <div className="segment" role="group" aria-label="AI Agent 실행 방식">
                    <button aria-pressed={agentMode === "cli"} type="button" onClick={() => setAgentMode("cli")}>LLM CLI</button>
                    <button aria-pressed={agentMode === "api"} type="button" onClick={() => setAgentMode("api")}>LLM API</button>
                  </div>
                </div>
                {!agentEnabled && (
                  <p className="settings-hint">AI Agent가 꺼져 있어요. 켜면 아래 설정을 쓸 수 있습니다.</p>
                )}
              </div>
            </div>

            <fieldset className="settings-agent-controls" disabled={!agentEnabled}>

            {agentMode === "cli" ? (
              <>
                <div className="settings-grid">
                  <label className="field">
                    <span>사용할 CLI</span>
                    <select value={agentProvider} onChange={(event) => setAgentProvider(event.currentTarget.value)}>
                      {(agentAdapters.length ? agentAdapters : [{ id: "codex", label: "Codex CLI" }, { id: "claude", label: "Claude Code CLI" }, { id: "antigravity", label: "Antigravity CLI" }]).map((adapter) => (
                        <option value={adapter.id} key={adapter.id}>{adapter.label || adapter.id}</option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    <span>모델</span>
                    <select value={agentModel} onChange={(event) => setAgentModel(event.currentTarget.value)}>
                      {selectedAgentChoices.length ? selectedAgentChoices.map((choice) => (
                        <option value={choice.value} key={choice.value}>{choice.label}</option>
                      )) : <option value="">모델 목록 없음</option>}
                    </select>
                  </label>
                </div>
                {/* 안내 화면과 같은 컴포넌트다. 안내가 "나중에 설정에서 바꿀 수 있습니다"라고
                    말하므로 설정에서도 설치·로그인이 되어야 그 말이 참이 된다. */}
                <AgentCliSetup
                  adapters={agentAdapters}
                  onSettings={(payload) => setAgentSettings((current) => ({ ...(current || {}), ...payload }))}
                />
              </>
            ) : (
              <>
                <label className="field">
                  <span>API 제공자</span>
                  <select value={provider} onChange={(event) => setProvider(providerOrDefault(event.currentTarget.value))}>
                    <option value="openai">GPT / OpenAI</option>
                    <option value="gemini">Gemini / Google</option>
                    <option value="claude">Claude / Anthropic</option>
                  </select>
                </label>
                <div className="settings-grid">
                  <label className="field">
                    <span>{selectedProviderMeta.name} API Key</span>
                    <input value={providerApiKey} onChange={(event) => setProviderApiKey(event.currentTarget.value)} type="password" autoComplete="off" placeholder={selectedProvider.hasApiKey ? `${selectedProvider.apiKeyMasked} 저장됨` : selectedProviderMeta.key} />
                  </label>
                  <label className="field">
                    <span>{selectedProviderMeta.name} Model</span>
                    <select value={providerModel} onChange={(event) => setProviderModel(event.currentTarget.value)}>
                      {providerChoices.length ? providerChoices.map((choice) => (
                        <option value={choice.value} key={choice.value}>{choice.label}</option>
                      )) : <option value="">모델 목록 없음</option>}
                    </select>
                  </label>
                </div>
                <div className="cli-provider-list" aria-live="polite">
                  {providerRows.map(({ providerId, row, label, className, detail, checkedAt }) => (
                    <div className="cli-provider-row" key={providerId}>
                      <div className="cli-provider-main">
                        <div className="cli-provider-head">
                          <strong>{row.label || PROVIDER_LABELS[providerId].name}</strong>
                          <span className={`cli-chip status-chip ${className}`}>{label}</span>
                          {/* 언제 잰 값인지 없으면 "사용 가능"이 지금인지 지난주인지 모른다. */}
                          {checkedAt && <span className="cli-provider-checked">{checkedAt} 확인</span>}
                        </div>
                        <div className="cli-provider-meta">{detail}</div>
                      </div>
                      <div className="cli-provider-actions">
                        <button className="btn" type="button" disabled={Boolean(llmStatus[providerId]?.checking)} onClick={() => testProvider(providerId)}>연결 확인</button>
                        {row.setupUrl && <a className="btn" href={row.setupUrl} target="_blank" rel="noreferrer">콘솔 열기</a>}
                      </div>
                    </div>
                  ))}
                </div>
                {/* 사용량과 잔액은 이 앱이 볼 수 없다. 조회에 관리자 키가 필요해서 일반 API
                    키로는 불가능하다 — 모르는 것을 아는 척하지 않고 어디서 보는지만 말한다. */}
                <p className="cli-setup-note">
                  이 앱은 키가 살아 있는지만 확인합니다. <b>사용량과 잔액은 제공사 콘솔</b>에서 보세요.
                </p>
              </>
            )}

            </fieldset>
            <div className="filter-actions settings-actions">
              {agentDirty && !busy && <span className="settings-dirty-hint">저장 안 된 변경</span>}
              <button className={agentDirty && !busy ? "btn btn--primary" : "btn"} type="button" onClick={saveAiAgentSettings} disabled={busy === "agent"}>AI Agent 설정 저장</button>
              <button className="btn" type="button" onClick={() => loadAll(true)} disabled={busy === "load"}>모델/상태 새로고침</button>
            </div>
            <PanelNote note={note} panel="agent" />
          </section>

          <section className="settings-panel input-panel">
            <div className="input-panel-header"><h3>API 연동</h3><p>외부 데이터 API 키를 설정합니다.</p></div>
            <div className="settings-grid">
              <label className="field"><span>FRED API Key</span><input value={apiDraft.fred} onChange={(event) => setApiDraft({ ...apiDraft, fred: event.currentTarget.value })} type="password" autoComplete="off" placeholder={settings?.fred?.hasApiKey ? `${settings.fred.apiKeyMasked} 저장됨` : "FRED API 키"} /></label>
              <div className="field"><span>FRED 상태</span><p className="section-subtitle">{statusText(settings?.fred?.hasApiKey, settings?.fred?.apiKeyMasked, "딥 리서치 미국 경제지표용 FRED API 키가 없습니다.", "FRED API 키")}</p></div>
            </div>
            <div className="settings-grid">
              <label className="field"><span>BOK API Key</span><input value={apiDraft.bok} onChange={(event) => setApiDraft({ ...apiDraft, bok: event.currentTarget.value })} type="password" autoComplete="off" placeholder={settings?.bok?.hasApiKey ? `${settings.bok.apiKeyMasked} 저장됨` : "BOK ECOS API 키"} /></label>
              <div className="field"><span>BOK 상태</span><p className="section-subtitle">{statusText(settings?.bok?.hasApiKey, settings?.bok?.apiKeyMasked, "딥 리서치 한국 경제지표용 BOK API 키가 없습니다.", "BOK API 키")}</p></div>
            </div>
            <div className="settings-grid">
              <label className="field"><span>DART API Key</span><input value={apiDraft.dart} onChange={(event) => setApiDraft({ ...apiDraft, dart: event.currentTarget.value })} type="password" autoComplete="off" placeholder={settings?.dart?.hasApiKey ? `${settings.dart.apiKeyMasked} 저장됨` : "OpenDART API 키"} /></label>
              <div className="field"><span>DART 상태</span><p className="section-subtitle">{statusText(settings?.dart?.hasApiKey, settings?.dart?.apiKeyMasked, "국내 기업 분석용 DART API 키가 없습니다.", "DART API 키")}</p></div>
            </div>
            <div className="filter-actions settings-actions">
              {apiDirty && !busy && <span className="settings-dirty-hint">저장 안 된 변경</span>}
              <button className={apiDirty && !busy ? "btn btn--primary" : "btn"} type="button" onClick={saveApiSettings} disabled={busy === "api"}>API 설정 저장</button>
            </div>
            <PanelNote note={note} panel="api" />
          </section>

          <section className="settings-panel input-panel">
            <div className="input-panel-header"><h3>Notion 연동</h3><p>브리핑과 보고서를 Notion 데이터베이스로 내보냅니다.</p></div>
            <div className="settings-grid">
              <label className="field"><span>Notion 통합 토큰</span><input value={notionDraft.token} onChange={(event) => setNotionDraft({ ...notionDraft, token: event.currentTarget.value })} type="password" autoComplete="off" placeholder={settings?.notion?.hasToken ? `${settings.notion.tokenMasked} 저장됨` : "ntn_..."} /></label>
              <div className="field"><span>토큰 상태</span><p className="section-subtitle">{settings?.notion?.hasToken ? `토큰 저장됨: ${settings.notion.tokenMasked}` : "Notion 통합 토큰이 없습니다."}</p></div>
            </div>
            <div className="settings-grid">
              <label className="field"><span>데이터베이스 ID</span><input value={notionDraft.dbId} onChange={(event) => setNotionDraft({ ...notionDraft, dbId: event.currentTarget.value })} placeholder="32자리 Database ID" /></label>
              <div className="field"><span>DB 상태</span><p className="section-subtitle">{settings?.notion?.hasDb ? `DB 저장됨: ${settings.notion.dbIdMasked}` : "Notion 데이터베이스 ID가 없습니다."}</p></div>
            </div>
            <div className="filter-actions settings-actions">
              {notionDirty && !busy && <span className="settings-dirty-hint">저장 안 된 변경</span>}
              <button className={notionDirty && !busy ? "btn btn--primary" : "btn"} type="button" onClick={saveNotionSettings} disabled={busy === "notion"}>Notion 설정 저장</button>
            </div>
            <PanelNote note={note} panel="notion" />
          </section>

          <section className="settings-panel input-panel">
            <div className="input-panel-header"><h3>Obsidian 연동</h3><p>원하면 Obsidian Vault로 보고서와 노트를 내보낼 수 있습니다.</p></div>
            <div className="settings-grid">
              <label className="field"><span>Vault 폴더 경로</span><input value={vaultPath} onChange={(event) => setVaultPath(event.currentTarget.value)} type="text" placeholder="C:\Users\username\Documents\MyVault" /></label>
              <div className="field"><span>경로 상태</span><p className="section-subtitle">{obsidian.vaultPath ? `설정됨: ${obsidian.vaultPath}` : "Vault 경로가 설정되지 않았습니다."}</p></div>
            </div>
            <div className="filter-actions settings-actions">
              {obsidianDirty && !busy && <span className="settings-dirty-hint">저장 안 된 변경</span>}
              <button className={obsidianDirty && !busy ? "btn btn--primary" : "btn"} type="button" onClick={saveObsidianSettings} disabled={busy === "obsidian"}>Obsidian 설정 저장</button>
            </div>
            <PanelNote note={note} panel="obsidian" />
          </section>
        </div>
      ) : (
        <div id="settings-admin" className="sub-tab-panel active">
          <section className="settings-panel input-panel" data-display-settings>
            <div className="input-panel-header">
              <div>
                <h3>화면</h3>
                <p>이 브라우저의 색상 모드와 움직임 방식을 저장합니다.</p>
              </div>
              <span className="settings-theme-status" aria-live="polite">
                현재 {theme.resolved === "dark" ? "다크" : "라이트"}
              </span>
            </div>
            <div className="field">
              <span id="themePreferenceLabel">테마</span>
              <div className="settings-theme-options" role="group" aria-labelledby="themePreferenceLabel">
                {([
                  ["light", "라이트"],
                  ["dark", "다크"],
                  ["system", "시스템"],
                ] as Array<[ThemePreference, string]>).map(([value, label]) => (
                  <button
                    type="button"
                    aria-pressed={theme.preference === value}
                    onClick={() => theme.setPreference(value)}
                    key={value}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="settings-grid">
              <label className="field">
                <span>움직임</span>
                <select
                  value={uiPreferences.preferences.motion}
                  onChange={(event) => uiPreferences.setMotion(event.currentTarget.value === "reduced" ? "reduced" : "system")}
                >
                  <option value="system">시스템 설정 따르기</option>
                  <option value="reduced">움직임 줄이기</option>
                </select>
              </label>
            </div>
          </section>

          <MarketScopePanel />

          <WorkspacePanel />

          <section className="settings-panel input-panel">
            <div className="input-panel-header"><h3>자동화</h3><p>수집, 중기 시장 정리, 브리핑 생성을 각각 독립 루틴으로 관리합니다.</p></div>
            <div className="automation-routines">
              <section className="automation-card">
                <div className="automation-card-head">
                  <div>
                    <span>RSS Collection</span>
                    <strong>RSS 수집</strong>
                    <p>뉴스 피드를 정해진 간격으로 가져와 research inbox와 인덱스에 반영합니다.</p>
                  </div>
                  <ToggleSwitch ariaLabel="RSS 자동 수집" checked={Boolean(automation.rss?.enabled)} onChange={(checked) => setAutomation({ ...automation, rss: { ...automation.rss, enabled: checked } })} compact />
                </div>
                <label className="field"><span>수집 간격</span><select value={String(automation.rss?.intervalMinutes || 60)} onChange={(event) => setAutomation({ ...automation, rss: { ...automation.rss, intervalMinutes: event.currentTarget.value } })}><option value="15">15분마다</option><option value="30">30분마다</option><option value="60">1시간마다</option><option value="180">3시간마다</option></select></label>
                <div className="automation-inline-switch"><span>기사 전문 저장 (무료 공개 본문만, 로컬 보관용)</span><ToggleSwitch ariaLabel="기사 전문 저장" checked={automation.rss?.saveFullText !== false} onChange={(checked) => setAutomation({ ...automation, rss: { ...automation.rss, saveFullText: checked } })} compact /></div>
                <label className="field">
                  <span>보관 기간</span>
                  <select
                    value={String(retentionDays)}
                    onChange={(event) => setAutomation({ ...automation, rss: { ...automation.rss, retentionDays: Number(event.currentTarget.value) } })}
                  >
                    {RETENTION_CHOICES.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
                  </select>
                </label>
                <RetentionNote preview={retentionPreview} days={retentionDays} />
                <div className="automation-card-actions">
                  <button
                    type="button"
                    className="btn"
                    disabled={busy === "retention"}
                    onClick={runRetentionNow}
                  >
                    {busy === "retention" ? "정리하는 중…" : "지금 정리"}
                  </button>
                  <span className="settings-hint">{reclaimHint(retentionPreview?.reclaimableBytes)}</span>
                </div>
                <LastRun run={lastRunByKind.rss} />
              </section>

              <section className="automation-card">
                <div className="automation-card-head">
                  <div>
                    <span>Market Memory</span>
                    <strong>시장 메모리 업데이트</strong>
                    <p>최근 RSS와 시장 자료를 중기 시장 판단용 컨텍스트로 정리합니다.</p>
                  </div>
                  <ToggleSwitch ariaLabel="Market Memory 자동 정리" checked={Boolean(automation.marketMemory?.enabled)} onChange={(checked) => setAutomation({ ...automation, marketMemory: { ...automation.marketMemory, enabled: checked } })} compact />
                </div>
                <label className="field"><span>정리 간격</span><select value={String(automation.marketMemory?.intervalMinutes || 1440)} onChange={(event) => setAutomation({ ...automation, marketMemory: { ...automation.marketMemory, intervalMinutes: event.currentTarget.value } })}><option value="720">12시간마다</option><option value="1440">하루마다</option><option value="2880">이틀마다</option><option value="10080">일주일마다</option></select></label>
                <div className="automation-inline-switch"><span>RSS 수집 직후에도 정리</span><ToggleSwitch ariaLabel="RSS 수집 직후 Market Memory 정리" checked={Boolean(automation.marketMemory?.runAfterRss)} onChange={(checked) => setAutomation({ ...automation, marketMemory: { ...automation.marketMemory, runAfterRss: checked } })} compact /></div>
                <LastRun run={lastRunByKind.marketMemory} />
              </section>

              <section className="automation-card">
                <div className="automation-card-head">
                  <div>
                    <span>Daily Briefing</span>
                    <strong>브리핑 생성</strong>
                    <p>예약한 시각에 그 시장의 일일 브리핑을 만듭니다. 마감 시각이 시장마다 달라 여러 개를 둘 수 있습니다.</p>
                  </div>
                </div>
                <BriefingSchedules
                  schedules={automation.briefingSchedules || []}
                  watched={watchedMarkets}
                  runsById={lastBriefingRunById}
                  onChange={(next) => setAutomation({ ...automation, briefingSchedules: next })}
                />
                <label className="field">
                  <span>시각을 놓쳤을 때</span>
                  <select
                    value={String(automation.missedRuns?.catchUpHours ?? 3)}
                    onChange={(event) => setAutomation({ ...automation, missedRuns: { catchUpHours: event.currentTarget.value } })}
                  >
                    {CATCH_UP_CHOICES.map((choice) => (
                      <option value={choice.value} key={choice.value}>{choice.label}</option>
                    ))}
                  </select>
                </label>
              </section>
            </div>
            <div className="filter-actions settings-actions">
              {automationDirty && !busy && <span className="settings-dirty-hint">저장 안 된 변경</span>}
              <button className={automationDirty && !busy ? "btn btn--primary" : "btn"} type="button" onClick={saveAutomationSettings} disabled={busy === "automation"}>자동화 저장</button>
            </div>
            <PanelNote note={note} panel="automation" />
          </section>
          <section className="settings-panel input-panel">
            <div className="input-panel-header">
              <div>
                <h3>캐시 관리</h3>
                <p>기업 분석용 SEC/DART per-company 캐시 중 오래된 항목만 정리합니다. 공통 ticker/corpCode 목록은 삭제하지 않습니다.</p>
              </div>
              <button className="btn" type="button" onClick={loadCacheStats} disabled={busy === "cache"}>
                {busy === "cache" ? "확인 중" : "상태 확인"}
              </button>
            </div>
            <div className="cache-summary">
              <section>
                <span>전체 캐시</span>
                <strong>{cacheStats ? `${cacheStats.total_mb || 0} MB` : "상태 미확인"}</strong>
              </section>
              <section>
                <span>정리 대상</span>
                <strong>{cacheStats ? `${cacheStats.stale_mb || 0} MB` : "상태 미확인"}</strong>
              </section>
            </div>
            {cacheStats?.stats?.length ? (
              <div className="cache-list">
                {cacheStats.stats.map((row) => (
                  <div className="cache-row" key={row.directory || "cache"}>
                    <strong>{row.directory}</strong>
                    <span>{row.files || 0}개 · {row.total_mb || 0}MB</span>
                    <small>오래된 항목 {row.stale_files || 0}개 · 보관 {row.max_age_days || 0}일</small>
                  </div>
                ))}
              </div>
            ) : (
              <p className="section-subtitle">상태 확인을 누르면 캐시 사용량을 확인합니다.</p>
            )}
            <div className="filter-actions settings-actions">
              <button className="btn" type="button" onClick={cleanupCache} disabled={busy === "cache-cleanup"}>
                {busy === "cache-cleanup" ? "정리 중" : "오래된 캐시 정리"}
              </button>
            </div>
            <PanelNote note={note} panel="cache" />
          </section>
          <section className="settings-panel input-panel">
            <div className="input-panel-header">
              <div>
                <h3>이전 작업 기록</h3>
                <p>예전 버전이 남긴 작업 기록 파일을 현재 저장소로 한 번만 옮깁니다. 보고서와 제안 파일은 건드리지 않습니다.</p>
              </div>
            </div>
            <WorkLogMigrationControl />
          </section>
        </div>
      )}
    </div>
  );
}
