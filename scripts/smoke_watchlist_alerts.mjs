/**
 * Node smoke for watchlist alert diff (localStorage stub).
 * Run from frontend so Vite resolves extensionless imports:
 *   cd frontend && npx vite-node ../scripts/smoke_watchlist_alerts.mjs
 */
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};

const { diffWatchlistAlerts, companySignals } = await import(
  '../frontend/src/lib/watchlistAlerts.js'
);

const company = {
  id: 42,
  ticker: 'JFC',
  dilution_pass: false,
  debt_to_equity: 1.5,
  div_yield: 0.02,
  check_pass_count: 6,
};

const thresholds = {
  peMax: '',
  pbMax: '',
  roeMin: '',
  yieldMin: '1',
  roicMin: '',
  deMax: '2',
};

const first = diffWatchlistAlerts([company], thresholds);
if (first.events.length !== 0) {
  throw new Error(`expected seed with 0 events, got ${first.events.length}`);
}

const flipped = {
  ...company,
  dilution_pass: true,
  check_pass_count: 5,
};
const second = diffWatchlistAlerts([flipped], thresholds);
const kinds = second.events.map((e) => e.kind).sort().join(',');
if (kinds !== 'checks,dilution') {
  throw new Error(
    `expected checks+dilution flip, got: ${kinds} ${JSON.stringify(second.events)}`,
  );
}

const third = diffWatchlistAlerts([flipped], thresholds);
if (third.events.length !== 0) {
  throw new Error(`expected no events on reload, got ${third.events.length}`);
}

const sig = companySignals(company, { ...thresholds, yieldMin: '' });
if (sig.yieldPass !== null) {
  throw new Error('blank yieldMin should skip yield alerts');
}

console.log('ok smoke_watchlist_alerts');
