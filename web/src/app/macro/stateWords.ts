/** 0.8 현재 상태 탭의 화면 말. 판정 규칙·enum은 그대로 두고 보이는 이름만 정한다(0.8_PLAN M8). */

export type AxisKey = "growth" | "inflation" | "financial_conditions" | "stress_vulnerability";
export type Market = "US" | "KR";

type AxisView = {
  name: string;
  measure: string;
  /** 왼쪽(적음·낮음)→오른쪽(많음·높음) 순서. 화살표 ↗는 항상 오른쪽 칸 쪽이다. */
  levels: string[];
  /** 오른쪽으로 움직이는 방향 값. 유동성은 금리 상승(rising)이 유동성 감소라 falling이 오른쪽이다. */
  rightward: "rising" | "falling";
  words: Record<string, string>;
  directions: Record<string, string>;
};

export const AXIS_ORDER: AxisKey[] = ["growth", "inflation", "financial_conditions", "stress_vulnerability"];

export const AXIS_VIEW: Record<AxisKey, AxisView> = {
  growth: {
    name: "경기",
    measure: "성장 속도",
    levels: ["contraction", "weak", "moderate", "strong"],
    rightward: "rising",
    words: { contraction: "수축", weak: "부진", moderate: "추세 성장", strong: "호조" },
    directions: { rising: "가속", falling: "둔화", flat: "횡보", mixed: "엇갈림" },
  },
  inflation: {
    name: "물가",
    measure: "상승률",
    levels: ["below_reference", "near_reference", "above_reference", "high"],
    rightward: "rising",
    words: { below_reference: "낮음", near_reference: "2% 부근", above_reference: "높음", high: "매우 높음" },
    directions: { rising: "가속", falling: "둔화", flat: "보합", mixed: "엇갈림" },
  },
  financial_conditions: {
    name: "유동성",
    measure: "돈 빌리기 쉬운 정도",
    levels: ["tight", "neutral", "loose"],
    rightward: "falling",
    words: { loose: "풍부", neutral: "중립", tight: "부족" },
    directions: { rising: "축소", falling: "확대", flat: "보합", mixed: "엇갈림" },
  },
  stress_vulnerability: {
    name: "신용 위험",
    measure: "금융시장 긴장 정도",
    levels: ["normal", "elevated", "high"],
    rightward: "rising",
    words: { normal: "안정", elevated: "주의", high: "경계" },
    directions: { rising: "악화", falling: "개선", flat: "보합", mixed: "엇갈림" },
  },
};

export const HOLD = "판단 보류";

export const levelWord = (axis: AxisKey, level: string | undefined) => AXIS_VIEW[axis].words[level || ""] || HOLD;
export const directionWord = (axis: AxisKey, direction: string | undefined) => AXIS_VIEW[axis].directions[direction || ""] || HOLD;

/** 칸 위 ▼(평균·기준 위치)와 칸 아래 경계 숫자. 위치는 눈금 너비의 백분율. */
type ScaleMarks = { mid: number; midLabel: string; cuts: [number, string][] };

export function scaleMarks(axis: AxisKey, market: Market): ScaleMarks {
  if (axis === "growth") return { mid: 62.5, midLabel: "추세", cuts: [] };
  if (axis === "inflation") return { mid: 37.5, midLabel: "2%", cuts: [[25, "1.5%"], [50, "2.5%"], [75, "4%"]] };
  if (axis === "financial_conditions") {
    return market === "US"
      ? { mid: 50, midLabel: "평균", cuts: [[100 / 3, "+0.25"], [200 / 3, "−0.25"]] }
      : { mid: 50, midLabel: "실질금리 0", cuts: [[100 / 3, "+1%p"], [200 / 3, "−1%p"]] };
  }
  return market === "US"
    ? { mid: 100 / 3, midLabel: "평균", cuts: [[100 / 3, "0"], [200 / 3, "1"]] }
    : { mid: 23.8, midLabel: "5년 중앙값", cuts: [[100 / 3, "70"], [200 / 3, "90"]] };
}

/** 줄 맨 아래 "기준" 설명. 무엇과 비교했고 칸이 어떻게 나뉘는지. */
export function criteria(axis: AxisKey, market: Market): string {
  if (market === "US") {
    return {
      growth: "추세 = 지난 10년 중앙값. 부진·호조는 GDP(추세 ±0.25%p)와 산업생산(추세 ±1%p)이 둘 다 추세를 밑돌거나 웃돌 때이고, 하나만 벗어나면 추세 성장입니다. 수축은 GDP·산업생산이 모두 마이너스이거나 실업률(3개월 평균)이 1년 중 최저보다 0.5%p 이상 오른 경우입니다.",
      inflation: "근원 PCE(식품·에너지 제외) 전년 대비. 2% ±0.5%p가 가운데 칸이고 4%를 넘으면 매우 높음입니다. 연준 목표는 전체 PCE 기준이라 목표 달성 판정이 아닙니다. 방향은 3개월 변화 ±0.3%p.",
      financial_conditions: "위치는 시카고 연준 금융여건지수(0 = 1971년 이후 평균, 낮을수록 풍부)로, 방향은 시장 금리(실효 연방기금금리)의 3개월 변화 ±0.25%p로 정합니다. 두 지표가 반대로 움직이면 엇갈림입니다. 중앙은행의 결정을 뜻하지 않습니다.",
      stress_vulnerability: "세인트루이스 연준 금융스트레스지수(0 = 평균). 0 이하 안정 · 0~1 주의 · 1 초과 경계입니다. 방향은 4주 변화 ±0.25.",
    }[axis];
  }
  return {
    growth: "추세 = 지난 10년 중앙값. 부진·호조는 GDP와 생산이 둘 다 추세를 밑돌거나 웃돌 때이고, 수축은 둘 다 마이너스이거나 실업률이 1년 중 최저보다 크게 오른 경우입니다.",
    inflation: "소비자물가 전년 대비, 한국은행 물가목표 2%를 참고선으로 씁니다. 한 달 수치라 목표 달성 판정이 아닙니다. 방향은 3개월 변화 ±0.3%p.",
    financial_conditions: "위치는 실질 기준금리(기준금리 − 소비자물가 상승률)로 ±1%p 안이면 중립, 방향은 한국은행 기준금리의 3개월 변화 ±0.25%p입니다. 원/달러 환율은 참고로만 봅니다.",
    stress_vulnerability: "회사채(AA−)와 국고채 3년 금리 차가 최근 5년 중 몇 번째 수준인지(백분위). 70 미만 안정 · 70~90 주의 · 90 이상 경계입니다.",
  }[axis];
}

// 한 줄 요약. 네 판정 값을 정해진 틀에 끼운다(AI가 쓰지 않는다).
const HIGH_SIDE: Record<AxisKey, string[]> = {
  growth: ["strong"],
  inflation: ["above_reference", "high"],
  financial_conditions: ["tight"],
  stress_vulnerability: ["elevated", "high"],
};
const LOW_SIDE: Record<AxisKey, string[]> = {
  growth: ["contraction", "weak"],
  inflation: ["below_reference"],
  financial_conditions: ["loose"],
  stress_vulnerability: ["normal"],
};
const STEM: Record<AxisKey, Record<string, string>> = {
  growth: { contraction: "수축 신호가 나왔", weak: "추세보다 부진하", moderate: "추세 성장 수준이", strong: "호조를 보이" },
  inflation: { below_reference: "2%보다 낮", near_reference: "2% 부근이", above_reference: "2%보다 높", high: "매우 높" },
  financial_conditions: { loose: "풍부하", neutral: "중립이", tight: "부족하" },
  stress_vulnerability: { normal: "안정 단계이", elevated: "주의 단계이", high: "경계 단계이" },
};
const MOVE: Record<AxisKey, Record<string, string>> = {
  growth: { rising: "성장 속도가 빨라지고 있습니다", falling: "성장 속도가 둔화되고 있습니다", flat: "큰 변화 없이 횡보합니다", mixed: "지표는 엇갈립니다" },
  inflation: { rising: "오름세가 가속되고 있습니다", falling: "오름세가 둔화되고 있습니다", flat: "보합입니다" },
  financial_conditions: { rising: "축소되는 중입니다", falling: "확대되는 중입니다", flat: "보합입니다", mixed: "지표가 엇갈립니다" },
  stress_vulnerability: { rising: "악화되는 중입니다", falling: "개선되는 중입니다", flat: "보합입니다" },
};

export type SummaryPart = { axis: AxisKey; subject: string; level: string; rest: string };

/** 굵게 보일 판정 부분(level)과 나머지를 나눠 돌려준다. */
export function summaryPart(axis: AxisKey, level: string | undefined, direction: string | undefined): SummaryPart {
  const subject = { growth: "경기는", inflation: "물가는", financial_conditions: "유동성은", stress_vulnerability: "신용 위험은" }[axis];
  const stem = STEM[axis][level || ""];
  if (!stem) return { axis, subject, level: HOLD, rest: "입니다." };
  const move = MOVE[axis][direction || ""];
  if (!move) return { axis, subject, level: `${stem}`, rest: "고, 방향은 판단 보류입니다." };
  const against = (LOW_SIDE[axis].includes(level || "") && direction === "rising") || (HIGH_SIDE[axis].includes(level || "") && direction === "falling");
  return { axis, subject, level: stem, rest: `${against ? "지만" : "고,"} ${move}.` };
}

export const CYCLE_STEPS = ["contraction_warning", "contraction_confirmed", "recovery_signal", "recovery_confirmed"];
export const CYCLE_WORDS: Record<string, string> = {
  contraction_warning: "수축 경고", contraction_confirmed: "수축 확인", recovery_signal: "회복 신호", recovery_confirmed: "회복 확인",
  none: "뚜렷한 전환 신호 없음", unknown: HOLD,
};
export const CORROBORATION: Record<string, string> = {
  agrees: "보조 지표(CFNAI)와 일치", strongly_agrees: "보조 지표(CFNAI)와 강하게 일치", disagrees: "보조 지표(CFNAI)와 불일치", not_available: "",
};

export const CONFIDENCE: Record<string, string> = { high: "높음", medium: "중간", low: "낮음" };

export const CONFLICTS: Record<string, string> = {
  growthDirectionDisagreement: "지표마다 방향이 다릅니다",
  growthLevelDisagreement: "GDP와 산업생산이 가리키는 칸이 다릅니다",
  auxiliaryInflationDisagreement: "보조 지표(CPI)가 다른 칸을 가리킵니다",
  financialDirectionDisagreement: "시장 금리와 금융여건지수의 움직임이 다릅니다",
  fxContext: "원/달러 환율이 크게 움직였습니다(참고)",
  auxiliaryIntegrityConflict: "보조 지표 원천 값에 충돌이 있습니다",
};

const SIGNAL_WORDS: Record<string, string> = {
  rising: "상승", falling: "하락", flat: "보합", mixed: "엇갈림",
  contraction: "수축", weak: "부진", moderate: "추세 성장", strong: "호조",
  below_reference: "낮음", near_reference: "2% 부근", above_reference: "높음", high: "매우 높음",
};

/** 엇갈림 한 줄: 무엇이 어떻게 다른지까지 적는다(예: 시장 금리 상승 · 금융여건지수 보합). */
export function conflictText(kind: string, signals: Record<string, string | number> | undefined, label: (id: string) => string): string {
  const head = CONFLICTS[kind];
  if (!head) return "";
  const detail = Object.entries(signals || {}).map(([id, value]) => `${label(id)} ${SIGNAL_WORDS[String(value)] || value}`).join(" · ");
  return detail ? `${head}: ${detail}` : head;
}
