/** 차트 텍스트 대체의 공통 조각.
 *
 *  화면 읽기 프로그램·키보드 사용자는 그림을 못 읽는다. 그림 하나마다 (1) 무엇을 그린 그림인지
 *  말하는 이름, (2) 지점을 옮겨 가며 읽는 판독값, (3) 같은 숫자를 담은 표가 있어야 한다.
 *  `BacktestChart`가 처음 이 세 가지를 갖췄고, 새 차트도 같은 조작 언어를 쓴다 — 렌더러가
 *  갈려도 조작은 갈리지 않는다.
 */

/** 표에 싣는 최대 행 수. 이보다 길면 균등 간격으로 대표 행만 남긴다. */
export const MAX_TABLE_ROWS = 72;

/** 첫 행과 마지막 행은 항상 남기고 나머지를 균등하게 뽑는다. */
export function sampleRows<T>(rows: ReadonlyArray<T>): T[] {
  if (rows.length <= MAX_TABLE_ROWS) return [...rows];
  const step = (rows.length - 1) / (MAX_TABLE_ROWS - 1);
  return Array.from({ length: MAX_TABLE_ROWS }, (_, index) => rows[Math.round(index * step)]);
}

/** 표 요약 줄. 표본을 뽑았으면 몇 개를 보여 주는지 밝힌다 — 전체인 줄 알면 안 된다. */
export function tableSummaryLabel(total: number, unit: string): string {
  return total > MAX_TABLE_ROWS ? `${MAX_TABLE_ROWS}개 대표 ${unit}` : `${total}개 ${unit}`;
}

/** 방향키 한 번이 옮기는 지점 수. 처음 누르면 가장 최근(마지막) 지점에서 시작한다.
 *  좌우 ±1, PageUp/PageDown ±10, Home/End 처음·끝 — BacktestChart 슬라이더와 같은 조작 언어다. */
export function nextPointIndex(args: { key: string; current: number | null; length: number }): number | null {
  const { key, current, length } = args;
  if (length <= 0) return null;
  const last = length - 1;
  const clamp = (value: number) => Math.min(last, Math.max(0, value));
  switch (key) {
    case "ArrowLeft": return current === null ? last : clamp(current - 1);
    case "ArrowRight": return current === null ? last : clamp(current + 1);
    case "PageUp": return current === null ? last : clamp(current - 10);
    case "PageDown": return current === null ? last : clamp(current + 10);
    case "Home": return 0;
    case "End": return last;
    default: return null;
  }
}
