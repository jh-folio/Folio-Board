import { useEffect, useState } from "react";
import { ApiRequestError, getJson, postJson } from "../api";
import { setReactAgentContextScope } from "./agentContext";
import { RouteHero } from "./RouteHero";
import { HoldingsTable, type PositionDraft } from "./portfolio/HoldingsTable";
import { ConsultationEntry } from "./portfolio/ConsultationEntry";
import { PortfolioAnalysis } from "./portfolio/PortfolioAnalysis";
import { PortfolioBacktest } from "./portfolio/PortfolioBacktest";
import { PortfolioTargets } from "./portfolio/PortfolioTargets";

type Portfolio = { revision: number; positions: PositionDraft[]; cash?: Array<{ currency: string; amount: number }>; updatedAt?: string };

/** 보유 종목과 그 종목으로 하는 일들.
 *
 *  탭을 셋으로 나눈 것은 빈도가 다르기 때문이다. 보유·평가는 열 때마다 보고, 목표는
 *  가끔 정하고, 백테스트는 드물게 돌린다. 한 화면에 세로로 쌓으면 매번 보는 것이
 *  거의 안 쓰는 것에 밀린다.
 *
 *  `revision`을 아래로 내려보내 저장 후 시세·비중·목표 차이를 다시 받게 한다.
 */

type Tab = "holdings" | "targets" | "backtest";

const TABS: ReadonlyArray<{ id: Tab; label: string }> = [
  { id: "holdings", label: "보유·평가" },
  // 목표 비중은 프리셋으로 할 수 있는 **여러 일 중 하나**다 — 백테스트와 비교
  // 백테스트의 입력도 같은 프리셋이라, 탭 이름이 그 셋 중 하나만 가리키면
  // 나머지 둘을 어디서 하는지 알 수 없다.
  { id: "targets", label: "프리셋" },
  { id: "backtest", label: "백테스트" },
];

export function PortfolioRoute() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [positions, setPositions] = useState<PositionDraft[]>([]);
  const [tab, setTab] = useState<Tab>("holdings");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const payload = await getJson<Portfolio>("/api/portfolio");
    setPortfolio(payload);
    setPositions(payload.positions || []);
  }

  useEffect(() => {
    load().catch((reason) => setError(reason instanceof Error ? reason.message : "Portfolio를 불러오지 못했습니다."));
    setReactAgentContextScope("portfolio", { surface: "portfolio", viewId: "portfolio", reportKind: "portfolio", reportId: "current" });
  }, []);

  async function save() {
    if (!portfolio) return;
    setBusy(true); setError(""); setStatus("");
    try {
      const payload = await postJson<Portfolio>("/api/portfolio", { expectedRevision: portfolio.revision, positions, cash: portfolio.cash || [] });
      setPortfolio(payload); setPositions(payload.positions || []); setStatus(`revision ${payload.revision}로 저장했습니다.`);
    } catch (reason) {
      if (reason instanceof ApiRequestError && reason.status === 409) {
        await load(); setError("다른 화면에서 Portfolio가 먼저 수정되어 최신본을 다시 불러왔습니다. 변경을 확인한 뒤 다시 저장하세요.");
      } else setError(reason instanceof Error ? reason.message : "Portfolio 저장에 실패했습니다.");
    } finally { setBusy(false); }
  }

  const revision = portfolio?.revision ?? 0;

  return (
    <main className="portfolio-route">
      <RouteHero eyebrow="Portfolio" title="보유 종목과 리서치 연결" description="입력 부담을 줄이고, 보유 포지션에서 시작해 뉴스·브리핑·시장 내러티브를 함께 검토합니다." />

      <div className="segment portfolio-tabs" role="group" aria-label="포트폴리오 보기">
        {TABS.map((item) => (
          <button type="button" key={item.id} aria-pressed={tab === item.id} onClick={() => setTab(item.id)}>
            {item.label}
          </button>
        ))}
      </div>

      {tab === "holdings" && (
        <div className="portfolio-route-grid">
          <section className="cockpit-panel portfolio-holdings" aria-labelledby="portfolio-holdings-title">
            <div className="cockpit-panel__head"><div><span>HOLDINGS</span><h2 id="portfolio-holdings-title">현재 보유 종목</h2></div><b>버전 {revision}</b></div>
            <div className="portfolio-actions">
              <button className="btn" type="button" onClick={() => setPositions([...positions, { ticker: "", quantity: "", averagePrice: "" }])}>종목 추가</button>
              <button className="btn btn--primary" type="button" disabled={busy || !portfolio} onClick={save}>{busy ? "저장 중" : "Portfolio 저장"}</button>
            </div>
            <HoldingsTable positions={positions} onChange={setPositions} />
            {status && <p className="react-reader-status">{status}</p>}
            {error && <p className="react-dashboard-error" role="alert">{error}</p>}
            <PortfolioAnalysis revision={revision} />
          </section>
          <aside className="cockpit-panel portfolio-research" aria-labelledby="portfolio-research-title">
            <div className="cockpit-panel__head"><div><span>RESEARCH</span><h2 id="portfolio-research-title">Agent와 검토</h2></div></div>
            <p>현재 보유 종목을 기준으로 최근 뉴스, 브리핑, 시장 내러티브의 변화와 반대 근거를 함께 살펴봅니다.</p>
            <ConsultationEntry tickers={positions.map((row) => row.ticker).filter(Boolean)} />
            <small>대화 내용은 보고서 근거로 사용되지 않습니다.</small>
          </aside>
        </div>
      )}

      {tab === "targets" && (
        <section className="cockpit-panel" aria-labelledby="portfolio-targets-title">
          <div className="cockpit-panel__head"><div><span>PRESETS</span><h2 id="portfolio-targets-title">프리셋</h2></div></div>
          <PortfolioTargets revision={revision} onChanged={() => { void load(); }} />
        </section>
      )}

      {tab === "backtest" && (
        <section className="cockpit-panel" aria-labelledby="portfolio-backtest-title">
          <div className="cockpit-panel__head"><div><span>BACKTEST</span><h2 id="portfolio-backtest-title">백테스트</h2></div></div>
          <PortfolioBacktest revision={revision} />
        </section>
      )}
    </main>
  );
}
