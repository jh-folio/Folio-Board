export type MacroPoint = {
  period: string; value: number | null; displayValue: number | null; displayUnit: string;
  metadata: { unit: string; frequency: string; adjustment: string }; metadataId: string;
  availabilityBasis: 'official_release' | 'provider_vintage' | 'local_observed';
  availableAt: string; releasedAt: string | null; vintageDate: string | null; fetchedAt: string;
  firstSeenAt?: string | null; calculationGap?: string | null; revised?: boolean;
};
export type MacroItem = {
  series: { id: string; label: string; axis: string; stage: string; frequency: string; sourceUrl: string; unit: string; transform: string; methodVersion: string; adjustment: string };
  latest: MacroPoint | null; history: MacroPoint[]; direction: string; quality: string[];
  coverage: { firstAvailableAt: string | null }; providerStates: { status: string; last_success: string; error_code: string }[];
  latestRevisedComparison: MacroPoint[]; revisions: MacroPoint[];
  revisionPeriod?: string | null;
  nextRelease?: { date: string; sourceUrl: string; precision: 'date'; basis: 'provider_schedule' } | null;
};
export type MacroSnapshot = { market: 'US' | 'KR'; mode: 'as_of' | 'latest_revised'; date: string; timezone: string; cutoff: string | null; axes: Record<string, string>; items: MacroItem[]; notes: string[] };

export function readMacroLocation() {
  const params = new URLSearchParams(window.location.hash.split('?')[1] || '');
  const market = params.get('market') === 'KR' ? 'KR' : 'US';
  return { market, mode: market === 'US' && params.get('mode') === 'as_of' ? 'as_of' : 'latest_revised', date: params.get('date') || '', series: params.get('series') || '', period: params.get('period') || '', years: params.get('years') === '50' ? '50' : '5' };
}
export function lastMacroView() {
  const saved = sessionStorage.getItem('folio.macro.lastView.v1');
  return saved?.startsWith('#/market-memory/macro') ? saved : '#/market-memory/macro';
}
export function navigateMacro(patch: Partial<ReturnType<typeof readMacroLocation>>) {
  const current = { ...readMacroLocation(), ...patch };
  if ('series' in patch || 'market' in patch) current.period = '';
  if (current.market === 'KR') current.mode = 'latest_revised';
  const params = new URLSearchParams(Object.entries(current).filter(([, value]) => Boolean(value)));
  window.location.hash = `/market-memory/macro?${params}`;
}
