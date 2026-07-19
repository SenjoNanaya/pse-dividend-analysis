import { DEFAULT_THRESHOLDS, normalizeThresholds, safeNum } from './metrics';
import { loadSignalSnapshot, saveSignalSnapshot } from './watchlist';

/**
 * Parse watchlist UI threshold strings into fractions used for signals.
 * yieldMin blank => null (skip yield alerts). deMax blank => default 2.
 */
function parseOptionalNumber(raw) {
  const s = String(raw ?? '').trim();
  if (s === '') return NaN;
  return Number(s);
}

export function parseWatchlistSignalThresholds(uiThresholds = {}) {
  const pe = parseOptionalNumber(uiThresholds.peMax);
  const pb = parseOptionalNumber(uiThresholds.pbMax);
  const roePct = parseOptionalNumber(uiThresholds.roeMin);
  const yieldPct = String(uiThresholds.yieldMin ?? '').trim();
  const roicPct = parseOptionalNumber(uiThresholds.roicMin);
  const deRaw = String(uiThresholds.deMax ?? '').trim();

  const yieldMin =
    yieldPct === '' || !Number.isFinite(Number(yieldPct))
      ? null
      : Number(yieldPct) / 100;

  const deMax =
    deRaw === '' || !Number.isFinite(Number(deRaw))
      ? DEFAULT_THRESHOLDS.deMax
      : Number(deRaw);

  return {
    ...normalizeThresholds({
      peMax: Number.isFinite(pe) ? pe : undefined,
      pbMax: Number.isFinite(pb) ? pb : undefined,
      roeMin: Number.isFinite(roePct) ? roePct / 100 : undefined,
      deMax,
    }),
    yieldMin,
    roicMin: Number.isFinite(roicPct) ? roicPct / 100 : null,
  };
}

export function companySignals(company, uiThresholds) {
  const t = parseWatchlistSignalThresholds(uiThresholds);
  const deVal = safeNum(company.debt_to_equity);
  let de = null;
  if (deVal != null && deVal >= 0) {
    de = deVal < t.deMax;
  }

  let yieldPass = null;
  if (t.yieldMin != null) {
    const y = safeNum(company.div_yield);
    yieldPass = y != null ? y >= t.yieldMin : null;
  }

  const dilution =
    company.dilution_pass === true
      ? true
      : company.dilution_pass === false
        ? false
        : null;

  const checkPass =
    company.check_pass_count != null && Number.isFinite(Number(company.check_pass_count))
      ? Number(company.check_pass_count)
      : null;

  return {
    dilution,
    de,
    yieldPass,
    checkPass,
    at: new Date().toISOString(),
  };
}

function boolLabel(v) {
  if (v === true) return 'pass';
  if (v === false) return 'fail';
  return 'n/a';
}

/**
 * Diff current companies vs prior snapshot.
 * First visit (no prior for that id) seeds without events.
 */
export function diffWatchlistAlerts(companies, uiThresholds, priorSnapshot = null) {
  const prior = priorSnapshot ?? loadSignalSnapshot();
  const next = { ...prior };
  const events = [];

  for (const company of companies) {
    const id = String(company.id);
    const ticker = company.ticker || company.symbol || id;
    const cur = companySignals(company, uiThresholds);
    const prev = prior[id];

    if (!prev) {
      next[id] = cur;
      continue;
    }

    if (prev.dilution != null && cur.dilution != null && prev.dilution !== cur.dilution) {
      events.push({
        id: company.id,
        ticker,
        kind: 'dilution',
        from: boolLabel(prev.dilution),
        to: boolLabel(cur.dilution),
        text: `${ticker}: share dilution now ${boolLabel(cur.dilution)} (was ${boolLabel(prev.dilution)})`,
      });
    }
    if (prev.de != null && cur.de != null && prev.de !== cur.de) {
      events.push({
        id: company.id,
        ticker,
        kind: 'de',
        from: boolLabel(prev.de),
        to: boolLabel(cur.de),
        text: `${ticker}: debt-to-equity now ${boolLabel(cur.de)} (was ${boolLabel(prev.de)})`,
      });
    }
    if (
      prev.yieldPass != null
      && cur.yieldPass != null
      && prev.yieldPass !== cur.yieldPass
    ) {
      events.push({
        id: company.id,
        ticker,
        kind: 'yield',
        from: boolLabel(prev.yieldPass),
        to: boolLabel(cur.yieldPass),
        text: `${ticker}: yield screen now ${boolLabel(cur.yieldPass)} (was ${boolLabel(prev.yieldPass)})`,
      });
    }
    if (
      prev.checkPass != null
      && cur.checkPass != null
      && prev.checkPass !== cur.checkPass
    ) {
      events.push({
        id: company.id,
        ticker,
        kind: 'checks',
        from: prev.checkPass,
        to: cur.checkPass,
        text: `${ticker}: checks ${prev.checkPass} → ${cur.checkPass}`,
      });
    }

    next[id] = cur;
  }

  saveSignalSnapshot(next);
  return { events, snapshot: next };
}
