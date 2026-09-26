import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useContentRevision } from "./useContentRevision";
import { getJson, postJson, type JobStatus } from "../api";
import { MarketStateDashboard } from "../islands/MarketStateDashboard";
import { RouteHero } from "./RouteHero";
import { NarrativeVerificationPanel } from "./marketMemory/NarrativeVerificationPanel";
import { InvestmentContextStrip, ownedTickersByState, useInvestmentContextSummary } from "./InvestmentContextCard";
import { setReactAgentContextScope } from "./agentContext";
import type { MarketStateContextProjection } from "./marketStateContext";
import { AgentJobTerminalError, pollAgentJobUntilTerminal } from "./agentPolling";
import { clearMarketMemoryJobId, discoverActiveMarketMemoryJob, persistMarketMemoryJobId, readMarketMemoryJobId, recoverMarketMemoryJob } from "./marketMemoryJobResume";
import { MacroMap } from "./macro/MacroMap";
import { lastMacroView } from "./macro/types";

type AgentJob = {
  id: string;
  kind?: string;
  status: JobStatus;
  message?: string;
  error?: string;
  result?: Record<string, unknown>;
};

type MemoryResult = {
  ok?: boolean;
  status?: string;
  message?: string;
  snapshot?: { headline?: string };
  snapshotId?: string;
  title?: string;
  savedCount?: number;
  estimatedInputTokens?: number;
  rawEntryCount?: number;
  droppedCount?: number;
};

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

function resultMessage(result: MemoryResult) {
  if (result.snapshot?.headline) {
    return result.message || `시장 상태 스냅샷을 저장했습니다: ${result.snapshot.headline}`;
  }
  if (result.snapshotId || result.title) {
    return result.message || `시장 상태 스냅샷을 저장했습니다${result.title ? `: ${result.title}` : ""}`;
  }
  const base = result.message || (result.ok ? "시장 내러티브를 정리했습니다." : "시장 내러티브 정리가 완료되었습니다.");
  const saved = Number.isFinite(Number(result.savedCount)) ? ` 저장 ${result.savedCount}건` : "";
  const tokenNote = result.estimatedInputTokens ? ` · 입력 약 ${result.estimatedInputTokens} tokens` : "";
  const diagnostic = result.rawEntryCount !== undefined ? ` · 응답 ${result.rawEntryCount}건 · 제외 ${result.droppedCount || 0}건` : "";
  return `${base}${saved}${tokenNote}${diagnostic}`;
}

function isAgentJob(value: unknown): value is AgentJob {
  const job = value as AgentJob;
  return Boolean(job?.id && job.status);
}

async function submitMemoryUpdate(): Promise<MemoryResult | AgentJob> {
  return postJson<MemoryResult | AgentJob>("/api/memory/update", {
    date: todayIsoDate(),
  });
}

export function MarketMemoryRoute() {
  const [macro, setMacro] = useState(() => window.location.hash.startsWith('#/market-memory/macro'));
  useEffect(() => {
    const sync = () => setMacro(window.location.hash.startsWith('#/market-memory/macro'));
    window.addEventListener('hashchange', sync); return () => window.removeEventListener('hashchange', sync);
  }, []);
  return <div className="react-market-memory-route" data-market-memory-route>
    <RouteHero eyebrow="Market Memory" title="시장 내러티브" description="중기 시장 흐름과 공식 거시 자료를 함께 확인합니다." />
    <nav className="memory-tabs" aria-label="시장 내러티브 하위 보기">
      <a className={`btn ${!macro ? 'btn--primary' : ''}`} aria-current={!macro ? 'page' : undefined} href="#/market-memory">내러티브</a>
      <a className={`btn ${macro ? 'btn--primary' : ''}`} aria-current={macro ? 'page' : undefined} href={lastMacroView()}>거시 지도</a>
    </nav>
    {macro ? <MacroMap /> : <NarrativeContent />}
  </div>;
}

function NarrativeContent() {
  const [refreshKey, setRefreshKey] = useState(0);
  // 시장 메모리 업데이트가 어디서 돌든 화면이 따라온다.
  const contentRevision = useContentRevision("marketMemory");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [resumableJob, setResumableJob] = useState<AgentJob | null>(() => {
    const id = readMarketMemoryJobId();
    return id ? { id, status: "running" } : null;
  });
  const pollController = useRef<AbortController | null>(null);
  // 개인 맥락은 한 번 읽어 두 자리에 나눠 준다: "다음 확인" 아래 한 줄과, 그 흐름의 검증 알림 표시.
  const contextSummary = useInvestmentContextSummary(refreshKey + contentRevision);
  const ownedTickers = useMemo(() => ownedTickersByState(contextSummary), [contextSummary]);
  const handleMarketStateContext = useCallback((marketState: MarketStateContextProjection | null) => {
    setReactAgentContextScope("market-memory", {
      surface: "market_state",
      viewId: "memory",
      reportKind: "",
      reportId: "",
      marketState,
    });
  }, []);

  function applyResult(result: MemoryResult) {
    if (result.ok === false) throw new Error(result.message || result.status || "시장 메모리 업데이트에 실패했습니다.");
    clearMarketMemoryJobId();
    setStatus(`시장 메모리를 업데이트했습니다. ${resultMessage(result)}`);
    setResumableJob(null);
    setRefreshKey((value) => value + 1);
  }

  useEffect(() => {
    let current = true;
    void (async () => {
      let recovery = await recoverMarketMemoryJob((id) => getJson<AgentJob>(`/api/jobs/${encodeURIComponent(id)}`));
      if (recovery.kind === "none") {
        recovery = await discoverActiveMarketMemoryJob(() => getJson<AgentJob[]>("/api/jobs"));
      }
      if (!current) return;
      if (recovery.kind === "active") {
        setResumableJob(recovery.job);
        setBusy(true);
        setStatus("이전에 시작한 서버 작업에 자동으로 다시 연결했습니다.");
        try {
          await finishJob(recovery.job);
        } catch (err) {
          if (!current) return;
          if (err instanceof AgentJobTerminalError) {
            clearMarketMemoryJobId();
            setResumableJob(null);
            setError(err.message);
            setStatus("");
          } else if (!(err instanceof DOMException && err.name === "AbortError")) {
            setError(err instanceof Error ? err.message : "작업 상태 확인에 실패했습니다.");
            setStatus("");
          }
        } finally {
          if (current) setBusy(false);
        }
      } else if (recovery.kind === "terminal") {
        setResumableJob(null);
        if (recovery.job.status === "done") applyResult((recovery.job.result || {}) as MemoryResult);
        else setError(recovery.job.message || recovery.job.error || "이전 시장 메모리 작업이 종료되었습니다.");
      } else if (recovery.kind === "unavailable") {
        setResumableJob({ id: recovery.id, status: "running" });
        setStatus("저장된 시장 메모리 작업의 상태를 다시 확인해야 합니다.");
      } else if (recovery.kind === "invalid") {
        setResumableJob(null);
        setError("저장된 시장 메모리 작업 정보를 확인할 수 없어 안전하게 제거했습니다.");
      }
    })();
    return () => {
      current = false;
      pollController.current?.abort();
    };
  }, []);

  async function finishJob(job: AgentJob) {
    pollController.current?.abort();
    const controller = new AbortController();
    pollController.current = controller;
    try {
      const done = await pollAgentJobUntilTerminal(job, { signal: controller.signal });
      applyResult((done.result || {}) as MemoryResult);
    } finally {
      if (pollController.current === controller) pollController.current = null;
    }
  }

  async function runMarketMemoryUpdate() {
    setBusy(true);
    setError("");
    setStatus("AI Agent가 단기 뉴스와 기존 중기 메모리를 업데이트하는 중입니다.");
    try {
      setStatus("시장 메모리와 화면용 시장 상태를 함께 갱신하는 중입니다.");
      const response = await submitMemoryUpdate();
      if (isAgentJob(response)) {
        persistMarketMemoryJobId(response.id);
        setResumableJob(response);
        await finishJob(response);
      } else applyResult(response);
    } catch (err) {
      if (err instanceof AgentJobTerminalError) {
        clearMarketMemoryJobId();
        setResumableJob(null);
        setError(err.message);
        setStatus("");
      } else if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError(err instanceof Error ? err.message : "시장 메모리 업데이트에 실패했습니다.");
        setStatus("");
      }
    } finally {
      setBusy(false);
    }
  }

  async function resumeMarketMemoryUpdate() {
    if (!resumableJob) return;
    setBusy(true);
    setError("");
    setStatus("같은 시장 메모리 작업의 상태를 다시 확인하는 중입니다.");
    try {
      await finishJob(resumableJob);
    } catch (err) {
      if (err instanceof AgentJobTerminalError) {
        clearMarketMemoryJobId();
        setResumableJob(null);
        setError(err.message);
        setStatus("");
      } else if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError(err instanceof Error ? err.message : "작업 상태 확인에 실패했습니다.");
        setStatus("");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="react-market-memory-content">

      {error && <p className="react-dashboard-error">{error}</p>}
      {status && <p className="react-dashboard-warning">{status}</p>}
      {resumableJob && !busy ? (
        <div className="react-dashboard-warning market-state-job-resume" data-qa="market-state-job-still-running" role="status">
          <span>작업 {resumableJob.id} · 서버에서 계속 실행 중</span>
          <button className="btn" type="button" data-qa="market-state-job-resume" onClick={() => void resumeMarketMemoryUpdate()}>같은 작업 다시 확인</button>
        </div>
      ) : null}

      <section className="market-state-dashboard react-market-memory-dashboard" aria-label="현재 중기 시장 상황">
        <MarketStateDashboard key={`${refreshKey}:${contentRevision}`} onUpdate={runMarketMemoryUpdate} updating={busy} updateDisabled={Boolean(resumableJob)} onContext={handleMarketStateContext} personalContext={<InvestmentContextStrip summary={contextSummary} />} />
      </section>

      {/* 위 카드는 스냅샷이 쓴 해석이고, 아래는 저장된 내러티브 상태의 규칙 판정이다.
          같은 층이 아니므로 섞지 않고 자기 자리에서 보여준다(0.6 Stage C.1). */}
      <NarrativeVerificationPanel refreshKey={refreshKey + contentRevision} ownedTickers={ownedTickers} />
    </div>
  );
}
