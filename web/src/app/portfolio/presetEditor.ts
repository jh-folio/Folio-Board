import type { Preset } from "./portfolioTypes";

export type PresetDraftRow = {
  readonly key: string;
  readonly ticker: string;
  readonly weightPercent: string;
};

export type PresetDraft = {
  readonly id?: string;
  readonly revision?: number;
  readonly name: string;
  readonly baseCurrency: "USD" | "KRW";
  readonly rows: ReadonlyArray<PresetDraftRow>;
  readonly normalizeWeights: boolean;
};

export type PresetValidation = {
  readonly errors: Readonly<Record<string, string>>;
  readonly total: string | null;
  readonly canNormalize: boolean;
  readonly valid: boolean;
};

export type PresetSavePayload = {
  readonly id?: string;
  readonly expectedRevision?: number;
  readonly name: string;
  readonly baseCurrency: "USD" | "KRW";
  readonly positions: ReadonlyArray<{ ticker: string; weightPercent: string }>;
  readonly normalizeWeights?: true;
};

const TICKER = /^[A-Z0-9][A-Z0-9.-]{0,15}$/;
const DECIMAL = /^(?:\d+(?:\.\d*)?|\.\d+)$/;
const MAX_DECIMAL_LENGTH = 256;

function expandDecimal(value: string): string {
  const match = /^([+-]?)(\d+)(?:\.(\d*))?(?:e([+-]?\d+))?$/i.exec(value);
  if (!match) return value;
  const [, sign, whole, fraction = "", exponentText] = match;
  const exponent = Number(exponentText || "0");
  if (!Number.isSafeInteger(exponent)) return value;
  const digits = `${whole}${fraction}` || "0";
  const point = whole.length + exponent;
  const unsigned = point <= 0 ? `0.${"0".repeat(-point)}${digits}` : point >= digits.length ? `${digits}${"0".repeat(point - digits.length)}` : `${digits.slice(0, point)}.${digits.slice(point)}`;
  return `${sign === "-" ? "-" : ""}${unsigned}`;
}

function displayPercent(value: number): string {
  if (!Number.isFinite(value)) return "";
  // Shift the JSON number's shortest decimal representation instead of multiplying a
  // binary float. This keeps a reopened preset from acquiring toFixed artefacts.
  const normalized = expandDecimal(value.toString());
  const negative = normalized.startsWith("-");
  const unsigned = negative ? normalized.slice(1) : normalized;
  const [whole, fraction = ""] = unsigned.split(".");
  const digits = `${whole}${fraction}` || "0";
  const point = whole.length + 2;
  const result = point >= digits.length ? `${digits}${"0".repeat(point - digits.length)}` : `${digits.slice(0, point)}.${digits.slice(point)}`;
  return normalizePercentInput(`${negative ? "-" : ""}${result}`);
}

export function normalizePercentInput(value: string): string {
  const trimmed = value.trim();
  if (trimmed.length > MAX_DECIMAL_LENGTH) return trimmed;
  if (!DECIMAL.test(trimmed)) return trimmed;
  const [wholeRaw, fractionRaw = ""] = trimmed.replace(/^\./, "0.").split(".");
  const whole = wholeRaw.replace(/^0+(?=\d)/, "") || "0";
  const fraction = fractionRaw.replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole;
}

function decimalParts(value: string): { digits: bigint; scale: number } | null {
  const normalized = normalizePercentInput(value);
  if (normalized.length > MAX_DECIMAL_LENGTH || !DECIMAL.test(normalized)) return null;
  const [whole, fraction = ""] = normalized.split(".");
  return { digits: BigInt(`${whole}${fraction}`), scale: fraction.length };
}

function canonicalTicker(value: string): string {
  const ticker = value.trim().toUpperCase();
  if (/^\d{6}$/.test(ticker)) return `${ticker}.KS`;
  if (/\.(KS|KQ|T|AS)$/.test(ticker)) return ticker;
  return ticker.replace(/\./g, "-");
}

function decimalTotal(values: ReadonlyArray<string>): string | null {
  const parsed = values.map(decimalParts);
  if (parsed.some((item) => item === null)) return null;
  const valid = parsed as Array<{ digits: bigint; scale: number }>;
  const scale = valid.reduce((maximum, item) => Math.max(maximum, item.scale), 0);
  const amount = valid.reduce((sum, item) => sum + item.digits * (10n ** BigInt(scale - item.scale)), 0n);
  const raw = amount.toString().padStart(scale + 1, "0");
  if (scale === 0) return raw;
  return `${raw.slice(0, -scale)}.${raw.slice(-scale)}`.replace(/\.?0+$/, "");
}

function equalsHundred(total: string | null): boolean {
  const parsed = total ? decimalParts(total) : null;
  if (!parsed) return false;
  const expected = 100n * (10n ** BigInt(parsed.scale));
  const difference = parsed.digits >= expected ? parsed.digits - expected : expected - parsed.digits;
  // API reads legacy fractional JSON numbers. Three equal thirds can therefore
  // display as 99.99999999999999%; accept the same 1e-9 percentage tolerance
  // as the server, without mutating the user's underlying decimal strings.
  return difference * 1_000_000_000n <= 10n ** BigInt(parsed.scale);
}

export function blankPresetDraft(): PresetDraft {
  return { name: "", baseCurrency: "USD", rows: [], normalizeWeights: false };
}

export function draftFromPreset(preset: Pick<Preset, "id" | "revision" | "name" | "baseCurrency" | "positions">): PresetDraft {
  return {
    id: preset.id,
    revision: preset.revision,
    name: preset.name,
    baseCurrency: preset.baseCurrency === "KRW" ? "KRW" : "USD",
    rows: preset.positions.map((position, index) => ({
      key: `${preset.id}-${index}`,
      ticker: position.ticker,
      weightPercent: displayPercent(position.weight),
    })),
    normalizeWeights: false,
  };
}

export function draftFromPositions(input: Pick<Preset, "name" | "baseCurrency" | "positions">): PresetDraft {
  return {
    name: input.name,
    baseCurrency: input.baseCurrency === "KRW" ? "KRW" : "USD",
    rows: input.positions.map((position, index) => ({
      key: `draft-${index}`,
      ticker: position.ticker,
      weightPercent: displayPercent(position.weight),
    })),
    normalizeWeights: false,
  };
}

export function clonePresetDraft(preset: Preset): PresetDraft {
  const source = draftFromPreset(preset);
  return { ...source, id: undefined, revision: undefined, name: `${source.name} 복사본` };
}

export function validatePresetDraft(draft: PresetDraft): PresetValidation {
  const errors: Record<string, string> = {};
  if (!draft.name.trim()) errors.name = "프리셋 이름을 입력하세요.";
  if (draft.baseCurrency !== "USD" && draft.baseCurrency !== "KRW") errors.baseCurrency = "기준 통화는 USD 또는 KRW여야 합니다.";

  const seen = new Set<string>();
  for (const [index, row] of draft.rows.entries()) {
    const ticker = row.ticker.trim().toUpperCase();
    const weight = normalizePercentInput(row.weightPercent);
    if (!ticker) errors[`row-${index}-ticker`] = "종목 코드를 입력하세요.";
    else if (!TICKER.test(ticker) || /[.-]$|\.\.|--|\.-|-\./.test(ticker)) errors[`row-${index}-ticker`] = "최대 16자의 영문·숫자와 . 또는 -만 사용할 수 있습니다.";
    else if (seen.has(canonicalTicker(ticker))) errors[`row-${index}-ticker`] = "같은 종목이 두 번 있습니다.";
    else seen.add(canonicalTicker(ticker));
    const decimal = decimalParts(weight);
    if (!weight) errors[`row-${index}-weight`] = "목표 비중을 입력하세요.";
    else if (!decimal) errors[`row-${index}-weight`] = "0 이상의 숫자를 입력하세요.";
  }

  const total = draft.rows.length ? decimalTotal(draft.rows.map((row) => normalizePercentInput(row.weightPercent))) : "0";
  const canNormalize = Boolean(total && decimalParts(total)?.digits && !equalsHundred(total));
  if (draft.rows.length && total !== null && !equalsHundred(total) && !draft.normalizeWeights) {
    errors.total = `합계가 ${total}%입니다. 100%로 맞추거나 정규화를 선택하세요.`;
  }
  if (draft.normalizeWeights && !canNormalize) {
    errors.total = "정규화하려면 합계가 0%보다 큰 유효한 비중이 필요합니다.";
  }
  return { errors, total, canNormalize, valid: Object.keys(errors).length === 0 };
}

export function presetSavePayload(draft: PresetDraft): PresetSavePayload {
  const payload: PresetSavePayload = {
    name: draft.name.trim(),
    baseCurrency: draft.baseCurrency,
    positions: draft.rows.map((row) => ({
      ticker: row.ticker.trim().toUpperCase(),
      weightPercent: normalizePercentInput(row.weightPercent),
    })),
  };
  if (draft.id) return { ...payload, id: draft.id, expectedRevision: draft.revision, ...(draft.normalizeWeights ? { normalizeWeights: true } : {}) };
  return draft.normalizeWeights ? { ...payload, normalizeWeights: true } : payload;
}

export function draftsEqual(left: PresetDraft | null, right: PresetDraft | null): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}
