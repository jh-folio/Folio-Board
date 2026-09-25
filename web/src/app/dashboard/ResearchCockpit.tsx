import { useCallback, useEffect, useState } from "react";
import { getJson, MARKET_CODE_LABELS } from "../../api";
import { MarketCalendar } from "./MarketCalendar";
import { NativeMarketChart } from "./NativeMarketChart";
import { STORY_MARKETS, StoryShare, type StoryMarket } from "./StoryShare";

type ProviderHealth = { provider?: string; sourceStatus?: string; errorCode?: string };
type Cockpit = {
  calendarRefs?: Array<Record<string, unknown>>;
  focusSymbols?: Array<{ symbol: string; label?: string; source?: string }>;
  providerHealth?: ProviderHealth[];
  invalidationToken?: string;
};

export function ResearchCockpit() {
  const [payload, setPayload] = useState<Cockpit | null>(null);
  const [error, setError] = useState("");
  const [storyMarket, setStoryMarket] = useState<StoryMarket>("us");
  const load = useCallback(() => getJson<Cockpit>("/api/dashboard/cockpit").then(setPayload).catch((err) => setError(err instanceof Error ? err.message : "대시보드를 불러오지 못했습니다.")), []);
  useEffect(() => { load(); const handler = () => load(); document.addEventListener("folio:generation-complete", handler); return () => document.removeEventListener("folio:generation-complete", handler); }, [load]);
  if (error) return <p className="react-dashboard-error">{error}</p>;
  if (!payload) return <p className="section-subtitle">대시보드를 불러오는 중입니다.</p>;

  const providerIssues = (payload.providerHealth || []).filter((row) => ["stale", "unhealthy"].includes(String(row.sourceStatus || "")));
  const focusSymbols = payload.focusSymbols || [];

  return (
    <div className="research-cockpit" data-invalidation-token={payload.invalidationToken}>
      {providerIssues.length ? <div className="cockpit-provider-status" role="status" aria-label="자료 수집 상태">
        {providerIssues.map((row) => (
          <span className="chip cockpit-provider-status__chip" data-tone="burgundy" key={row.provider}>{row.provider} 수집 문제</span>
        ))}
      </div> : null}
      <section className="cockpit-panel cockpit-story-share" aria-labelledby="cockpit-story-share-title">
        <div className="cockpit-panel__head">
          <div><span>MARKET NARRATIVE</span><h2 id="cockpit-story-share-title">시장 뉴스 분포</h2></div>
          <div className="segment story-share__toggle" role="group" aria-label="이야기 비중 시장">
            {STORY_MARKETS.map((option) => (
              <button key={option} type="button" aria-pressed={storyMarket === option} onClick={() => setStoryMarket(option)}>
                {MARKET_CODE_LABELS[option]}
              </button>
            ))}
          </div>
        </div>
        <StoryShare market={storyMarket} />
      </section>
      <MarketCalendar focusSymbols={focusSymbols} />
      <NativeMarketChart symbols={focusSymbols} />
    </div>
  );
}
