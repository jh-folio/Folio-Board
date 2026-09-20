/** 시장 가격 차트의 텍스트 대체 — 그림 이름·지점 판독값·표 열.
 *
 *  Lightweight Charts는 canvas에 그려서 화면 읽기 프로그램이 볼 것이 없다. 아래 함수들이 같은
 *  봉 자료에서 이름과 판독값을 만들어 그림 밖에 둔다. 순수 함수라 브라우저 없이 검증한다.
 */

export type A11yBar = {
  time: string;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close: number;
};

const priceFormat = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 });
const price = (value: number) => priceFormat.format(value);

/** 일봉은 날짜, 분봉은 날짜+시각(거래소 현지 벽시계 — 차트 축이 보여 주는 값과 같다). */
export function barTimeText(raw: string, intraday: boolean): string {
  const text = String(raw || "");
  if (!intraday) return text.slice(0, 10);
  const match = /^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2})/.exec(text);
  return match ? `${match[1]} ${match[2]}` : text;
}

/** 값이 있는 OHLC를 다 갖춘 봉만 캔들로 읽는다(차트가 캔들을 그리는 조건과 같다). */
export function hasOhlc(row: A11yBar): boolean {
  return row.open != null && row.high != null && row.low != null;
}

export function isCandleView(style: "candle" | "line", rows: ReadonlyArray<A11yBar>): boolean {
  return style === "candle" && rows.some(hasOhlc);
}

const signed = (value: number, digits: number) => `${value >= 0 ? "+" : ""}${value.toLocaleString("ko-KR", { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;

/** 그림 전체의 이름 — 무엇을, 언제부터 언제까지, 얼마에서 얼마로 움직였는지. */
export function chartSummaryLabel(args: {
  name: string;
  rangeLabel: string;
  style: "candle" | "line";
  rows: ReadonlyArray<A11yBar>;
  intraday: boolean;
}): string {
  const { name, rangeLabel, style, rows, intraday } = args;
  if (!rows.length) return `${name} 가격 차트. 표시할 자료가 없습니다.`;
  const first = rows[0];
  const last = rows[rows.length - 1];
  const highs = rows.map((row) => row.high ?? row.close);
  const lows = rows.map((row) => row.low ?? row.close);
  const kind = isCandleView(style, rows) ? "캔들" : "라인";
  const move = first.close ? ` (${signed(((last.close - first.close) / first.close) * 100, 1)}%)` : "";
  return [
    `${name} ${rangeLabel} ${kind} 가격 차트.`,
    `${barTimeText(first.time, intraday)}부터 ${barTimeText(last.time, intraday)}까지 ${rows.length}개 봉.`,
    `처음 종가 ${price(first.close)}, 마지막 종가 ${price(last.close)}${move}, 최고 ${price(Math.max(...highs))}, 최저 ${price(Math.min(...lows))}.`,
    "차트에 초점을 두고 좌우 방향키로 봉을 옮기면 값을 읽어 줍니다.",
  ].join(" ");
}

/** 봉 하나의 판독값. 방향키로 지점을 옮길 때 `aria-live`로 읽힌다. */
export function barReadout(args: {
  rows: ReadonlyArray<A11yBar>;
  index: number;
  intraday: boolean;
  candle: boolean;
}): string {
  const { rows, index, intraday, candle } = args;
  const row = rows[index];
  if (!row) return "";
  const previous = index > 0 ? rows[index - 1] : null;
  const basis = intraday ? "직전 봉" : "전일";
  const change = previous && previous.close
    ? `${basis} 대비 ${signed(row.close - previous.close, 2)} (${signed(((row.close - previous.close) / previous.close) * 100, 2)}%)`
    : `${basis} 대비 없음`;
  const body = candle && hasOhlc(row)
    ? `시가 ${price(row.open as number)}, 고가 ${price(row.high as number)}, 저가 ${price(row.low as number)}, 종가 ${price(row.close)}`
    : `종가 ${price(row.close)}`;
  return `${barTimeText(row.time, intraday)}. ${body}. ${change}. ${index + 1}번째 봉, 전체 ${rows.length}개.`;
}

/** 방향키 이동은 모든 차트가 같은 규칙을 쓴다(charts/chartA11y.ts). 봉 차트 쪽 이름만 남긴다. */
export { nextPointIndex as nextBarIndex } from "../charts/chartA11y";
