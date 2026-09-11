const FolioAgent = {
  agentProvider: "codex",
  currentContext: {
    surface: "",
    viewId: "",
    reportKind: "",
    reportId: "",
    marketScope: "",
    selectedText: "",
    visibleSection: "",
    portfolioLinked: false,
  },
};

window.FolioAgent = FolioAgent;

const CODEX_COLOR_LOGO = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="M19.503 0H4.496A4.496 4.496 0 000 4.496v15.007A4.496 4.496 0 004.496 24h15.007A4.496 4.496 0 0024 19.503V4.496A4.496 4.496 0 0019.503 0z" fill="#fff"></path><path d="M9.064 3.344a4.578 4.578 0 012.285-.312c1 .115 1.891.54 2.673 1.275.01.01.024.017.037.021a.09.09 0 00.043 0 4.55 4.55 0 013.046.275l.047.022.116.057a4.581 4.581 0 012.188 2.399c.209.51.313 1.041.315 1.595a4.24 4.24 0 01-.134 1.223.123.123 0 00.03.115c.594.607.988 1.33 1.183 2.17.289 1.425-.007 2.71-.887 3.854l-.136.166a4.548 4.548 0 01-2.201 1.388.123.123 0 00-.081.076c-.191.551-.383 1.023-.74 1.494-.9 1.187-2.222 1.846-3.711 1.838-1.187-.006-2.239-.44-3.157-1.302a.107.107 0 00-.105-.024c-.388.125-.78.143-1.204.138a4.441 4.441 0 01-1.945-.466 4.544 4.544 0 01-1.61-1.335c-.152-.202-.303-.392-.414-.617a5.81 5.81 0 01-.37-.961 4.582 4.582 0 01-.014-2.298.124.124 0 00.006-.056.085.085 0 00-.027-.048 4.467 4.467 0 01-1.034-1.651 3.896 3.896 0 01-.251-1.192 5.189 5.189 0 01.141-1.6c.337-1.112.982-1.985 1.933-2.618.212-.141.413-.251.601-.33.215-.089.43-.164.646-.227a.098.098 0 00.065-.066 4.51 4.51 0 01.829-1.615 4.535 4.535 0 011.837-1.388zm3.482 10.565a.637.637 0 000 1.272h3.636a.637.637 0 100-1.272h-3.636zM8.462 9.23a.637.637 0 00-1.106.631l1.272 2.224-1.266 2.136a.636.636 0 101.095.649l1.454-2.455a.636.636 0 00.005-.64L8.462 9.23z" fill="url(#folio-legacy-codex-gradient)"></path><defs><linearGradient gradientUnits="userSpaceOnUse" id="folio-legacy-codex-gradient" x1="12" x2="12" y1="3" y2="21"><stop stop-color="#B1A7FF"></stop><stop offset=".5" stop-color="#7A9DFF"></stop><stop offset="1" stop-color="#3941FF"></stop></linearGradient></defs></svg>`;
const CLAUDE_COLOR_LOGO = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z" fill="#D97757" fill-rule="nonzero"></path></svg>`;
const ANTIGRAVITY_COLOR_LOGO = `<svg viewBox="0 0 24 24" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><path d="M21.751 22.607c1.34 1.005 3.35.335 1.508-1.508C17.73 15.74 18.904 1 12.037 1 5.17 1 6.342 15.74.815 21.1c-2.01 2.009.167 2.511 1.507 1.506 5.192-3.517 4.857-9.714 9.715-9.714 4.857 0 4.522 6.197 9.714 9.715z" fill="url(#folio-legacy-antigravity-gradient)"></path><defs><linearGradient id="folio-legacy-antigravity-gradient" x1="5" x2="19" y1="22" y2="2" gradientUnits="userSpaceOnUse"><stop stop-color="#3186FF"></stop><stop offset=".42" stop-color="#34A853"></stop><stop offset=".72" stop-color="#FBBC04"></stop><stop offset="1" stop-color="#EA4335"></stop></linearGradient></defs></svg>`;
const DEFAULT_AGENT_LOGO = `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M9 3c.4 3.9 3.1 6.6 7 7-3.9.4-6.6 3.1-7 7-.4-3.9-3.1-6.6-7-7 3.9-.4 6.6-3.1 7-7z"/><path d="M17.8 13c.25 2.4 1.85 4 4.2 4.25-2.35.25-3.95 1.85-4.2 4.25-.25-2.4-1.85-4-4.2-4.25 2.35-.25 3.95-1.85 4.2-4.25z" opacity=".7"/></svg>`;

function agentProviderMeta(provider) {
  const id = String(provider || FolioAgent.agentProvider || "codex").toLowerCase();
  if (id === "claude") return { color: "#d97757", logo: CLAUDE_COLOR_LOGO };
  if (id === "antigravity") return { color: "#3186ff", logo: ANTIGRAVITY_COLOR_LOGO };
  if (id === "codex") return { color: "#3941ff", logo: CODEX_COLOR_LOGO };
  return { color: "#c79a45", logo: DEFAULT_AGENT_LOGO };
}

window.addEventListener("folio:agent-settings-updated", (event) => {
  const detail = event.detail || {};
  const provider = detail.provider || detail.selectedAdapter || "";
  if (provider) FolioAgent.agentProvider = provider;
  applyAgentBranding();
});

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function updateAgentContext(patch = {}) {
  FolioAgent.currentContext = { ...FolioAgent.currentContext, ...patch };
}

function applyAgentBranding() {
  const meta = agentProviderMeta(FolioAgent.agentProvider);
  document.documentElement.style.setProperty("--agent-accent", meta.color);
  document.querySelectorAll(".agent-logo-slot").forEach((slot) => {
    slot.innerHTML = meta.logo;
  });
}

function openAgentDock(context = {}) {
  updateAgentContext(context);
  window.dispatchEvent(new CustomEvent("folio:react-agent-request", { detail: context }));
}

function sourceLink(item) {
  const title = item?.title || item?.url || item?.path || "source";
  if (item?.url) return `<a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">${escapeHtml(title)}</a>`;
  return `<span>${escapeHtml(title)}</span>`;
}

// ReportBody·서버와 같은 안전-느슨 헤딩 계약(번호 접두·시장 접미·괄호 부연 허용, 자유 꼬리 불허).
function markdownSourceSection(value) {
  const text = String(value || "").replace(/\r\n/g, "\n");
  // 참고자료 섹션(들)만 모은다 — 뒤따르는 다른 섹션의 링크를 패널로 끌고 오지 않고,
  // 참고자료 헤딩이 둘이어도(2026-08-22 사용자 보고) 둘 다 걷는다.
  const headings = [...text.matchAll(/^#{1,3}\s*(?:\d+\.\s*)?(?:참고\s*자료|sources(?:\s+used)?)\s*(?:[—-]\s*(?:미국장|한국장|유럽장|일본장))?\s*(?:\([^)\n]{0,80}\))?\s*:?\s*$/gim)];
  return headings.map((match) => {
    const bodyStart = match.index + match[0].length;
    const next = /^#{1,3}\s/m.exec(text.slice(bodyStart));
    return next ? text.slice(match.index, bodyStart + next.index) : text.slice(match.index);
  }).join("\n\n");
}

function markdownSourceSectionHasLinks(value) {
  const section = markdownSourceSection(value);
  if (!section) return false;
  return /\[((?:\\.|[^\]\\])+)\]\(https?:\/\/[^)\s]+(?:\([^)]*\)[^)\s]*)?\)/i.test(section);
}

function briefingSources(briefing) {
  const rows = [];
  const seen = new Set();
  const add = (source) => {
    let key = source?.url || source?.path || source?.title;
    if (source?.url) {
      try {
        const url = new URL(source.url);
        url.hash = "";
        for (const name of [...url.searchParams.keys()]) {
          if (/^(utm_.+|mod|ref|referrer|fbclid|gclid)$/i.test(name)) url.searchParams.delete(name);
        }
        url.searchParams.sort();
        key = url.href;
      } catch (_) { /* Keep the original identity for non-URL sources. */ }
    }
    if (!key || seen.has(key)) return;
    seen.add(key);
    rows.push(source);
  };
  (briefing?.sources || []).forEach(add);
  (briefing?.headlines || []).forEach((headline) => (headline.sources || []).forEach(add));
  for (const match of markdownSourceSection(briefing?.markdown).matchAll(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g)) {
    add({ title: match[1], url: match[2] });
  }
  // 서버가 이미 종류별 상한(일간 24·주간 40)으로 선별했다. 여기서 14로 다시 자르면
  // 프롬프트가 본 근거의 절반이 어느 화면에도 보이지 않는다 — "참고자료는 프롬프트가
  // 본 문서 전부"(2026-08-20 결정)를 패널이 마지막에 배반하고 있었다.
  return rows;
}

function renderSourcePanel(sources) {
  if (!sources.length) return "";
  return `<article class="headline markdown-brief source-panel"><details>
    <summary>참고자료 ${sources.length}건</summary>
    <p class="meta">작성에 전달한 자료와 연결된 기사 목록입니다. 목록에 있다는 이유만으로 본문의 모든 주장을 뒷받침하는 것은 아닙니다.</p>
    <div class="sources">
      ${sources.map((source) => `<div class="source-panel-row">${sourceLink(source)}<div class="meta">${[source.source, source.date, source.type].filter(Boolean).map(escapeHtml).join(" · ")}</div></div>`).join("")}
    </div>
  </details></article>`;
}

function unescapeMarkdownText(text) {
  return String(text || "").replace(/\\([\\[\]()`*_{}])/g, "$1");
}

function inlineMarkdown(text) {
  const raw = String(text || "");
  const parts = [];
  const linkPattern = /\[((?:\\.|[^\]\\])+)\]\((https?:\/\/[^)\s]+(?:\([^)]*\)[^)\s]*)?)\)/g;
  let lastIndex = 0;
  let match;
  while ((match = linkPattern.exec(raw))) {
    parts.push(escapeHtml(raw.slice(lastIndex, match.index)));
    parts.push(`<a href="${escapeHtml(match[2])}" target="_blank" rel="noreferrer">${escapeHtml(unescapeMarkdownText(match[1]))}</a>`);
    lastIndex = match.index + match[0].length;
  }
  parts.push(escapeHtml(raw.slice(lastIndex)));
  return parts.join("").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
}

// 딥 리서치 본문에는 섹션별 근거 연결용 숨김 태그가 붙는다. 이 렌더러는 모든 텍스트를
// escape하므로 HTML 주석이 주석으로 사라지지 않고 글자 그대로 화면에 남는다(사용자 보고).
//
// **태그 이름을 특정하지 않고 주석 전체를 지운다.** `folio-source-ids`만 지우던 때
// 모델이 `<!-- sources: ev_015 -->`라는 새 이름을 스스로 만들어 22개를 썼고, 그것이
// 그대로 화면에 보였다. 리더 본문에서 HTML 주석이 읽을 내용인 경우는 없다.
// 저장된 보고서에도 이미 들어 있으므로 렌더 경계에서 지운다 — Canonical 본문은 그대로 둔다.
const HTML_COMMENT = /<!--[\s\S]*?-->/g;
// 주석을 막으면 모델은 본문에 `[macro_T5YIE, ev_019]`처럼 쓴다(실측 18곳). 독자에게
// 내부 식별자는 아무 뜻이 없다. 항목이 **전부** 근거 ID일 때만 지워 일반 대괄호는 남긴다.
const INLINE_SOURCE_ID = /\s*\[(?:(?:ev|market|macro)_[A-Za-z0-9_.-]+)(?:\s*,\s*(?:ev|market|macro)_[A-Za-z0-9_.-]+)*\]/g;

function stripSourceIdTags(value) {
  return String(value || "")
    .replace(HTML_COMMENT, "")
    .replace(INLINE_SOURCE_ID, "");
}

function renderMarkdown(value) {
  const normalized = stripSourceIdTags(value)
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+$/gm, "")
    .replace(/\n{3,}/g, "\n\n");
  const lines = normalized.split(/\n/);
  const html = [];
  let listOpen = false;
  let tableOpen = false;
  let calendarTable = false;
  // 섹션 요약 blockquote — 헤딩 바로 다음에 오면(사이에 빈 줄이 있어도 됨, html[]에
  // 아무것도 안 쌓이므로) 그 자리에서만 특수 스타일을 입힌다. 본문 중간의 일반
  // blockquote(임원 인용 등)는 그대로 둔다.
  let blockquoteOpen = false;
  let blockquoteIsSummary = false;
  let blockquoteBuffer = [];
  const closeList = () => {
    if (listOpen) {
      html.push("</ul>");
      listOpen = false;
    }
  };
  const closeTable = () => {
    if (tableOpen) {
      html.push("</tbody></table></div>");
      tableOpen = false;
    }
  };
  const closeBlockquote = () => {
    if (blockquoteOpen) {
      const cls = blockquoteIsSummary ? ' class="section-summary"' : "";
      html.push(`<blockquote${cls}><p>${blockquoteBuffer.join(" ")}</p></blockquote>`);
      blockquoteOpen = false;
      blockquoteBuffer = [];
    }
  };
  const isTableLine = (line) => line.startsWith("|") && line.endsWith("|") && line.includes("|");
  const isTableSeparator = (line) => /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line);
  // 셀 하나하나를 본다(열 위치가 아니라) — 같은 표 안에도 "확인되지 않음" 같은 텍스트
  // 값과 "$8.25B" 같은 숫자 값이 섞이고, 리스크·체크포인트 표는 첫 열 말고도 전부
  // 산문이라 "첫 열만 라벨" 규칙이 안 통한다.
  const NUMERIC_CELL = /^[+-]?[$₩]?[\d,]+(\.\d+)?\s*(%|배|bp|[BMK])?$/;
  const tableCells = (line) => line.split("|").slice(1, -1).map((cell) => {
    const raw = cell.trim();
    return { html: inlineMarkdown(raw), numeric: NUMERIC_CELL.test(raw) };
  });
  const listDepth = (space) => Math.min(2, Math.floor(String(space || "").replace(/\t/g, "  ").length / 2));

  for (const rawLine of lines) {
    const line = rawLine.trim();
    const bulletMatch = rawLine.match(/^(\s*)[-*·]\s+(.+)$/);
    const blockquoteMatch = line.match(/^>\s?(.*)$/);
    if (!line) {
      closeList();
      closeTable();
      closeBlockquote();
      continue;
    }
    if (isTableSeparator(line)) continue;
    if (isTableLine(line)) {
      closeList();
      closeBlockquote();
      const cells = tableCells(line);
      if (!tableOpen) {
        calendarTable = cells.some((cell) => /일정|이벤트/.test(cell.html)) && cells.some((cell) => /날짜|일자/.test(cell.html));
        html.push(`<div class="table-wrap${calendarTable ? " briefing-calendar-table" : ""}"><table><thead><tr>${cells.map((cell) => `<th${cell.numeric ? ' class="num"' : ""}>${cell.html}</th>`).join("")}</tr></thead><tbody>`);
        tableOpen = true;
      } else {
        const statuses = { confirmed: "확정", estimated: "예상", actual: "발표됨", tentative: "잠정" };
        html.push(`<tr>${cells.map((cell) => `<td${cell.numeric ? ' class="num"' : ""}>${calendarTable ? statuses[cell.html] || cell.html : cell.html}</td>`).join("")}</tr>`);
      }
      continue;
    }
    if (line === "---") {
      closeList();
      closeTable();
      closeBlockquote();
      html.push("<hr />");
      continue;
    }
    if (line.startsWith("# ")) {
      closeList();
      closeTable();
      closeBlockquote();
      html.push(`<h2>${inlineMarkdown(line.slice(2))}</h2>`);
      continue;
    }
    if (line.startsWith("## ")) {
      closeList();
      closeTable();
      closeBlockquote();
      html.push(`<h3>${inlineMarkdown(line.slice(3).replace(/^Source & Data Notes$/, "자료 기준과 한계"))}</h3>`);
      continue;
    }
    if (line.startsWith("### ")) {
      closeList();
      closeTable();
      closeBlockquote();
      html.push(`<h4>${inlineMarkdown(line.slice(4))}</h4>`);
      continue;
    }
    if (blockquoteMatch) {
      closeList();
      closeTable();
      if (!blockquoteOpen) {
        blockquoteIsSummary = html.length > 0 && /^<h3>/.test(html[html.length - 1]);
        blockquoteOpen = true;
        blockquoteBuffer = [];
      }
      if (blockquoteMatch[1].trim()) blockquoteBuffer.push(inlineMarkdown(blockquoteMatch[1].trim()));
      continue;
    }
    if (bulletMatch) {
      closeTable();
      closeBlockquote();
      if (!listOpen) {
        html.push("<ul>");
        listOpen = true;
      }
      html.push(`<li class="depth-${listDepth(bulletMatch[1])}">${inlineMarkdown(bulletMatch[2])}</li>`);
      continue;
    }
    closeList();
    closeTable();
    closeBlockquote();
    html.push(`<p>${inlineMarkdown(line)}</p>`);
  }
  closeList();
  closeTable();
  closeBlockquote();
  return html.join("");
}

function splitReportTitle(markdown) {
  const text = String(markdown || "").replace(/\r\n/g, "\n");
  const lines = text.split("\n");
  const index = lines.findIndex((line) => /^#\s+/.test(line.trim()));
  if (index < 0) return { title: null, body: text };
  const title = lines[index].trim().replace(/^#\s+/, "").trim();
  const body = [...lines.slice(0, index), ...lines.slice(index + 1)].join("\n").trim();
  return { title, body };
}

window.FolioBridge = {
  updateAgentContext,
  applyAgentBranding,
  openAgentDock,
  renderMarkdown(markdown) {
    return renderMarkdown(String(markdown || ""));
  },
  splitReportTitle(markdown) {
    return splitReportTitle(String(markdown || ""));
  },
  briefingSourcePanelHtml(briefing) {
    if (!briefing || !briefing.markdown) return "";
    return renderSourcePanel(briefingSources(briefing));
  },
  renderBriefingVisuals(article, briefing) {
    if (!article || !briefing || !briefing.markdown) return;
    Promise.resolve(window.FolioBriefingVisuals?.renderInline(article, briefing)).then(() => {
      window.requestAnimationFrame(() => window.FolioBriefingVisuals?.relayout?.());
      setTimeout(() => window.FolioBriefingVisuals?.relayout?.(), 400);
    });
  },
  cleanupBriefingVisuals() {
    window.FolioBriefingVisuals?.cleanup?.();
  },
};
