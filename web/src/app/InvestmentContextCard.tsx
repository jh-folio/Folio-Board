import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getJson,
  postJson,
  type InvestmentContextSummary,
  type InvestmentContextExplanationJob,
  type InvestmentTickerContext,
} from "../api";
import { pollAgentJobBounded } from "./agentPolling";

export type InvestmentContextMode = "home" | "market-memory" | "collection" | "deep-research";

type InvestmentContextCardViewProps = {
  readonly mode: InvestmentContextMode;
  readonly summary: InvestmentContextSummary | null;
  readonly collectionId?: string;
  readonly dismissible?: boolean;
  readonly onDismiss?: () => void;
  readonly onReference?: (context: InvestmentTickerContext) => void;
  readonly onExplain?: (context: InvestmentTickerContext) => void;
  readonly explainingTicker?: string;
  readonly explanation?: { readonly ticker: string; readonly reply: string } | null;
  readonly explanationError?: string;
};

type InvestmentContextCardProps = Omit<InvestmentContextCardViewProps, "summary" | "onDismiss">;

const CONTEXT_DISMISS_KEY = "folio.investmentContext.dismissed.v1";

const contextBoundary = {
  layer: "hypothesis",
  reuseAsEvidence: false,
} as const;

const MODE_COPY: Record<InvestmentContextMode, { title: string; description: string }> = {
  home: {
    title: "내 리서치 연결",
    description: "관심 종목과 확인 일정을 현재 리서치 화면에만 연결합니다.",
  },
  "market-memory": {
    title: "이 흐름과 연결된 종목",
    description: "시장 드라이버가 개인 포트폴리오·워치리스트와 만나는 지점입니다.",
  },
  collection: {
    title: "이 Collection과 연결된 개인 맥락",
    description: "저장 필터와 겹치는 종목만 표시하며 외부 근거에는 포함하지 않습니다.",
  },
  "deep-research": {
    title: "질문에 참고할 개인 맥락",
    description: "선택한 종목만 추가 컨텍스트에 hypothesis로 복사할 수 있습니다.",
  },
};

function sourceLabel(source: InvestmentTickerContext["source"]) {
  if (source === "both") return "포트폴리오 · 워치리스트";
  return source === "portfolio" ? "포트폴리오" : "워치리스트";
}

// 포트폴리오 종목은 포트폴리오로, 워치리스트에 있는 종목은 워치리스트로 간다. 예전에는
// 포트폴리오 종목이 시장 내러티브로 가서, 그 화면에서 누르면 제자리에 머물렀다.
export function investmentContextLink(context: InvestmentTickerContext) {
  return context.source === "portfolio"
    ? { href: "#/portfolio", label: "포트폴리오에서 보기" }
    : { href: "#/watchlist", label: "워치리스트에서 보기" };
}

// 주의로 분류된 이유(전환·약화)만 이름 옆에 붙인다. 안정·강화는 이 카드에 오른 이유가 아니다.
const MOMENTUM_NOTE: Record<string, string> = { turning: "전환", fading: "약화" };

function driverText(context: InvestmentTickerContext, limit: number) {
  return context.marketDrivers.slice(0, limit).map((driver) => {
    const note = MOMENTUM_NOTE[driver.momentum];
    return note ? `${driver.label}(${note})` : driver.label;
  });
}

/** 시장 내러티브 상태 ID → 그 흐름과 닿은 내 종목. 이름이 아니라 ID로만 잇는다. */
export function ownedTickersByState(summary: InvestmentContextSummary | null): Record<string, string[]> {
  const byState: Record<string, string[]> = {};
  for (const context of summary?.watchContexts || []) {
    for (const driver of context.marketDrivers) {
      const tickers = byState[driver.stateId] || (byState[driver.stateId] = []);
      if (!tickers.includes(context.ticker)) tickers.push(context.ticker);
    }
  }
  return byState;
}

function contextsFor(
  summary: InvestmentContextSummary,
  mode: InvestmentContextMode,
  collectionId?: string,
) {
  if (mode !== "collection") return summary.watchContexts;
  return summary.watchContexts.filter((context) =>
    context.collections.some((collection) => collection.id === collectionId)
  );
}

function rowMeta(context: InvestmentTickerContext) {
  const details = [
    sourceLabel(context.source),
    ...driverText(context, 2),
    context.dueCheckpoints.length ? `확인 예정 ${context.dueCheckpoints.length}` : "",
  ].filter(Boolean);
  return details.join(" · ");
}

const CONTEXT_FOOTNOTE = "내 포트폴리오·워치리스트 기준 참고 정보예요. 보고서 근거로는 쓰지 않아요.";

function ExplanationReply({ reply }: { readonly reply: string }) {
  const lines = reply.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  return (
    <div className="investment-context-explanation-body">
      {lines.map((line, index) => {
        if (line.startsWith("### ")) {
          return <h3 key={`${index}:${line}`}>{line.slice(4)}</h3>;
        }
        if (line.startsWith("- ")) {
          return <p className="is-bullet" key={`${index}:${line}`}>{line.slice(2)}</p>;
        }
        return <p key={`${index}:${line}`}>{line}</p>;
      })}
    </div>
  );
}

export function InvestmentContextCardView({
  mode,
  summary,
  collectionId,
  dismissible = false,
  onDismiss,
  onReference,
  onExplain,
  explainingTicker = "",
  explanation = null,
  explanationError = "",
}: InvestmentContextCardViewProps) {
  const contexts = useMemo(
    () => summary ? contextsFor(summary, mode, collectionId).slice(0, mode === "home" ? 4 : 3) : [],
    [collectionId, mode, summary],
  );
  const copy = MODE_COPY[mode];

  // 아직 불러오지 못했거나 실패했을 때 자리만 차지하는 안내는 두지 않는다.
  // 이 카드는 보조 정보라, 없으면 조용히 비어 있는 편이 화면에 낫다.
  if (!summary) return null;

  // 연결된 맥락이 하나도 없으면 어떤 화면에서도 렌더링하지 않는다. 홈에서 빈 카드가
  // 상시 떠 있으면 아직 쓰지 않은 기능을 계속 광고하는 꼴이 된다.
  if (!contexts.length) return null;

  const dueCount = contexts.reduce((total, context) => total + context.dueCheckpoints.length, 0);
  return (
    <aside
      className={`investment-context-card mode-${mode}`}
      data-qa={`investment-context-${mode}`}
      data-layer={contextBoundary.layer}
      data-reuse-as-evidence={String(contextBoundary.reuseAsEvidence)}
    >
      <div className="investment-context-head">
        <div>
          <p>내 투자 맥락 · 가설 (근거 아님)</p>
          <h2>{copy.title}</h2>
          <span>{copy.description}</span>
        </div>
        {dismissible && onDismiss ? <button type="button" className="btn btn--icon investment-context-dismiss" aria-label="개인 맥락 카드 닫기" onClick={onDismiss}>×</button> : null}
      </div>

      {/* 확인 예정은 있을 때만 말한다. "확인 예정 0"은 읽을 것이 없는 숫자다. */}
      <div className="investment-context-summary" aria-label="개인 맥락 요약">
        <span>연결 {contexts.length}</span>
        {dueCount ? <span>확인 예정 {dueCount}</span> : null}
      </div>

      <ul className="investment-context-ledger">
        {contexts.map((context) => {
          const link = investmentContextLink(context);
          return (
            <li key={context.ticker}>
              <div>
                <strong>{context.ticker}</strong>
                <small>{rowMeta(context)}</small>
              </div>
              <div className="investment-context-row-actions">
                {mode === "deep-research" && onReference ? (
                  <button className="btn btn--sm" type="button" onClick={() => onReference(context)}>질문에 참고</button>
                ) : (
                  <a className="btn btn--sm btn--text" href={link.href}>{link.label}</a>
                )}
                {onExplain ? (
                  <ExplainButton context={context} explainingTicker={explainingTicker} onExplain={onExplain} />
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>

      <ExplanationSection explanation={explanation} explanationError={explanationError} />

      {mode === "home" ? (
        <nav className="investment-context-links" aria-label="연결된 리서치 화면">
          <a className="btn btn--sm btn--text" href="#/market-memory">시장 내러티브</a>
          <a className="btn btn--sm btn--text" href="#/deep-research">딥 리서치</a>
        </nav>
      ) : null}
      <small className="investment-context-boundary">{CONTEXT_FOOTNOTE}</small>
    </aside>
  );
}

function ExplainButton({ context, explainingTicker, onExplain }: {
  readonly context: InvestmentTickerContext;
  readonly explainingTicker: string;
  readonly onExplain: (context: InvestmentTickerContext) => void;
}) {
  return (
    <button
      className="btn btn--sm"
      type="button"
      disabled={Boolean(explainingTicker)}
      title={explainingTicker && explainingTicker !== context.ticker ? "다른 종목 설명이 끝나면 누를 수 있어요" : undefined}
      onClick={() => onExplain(context)}
    >
      {explainingTicker === context.ticker ? "설명 중…" : "Agent로 위험 설명"}
    </button>
  );
}

function ExplanationSection({ explanation, explanationError }: {
  readonly explanation: { readonly ticker: string; readonly reply: string } | null;
  readonly explanationError: string;
}) {
  return (
    <>
      {explanation ? (
        <section className="investment-context-explanation" aria-live="polite">
          <strong>{explanation.ticker} · Agent 설명</strong>
          <ExplanationReply reply={explanation.reply} />
        </section>
      ) : null}
      {explanationError ? (
        <p className="investment-context-error" role="status">{explanationError}</p>
      ) : null}
    </>
  );
}

type InvestmentContextStripViewProps = {
  readonly summary: InvestmentContextSummary | null;
  readonly onExplain?: (context: InvestmentTickerContext) => void;
  readonly explainingTicker?: string;
  readonly explanation?: { readonly ticker: string; readonly reply: string } | null;
  readonly explanationError?: string;
};

/**
 * 시장 내러티브 화면의 한 줄 표시. 카드로 올려 두면 개인 참고 정보가 시장 상태를 밀어내고
 * 화면의 주인공처럼 보였다(2026-09-25 사용자 결정 — "다음 확인" 아래 한 줄).
 * 색 워시 없이 3px 보라 줄과 보라 라벨로만 개인 층임을 말한다: HDR에서 채도가 눌리면
 * 옅은 보라 배경은 사라지지만 선과 글자는 남는다.
 */
export function InvestmentContextStripView({
  summary,
  onExplain,
  explainingTicker = "",
  explanation = null,
  explanationError = "",
}: InvestmentContextStripViewProps) {
  const contexts = summary?.watchContexts.slice(0, 3) || [];
  if (!contexts.length) return null;
  return (
    <aside
      className="surface--group investment-context-strip"
      data-qa="investment-context-market-memory"
      data-layer={contextBoundary.layer}
      data-reuse-as-evidence={String(contextBoundary.reuseAsEvidence)}
      aria-label="내 종목과 닿은 흐름"
    >
      <p className="investment-context-strip__kicker">내 종목과 닿은 흐름 · 가설 (근거 아님)</p>
      <ul className="investment-context-strip__list">
        {contexts.map((context) => {
          const link = investmentContextLink(context);
          return (
            <li key={context.ticker}>
              <strong>{context.ticker}</strong>
              <span>{driverText(context, 3).join(" · ")}</span>
              <span className="investment-context-strip__actions">
                <a className="btn btn--sm btn--text" href={link.href}>{link.label}</a>
                {onExplain ? (
                  <ExplainButton context={context} explainingTicker={explainingTicker} onExplain={onExplain} />
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>
      <ExplanationSection explanation={explanation} explanationError={explanationError} />
      <small className="investment-context-strip__note">{CONTEXT_FOOTNOTE}</small>
    </aside>
  );
}

/** 개인 맥락 요약을 한 번 읽는다. 보조 정보라 실패하면 null로 남고 화면은 조용하다. */
export function useInvestmentContextSummary(refreshKey = 0) {
  const [summary, setSummary] = useState<InvestmentContextSummary | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    getJson<InvestmentContextSummary>("/api/investment-context/summary", { signal: controller.signal })
      .then(setSummary)
      .catch(() => {
        // 보조 카드라 실패하면 조용히 사라진다. 리서치 화면에 오류 배너를 띄울 만한 정보가 아니다.
      });
    return () => controller.abort();
  }, [refreshKey]);
  return summary;
}

/** `Agent로 위험 설명`: 사용자가 누를 때만 job을 만든다. */
function useInvestmentContextExplanation() {
  const [explainingTicker, setExplainingTicker] = useState("");
  const [explanation, setExplanation] = useState<{ ticker: string; reply: string } | null>(null);
  const [explanationError, setExplanationError] = useState("");
  const explanationController = useRef<AbortController | null>(null);

  useEffect(() => () => explanationController.current?.abort(), []);

  const requestExplanation = useCallback(async (context: InvestmentTickerContext) => {
    explanationController.current?.abort();
    const controller = new AbortController();
    explanationController.current = controller;
    setExplainingTicker(context.ticker);
    setExplanation(null);
    setExplanationError("");
    try {
      const job = await postJson<InvestmentContextExplanationJob>(
        "/api/agent/investment-context/explain",
        { tickers: [context.ticker] },
        { signal: controller.signal },
      );
      const done = await pollAgentJobBounded(job, { signal: controller.signal });
      const reply = done.result?.reply?.trim() || "";
      if (!reply) throw new Error("설명 결과가 비어 있습니다.");
      setExplanation({ ticker: context.ticker, reply });
    } catch (requestError) {
      if (requestError instanceof DOMException && requestError.name === "AbortError") return;
      setExplanationError(
        requestError instanceof Error
          ? requestError.message
          : "Agent 설명을 완료하지 못했습니다.",
      );
    } finally {
      if (explanationController.current === controller) {
        explanationController.current = null;
        setExplainingTicker("");
      }
    }
  }, []);

  return { explainingTicker, explanation, explanationError, requestExplanation };
}

export function InvestmentContextStrip({ summary }: { readonly summary: InvestmentContextSummary | null }) {
  const { explainingTicker, explanation, explanationError, requestExplanation } = useInvestmentContextExplanation();
  return (
    <InvestmentContextStripView
      summary={summary}
      onExplain={requestExplanation}
      explainingTicker={explainingTicker}
      explanation={explanation}
      explanationError={explanationError}
    />
  );
}

export function InvestmentContextCard(props: InvestmentContextCardProps) {
  const summary = useInvestmentContextSummary();
  // 닫기는 브라우저에 기억한다. 컴포넌트 state로만 두면 화면을 옮길 때마다 되살아나서
  // "닫았는데 또 뜬다"가 된다. 닫기 버튼이 있는 카드(홈)에만 적용한다 — 예전에는 홈에서
  // 닫은 것이 닫기 버튼도 없는 다른 화면의 카드까지 숨겼다.
  const [dismissed, setDismissed] = useState(() => {
    try {
      return window.localStorage.getItem(CONTEXT_DISMISS_KEY) === "1";
    } catch {
      return false;
    }
  });
  const { explainingTicker, explanation, explanationError, requestExplanation } = useInvestmentContextExplanation();

  if (dismissed && props.dismissible) return null;
  return (
    <InvestmentContextCardView
      {...props}
      summary={summary}
      onDismiss={props.dismissible ? () => {
        setDismissed(true);
        try {
          window.localStorage.setItem(CONTEXT_DISMISS_KEY, "1");
        } catch {
          // 저장이 막혀 있어도 이번 화면에서는 닫힌 상태를 유지한다.
        }
      } : undefined}
      onExplain={requestExplanation}
      explainingTicker={explainingTicker}
      explanation={explanation}
      explanationError={explanationError}
    />
  );
}