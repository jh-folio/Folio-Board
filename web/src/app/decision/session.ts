// Ephemeral references only; reloading the browser clears this state.
let portfolioBasisId: string | null = null;
export const currentPortfolioBasisId = () => portfolioBasisId;
export function rememberPortfolioBasis(id: string) { portfolioBasisId = id; }
export function clearPortfolioBasis() { portfolioBasisId = null; }
