import type { CSSProperties } from "react";
import {
  NOTICE_TEXT, SCENARIO_NAMES, SCENARIO_ORDER, atLeastRequired, decompositionCards, irrText, irrValue, money, multiple, pct, pctPlain, pctSigned,
  rangePosition, reasonText, rowFor, scaleLayout, toNumber,
} from "./format";
import type { Criteria, HistoryRow, MyAssumptions, Projection, ScenarioRow, SnapshotView } from "./types";

const at = (left: number): CSSProperties => ({ left: `${left.toFixed(2)}%` });
const ROW_STEP = 22;
const align = (left: number): CSSProperties => ({ transform: left < 8 ? "none" : left > 92 ? "translateX(-100%)" : "translateX(-50%)" });

/** 한 숫자 줄: 말이 아니라 숫자 자체를 읽는 사람을 위해 카드와 같은 값을 글자로 함께 둔다. */
export function ScaleBar({ rows, horizon, selected, goal }: { rows: ScenarioRow[]; horizon: number; selected: number; goal: number | null }) {
  const values = SCENARIO_ORDER.map(key => ({ key, label: SCENARIO_NAMES[key].name, value: irrValue(rowFor(rows, key, horizon)) }))
    .filter((item): item is { key: typeof SCENARIO_ORDER[number]; label: string; value: number } => item.value !== null)
    .map(item => ({ ...item, value: item.value * 100 }));
  if (values.length < 3) return null;
  const layout = scaleLayout(values, goal);
  const summary = `${horizon}년 보유 시 연 수익률: ${values.map(item => `${item.label} ${pct(item.value / 100)}`).join(", ")}${goal === null ? "" : `. 내 기준 연 ${pct(goal / 100, 0)}`}`;
  const maxRow = Math.max(...layout.points.map(point => point.row));
  return (
    <div className="price-hr" role="img" aria-label={summary} style={{ marginTop: `${6 + maxRow * ROW_STEP}px` }}>
      <div className="price-hr__base" />
      <div className="price-hr__span" style={{ left: `${layout.spanLeft.toFixed(2)}%`, width: `${(layout.spanRight - layout.spanLeft).toFixed(2)}%` }} />
      {layout.ticks.filter(tick => layout.goalLeft === null || Math.abs(tick.left - layout.goalLeft) >= 12).map(tick => (
        <span key={tick.value}>
          <div className="price-hr__tick" style={at(tick.left)} />
          <span className="price-hr__t price-hr__t--tick" style={at(tick.left)}>{tick.value}%</span>
        </span>
      ))}
      {layout.goalLeft !== null && (
        <>
          <div className="price-hr__goal" style={at(layout.goalLeft)} />
          <span className="price-hr__t price-hr__t--goal" style={{ ...at(layout.goalLeft), ...align(layout.goalLeft) }}>내 기준 {pct(goal! / 100, 0)}</span>
        </>
      )}
      {layout.points.map((point, index) => (
        <span key={point.key}>
          <div className={`price-hr__pt${index === selected ? " price-hr__pt--base" : ""}`} style={at(point.left)} />
          {point.row > 0 && <div className="price-hr__lead" style={{ ...at(point.left), top: `${14 - point.row * ROW_STEP}px`, height: `${10 + point.row * ROW_STEP}px` }} />}
          <span className={`price-hr__t ${index === selected ? "price-hr__t--base" : "price-hr__t--sc"}`} style={{ ...at(point.left), ...align(point.left), top: `${(index === selected ? -2 : 0) - point.row * ROW_STEP}px` }}>
            {point.label} {pct(point.value / 100)}
          </span>
        </span>
      ))}
    </div>
  );
}

export function ScenarioCards({ rows, horizon, selected, required, onSelect }: { rows: ScenarioRow[]; horizon: number; selected: number; required: string | null; onSelect: (index: number) => void }) {
  return (
    <div className="price-cards" role="group" aria-label="시나리오 선택: 누르면 막대에서 강조">
      {SCENARIO_ORDER.map((key, index) => {
        const row = rowFor(rows, key, horizon);
        const value = irrValue(row);
        return (
          <button key={key} type="button" className="price-card" aria-pressed={index === selected} onClick={() => onSelect(index)}>
            <b>{SCENARIO_NAMES[key].name}</b>
            <small>{SCENARIO_NAMES[key].short}</small>
            <strong>{value === null ? irrText(row) : `연 ${pct(value)}`}</strong>
            {atLeastRequired(row, required) !== null && <span>기준보다 {atLeastRequired(row, required) ? "높음" : "낮음"}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function ScenarioTable({ rows, horizon }: { rows: ScenarioRow[]; horizon: number }) {
  return (
    <table className="price-table">
      <caption className="sr-only">보수·기본·낙관 가정과 5년·10년 보유 시 연 수익률</caption>
      <thead>
        <tr>
          <th scope="col">가정</th><th scope="col">이익 성장 (연)</th><th scope="col">끝날 때 PER</th><th scope="col">배당성향</th>
          <th scope="col" className={horizon === 5 ? "is-sel" : undefined}>5년 보유 (연)</th>
          <th scope="col" className={horizon === 10 ? "is-sel" : undefined}>10년 보유 (연)</th>
        </tr>
      </thead>
      <tbody>
        {SCENARIO_ORDER.map(key => {
          const five = rowFor(rows, key, 5);
          const ten = rowFor(rows, key, 10);
          const ref = five && five.status === "available" ? five : ten && ten.status === "available" ? ten : null;
          const names = SCENARIO_NAMES[key];
          return (
            <tr key={key} className={key === "base" ? "is-base" : undefined}>
              <th scope="row">{names.name}<small>{names.note}</small>
                {ref && <span className="price-table__mobile">성장 {pct(ref.g)} · PER {multiple(ref.exitPE)} · 배당 {pct(ref.payout, 0)}</span>}
              </th>
              <td className="is-assume">{ref ? pct(ref.g) : "—"}</td>
              <td className="is-assume">{ref ? multiple(ref.exitPE) : "—"}</td>
              <td className="is-assume">{ref ? pct(ref.payout, 0) : "—"}</td>
              <td className={`is-ret${horizon === 5 ? " is-sel" : ""}`} data-label="5년">{irrText(five)}</td>
              <td className={`is-ret${horizon === 10 ? " is-sel" : ""}`} data-label="10년">{irrText(ten)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function MiniRange({ label, value, valueText, min, max, median, unit }: { label: string; value: number; valueText: string; min: number; max: number; median: number; unit: (v: number) => string }) {
  const position = rangePosition(value, min, max);
  const sentence = `과거 10년 범위(${unit(min)}~${unit(max)})${position.where}`;
  return (
    <div className="price-range" role="img" aria-label={`${label} ${valueText}. ${sentence}. 보통 ${unit(median)}`}>
      <span className="price-range__pos">{sentence}</span>
      <div className="price-range__bar">
        <div className="price-range__base" />
        <div className="price-range__span" style={{ left: `${position.minLeft.toFixed(2)}%`, width: `${(position.maxLeft - position.minLeft).toFixed(2)}%` }} />
        <div className="price-range__mark" style={at(position.valueLeft)} />
        <span className="price-range__mlabel" style={{ ...at(position.valueLeft), ...align(position.valueLeft) }}>필요 {valueText}</span>
      </div>
      <div className="price-range__legend">
        <span style={at(position.minLeft)}>{unit(min)}</span>
        <span style={{ left: `${((position.minLeft + position.maxLeft) / 2).toFixed(2)}%` }}>과거 10년</span>
        <span style={at(position.maxLeft)}>{unit(max)}</span>
      </div>
    </div>
  );
}

function rangeOf(view: SnapshotView, key: "growth" | "pe" | "netMargin") {
  const block = view.results.ranges[key];
  const values = (block.values || []).map(item => Number(item.value)).filter(Number.isFinite);
  return values.length ? { min: Math.min(...values), max: Math.max(...values), median: toNumber(block.p50) ?? values[0] } : null;
}

/** 지금 가격이 전제하는 것. 문장 + 과거 범위 위의 위치. 달성 가능성은 판정하지 않는다. */
export function RequirementSection({ view, projection, horizon, onSetCriteria }: { view: SnapshotView; projection: Projection | null; horizon: number; onSetCriteria: () => void }) {
  const key = String(horizon);
  const reverse = view.results.reverse;
  const pe = reverse.breakEvenPE[key];
  const margin = reverse.breakEvenMargin[key];
  const growthRange = rangeOf(view, "growth");
  const peRange = rangeOf(view, "pe");
  const marginRange = rangeOf(view, "netMargin");
  const required = projection?.criteria?.requiredReturn ?? null;
  const need = projection?.requirement;
  const needGrowth = need?.growth?.[key];
  return (
    <div className="price-reverse">
      {pe && pe.status === "available" && pe.state === "needed" && pe.exitPE && (
        <div className="price-rev">
          <p>손실이 나지 않으려면(손익분기) {horizon}년 뒤 주가가 그해 이익의 <strong>{multiple(pe.exitPE)}</strong>(PER) 이상이어야 합니다.</p>
          {peRange && <MiniRange label="손익분기 PER" value={Number(pe.exitPE)} valueText={multiple(pe.exitPE)} min={peRange.min} max={peRange.max} median={peRange.median} unit={v => multiple(v)} />}
        </div>
      )}
      {pe && pe.status === "available" && pe.state === "not_needed" && (
        <div className="price-rev"><p>배당만으로 지금 가격을 회수할 수 있어, 손실이 나지 않기 위한 PER 조건이 필요 없습니다.</p></div>
      )}
      {pe && pe.status === "unavailable" && <div className="price-rev"><p>손익분기 PER은 계산하지 못했습니다 — {reasonText(pe.reason.code)}.</p></div>}
      {required !== null ? (
        needGrowth && needGrowth.status === "available" && needGrowth.value ? (
          <div className="price-rev">
            <p>내 기준 연 {pctPlain(required, Number(required) % 1 === 0 ? 0 : 1)}를 얻으려면 이익이 매년 <strong>{pct(needGrowth.value)}</strong> 자라야 합니다.</p>
            {growthRange && <MiniRange label="필요 성장률" value={Number(needGrowth.value)} valueText={pct(needGrowth.value)} min={growthRange.min} max={growthRange.max} median={growthRange.median} unit={v => pct(v)} />}
          </div>
        ) : needGrowth && needGrowth.status === "available" && needGrowth.range ? (
          <div className="price-rev"><p>내 기준을 얻는 데 필요한 이익 성장률이 계산 범위({needGrowth.range === "above_range" ? "연 100% 초과" : "연 −50% 미만"})를 벗어납니다.</p></div>
        ) : (
          <div className="price-rev"><p>내 기준에 필요한 이익 성장률은 계산하지 못했습니다.</p></div>
        )
      ) : (
        <div className="price-rev">
          <p>원하는 수익률을 정하면, 그걸 얻는 데 필요한 이익 성장률을 보여 드립니다.</p>
          <div><button className="btn btn--sm" type="button" onClick={onSetCriteria}>기준 정하기</button></div>
        </div>
      )}
      {margin && margin.status === "available" && margin.margin !== null && (
        <div className="price-rev">
          <p>손실이 나지 않으려면(손익분기) {horizon}년 뒤 매출에서 남는 이익(순이익률)이 <strong>{pct(margin.margin)}</strong> 이상이어야 합니다. <span className="price-meta">(지금 {pct(margin.currentMargin, 0)})</span></p>
          {marginRange && <MiniRange label="손익분기 순이익률" value={Number(margin.margin)} valueText={pct(margin.margin)} min={marginRange.min} max={marginRange.max} median={marginRange.median} unit={v => pct(v)} />}
        </div>
      )}
    </div>
  );
}

const DEC_COLOR: Record<string, string> = { R: "price-c1", M: "price-c3", S: "price-c5" };

export function DecompositionSection({ view, selected, onSelect }: { view: SnapshotView; selected: string | null; onSelect: (key: string | null) => void }) {
  const block = view.results.decomposition;
  if (block.status !== "available") return <p className="price-note">과거 이익 성장의 출처는 계산하지 못했습니다 — {reasonText(block.reason.code)}.</p>;
  const recent = block.windows[block.windows.length - 1];
  const cards = decompositionCards(recent.annual);
  const total = cards.reduce((sum, card) => sum + card.weight, 0) || 1;
  const summary = `매출이 늘어서 연 ${pctSigned(cards[0].value)}, 이익률이 좋아져서 연 ${pctSigned(cards[1].value)}, 주식 수가 줄어서 연 ${pctSigned(cards[2].value)}`;
  return (
    <>
      <p>주당이익이 매년 <strong>{pct(Math.exp(Number(recent.annual.total)) - 1)}</strong>씩 늘었습니다. 나눠 보면:</p>
      <div className="price-dec">
        <div className="price-dec__cards" role="group" aria-label="성장 요인 선택: 누르면 막대에서 강조">
          {cards.map(card => (
            <button key={card.key} type="button" className="price-dec__card" aria-pressed={selected === card.key} onClick={() => onSelect(selected === card.key ? null : card.key)}>
              <i className={DEC_COLOR[card.key]} /><span>{card.title}</span><strong>{pctSigned(card.value)}</strong>
            </button>
          ))}
        </div>
        <div className="price-dec__bar" role="img" aria-label={summary}>
          {cards.map(card => <span key={card.key} className={`${DEC_COLOR[card.key]}${selected !== null && selected !== card.key ? " is-dim" : ""}`} style={{ width: `${((card.weight / total) * 100).toFixed(1)}%` }} />)}
        </div>
      </div>
      {block.notes.map(note => (
        <p key={note.code} className="price-note">
          {note.code === "margin_majority"
            ? "과거 주당이익 성장의 절반 이상이 마진 개선에서 왔습니다. 마진은 계속 오를 수 없으므로 같은 성장률이 되풀이되기 어려울 수 있습니다."
            : "성장의 상당 부분이 주식 수 감소(자사주 매입 등)에서 왔습니다."}
        </p>
      ))}
    </>
  );
}

export function SourcesDetails({ view }: { view: SnapshotView }) {
  const { results, inputSummary } = view;
  const base = results.base.status === "available" ? results.base : null;
  const notices = [...results.support.notices, ...results.notices];
  const lines = [
    `기준 가격 ${money(inputSummary.price.value, inputSummary.price.currency)} (${inputSummary.price.sessionDate} 종가, 분할만 반영한 실제 종가)`,
    base ? `최근 회계연도 ${base.fiscalYear}(${base.periodEnd} 마감) 희석 주당이익 ${base.eps0} · 기준 가격과 ${base.monthsBeforeSession}개월 차이` : "최근 회계연도 주당이익을 확인하지 못했습니다.",
    `계산 방법 ${view.methodVersion} · 스냅샷 ${view.snapshotId}`,
  ];
  return (
    <>
      {lines.map(line => <p key={line}>{line}</p>)}
      {(["growth", "pe", "payout", "netMargin"] as const).map(key => {
        const block = results.ranges[key];
        const names = { growth: "이익 성장", pe: "끝날 때 PER", payout: "배당성향", netMargin: "순이익률" }[key];
        if (block.status !== "available") return <p key={key}>{names}: 과거 범위를 만들지 못했습니다 — {reasonText(block.reason?.code)}.</p>;
        const fmt = key === "pe" ? (v?: string) => multiple(v) : (v?: string) => pct(v);
        return <p key={key}>{names} 과거 범위(표본 {block.n}개): 낮은 편 {fmt(block.p25)} · 중간값 {fmt(block.p50)} · 높은 편 {fmt(block.p75)}</p>;
      })}
      {notices.map(code => NOTICE_TEXT[code] && <p key={code}>{NOTICE_TEXT[code]}</p>)}
    </>
  );
}

const CHANGE_TEXT: Record<string, string> = {
  price_moved: "종가가 바뀜", new_fiscal_year: "새 회계연도 공시", restated: "공시 정정", share_event_added: "주식 수 변화 사건 추가",
  dcf_assumption_changed: "할인 계산 가정 변경", method_changed: "계산 방법 변경", input_changed: "입력 자료 변경",
};

export function HistoryList({ history, currentId, onOpen }: { history: HistoryRow[]; currentId: string | null; onOpen: (id: string) => void }) {
  return (
    <ul className="price-history">
      {history.map(row => {
        const reasons = [...new Set(row.changeReasons.map(reason => CHANGE_TEXT[reason.code] || reason.code))];
        return (
          <li key={row.snapshotId}>
            <div>
              <strong>{row.asOf}</strong>
              <p className="price-meta">{reasons.length ? reasons.join(" · ") : "첫 계산"}</p>
            </div>
            <span className="price-row">
              {row.reviewCount > 0 && <span className="chip" data-tone="burgundy">다시 볼 필요</span>}
              {row.snapshotId === currentId ? <span className="chip" data-tone="muted">현재</span> : <button className="btn btn--sm" type="button" onClick={() => onOpen(row.snapshotId)}>열기</button>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function CriteriaLine({ projection, criteria, onEdit }: { projection: Projection | null; criteria: Criteria | null; onEdit: () => void }) {
  const set = criteria && (criteria.requiredReturn !== null || criteria.minMarginOfSafety !== null);
  const ret = projection?.verdict.return;
  const mos = projection?.verdict.marginOfSafety;
  return (
    <div className="price-criteria-line">
      <div className="price-verdict">
        {!set && <span className="chip" data-tone="muted">내 기준 없음</span>}
        {set && criteria?.requiredReturn !== null && ret && ret.state !== "unknown" && (
          <span className="chip" data-tone={ret.state === "met" ? "teal" : "burgundy"}>수익률 {ret.state === "met" ? "기준 충족" : "기준 미달"} · {criteria?.holdingYears}년</span>
        )}
        {set && criteria?.requiredReturn !== null && ret && ret.state === "unknown" && <span className="chip" data-tone="muted">수익률 판정 보류</span>}
        {set && criteria?.minMarginOfSafety !== null && mos && (
          mos.state === "unknown"
            ? <span className="chip" data-tone="muted">안전마진 판정 보류</span>
            : <span className="chip" data-tone={mos.state === "met" ? "teal" : "burgundy"}>안전마진 {mos.state === "met" ? "기준 충족" : "기준 미달"}</span>
        )}
      </div>
      <p className="price-meta">
        {set
          ? `내 기준: ${criteria?.requiredReturn !== null ? `연 ${pctPlain(criteria?.requiredReturn)} 이상` : "수익률 정하지 않음"} · 안전마진 ${criteria?.minMarginOfSafety !== null ? `${pctPlain(criteria?.minMarginOfSafety)} 이상` : "정하지 않음"} · 기본 보유 ${criteria?.holdingYears}년`
          : "원하는 수익률과 안전마진을 정하면 비교해 드립니다."}
      </p>
      <button className="btn btn--sm" type="button" onClick={onEdit}>{set ? "기준 편집" : "기준 정하기"}</button>
    </div>
  );
}

export function MyAssumptionsResult({ mine, base, horizon }: { mine: MyAssumptions | null; base: ScenarioRow | undefined; horizon: number }) {
  const row = mine?.rows.find(item => item.horizon === horizon);
  if (!mine || !row || row.status !== "available") return null;
  const baseText = irrText(base);
  return <p className="price-mine">내 가정이면 {horizon}년 보유 시 <strong>연 {row.irrRange ? (row.irrRange === "above_range" ? "100% 초과" : "−99% 미만") : pct(row.irr)}</strong> (기본 가정 {baseText === "계산 불가" ? baseText : `연 ${baseText}`})</p>;
}
