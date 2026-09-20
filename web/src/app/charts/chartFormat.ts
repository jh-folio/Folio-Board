/** 금액·분기 표기의 단일 출처.
 *
 *  같은 한국 회사가 기업분석 차트에서는 `₩79.1T`, 워치리스트에서는 `79.1조`로 읽혔다.
 *  단위 체계(조·억 vs T·B·M)를 고르는 규칙이 두 곳에 따로 있어서였다 — 규칙을 여기 하나로
 *  두고, 화면마다 다른 것(통화 기호 유무·소수 자릿수)만 함수로 나눈다.
 *
 *  새 차트는 이 파일의 함수를 쓴다. 화면 안에서 단위 접기를 다시 쓰지 않는다.
 */

interface AmountUnit {
  limit: number;
  suffix: string;
}

/** 조·억. 원과 엔은 이 단위로 읽는다 — 삼성전자 133,873,444,000,000은 자릿수만으로는 읽히지 않는다. */
const KOREAN_UNITS: readonly AmountUnit[] = [
  { limit: 1e12, suffix: "조" },
  { limit: 1e8, suffix: "억" },
];

const LATIN_UNITS: readonly AmountUnit[] = [
  { limit: 1e12, suffix: "T" },
  { limit: 1e9, suffix: "B" },
  { limit: 1e6, suffix: "M" },
];

function normalizeCurrency(currency?: string): string {
  const code = String(currency || "USD").toUpperCase();
  return code === "KRX" ? "KRW" : code;
}

function usesKoreanUnits(currency?: string): boolean {
  const code = normalizeCurrency(currency);
  return code === "KRW" || code === "JPY";
}

export function currencySymbol(currency?: string): string {
  const code = normalizeCurrency(currency);
  if (code === "KRW") return "₩";
  if (code === "JPY") return "¥";
  if (code === "EUR") return "€";
  if (code === "GBP") return "£";
  return "$";
}

/** 통화 기호 없는 짧은 금액 — 패널 본문·표 셀용(`79.1조`, `5.6B`, `8.13M`). */
export function compactAmount(value: number | null | undefined, currency = "USD"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const korean = usesKoreanUnits(currency);
  const locale = korean ? "ko-KR" : "en-US";
  const unit = (korean ? KOREAN_UNITS : LATIN_UNITS).find((candidate) => Math.abs(value) >= candidate.limit);
  if (!unit) return value.toLocaleString(locale, { maximumFractionDigits: 0 });
  return `${(value / unit.limit).toLocaleString(locale, { maximumFractionDigits: korean ? 1 : 2 })}${unit.suffix}`;
}

/** 통화 기호를 붙인 차트 축·판독값(`₩79.1조`, `$1.5B`). 소수 한 자리로 고정한다 —
 *  눈금이 `1B`, `1.5B`, `2B`로 자릿수가 들쭉날쭉하면 축이 정돈돼 보이지 않는다. */
export function chartMoney(value: number | null | undefined, currency?: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  const symbol = currencySymbol(currency);
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const unit = (usesKoreanUnits(currency) ? KOREAN_UNITS : LATIN_UNITS).find((candidate) => abs >= candidate.limit);
  if (!unit) return `${sign}${symbol}${abs.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
  return `${sign}${symbol}${(abs / unit.limit).toFixed(1)}${unit.suffix}`;
}

/** 분기 키(2026-06-30)를 축 라벨로 — 레퍼런스와 같은 "26년 6월" 형태. */
export function quarterAxisLabel(quarter: string | undefined): string {
  const text = String(quarter || "");
  if (!/^\d{4}-\d{2}/.test(text)) return "";
  return `${text.slice(2, 4)}년 ${Number(text.slice(5, 7))}월`;
}
