import { useEffect, useState } from "react";
import { RouteHero } from "../RouteHero";
import { MacroMap } from "./MacroMap";
import { CurrentState, ValidationHistory } from "./MacroStateView";
import { lastMacroView } from "./types";

export function MacroRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const sync = () => {
      const current = window.location.hash;
      if (current.startsWith("#/market-memory/macro")) { window.location.replace(current.replace("#/market-memory/macro", "#/macro/map")); return; }
      if (current === "#/macro" || current === "#/macro/") { window.location.replace(lastMacroView()); return; }
      setHash(current);
    };
    sync(); window.addEventListener("hashchange", sync); return () => window.removeEventListener("hashchange", sync);
  }, []);
  const active = hash.startsWith("#/macro/state") ? "state" : hash.startsWith("#/macro/validation") ? "validation" : "map";
  return <div className="macro-route"><RouteHero eyebrow="Market & Macro" title="시장·거시" description="공식 지표의 변화와 공시에서 확인한 전달 경로를 살펴봅니다." />
    <div className="segment memory-tabs" role="group" aria-label="시장·거시 하위 보기">{[["state", "현재 상태"], ["map", "거시 지도"], ["validation", "검증 이력"]].map(([id, label]) => <button key={id} type="button" aria-pressed={active === id} onClick={() => { window.location.hash = id === "map" ? lastMacroView() : `#/macro/${id}`; }}>{label}</button>)}</div>
    {active === "map" ? <MacroMap /> : active === "state" ? <CurrentState /> : <ValidationHistory />}
  </div>;
}
