import { useEffect, useMemo, useRef } from "react";
import { legacyBridge } from "../legacyBridge";
import { MarkdownRenderer } from "./MarkdownRenderer";

type ReportBodyProps = {
  markdown?: string;
  marketScope?: string;
  // 전달하면 브리핑 가격 차트/히트맵 snapshot을 본문 안에 렌더한다.
  briefing?: unknown;
  // 참고자료 보강 패널 HTML(레거시 briefingSourcePanelHtml 결과). 비면 렌더하지 않는다.
  sourcePanelHtml?: string;
};

// 서버 `daily_briefing/service.py::strip_markdown_sources_section`을 그대로 옮긴다.
// 안전-느슨 계약: 번호 접두(`## 7.`)·시장 접미(`— 한국장`)·괄호 부연(`(24건)`)만 허용,
// 자유 꼬리 불허("Sources of Uncertainty"는 분석 섹션이라 자르면 안 된다).
const REFERENCE_HEADING = /^#{1,3}\s*(?:\d+\.\s*)?(?:참고\s*자료|Sources(?:\s+Used)?)\s*(?:[—-]\s*(?:미국장|한국장|유럽장|일본장))?\s*(?:\([^)\n]{0,80}\))?\s*:?\s*$/im;

export function stripInlineReferenceSections(markdown = "") {
  const normalized = markdown.replace(/\r\n/g, "\n");
  if (!REFERENCE_HEADING.test(normalized)) return markdown;
  // 참고자료 섹션과 그 목록만 걷어내고 다른 섹션은 남긴다. 문서 끝까지 자르면 그
  // 아래에 온 정상 섹션("밸류에이션과 DCF 관련 주의")이 사라지고(실측: notes
  // 2,031→978자), 참고자료 헤딩이 둘이면(2026-08-22 사용자 보고) 두 번째가 본문에 남는다.
  let text = normalized;
  for (;;) {
    const match = REFERENCE_HEADING.exec(text);
    if (!match || match.index === undefined) return text.trim();
    const rest = text.slice(match.index + match[0].length);
    const nextHeading = /^#{1,3}\s/m.exec(rest);
    const tail = nextHeading ? rest.slice(nextHeading.index) : "";
    // 코드가 붙이던 구분선(`---`)이 꼬리에 남지 않게.
    const head = text.slice(0, match.index).replace(/\s+$/, "").replace(/(?:\n\s*---\s*)+$/, "").replace(/\s+$/, "");
    const reduced = tail.trim() ? `${head}\n\n${tail.replace(/^\s+/, "")}`.trim() : head;
    if (reduced === text) return text.trim();
    text = reduced;
  }
}

// 리더 본문은 별도 파서를 두지 않고 검증된 레거시 renderMarkdown()을 재사용해
// 표·링크·리스트·차트·소스패널 parity를 확보한다. bridge가 없으면 안전한 subset으로 폴백한다.
export function ReportBody({ markdown = "", marketScope = "both", briefing, sourcePanelHtml = "" }: ReportBodyProps) {
  const ref = useRef<HTMLElement>(null);
  const bridge = legacyBridge();
  const bodyMarkdown = sourcePanelHtml ? stripInlineReferenceSections(markdown) : markdown;
  const html = bridge.renderMarkdown?.(bodyMarkdown);
  // React must not replace the article's HTML on unrelated route updates: the
  // visual renderer owns chart DOM inserted after the Markdown was committed.
  const innerHtml = useMemo(() => ({ __html: html || "" }), [html]);

  useEffect(() => {
    const article = ref.current;
    if (!article || !briefing || !bridge.renderBriefingVisuals) return;
    bridge.renderBriefingVisuals(article, briefing);
    return () => bridge.cleanupBriefingVisuals?.();
  }, [bodyMarkdown, briefing]);

  if (html === undefined) {
    return <MarkdownRenderer markdown={bodyMarkdown} />;
  }

  return (
    <>
      <article
        ref={ref}
        className="markdown-brief report-body"
        data-market-scope={marketScope}
        dangerouslySetInnerHTML={innerHtml}
      />
      {sourcePanelHtml && <div dangerouslySetInnerHTML={{ __html: sourcePanelHtml }} />}
    </>
  );
}
