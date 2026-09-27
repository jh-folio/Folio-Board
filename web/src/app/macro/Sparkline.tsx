/**
 * 거시 지도 개요 한 줄의 작은 추이선.
 *
 * 차트 층 계약(새 차트는 FolioChart)의 **기록된 예외**다(DESIGN_SYSTEM §3 차트 층, 2026-09-27).
 * 한 화면에 16개가 놓여 ECharts 인스턴스 16개는 무겁고, 이 그림은 장식이 아니라 흐름의 인상만
 * 준다 — 같은 숫자(머리 숫자·직전 값)가 바로 옆에 글자로 있고, 전체 이력과 데이터 표는 상세의
 * FolioChart가 맡는다. 그래서 스크린리더에는 숨기고(`aria-hidden`), 색은 차트 토큰만 쓴다.
 * 변화율(전분기·전월 대비)은 막대, 수준·전년비는 선으로 그린다.
 */
const WIDTH = 112;
const HEIGHT = 34;

export function Sparkline({ points, shape }: { points: [string, number | null][]; shape: "bars" | "line" }) {
  const values = points.map(([, value]) => value).filter((value): value is number => value != null && Number.isFinite(value));
  if (!values.length) return <svg className="macro-spark" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} aria-hidden="true" />;
  const floor = shape === "bars" ? Math.min(0, ...values) : Math.min(...values);
  const ceiling = shape === "bars" ? Math.max(0, ...values) : Math.max(...values);
  const span = ceiling - floor || 1;
  const y = (value: number) => HEIGHT - 3 - ((value - floor) / span) * (HEIGHT - 6);

  if (shape === "bars") {
    const band = WIDTH / points.length;
    const zero = y(0);
    return (
      <svg className="macro-spark" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} aria-hidden="true" preserveAspectRatio="none">
        <line className="macro-spark__zero" x1={0} x2={WIDTH} y1={zero} y2={zero} />
        {points.map(([period, value], index) => {
          if (value == null) return null;
          const [top, bottom] = [y(value), zero].sort((a, b) => a - b);
          return (
            <rect
              key={period}
              className={index === points.length - 1 ? "macro-spark__bar macro-spark__bar--last" : "macro-spark__bar"}
              x={index * band + band * 0.18}
              y={top}
              width={band * 0.64}
              height={Math.max(bottom - top, 1)}
              rx={1}
            />
          );
        })}
      </svg>
    );
  }

  const step = WIDTH / Math.max(points.length - 1, 1);
  let path = "";
  let pen = "M";
  points.forEach(([, value], index) => {
    if (value == null) {
      pen = "M";
      return;
    }
    path += `${pen}${(index * step).toFixed(1)},${y(value).toFixed(1)} `;
    pen = "L";
  });
  const last = points[points.length - 1]?.[1];
  return (
    <svg className="macro-spark" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} aria-hidden="true">
      <path className="macro-spark__line" d={path.trim()} />
      {last != null && <circle className="macro-spark__dot" cx={(points.length - 1) * step} cy={y(last)} r={2.5} />}
    </svg>
  );
}
