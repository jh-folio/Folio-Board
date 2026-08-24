import { useEffect, useState } from "react";
import { getJson, MARKET_KO_LABELS } from "../../api";

export const STORY_MARKETS = ["us", "kr", "europe", "jp"] as const;
export type StoryMarket = (typeof STORY_MARKETS)[number];
export const STORY_MARKET_LABELS: Record<StoryMarket, string> = {
  us: MARKET_KO_LABELS.us, kr: MARKET_KO_LABELS.kr,
  europe: MARKET_KO_LABELS.europe, jp: MARKET_KO_LABELS.jp,
};

type StoryShareRow = {
  label: string;
  count: number;
  share: number;
  isOther?: boolean;
  previousShare?: number | null;
  deltaPp?: number | null;
};

type StorySharePayload = {
  date?: string;
  market?: string;
  collectedCount?: number;
  previousDate?: string;
  previousDates?: string[];
  previousSessionCount?: number;
  previousCollectedCount?: number;
  items?: StoryShareRow[];
  warnings?: string[];
  smallSample?: boolean;
  minConfidentSample?: number;
  driverBasis?: { kind?: string; count?: number };
};

/** 비교 기준을 정확히 말한다. "직전 거래일 대비"는 창이 하루일 때만 맞는 말이다. */
export function comparisonLabel(payload: StorySharePayload): string {
  const sessions = payload.previousSessionCount || 0;
  if (!sessions) return "비교 기준 없음";
  if (sessions === 1) return "직전 거래일 대비";
  const collected = payload.previousCollectedCount;
  const volume = typeof collected === "number" ? ` ${collected}건` : "";
  return `직전 ${sessions}거래일 합산${volume} 대비`;
}

// 순위별 고정 팔레트 + "그 외"는 회색. 색이 의미(순위)를 담는다.
const SEGMENT_TONES = ["blue", "teal", "gold", "purple"] as const;

function segmentTone(row: StoryShareRow, index: number): string {
  return row.isOther ? "other" : SEGMENT_TONES[index] || "other";
}

/** ▲ +13%p / ▼ -9%p / ─. 1%p 미만 이동은 유지로 본다. */
export function deltaText(row: StoryShareRow): { text: string; tone: "up" | "down" | "flat" } {
  const delta = row.deltaPp;
  if (delta == null || !Number.isFinite(delta)) return { text: "", tone: "flat" };
  if (Math.abs(delta) < 1) return { text: "─", tone: "flat" };
  return delta > 0
    ? { text: `▲ +${Math.round(delta)}%p`, tone: "up" }
    : { text: `▼ ${Math.round(delta)}%p`, tone: "down" };
}

export function StoryShare({ market }: { market: StoryMarket }) {
  const [payload, setPayload] = useState<StorySharePayload | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    setError("");
    getJson<StorySharePayload>(`/api/dashboard/story-share?market=${market}`)
      .then((data) => { if (alive) setPayload(data); })
      .catch((err) => { if (alive) setError(err instanceof Error ? err.message : "이야기 비중을 불러오지 못했습니다."); });
    return () => { alive = false; };
  }, [market]);

  if (error) return <p className="story-share__note">{error}</p>;
  if (!payload) return <p className="story-share__note">이야기 비중을 계산하는 중입니다.</p>;
  const rows = payload.items || [];
  if (!rows.length) {
    return <p className="story-share__note">이 날짜에 수집된 시장 뉴스가 없습니다. RSS 수집 후 다시 확인해 주세요.</p>;
  }

  return (
    <div className="story-share">
      <div className="story-share__head">
        <span className="story-share__title">오늘의 이야기 비중</span>
        <span className="story-share__meta">
          수집 기사 {payload.collectedCount || 0}건 · {comparisonLabel(payload)}
        </span>
      </div>
      {payload.smallSample && (
        // 표본이 적으면 기사 한두 건이 비중을 수십 %p 움직인다. 그 흔들림을
        // 변화로 읽지 않도록 밝힌다.
        <p className="story-share__note">
          수집량이 적어({payload.collectedCount || 0}건) 비중과 증감이 크게 흔들릴 수 있습니다.
        </p>
      )}
      <div className="story-share__bar" role="img" aria-label={`이야기 비중: ${rows.map((row) => `${row.label} ${Math.round(row.share * 100)}%`).join(", ")}`}>
        {rows.map((row, index) => (
          <span key={row.label} data-tone={segmentTone(row, index)} style={{ width: `${Math.max(row.share * 100, 1)}%` }} />
        ))}
      </div>
      <ul className="story-share__legend">
        {rows.map((row, index) => {
          const delta = deltaText(row);
          return (
            <li key={row.label} data-other={row.isOther ? "true" : undefined}>
              <span className="story-share__dot" data-tone={segmentTone(row, index)} aria-hidden="true" />
              <span className="story-share__label">{row.label}</span>
              <span className="story-share__count">{row.count}건</span>
              <span className="story-share__share">{Math.round(row.share * 100)}%</span>
              <span className="story-share__delta" data-tone={delta.tone}>{row.isOther ? "" : delta.text}</span>
            </li>
          );
        })}
      </ul>
      {/* 동인은 고정 어휘표다. 표에 없는 주제는 아무리 크게 보도돼도 이 막대에 나타나지
          않으므로, 무엇을 보고 있는지 밝힌다. */}
      <p className="story-share__note">
        수집된 뉴스 기준 규칙 계산 · 브리핑과 독립 · 비중 이동은 보도량 변화일 뿐 내용 변화가 아닙니다
        {payload.driverBasis?.count ? ` · 고정된 ${payload.driverBasis.count}개 동인 기준` : ""}
      </p>
    </div>
  );
}
