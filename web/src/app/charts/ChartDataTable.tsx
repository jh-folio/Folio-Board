import { memo } from "react";

import { sampleRows, tableSummaryLabel } from "./chartA11y";

/** 그림과 같은 숫자를 담은 표 — 텍스트 대체 계약의 세 번째 조각(`chartA11y.ts`).
 *
 *  접혀 있어도 DOM에는 있어 화면 읽기 프로그램이 읽는다. 가로로 넘치면 표 안에서만
 *  스크롤하고, 스크롤 영역은 키보드로 초점을 받는다.
 *  첫 열은 행 머리(날짜 등)이고 나머지는 값이다. 값은 호출하는 쪽이 이미 화면 표기로 만들어 넘긴다.
 */
export const ChartDataTable = memo(function ChartDataTable({
  title,
  unit,
  columns,
  rows,
}: {
  readonly title: string;
  /** 행 하나가 무엇인지(`봉`, `날짜`). 표본일 때 요약 줄에 들어간다. */
  readonly unit: string;
  readonly columns: ReadonlyArray<string>;
  readonly rows: ReadonlyArray<ReadonlyArray<string>>;
}) {
  if (!rows.length) return null;
  return (
    <details className="chart-data">
      <summary>차트 데이터 표 보기 ({tableSummaryLabel(rows.length, unit)})</summary>
      <div className="chart-data__scroll" role="region" aria-label={`${title} 데이터 표`} tabIndex={0}>
        <table>
          <thead>
            <tr>{columns.map((column) => <th scope="col" key={column}>{column}</th>)}</tr>
          </thead>
          <tbody>
            {sampleRows(rows).map((row) => (
              <tr key={row[0]}>
                <th scope="row">{row[0]}</th>
                {row.slice(1).map((cell, index) => <td key={columns[index + 1]}>{cell}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
});
