import { useEffect } from "react";
import { setReactAgentContextScope } from "./agentContext";
import { ResearchCockpit } from "./dashboard/ResearchCockpit";
import { RouteHero } from "./RouteHero";

// 0.5: Legacy(TradingView 위젯 보드 + 투자 리뷰 요약) 모드를 삭제했다. 0.4에서
// rollback 경로로 한 릴리즈만 남기기로 한 것이고, Cockpit이 자리를 잡은 지금은
// 같은 화면을 두 벌 유지할 이유가 없다. 사용자 설정 파일
// (`data/market-widget-settings.json`)은 계약대로 삭제하지 않고 그대로 둔다.
export function Dashboard() {
  useEffect(() => {
    setReactAgentContextScope("dashboard", { surface: "dashboard", viewId: "dashboard", reportKind: "", reportId: "" });
  }, []);

  return (
    <div className="react-dashboard" data-react-dashboard data-dashboard-mode="cockpit">
      <RouteHero
        eyebrow="Research Cockpit"
        title="대시보드"
        description="시장 뉴스 분포, 주요 일정, 가격 차트를 한 화면에서 확인합니다."
      />
      <ResearchCockpit />
    </div>
  );
}
