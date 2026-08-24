import { useEffect, useRef } from "react";
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

function stripInlineReferenceSections(markdown = "") {
  const normalized = markdown.replace(/\r\n/g, "\n");
  // 서버의 _SOURCE_HEADING_LOOSE_RE와 같은 안전-느슨 계약: 번호 접두·괄호 부연 허용,
  // 자유 꼬리 불허("Sources of Uncertainty"는 분석 섹션이다). 정확 일치로 두면 모델이
  // 변형 헤딩으로 쓴 목록이 본문에 남아 패널과 두 번 보인다.
  const referenceHeading = /^#{1,3}\s*(?:\d+\.\s*)?(?:참고\s*자료|Sources(?:\s+Used)?)\s*(?:\([^)\n]{0,80}\))?\s*:?\s*$/gim;
  const match = referenceHeading.exec(normalized);
  if (!match || match.index === undefined) return markdown;
  return normalized.slice(0, match.index).trim();
}

// 리더 본문은 별도 파서를 두지 않고 검증된 레거시 renderMarkdown()을 재사용해
// 표·링크·리스트·차트·소스패널 parity를 확보한다. bridge가 없으면 안전한 subset으로 폴백한다.
export function ReportBody({ markdown = "", marketScope = "both", briefing, sourcePanelHtml = "" }: ReportBodyProps) {
  const ref = useRef<HTMLElement>(null);
  const bridge = legacyBridge();
  const bodyMarkdown = stripInlineReferenceSections(markdown);
  const html = bridge.renderMarkdown?.(bodyMarkdown);

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
        dangerouslySetInnerHTML={{ __html: html }}
      />
      {sourcePanelHtml && <div dangerouslySetInnerHTML={{ __html: sourcePanelHtml }} />}
    </>
  );
}
