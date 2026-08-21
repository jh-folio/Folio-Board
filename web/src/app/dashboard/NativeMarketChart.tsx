import { useEffect, useRef, useState } from "react";
import { getJson, postJson } from "../../api";
import { MarketChartFigure, RANGES } from "./MarketChartFigure";

// `chartTime`은 공용 컴포넌트로 옮겼다. 기존 import 경로를 쓰는 곳이 있어 다시 내보낸다.
export { chartTime } from "./MarketChartFigure";

const INDEX_SYMBOLS: Array<{ symbol: string; label: string }> = [
  { symbol: "^GSPC", label: "S&P 500" },
  { symbol: "^IXIC", label: "NASDAQ" },
  { symbol: "^DJI", label: "DOW" },
  { symbol: "^KS11", label: "KOSPI" },
  { symbol: "^KQ11", label: "KOSDAQ" },
  { symbol: "KRW=X", label: "USD/KRW" },
];

export function NativeMarketChart({ symbols }: { symbols: Array<{ symbol: string; label?: string; source?: string }> }) {
  const watchSymbols = symbols.filter((row) => row.source !== "fallback" && !INDEX_SYMBOLS.some((index) => index.symbol === row.symbol));
  const [draftSymbol, setDraftSymbol] = useState("");
  const [watchError, setWatchError] = useState("");
  const [symbol, setSymbol] = useState(INDEX_SYMBOLS[0].symbol);
  const [range, setRange] = useState("3m");
  const [style, setStyle] = useState<"candle" | "line">("line");
  const settingsRef = useRef(false);

  // 관심 종목 목록의 주인은 워치리스트다. 차트에서 편집해도 저장소는 한 곳이라
  // 같은 목록을 두 곳에서 따로 관리하는 일이 생기지 않는다.
  async function saveWatchlist(next: string[]) {
    await postJson("/api/watchlist", { items: next });
    document.dispatchEvent(new CustomEvent("folio:generation-complete"));
  }

  async function addWatchSymbol() {
    const value = draftSymbol.trim().toUpperCase();
    if (!value) return;
    setWatchError("");
    try {
      const current = await getJson<string[]>("/api/watchlist");
      if (current.some((item) => item.toUpperCase() === value)) {
        setWatchError("이미 관심 종목에 있습니다.");
        return;
      }
      await saveWatchlist([...current, value]);
      setDraftSymbol("");
    } catch (reason) {
      setWatchError(reason instanceof Error ? reason.message : "추가하지 못했습니다.");
    }
  }

  async function removeWatchSymbol(target: string) {
    setWatchError("");
    try {
      const current = await getJson<string[]>("/api/watchlist");
      const row = symbols.find((item) => item.symbol === target);
      const label = (row?.label || "").toLowerCase();
      const next = current.filter((item) => {
        const token = item.trim().toLowerCase();
        return token !== target.toLowerCase() && (!label || token !== label);
      });
      if (next.length === current.length) {
        setWatchError("워치리스트에서 해당 항목을 찾지 못했습니다.");
        return;
      }
      await saveWatchlist(next);
    } catch (reason) {
      setWatchError(reason instanceof Error ? reason.message : "제거하지 못했습니다.");
    }
  }

  useEffect(() => {
    if (settingsRef.current) return;
    settingsRef.current = true;
    getJson<{ chartSymbol?: string; chartRange?: string; chartStyle?: string }>("/api/dashboard/settings")
      .then((row) => {
        if (row.chartRange && RANGES.includes(row.chartRange)) setRange(row.chartRange);
        if (row.chartSymbol) setSymbol(row.chartSymbol);
        if (row.chartStyle === "line" || row.chartStyle === "candle") setStyle(row.chartStyle);
      })
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    const known = INDEX_SYMBOLS.some((row) => row.symbol === symbol) || watchSymbols.some((row) => row.symbol === symbol);
    if (!known) setSymbol(INDEX_SYMBOLS[0].symbol);
  }, [watchSymbols, symbol]);

  function pickSymbol(value: string) {
    setSymbol(value);
    postJson("/api/dashboard/settings", { chartSymbol: value }).catch(() => undefined);
  }
  function pickRange(value: string) {
    setRange(value);
    postJson("/api/dashboard/settings", { chartRange: value }).catch(() => undefined);
  }
  function pickStyle(value: "candle" | "line") {
    setStyle(value);
    postJson("/api/dashboard/settings", { chartStyle: value }).catch(() => undefined);
  }


  return (
    <section className="cockpit-panel cockpit-chart" aria-labelledby="native-chart-title">
      <div className="cockpit-panel__head">
        <div><span>MARKET CHART</span><h2 id="native-chart-title">시장 차트</h2></div>
        {/* 종목 선택은 제목 줄 우측. 지수 6개 + 관심 종목을 칩으로 늘어놓으면 제목
            줄이 넘치므로 접이식 둘로 묶는다. */}
        <div className="chart-pickers">
          <details className="chart-picker">
            <summary>지수</summary>
            <div className="chart-picker__list">
              {INDEX_SYMBOLS.map((row) => (
                <button type="button" key={row.symbol}
                  className={`sym-chip${row.symbol === symbol ? " sym-chip--active" : ""}`}
                  aria-pressed={row.symbol === symbol} onClick={() => pickSymbol(row.symbol)}>{row.label}</button>
              ))}
            </div>
          </details>
          <details className="chart-picker">
            <summary>관심 종목{watchSymbols.length ? ` ${watchSymbols.length}` : ""}</summary>
            <div className="chart-picker__list">
              {watchSymbols.map((row) => (
                <span className="chart-picker__row" key={row.symbol}>
                  <button type="button" title={row.label || row.symbol}
                    className={`sym-chip${row.symbol === symbol ? " sym-chip--active" : ""}`}
                    aria-pressed={row.symbol === symbol} onClick={() => pickSymbol(row.symbol)}>{row.symbol}</button>
                  <button type="button" className="btn btn--icon chart-picker__remove"
                    aria-label={`${row.label || row.symbol} 관심 종목에서 제거`}
                    onClick={() => void removeWatchSymbol(row.symbol)}>×</button>
                </span>
              ))}
              {/* 워치리스트가 관리 주체다. 여기서 더하면 워치리스트에 반영돼
                  같은 목록을 두 곳에서 따로 관리하는 일이 생기지 않는다. */}
              <form className="chart-picker__add" onSubmit={(event) => { event.preventDefault(); void addWatchSymbol(); }}>
                <input value={draftSymbol} onChange={(event) => setDraftSymbol(event.currentTarget.value)}
                  placeholder="티커 추가" aria-label="관심 종목 추가" />
                <button className="btn btn--sm" type="submit" disabled={!draftSymbol.trim()}>추가</button>
              </form>
              {watchError && <p className="chart-picker__error">{watchError}</p>}
            </div>
          </details>
        </div>
      </div>
      <MarketChartFigure
        symbol={symbol}
        label={INDEX_SYMBOLS.find((row) => row.symbol === symbol)?.label || symbol}
        range={range}
        style={style}
        onRange={pickRange}
        onStyle={pickStyle}
      />
    </section>
  );
}
