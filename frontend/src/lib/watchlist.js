const STORAGE_KEY_V1 = 'pse_edge_watchlist_v1';
const STORAGE_KEY = 'pse_edge_watchlist_v2';
const SIGNALS_KEY = 'pse_edge_watchlist_signals_v1';

export const WATCHLIST_MAX = 50;

export const EMPTY_WATCHLIST_THRESHOLDS = {
  peMax: '',
  pbMax: '',
  roeMin: '',
  yieldMin: '',
  roicMin: '',
  deMax: '',
};

function hasAnyThresholdValue(thresholds) {
  return Object.values(thresholds || {}).some((v) => String(v ?? '').trim() !== '');
}

/** Missing flag: blank alert fields → follow list; any stored values → detached. */
function migrateAlertsFollowList(raw, thresholds) {
  if (typeof raw === 'boolean') return raw;
  return !hasAnyThresholdValue(thresholds);
}

function emptyState() {
  return {
    ids: [],
    meta: {},
    thresholds: { ...EMPTY_WATCHLIST_THRESHOLDS },
    alertsFollowList: true,
  };
}

function normalizeIds(rawIds) {
  return [...new Set((rawIds || []).map(Number))].filter(
    (id) => Number.isFinite(id) && id > 0,
  );
}

function normalizeMeta(rawMeta, ids) {
  const meta = {};
  const src =
    rawMeta && typeof rawMeta === 'object' && !Array.isArray(rawMeta) ? rawMeta : {};
  for (const id of ids) {
    const key = String(id);
    if (src[key]) meta[key] = src[key];
  }
  return meta;
}

function normalizeThresholds(raw) {
  const out = { ...EMPTY_WATCHLIST_THRESHOLDS };
  if (!raw || typeof raw !== 'object') return out;
  for (const key of Object.keys(EMPTY_WATCHLIST_THRESHOLDS)) {
    if (raw[key] != null) out[key] = String(raw[key]);
  }
  return out;
}

function readRaw(key) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function loadWatchlist() {
  const v2 = readRaw(STORAGE_KEY);
  if (v2) {
    const ids = normalizeIds(v2.ids);
    const thresholds = normalizeThresholds(v2.thresholds);
    return {
      ids,
      meta: normalizeMeta(v2.meta, ids),
      thresholds,
      alertsFollowList: migrateAlertsFollowList(v2.alertsFollowList, thresholds),
    };
  }
  const v1 = readRaw(STORAGE_KEY_V1);
  if (v1) {
    const ids = normalizeIds(v1.ids);
    const migrated = {
      ids,
      meta: normalizeMeta(v1.meta, ids),
      thresholds: { ...EMPTY_WATCHLIST_THRESHOLDS },
      alertsFollowList: true,
    };
    return saveWatchlist(migrated);
  }
  return emptyState();
}

export function saveWatchlist(state) {
  const ids = normalizeIds(state.ids);
  const thresholds = normalizeThresholds(state.thresholds);
  const next = {
    ids,
    meta: normalizeMeta(state.meta, ids),
    thresholds,
    alertsFollowList:
      typeof state.alertsFollowList === 'boolean'
        ? state.alertsFollowList
        : migrateAlertsFollowList(undefined, thresholds),
  };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Quota / private mode: still return in-memory shape
  }
  return next;
}

export function getWatchlistThresholds(state) {
  return normalizeThresholds(state?.thresholds);
}

export function getAlertsFollowList(state) {
  return Boolean(state?.alertsFollowList);
}

/**
 * @param {object} state
 * @param {object|null|undefined} thresholds — omit/null to keep current
 * @param {{ followList?: boolean }} [opts]
 */
export function setWatchlistThresholds(state, thresholds, opts = {}) {
  const nextThresh =
    thresholds != null
      ? normalizeThresholds(thresholds)
      : normalizeThresholds(state.thresholds);
  return saveWatchlist({
    ...state,
    thresholds: nextThresh,
    alertsFollowList:
      typeof opts.followList === 'boolean'
        ? opts.followList
        : state.alertsFollowList,
  });
}

export function isWatched(state, companyId) {
  const id = Number(companyId);
  return state.ids.includes(id);
}

export function toggleWatch(state, company) {
  const id = Number(company?.id);
  if (!Number.isFinite(id) || id <= 0) return state;
  const key = String(id);
  if (state.ids.includes(id)) {
    const ids = state.ids.filter((x) => x !== id);
    const meta = { ...state.meta };
    delete meta[key];
    return saveWatchlist({ ...state, ids, meta });
  }
  if (state.ids.length >= WATCHLIST_MAX) return state;
  const ticker = company.ticker || company.symbol || '';
  const meta = {
    ...state.meta,
    [key]: {
      ticker,
      name: company.name || '',
      addedAt: new Date().toISOString(),
    },
  };
  return saveWatchlist({ ...state, ids: [...state.ids, id], meta });
}

export function removeWatch(state, companyId) {
  const id = Number(companyId);
  if (!state.ids.includes(id)) return state;
  const key = String(id);
  const meta = { ...state.meta };
  delete meta[key];
  return saveWatchlist({
    ...state,
    ids: state.ids.filter((x) => x !== id),
    meta,
  });
}

export function pruneWatchlistIds(state, keepIds) {
  const keep = new Set(normalizeIds(keepIds));
  const ids = state.ids.filter((id) => keep.has(id));
  if (ids.length === state.ids.length) return state;
  return saveWatchlist({ ...state, ids });
}

export function clearWatchlist() {
  saveSignalSnapshot({});
  return saveWatchlist(emptyState());
}

export function watchlistIdsParam(ids) {
  return normalizeIds(ids).join(',');
}

export function loadSignalSnapshot() {
  const raw = readRaw(SIGNALS_KEY);
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  return raw;
}

export function saveSignalSnapshot(snapshot) {
  try {
    localStorage.setItem(SIGNALS_KEY, JSON.stringify(snapshot || {}));
  } catch {
    /* ignore */
  }
  return snapshot || {};
}
