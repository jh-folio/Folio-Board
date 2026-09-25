import type { AgentAdapterSettings, AgentJob, AgentModelChoice, AgentSettings, RecentReport } from "./types";

const PROVIDERS = new Set(["codex", "claude", "antigravity"]);
const AGENT_MANAGED_JOB_KINDS = new Set(["agent_bridge", "rss"]);

// 어댑터·모델 정보가 아직 없을 때만 쓰는 자리표시자(설정을 못 불러왔을 때 등) — 실제
// 값은 항상 서버(features/llm_settings/reasoning.py)가 계산해 보내는 adapter별
// reasoningChoices/reasoningByModel을 그대로 쓴다.
const FALLBACK_EFFORT_CHOICES: AgentModelChoice[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "max", label: "Max" },
];

/** 이 CLI(모델)가 실제로 받는 노력 단계 목록 — Codex는 low를 "Light"로 부르고
 *  ultra까지, Claude는 "Low"로 부르고 대개 max까지처럼 어댑터·모델마다 이름과
 *  범위가 다르다. `provider_default`(제공자 기본값)는 여기서는 안 보여준다 —
 *  이 화면은 항상 명시적인 단계 하나를 보낸다. */
export function reasoningChoicesFor(adapter: AgentAdapterSettings | null, model: string): AgentModelChoice[] {
  const byModel = adapter?.reasoningByModel?.[model] || [];
  const source = byModel.length ? byModel : adapter?.reasoningChoices || [];
  const explicit = source.filter((choice) => choice?.value && choice.value !== "provider_default");
  const deduped = explicit.filter((choice, index, all) => all.findIndex((item) => item.value === choice.value) === index);
  return deduped.length ? deduped : FALLBACK_EFFORT_CHOICES;
}

export function effortLabel(adapter: AgentAdapterSettings | null, model: string, value: string) {
  return reasoningChoicesFor(adapter, model).find((choice) => choice.value === value)?.label || value;
}

export function elapsedSeconds(startedAt: number) {
  return `${Math.max(1, Math.round((Date.now() - startedAt) / 1000))}초`;
}

export function isAgentManagedJob(job: AgentJob) {
  const label = `${job.label || ""} ${job.message || ""}`;
  return AGENT_MANAGED_JOB_KINDS.has(String(job.kind || "")) || /^LLM CLI|Agent/.test(label);
}

export function formatJobTime(job: AgentJob) {
  const value = job.finishedAt || job.updatedAt || job.createdAt || "";
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return value.slice(0, 16);
  }
}

export function jobArtifactRoute(job: AgentJob) {
  const result = job.result || {};
  const artifactType = result.artifactType || "";
  const artifactId = result.artifactId || result.reportId || "";
  const date = result.date || "";
  if (artifactType === "briefing" && date) return `#/briefing/${date}/both`;
  if (artifactType === "company_analysis" && artifactId) return `#/analysis/${encodeURIComponent(artifactId)}`;
  if (artifactType === "topic_report" && artifactId) return `#/deep-research/${encodeURIComponent(artifactId)}`;
  if (String(job.label || "").includes("RSS")) return "#/rss";
  return "";
}

export function selectedAdapter(settings: AgentSettings | null): AgentAdapterSettings | null {
  const provider = settings?.provider && PROVIDERS.has(settings.provider)
    ? settings.provider
    : settings?.selectedAdapter || "";
  return settings?.adapters?.find((adapter) => adapter.id === provider) || null;
}

export function modelChoicesFor(adapter: AgentAdapterSettings | null) {
  return adapter?.modelChoices || [];
}

export function preferredModel(adapter: AgentAdapterSettings | null) {
  const choices = modelChoicesFor(adapter);
  if (!choices.length) return "";
  return choices.some((choice) => choice.value === adapter?.model) ? String(adapter?.model || "") : choices[0].value;
}

export function isJobResponse(value: unknown): value is AgentJob {
  const job = value as AgentJob;
  return Boolean(job?.id && ["queued", "running"].includes(job.status));
}

export function reportRoute(report: RecentReport) {
  const view = String(report.view || "").trim();
  const scope = report.marketScope === "us" || report.marketScope === "kr" || report.marketScope === "both"
    ? report.marketScope
    : report.scope === "us" || report.scope === "kr" || report.scope === "both"
      ? report.scope
      : "both";
  if (view === "briefing" && /^\d{4}-\d{2}-\d{2}$/.test(String(report.date || ""))) {
    return `#/briefing/${report.date}/${scope}`;
  }
  const routeByView: Record<string, string> = {
    review: "dashboard",
    dashboard: "dashboard",
    briefing: "briefing",
    rssfeed: "rss",
    memory: "market-memory",
    analysis: "analysis",
    topicrpt: "deep-research",
    watchlist: "watchlist",
    settings: "settings",
  };
  return `#/${routeByView[view] || "dashboard"}`;
}

export function recentKey(report: RecentReport, index: number) {
  return `${report.view || "report"}-${report.date || ""}-${report.title || index}`;
}

