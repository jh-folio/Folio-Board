import { ApiRequestError } from "../../api";

/** Backtest route errors are user-facing; fetch's technical URL/status message is not. */
export function backtestErrorMessage(reason: unknown, fallback: string): string {
  if (!(reason instanceof ApiRequestError)) return reason instanceof Error && reason.message ? reason.message : fallback;
  const payload = reason.payload;
  if (payload && typeof payload === "object") {
    const detail = (payload as Record<string, unknown>).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (detail && typeof detail === "object") {
      const nested = detail as Record<string, unknown>;
      if (typeof nested.message === "string" && nested.message.trim()) return nested.message;
      if (typeof nested.detail === "string" && nested.detail.trim()) return nested.detail;
    }
  }
  return fallback;
}
