import type { JSX } from "react";

type MarkdownRendererProps = {
  markdown?: string;
};

type InlinePart =
  | { type: "text"; value: string }
  | { type: "strong"; value: string }
  | { type: "code"; value: string }
  | { type: "link"; label: string; href: string };

type TableCell = { raw: string; numeric: boolean };

function inlineParts(text: string): InlinePart[] {
  const parts: InlinePart[] = [];
  const pattern = /(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\((https?:\/\/[^)\s]+)\))/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index === undefined) continue;
    if (match.index > last) parts.push({ type: "text", value: text.slice(last, match.index) });
    if (match[2]) parts.push({ type: "strong", value: match[2] });
    else if (match[3]) parts.push({ type: "code", value: match[3] });
    else if (match[4] && match[5]) parts.push({ type: "link", label: match[4], href: match[5] });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ type: "text", value: text.slice(last) });
  return parts;
}

function renderInline(text: string) {
  return inlineParts(text).map((part, index) => {
    if (part.type === "strong") return <strong key={index}>{part.value}</strong>;
    if (part.type === "code") return <code key={index}>{part.value}</code>;
    if (part.type === "link") {
      return (
        <a key={index} href={part.href} target="_blank" rel="noreferrer">
          {part.label}
        </a>
      );
    }
    return <span key={index}>{part.value}</span>;
  });
}

function flushParagraph(buffer: string[], nodes: JSX.Element[]) {
  if (!buffer.length) return;
  nodes.push(<p key={`p-${nodes.length}`}>{renderInline(buffer.join(" "))}</p>);
  buffer.length = 0;
}

// app.js::renderMarkdown()과 같은 셀 단위 판정 — 열 위치가 아니라 셀 내용을 본다.
// 리스크·체크포인트 표는 라벨 열 말고도 전부 산문이라 "첫 열만 라벨" 규칙이 안 통한다.
const NUMERIC_CELL = /^[+-]?[$₩]?[\d,]+(\.\d+)?\s*(%|배|bp|[BMK])?$/;
const CALENDAR_STATUS_LABELS: Record<string, string> = {
  confirmed: "확정",
  estimated: "예상",
  actual: "발표됨",
  tentative: "잠정",
};

function isTableRow(line: string) {
  return line.startsWith("|") && line.endsWith("|");
}

function isTableSeparator(line: string) {
  return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line);
}

function tableCells(line: string): TableCell[] {
  return line
    .split("|")
    .slice(1, -1)
    .map((cell) => {
      const raw = cell.trim();
      return { raw, numeric: NUMERIC_CELL.test(raw) };
    });
}

export function MarkdownRenderer({ markdown = "" }: MarkdownRendererProps) {
  const nodes: JSX.Element[] = [];
  const paragraph: string[] = [];
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  let listItems: string[] = [];
  // app.js::renderMarkdown()과 같은 규칙: 헤딩 바로 다음(사이 빈 줄 허용) blockquote만
  // 섹션 요약으로 본다. 마지막 노드 태그를 보고 판단하므로 별도 상태 없이 검사한다.
  let blockquoteLines: string[] = [];
  let tableHeader: TableCell[] | null = null;
  let tableRows: TableCell[][] = [];
  let tableIsCalendar = false;

  function lastWasHeading(level: 2 | 3 | 4) {
    const last = nodes[nodes.length - 1];
    return !!last && last.type === `h${level}`;
  }

  function flushList() {
    if (!listItems.length) return;
    nodes.push(
      <ul key={`ul-${nodes.length}`}>
        {listItems.map((item, index) => <li key={index}>{renderInline(item)}</li>)}
      </ul>,
    );
    listItems = [];
  }

  function flushBlockquote() {
    if (!blockquoteLines.length) return;
    const isSummary = lastWasHeading(3);
    nodes.push(
      <blockquote key={`bq-${nodes.length}`} className={isSummary ? "section-summary" : undefined}>
        <p>{renderInline(blockquoteLines.join(" "))}</p>
      </blockquote>,
    );
    blockquoteLines = [];
  }

  // app.js::renderMarkdown()과 같은 표 구조(table-wrap div + thead/tbody)와 캘린더 표
  // 특수 처리(헤더에 "일정/이벤트"와 "날짜/일자"가 함께 있으면 상태값을 한글로 치환)를 그대로 낸다.
  function flushTable() {
    if (!tableHeader) return;
    const header = tableHeader;
    const isCalendar = tableIsCalendar;
    nodes.push(
      <div key={`table-${nodes.length}`} className={`table-wrap${isCalendar ? " briefing-calendar-table" : ""}`}>
        <table>
          <thead>
            <tr>
              {header.map((cell, index) => (
                <th key={index} className={cell.numeric ? "num" : undefined}>
                  {renderInline(cell.raw)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => {
                  const text = isCalendar ? CALENDAR_STATUS_LABELS[cell.raw] ?? cell.raw : cell.raw;
                  return (
                    <td key={cellIndex} className={cell.numeric ? "num" : undefined}>
                      {renderInline(text)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>,
    );
    tableHeader = null;
    tableRows = [];
    tableIsCalendar = false;
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph(paragraph, nodes);
      flushList();
      flushBlockquote();
      flushTable();
      continue;
    }

    if (isTableSeparator(trimmed)) continue;

    if (isTableRow(trimmed)) {
      flushParagraph(paragraph, nodes);
      flushList();
      flushBlockquote();
      const cells = tableCells(trimmed);
      if (!tableHeader) {
        tableHeader = cells;
        tableIsCalendar =
          cells.some((cell) => /일정|이벤트/.test(cell.raw)) && cells.some((cell) => /날짜|일자/.test(cell.raw));
      } else {
        tableRows.push(cells);
      }
      continue;
    }

    // app.js::renderMarkdown()과 같은 시프트: 보고서 자체 제목(# )이 h2를 쓰므로
    // 섹션 헤딩(## )은 h3, 그 아래(### )는 h4다. 레벨을 그대로 옮기면(##→h2) 두
    // 렌더러가 같은 마크다운에서 다른 헤딩 레벨을 내 접근성 트리가 갈린다.
    const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushParagraph(paragraph, nodes);
      flushList();
      flushBlockquote();
      flushTable();
      const level = heading[1].length;
      const text = level === 2 ? heading[2].replace(/^Source & Data Notes$/, "자료 기준과 한계") : heading[2];
      const content = renderInline(text);
      if (level === 1) nodes.push(<h2 key={`h-${nodes.length}`}>{content}</h2>);
      else if (level === 2) nodes.push(<h3 key={`h-${nodes.length}`}>{content}</h3>);
      else nodes.push(<h4 key={`h-${nodes.length}`}>{content}</h4>);
      continue;
    }

    const blockquote = trimmed.match(/^>\s?(.*)$/);
    if (blockquote) {
      flushParagraph(paragraph, nodes);
      flushList();
      flushTable();
      if (blockquote[1].trim()) blockquoteLines.push(blockquote[1].trim());
      continue;
    }

    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      flushParagraph(paragraph, nodes);
      flushBlockquote();
      flushTable();
      listItems.push(bullet[1]);
      continue;
    }

    flushBlockquote();
    flushTable();
    paragraph.push(trimmed);
  }
  flushParagraph(paragraph, nodes);
  flushList();
  flushBlockquote();
  flushTable();

  return <div className="react-markdown markdown-brief report-body">{nodes}</div>;
}
