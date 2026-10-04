import type { ReactNode } from "react";
import { atLeastRequired, cashPerHundred, cashSpan, goalText, irrText, multiple, percentOne, plainOne, rowFor, toNumber, usableGoal } from "./format";
import type { Criteria, Projection, SnapshotView } from "./types";

// 가격 탭을 읽는 순서를 화면에 드러내는 틀: ①②③ 묶음, 섹션마다 같은 틀(질문·계산·이렇게 보세요), 한눈에 보기.
// 여기서는 서버 값을 글로 옮기기만 하고 판정을 새로 만들지 않는다.

export const SECTION_IDS = {
  parts: "price-parts-title",
  reverse: "price-reverse-title",
  noGrowth: "price-no-growth-title",
  cash: "price-cash-title",
} as const;

export function scrollToSection(id: string) {
  const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  document.getElementById(id)?.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
}

/** ①②③ 묶음 머리. */
export function PartHeader({ number, title, sub }: { number: number; title: string; sub: string }) {
  return (
    <div className="price-part">
      <span className="price-part__num" aria-hidden="true">{number}</span>
      <div><h3>{title}</h3><p>{sub}</p></div>
    </div>
  );
}

/** 섹션마다 같은 틀: 제목 → 이 섹션이 답하는 질문 → 내용 → 계산 → 이렇게 보세요. */
export function GuideSection({ id, title, meta, question, hint, calc, read, children }: {
  id: string; title: string; meta?: ReactNode; question?: ReactNode; hint?: string; calc?: ReactNode; read?: ReactNode; children: ReactNode;
}) {
  return (
    <section className="price-section" aria-labelledby={id}>
      <div className="watchlist-detail-section__head"><h4 id={id}>{title}</h4>{meta && <span className="price-meta">{meta}</span>}</div>
      {question && <p className="price-question">{question}{hint && <span className="price-hint">{hint}</span>}</p>}
      {children}
      {calc && <div className="price-calc"><b>계산</b><span>{calc}</span></div>}
      {read && <p className="price-read"><b>이렇게 보세요</b>{read}</p>}
    </section>
  );
}

type GlanceItem = { key: string; body: ReactNode; target: string; label: string };

function rangeOf(view: SnapshotView, key: "pe") {
  const block = view.results.ranges[key];
  const values = (block.values || []).map(item => Number(item.value)).filter(Number.isFinite);
  return values.length ? { min: Math.min(...values), max: Math.max(...values), median: toNumber(block.p50) ?? values[0] } : null;
}

/** 한눈에 보기 다섯 줄. 계산할 수 없는 줄은 빼거나 사유로 바꾼다. */
export function glanceItems({ view, projection, criteria, horizon }: { view: SnapshotView; projection: Projection | null; criteria: Criteria | null; horizon: 5 | 10 }): GlanceItem[] {
  const items: GlanceItem[] = [];
  const rows = view.results.scenarios;
  const base = rowFor(rows, "base", horizon);
  const holding = criteria?.holdingYears ?? null;
  const goal = usableGoal(criteria?.requiredReturn ?? null);
  if (base && base.status === "available") {
    const value = `연평균 ${irrText(base)}`;
    const head = <>과거 10년 흐름(이익 연 {plainOne(percentOne(base.g) ?? 0)} 성장, PER {multiple(base.exitPE)})이 이어진다면 {horizon}년 보유 시 <b>{value}</b>(주가 상승 + 배당)</>;
    let tail = "입니다.";
    if (goal !== null && holding !== null) {
      const baseHolding = rowFor(rows, "base", holding);
      const word = (atLeastRequired(horizon === holding ? base : baseHolding, goal) ? "높습니다" : "낮습니다");
      tail = horizon === holding
        ? `로, 내가 정한 최소 수익률 ${goalText(goal)}보다 ${word}.`
        : baseHolding && baseHolding.status === "available"
          ? `입니다. 내 기준 비교는 ${holding}년(연평균 ${irrText(baseHolding)})으로 하며, 최소 수익률 ${goalText(goal)}보다 ${word}.`
          : "입니다.";
    }
    items.push({ key: "return", body: <>{head}{tail}</>, target: SECTION_IDS.parts, label: "① 수익률은 어디서 나오나" });
  }
  const parts = Array.isArray(view.results.returnParts) ? view.results.returnParts : null;
  const part = parts?.find(item => item.label === "base" && item.horizon === horizon);
  if (part && part.status === "available") {
    const rerating = toNumber(part.rerating) ?? 0;
    const flat = plainOne(percentOne(part.irrFlat) ?? 0);
    const body = rerating < 0
      ? <>이 수익률은 PER이 {multiple(part.peNow)}에서 {multiple(part.exitPE)}로 <b>내려간다고 본 값</b>입니다. PER이 그대로라면 연 {flat}입니다.</>
      : rerating > 0
        ? <>이 수익률은 PER이 {multiple(part.peNow)}에서 {multiple(part.exitPE)}로 <b>올라간다고 본 값</b>입니다. PER이 그대로라면 연 {flat}입니다.</>
        : <>이 수익률은 PER이 지금({multiple(part.peNow)})과 같다고 본 값입니다.</>;
    items.push({ key: "rerating", body, target: SECTION_IDS.parts, label: "①" });
  }
  const pe = view.results.reverse.breakEvenPE[String(horizon)];
  if (pe && pe.status === "available") {
    if (pe.state === "not_needed") {
      items.push({ key: "breakEven", body: <>배당만으로 지금 가격을 회수할 수 있어, 손실이 나지 않기 위한 PER 조건이 없습니다.</>, target: SECTION_IDS.reverse, label: "② 지금 가격이 전제하는 것" });
    } else if (pe.exitPE) {
      const value = Number(pe.exitPE);
      const range = rangeOf(view, "pe");
      const where = !range ? "" : value < range.min ? ` 과거 10년 최저(${multiple(range.min)})보다 낮습니다.`
        : value > range.max ? ` 과거 10년 최고(${multiple(range.max)})보다 높습니다.`
          : ` 과거 10년 범위(${multiple(range.min)}~${multiple(range.max)}) 안이며, 보통(${multiple(range.median)})보다 ${value < range.median ? "낮습니다" : "높습니다"}.`;
      items.push({ key: "breakEven", body: <>손실이 나지 않으려면 {horizon}년 뒤 PER <b>{multiple(pe.exitPE)}</b>면 됩니다.{where}</>, target: SECTION_IDS.reverse, label: "② 지금 가격이 전제하는 것" });
    }
  }
  const noGrowth = projection?.noGrowth;
  if (noGrowth && noGrowth.status === "available") {
    const basis = `내 기준 연 ${plainOne(percentOne(noGrowth.requiredReturn) ?? 0).replace(".0%", "%")}로 계산`;
    items.push({ key: "noGrowth", body: noGrowth.hasGrowthShare
      ? <>지금 가격의 <b>{cashPerHundred(noGrowth.growthShare)}%</b>는 앞으로의 성장에 거는 몫입니다({basis}).</>
      : <>성장이 없어도 지금 가격이 설명됩니다({basis}).</>, target: SECTION_IDS.noGrowth, label: "② 성장이 없다면" });
  } else if (noGrowth && noGrowth.status === "unavailable" && noGrowth.reason.code === "criteria_not_set") {
    items.push({ key: "noGrowth", body: <>내 기준(원하는 최소 수익률)을 정하면, 지금 가격 중 성장에 거는 몫을 보여 드립니다.</>, target: SECTION_IDS.noGrowth, label: "② 성장이 없다면" });
  }
  const cash = view.results.cashConversion;
  if (cash && cash.status === "available") {
    const span = cashSpan(cash.years ?? []);
    items.push({ key: "cash", body: Number(cash.ratio) < 0
      ? <>{span} 순이익은 플러스였지만 설비투자를 뺀 현금은 마이너스였습니다.</>
      : <>{span} 순이익 100당 현금 <b>{cashPerHundred(cash.ratio)}</b>이 남았습니다.</>, target: SECTION_IDS.cash, label: "③ 이익이 현금으로 남았나" });
  }
  return items;
}

export function GlanceSection({ items }: { items: GlanceItem[] }) {
  if (!items.length) return null;
  return (
    <section className="surface surface--group price-glance" aria-labelledby="price-glance-title">
      <h3 id="price-glance-title">한눈에 보기</h3>
      <ol>
        {items.map(item => (
          <li key={item.key}>{item.body} <button className="price-glance__link" type="button" onClick={() => scrollToSection(item.target)}>{item.label}</button></li>
        ))}
      </ol>
      <p className="price-meta">아래 계산을 요약한 것이며, 사고팔라는 의견이나 판정이 아닙니다.</p>
    </section>
  );
}
