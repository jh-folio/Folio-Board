import type { ReactNode } from "react";

type AgentMessageContentProps = {
  text?: string;
};

type AgentRunCardProps = {
  state?: "pending" | "done" | "error";
  title: string;
  meta?: string;
  /** Real phase + elapsed time once the first poll tick arrives (Agent Dock
   *  Stage C). Falls back to a generic hint before that, so the card never
   *  shows an empty line. */
  pendingHint?: string;
};

type InlinePart =
  | { type: "text"; value: string }
  | { type: "strong"; value: string }
  | { type: "code"; value: string }
  | { type: "link"; label: string; href: string };

function inlineParts(text: string): InlinePart[] {
  const parts: InlinePart[] = [];
  const pattern = /(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\))/g;
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
      if (!/^https?:\/\//i.test(part.href)) {
        return <code key={index} title={part.href}>{part.label}</code>;
      }
      return (
        <a key={index} href={part.href} target="_blank" rel="noreferrer">
          {part.label}
        </a>
      );
    }
    return <span key={index}>{part.value}</span>;
  });
}

function flushParagraph(buffer: string[], nodes: ReactNode[]) {
  if (!buffer.length) return;
  nodes.push(<p key={`p-${nodes.length}`}>{renderInline(buffer.join(" "))}</p>);
  buffer.length = 0;
}

export function AgentMessageContent({ text = "" }: AgentMessageContentProps) {
  const nodes: ReactNode[] = [];
  const paragraph: string[] = [];
  let listItems: string[] = [];
  let listType: "ul" | "ol" | "" = "";

  function flushList() {
    if (!listItems.length) return;
    const items = listItems.map((item, index) => <li key={index}>{renderInline(item)}</li>);
    nodes.push(listType === "ol" ? <ol key={`ol-${nodes.length}`}>{items}</ol> : <ul key={`ul-${nodes.length}`}>{items}</ul>);
    listItems = [];
    listType = "";
  }

  for (const rawLine of text.replace(/\r\n/g, "\n").split("\n")) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph(paragraph, nodes);
      flushList();
      continue;
    }

    const heading = line.match(/^(#{2,4})\s+(.+)$/);
    if (heading) {
      flushParagraph(paragraph, nodes);
      flushList();
      nodes.push(<h4 key={`h-${nodes.length}`}>{renderInline(heading[2])}</h4>);
      continue;
    }

    const ordered = line.match(/^\d+[.)]\s+(.+)$/);
    if (ordered) {
      flushParagraph(paragraph, nodes);
      if (listType && listType !== "ol") flushList();
      listType = "ol";
      listItems.push(ordered[1]);
      continue;
    }

    const bullet = line.match(/^[-*•]\s+(.+)$/);
    if (bullet) {
      flushParagraph(paragraph, nodes);
      if (listType && listType !== "ul") flushList();
      listType = "ul";
      listItems.push(bullet[1]);
      continue;
    }

    if (listItems.length) {
      listItems[listItems.length - 1] = `${listItems[listItems.length - 1]} ${line}`;
      continue;
    }

    paragraph.push(line);
  }
  flushParagraph(paragraph, nodes);
  flushList();

  return <div className="agent-chat-markdown">{nodes}</div>;
}

export function AgentRunCard({ state = "pending", title, meta, pendingHint }: AgentRunCardProps) {
  return (
    <div className={`agent-run-card ${state}`}>
      <span className="agent-run-icon" aria-hidden="true" />
      <div>
        <strong>
          {title}
          {state === "pending" && <span className="agent-run-eta">{pendingHint || "보통 40~60초"}</span>}
        </strong>
        {meta && <span>{meta}</span>}
      </div>
    </div>
  );
}
