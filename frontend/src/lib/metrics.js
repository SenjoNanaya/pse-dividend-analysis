/** Build report metrics from company detail API payload (mirrors report_generator.py). */

export function safeNum(v) {
  if (v == null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Keep in sync with src/report_metrics.py DEFAULT_THRESHOLDS */
export const DEFAULT_THRESHOLDS = {
  peMax: 22,
  pbMax: 1,
  roeMin: 0.1,
  deMax: 2,
};

/** P&L % growth only when both periods are profitable (mirror report_metrics.PL_*) */
const ZERO_AS_MISSING_KEYS = new Set(['revenue', 'eps']);
const PL_MIN_ABS_PREV = {
  net_income: 1_000_000,
  revenue: 1_000_000,
  eps: 0.05,
};

export function normalizeThresholds(thresholds) {
  const peMax = safeNum(thresholds?.peMax);
  const pbMax = safeNum(thresholds?.pbMax);
  const roeMin = safeNum(thresholds?.roeMin);
  const deMax = safeNum(thresholds?.deMax);
  return {
    peMax: peMax != null ? peMax : DEFAULT_THRESHOLDS.peMax,
    pbMax: pbMax != null ? pbMax : DEFAULT_THRESHOLDS.pbMax,
    roeMin: roeMin != null ? roeMin : DEFAULT_THRESHOLDS.roeMin,
    deMax: deMax != null ? deMax : DEFAULT_THRESHOLDS.deMax,
  };
}

/** Total liabilities ÷ equity (NA for financials / missing / non-positive equity). */
export function debtToEquityRatio(row, company) {
  if (!row) return null;
  if (isFinancialSector(company)) return null;
  const liab = safeNum(row.total_liabilities);
  if (liab == null) return null;
  let eq = safeNum(row.stockholders_equity);
  if (eq == null || Math.abs(eq) < 1e-9) {
    const assets = safeNum(row.total_assets);
    if (assets == null) return null;
    eq = assets - liab;
  }
  if (eq == null || eq <= 0) return null;
  return liab / eq;
}

export function debtToEquityPass(de, deMax) {
  const d = safeNum(de);
  const cap = safeNum(deMax);
  if (d == null || cap == null || d < 0) return null;
  return d < cap;
}

/** Exact-zero revenue/EPS are placeholders, not prints. */
export function metricValue(v, key) {
  const n = safeNum(v);
  if (n == null) return null;
  if (ZERO_AS_MISSING_KEYS.has(key) && n === 0) return null;
  return n;
}

export function peCheckPass(pe, peMax) {
  const p = safeNum(pe);
  const cap = safeNum(peMax);
  if (p == null || cap == null) return null;
  return p > 0 && p < cap;
}

export function earningsUsableForValuation(eps, netIncome) {
  const e = safeNum(eps);
  if (e == null || e <= 0) return false;
  if (netIncome != null) {
    const ni = safeNum(netIncome);
    if (ni != null && ni <= 0) return false;
  }
  return true;
}

export function sanitizePeDisplay(pe) {
  const p = safeNum(pe);
  if (p == null || p <= 0 || Math.abs(p) > 1000) return null;
  return p;
}

export function sanitizeRoeDisplay(roe, netIncome) {
  const r = safeNum(roe);
  if (r == null) return null;
  const ni = safeNum(netIncome);
  if (ni != null && ni <= 0) return null;
  if (Math.abs(r) < 0.0005) return null;
  return r;
}

/** Prefer NI/equity when disclosure FR looks double-scaled (~0.19% vs ~19%). */
export function preferRoe(scraped, computed) {
  const s = safeNum(scraped);
  let c = safeNum(computed);
  if (c != null && Math.abs(c) > 2) c = null; // absurd NI/E (bad equity scale)
  if (s == null) return c;
  if (c == null) return s;
  if (Math.abs(s) < 0.01 && Math.abs(c) > 0.05) return c;
  return s;
}

/** G&A is always a positive expense magnitude. */
export function normalizeGaExpense(ga) {
  const v = safeNum(ga);
  if (v == null) return null;
  return Math.abs(v);
}

const OI_ANCHOR_MIN = 1_000_000;
const OI_IBT_MIN_RATIO = 0.40;

/** Reject GP that cannot be a statement gross profit. */
export function grossProfitSane(gp, {
  revenue = null,
  totalAssets = null,
  netIncome = null,
} = {}) {
  const v = safeNum(gp);
  if (v == null) return false;
  const rev = safeNum(revenue);
  if (rev != null && Math.abs(rev) >= OI_ANCHOR_MIN && Math.abs(v) > Math.abs(rev) * 1.05) {
    return false;
  }
  const assets = safeNum(totalAssets);
  if (assets != null && Math.abs(assets) >= OI_ANCHOR_MIN && Math.abs(v) > Math.abs(assets)) {
    return false;
  }
  const ni = safeNum(netIncome);
  if (ni != null && Math.abs(ni) >= OI_ANCHOR_MIN && Math.abs(v) > 50 * Math.abs(ni)) {
    return false;
  }
  return true;
}

/**
 * Reject OI that cannot be core ops (oversized, undersized vs GP/NI, or <0.4× IBT).
 */
export function operatingIncomeSane(oi, {
  revenue = null,
  grossProfit = null,
  netIncome = null,
  incomeBeforeTax = null,
  allowBelowIbt = false,
} = {}) {
  const v = safeNum(oi);
  if (v == null) return false;
  const rev = safeNum(revenue);
  const gp = safeNum(grossProfit);

  if (rev != null && Math.abs(v) > Math.abs(rev) * 1.05) {
    const revBelievable = gp == null || Math.abs(gp) <= Math.abs(rev) * 1.05;
    if (revBelievable) return false;
  }
  if (gp != null && Math.abs(gp) > 0 && Math.abs(v) > 3 * Math.abs(gp)) return false;

  if (gp != null && Math.abs(gp) >= OI_ANCHOR_MIN && Math.abs(v) < 0.03 * Math.abs(gp)) {
    return false;
  }

  const ni = safeNum(netIncome);
  const ibt = safeNum(incomeBeforeTax);
  if (
    !allowBelowIbt
    && ibt != null
    && Math.abs(ibt) >= OI_ANCHOR_MIN
    && ((v > 0 && ibt > 0) || (v < 0 && ibt < 0))
    && Math.abs(v) < OI_IBT_MIN_RATIO * Math.abs(ibt)
  ) {
    return false;
  }

  const earn = ni != null ? ni : ibt;
  if (earn != null && Math.abs(earn) >= OI_ANCHOR_MIN && Math.abs(v) < 0.05 * Math.abs(earn)) {
    const gpOk = (
      gp != null
      && Math.abs(gp) >= OI_ANCHOR_MIN
      && Math.abs(gp) >= 0.10 * Math.abs(earn)
    );
    if (!gpOk) return false;
  }
  if (earn != null && Math.abs(earn) >= OI_ANCHOR_MIN && Math.abs(v) > 5.0 * Math.abs(earn)) {
    return false;
  }
  return true;
}

export function normalizeExpenseMagnitude(raw) {
  const v = safeNum(raw);
  if (v == null) return null;
  return Math.abs(v);
}

export function derivedGrossProfit(row) {
  if (!row) return null;
  const rev = safeNum(row.revenue) ?? safeNum(row.gross_revenue);
  const cogs = normalizeExpenseMagnitude(row.cost_of_sales);
  if (rev == null || cogs == null) return null;
  const gp = rev - cogs;
  if (!grossProfitSane(gp, {
    revenue: rev,
    totalAssets: row.total_assets,
    netIncome: row.net_income,
  })) {
    return null;
  }
  return gp;
}

/** IBT + interest, else GP − |GA| − other (ALI-class statements). */
export function constructedOperatingIncome(row) {
  if (!row) return null;
  const ibt = safeNum(row.income_before_tax);
  const interest = normalizeExpenseMagnitude(row.interest_expense);
  // Ignore note-scale interest crumbs vs material IBT
  if (
    ibt != null
    && interest != null
    && Math.abs(ibt) >= OI_ANCHOR_MIN
    && Math.abs(interest) >= Math.max(OI_ANCHOR_MIN, 0.02 * Math.abs(ibt))
  ) {
    return ibt + interest;
  }

  const gp = safeNum(row.gross_profit);
  const ga = normalizeGaExpense(row.ga_expense);
  const other = normalizeExpenseMagnitude(row.other_expenses);
  if (gp == null || ga == null || other == null) return null;
  const rev = safeNum(row.revenue) ?? safeNum(row.gross_revenue);
  if (!grossProfitSane(gp, {
    revenue: rev,
    totalAssets: row.total_assets,
    netIncome: row.net_income,
  })) {
    return null;
  }
  return gp - ga - other;
}

export function derivedOperatingIncome(row) {
  if (!row) return null;
  const gp = safeNum(row.gross_profit);
  const ga = normalizeGaExpense(row.ga_expense);
  if (gp == null || ga == null) return null;
  const rev = safeNum(row.revenue) ?? safeNum(row.gross_revenue);
  if (!grossProfitSane(gp, {
    revenue: rev,
    totalAssets: row.total_assets,
    netIncome: row.net_income,
  })) {
    return null;
  }
  return gp - ga;
}

/** Prefer scraped OI when sane; else IBT+interest / GP−GA−other / GP−|GA|. */
export function preferOperatingIncome(row) {
  if (!row) return null;
  const rev = safeNum(row.revenue) ?? safeNum(row.gross_revenue);
  let gp = safeNum(row.gross_profit);
  if (gp == null) gp = derivedGrossProfit(row);
  const ni = row.net_income;
  const ibt = row.income_before_tax;
  const oi = safeNum(row.operating_income);
  const opts = {
    revenue: rev,
    grossProfit: gp,
    netIncome: ni,
    incomeBeforeTax: ibt,
  };
  if (oi != null && operatingIncomeSane(oi, opts)) return oi;
  const interest = normalizeExpenseMagnitude(row.interest_expense);
  const ibtN = safeNum(ibt);
  if (
    ibtN != null
    && interest != null
    && Math.abs(ibtN) >= OI_ANCHOR_MIN
    && Math.abs(interest) >= Math.max(OI_ANCHOR_MIN, 0.02 * Math.abs(ibtN))
  ) {
    const ibtOi = ibtN + interest;
    if (operatingIncomeSane(ibtOi, {
      revenue: rev,
      grossProfit: null,
      netIncome: ni,
      incomeBeforeTax: ibt,
      allowBelowIbt: true,
    })) {
      return ibtOi;
    }
  }
  const synthOpts = { ...opts, allowBelowIbt: true };
  for (const candidate of [
    constructedOperatingIncome({ ...row, gross_profit: gp ?? row.gross_profit }),
    derivedOperatingIncome({ ...row, gross_profit: gp ?? row.gross_profit }),
  ]) {
    if (candidate != null && operatingIncomeSane(candidate, synthOpts)) return candidate;
  }
  return null;
}

export function equityForRoe(latest, company) {
  if (!latest) return null;
  const stmt = safeNum(latest.stockholders_equity);
  if (stmt != null && Math.abs(stmt) > 0) return stmt;
  const bv = safeNum(latest.book_value);
  const shares =
    safeNum(latest.outstanding_shares) ?? safeNum(company?.outstanding_shares);
  if (bv != null && shares != null && Math.abs(shares) > 0) return bv * shares;
  return null;
}

export function formatBillions(v, digits = 2) {
  const n = safeNum(v);
  if (n == null) return '—';
  return (n / 1e9).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatCompact(v, scale = 1, digits = 2) {
  const n = safeNum(v);
  if (n == null) return '—';
  return (n / scale).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatMarketCap(v) {
  const n = safeNum(v);
  if (n == null) return '—';
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)} B`;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)} M`;
  return n.toLocaleString();
}

/** PHP market-cap tiers: Micro <3B, Small 3–20B, Mid 20–100B, Large ≥100B. */
export function marketCapTier(v) {
  const n = safeNum(v);
  if (n == null) return null;
  if (n < 3e9) return 'MICRO';
  if (n < 20e9) return 'SMALL';
  if (n < 100e9) return 'MID';
  return 'LARGE';
}

export function formatPrice(v) {
  const n = safeNum(v);
  if (n == null) return '—';
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatPct(v, digits = 2) {
  const n = safeNum(v);
  if (n == null) return '—';
  return `${(n * 100).toFixed(digits)}%`;
}

export function formatPhp(v, digits = 2) {
  const n = safeNum(v);
  if (n == null) return '—';
  return `₱${n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

function sortedFinancials(financials = []) {
  return [...financials]
    .filter((f) => f.fiscal_year != null)
    .sort((a, b) => a.fiscal_year - b.fiscal_year);
}

/** Rows that have enough statement data for ratios / growth checks. */
function hasCoreMetrics(f) {
  return (
    safeNum(f?.book_value) != null
    || safeNum(f?.net_income) != null
    || safeNum(f?.total_assets) != null
    || metricValue(f?.revenue, 'revenue') != null
    || metricValue(f?.eps, 'eps') != null
  );
}

function completeFinancials(financials = []) {
  return sortedFinancials(financials).filter(hasCoreMetrics);
}

export function seriesByKey(financials, key) {
  return sortedFinancials(financials)
    .map((f) => ({
      year: String(f.fiscal_year),
      value: metricValue(f[key], key) ?? (
        ZERO_AS_MISSING_KEYS.has(key) ? null : safeNum(f[key])
      ),
    }))
    .filter((d) => d.value != null);
}

/** Series suitable for P&L CAGR (strictly profitable points only). */
export function plGrowthSeries(financials, key) {
  const floor = PL_MIN_ABS_PREV[key] ?? 0;
  return seriesByKey(financials, key).filter((d) => d.value > 0 && d.value >= floor);
}

export function computeCagr(series) {
  if (!series || series.length < 2) return null;
  const first = series[0].value;
  const last = series[series.length - 1].value;
  if (first == null || last == null || first === 0) return null;
  const periods = series.length - 1;
  if (first < 0 || last < 0) return null;
  return (last / first) ** (1 / periods) - 1;
}

/**
 * Invested capital for ROIC.
 * Proper: Assets − Cash − Current Liabilities when all present.
 * Else Assets − Current Liabilities; else Total Assets (proxy).
 */
export function investedCapital(row, { proper = false } = {}) {
  if (!row) return null;
  const assets = safeNum(row.total_assets);
  const cash = safeNum(row.cash_and_equivalents);
  const currentLiab = safeNum(row.total_current_liabilities);
  if (
    proper
    && assets != null
    && cash != null
    && currentLiab != null
    && assets > cash + currentLiab
  ) {
    return assets - cash - currentLiab;
  }
  if (assets != null && currentLiab != null && assets > currentLiab) {
    return assets - currentLiab;
  }
  if (assets != null && assets !== 0) return assets;
  const liab = safeNum(row.total_liabilities);
  let equity = safeNum(row.stockholders_equity);
  if (equity == null && assets != null && liab != null) equity = assets - liab;
  if (equity != null && liab != null) return equity + liab;
  return equity;
}

export function approxOperatingIncome(row) {
  return preferOperatingIncome(row);
}

export function effectiveTaxRate(row) {
  const tax = safeNum(row.income_tax_expense);
  const ibt = safeNum(row.income_before_tax);
  if (tax != null && ibt != null && ibt !== 0) {
    const t = tax / ibt;
    if (t >= 0 && t <= 0.5) return t;
  }
  return null;
}

export function isFinancialSector(company) {
  const blob = `${company?.sector || ''} ${company?.subsector || ''}`.toLowerCase();
  if (!blob.trim()) return false;
  return (
    blob.includes('bank')
    || blob.includes('financials')
    || blob.includes('financial services')
    || blob.includes('insurance')
    || blob.includes('other financial institutions')
  );
}

/**
 * ROIC / bank capital-return series (percentage points for charts).
 * mode: 'proper' | 'proxy' | 'equity'
 * Banks/insurance use equity mode (NI ÷ avg equity) — not industrial A−cash−CL.
 */
export function computeRoicSeries(financials = [], company = null) {
  const rows = completeFinancials(financials);
  let statementScope = null;
  for (const row of rows) {
    if (row.statement_scope && !statementScope) {
      statementScope = row.statement_scope;
    }
  }

  if (isFinancialSector(company)) {
    const out = [];
    for (let i = 0; i < rows.length; i += 1) {
      const row = rows[i];
      const ni = safeNum(row.net_income);
      const eqEnd = equityForRoe(row, company);
      if (ni == null || eqEnd == null || eqEnd === 0) continue;

      let eq = eqEnd;
      if (i > 0) {
        const eqBeg = equityForRoe(rows[i - 1], company);
        if (eqBeg != null && eqBeg !== 0) eq = (eqBeg + eqEnd) / 2;
      }
      if (eq === 0) continue;

      out.push({
        year: String(row.fiscal_year),
        value: (ni / eq) * 100,
        usedCurrentLiab: false,
        mode: 'equity',
      });
    }
    return {
      series: out,
      mode: 'equity',
      statementScope,
      taxAssumed: false,
    };
  }

  const canProper = rows.some(
    (r) =>
      approxOperatingIncome(r) != null
      && safeNum(r.total_assets) != null
      && safeNum(r.cash_and_equivalents) != null
      && safeNum(r.total_current_liabilities) != null,
  );

  const mode = canProper ? 'proper' : 'proxy';
  const out = [];
  let taxAssumed = false;

  for (let i = 0; i < rows.length; i += 1) {
    const row = rows[i];

    const icEnd = investedCapital(row, { proper: mode === 'proper' });
    if (icEnd == null || icEnd === 0) continue;

    let ic = icEnd;
    if (i > 0) {
      const icBeg = investedCapital(rows[i - 1], { proper: mode === 'proper' });
      if (icBeg != null && icBeg !== 0) ic = (icBeg + icEnd) / 2;
    }
    if (ic === 0) continue;

    let nopat = null;
    if (mode === 'proper') {
      const op = approxOperatingIncome(row);
      if (op == null) continue;
      let t = effectiveTaxRate(row);
      if (t == null) {
        t = 0.25;
        taxAssumed = true;
      }
      nopat = op * (1 - t);
    } else {
      nopat = safeNum(row.net_income);
      if (nopat == null) continue;
    }

    out.push({
      year: String(row.fiscal_year),
      value: (nopat / ic) * 100,
      usedCurrentLiab: safeNum(row.total_current_liabilities) != null,
      mode,
    });
  }

  return { series: out, mode, statementScope, taxAssumed };
}

const MAX_PLAUSIBLE_CASH_DPS = 1000;
const MAX_CASH_DPS_OVER_PRICE = 2;

/** Reject entitlement misparses / digit-strip junk for yield & charts. */
export function plausibleCashDps(amount, price = null) {
  const amt = safeNum(amount);
  if (amt == null || amt <= 0) return false;
  if (amt > MAX_PLAUSIBLE_CASH_DPS) return false;
  const p = safeNum(price);
  if (p != null && p > 0 && amt > p * MAX_CASH_DPS_OVER_PRICE) return false;
  return true;
}

export function dividendsByYear(dividends = [], price = null) {
  const map = new Map();
  for (const d of dedupeDividends(dividends)) {
    if (!isCommonDividend(d) || !isCashDividend(d)) continue;
    const amount = safeNum(d.amount);
    if (amount == null || !d.ex_date) continue;
    if (!plausibleCashDps(amount, price)) continue;
    const year = String(d.ex_date).slice(0, 4);
    if (!/^\d{4}$/.test(year)) continue;
    map.set(year, (map.get(year) || 0) + amount);
  }
  return [...map.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([year, value]) => ({ year, value }));
}

/** Strict TTM common cash DPS ending at asOf (default: today). No older-year fallback. */
export function trailingAnnualDividend(
  dividends = [],
  asOf = null,
  windowDays = 365,
  price = null,
) {
  const rows = [];
  for (const d of dedupeDividends(dividends)) {
    if (!isCommonDividend(d) || !isCashDividend(d)) continue;
    const amount = safeNum(d.amount);
    const ex = parseExDate(d.ex_date);
    if (amount == null || !ex) continue;
    if (!plausibleCashDps(amount, price)) continue;
    rows.push({ ex, amount });
  }
  if (!rows.length) return null;

  const end = asOf ? parseExDate(asOf) : new Date();
  if (!end || Number.isNaN(end.getTime())) return null;
  // Normalize to UTC midnight for stable day windows
  const endUtc = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate()));
  const startUtc = new Date(endUtc);
  startUtc.setUTCDate(startUtc.getUTCDate() - windowDays);

  let ttm = 0;
  for (const { ex, amount } of rows) {
    if (ex > startUtc && ex <= endUtc) ttm += amount;
  }
  return ttm > 0 ? ttm : null;
}

export function computeDivYield(price, dividends = [], asOf = null) {
  const p = safeNum(price);
  if (p == null || p <= 0) return null;
  const annual = trailingAnnualDividend(dividends, asOf, 365, p);
  if (annual == null || annual <= 0) return null;
  const y = annual / p;
  if (y > 1) return null;
  return y;
}

function parseExDate(value) {
  if (!value) return null;
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
  const text = String(value).slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null;
  const d = new Date(`${text}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function isCashDividend(d) {
  const dtype = String(d.type || 'cash').trim().toLowerCase();
  return dtype === 'cash' || dtype === '';
}

function isCommonDividend(d) {
  if (d.is_common === 0 || d.is_common === false) return false;
  if (d.is_common === 1 || d.is_common === true) return true;
  const sec = String(d.security || '').toUpperCase();
  if (!sec) return true; // legacy rows treated as common
  return sec === 'COMMON' || sec.startsWith('COMMON ');
}

function dividendRank(d) {
  const flagged =
    d.is_common === 1
    || d.is_common === true
    || String(d.security || '').toUpperCase().startsWith('COMMON');
  const hasRecord = Boolean(d.record_date);
  const hasSecurity = Boolean(d.security);
  // Higher is better — prefer COMMON + record_date over legacy null-security dupes
  return (flagged ? 4 : 0) + (hasRecord ? 2 : 0) + (hasSecurity ? 1 : 0);
}

function dedupeDividends(dividends = []) {
  const stockKeys = new Set();
  const propertyDates = new Set();
  for (const d of dividends) {
    const amount = safeNum(d.amount);
    if (amount == null || !d.ex_date) continue;
    const dtype = String(d.type || 'cash').trim().toLowerCase() || 'cash';
    if (dtype === 'stock') stockKeys.add(`${d.ex_date}|${amount}`);
    if (dtype === 'property') propertyDates.add(d.ex_date);
  }

  const best = new Map();
  for (const d of dividends) {
    const amount = safeNum(d.amount);
    if (amount == null || !d.ex_date) continue;
    const dtype = String(d.type || 'cash').trim().toLowerCase() || 'cash';
    // Drop cash rows that duplicate a stock dividend at the same date/amount
    if (dtype === 'cash' && stockKeys.has(`${d.ex_date}|${amount}`)) continue;
    // Cash beside property on same ex-date with large rate → entitlement misparse
    if (dtype === 'cash' && propertyDates.has(d.ex_date) && amount >= 5) continue;
    const key = `${d.ex_date}|${amount}|${dtype}`;
    const prev = best.get(key);
    if (!prev || dividendRank(d) > dividendRank(prev)) {
      best.set(key, d);
    }
  }
  return [...best.values()];
}

export function dividendHistoryRows(dividends = []) {
  return dedupeDividends(dividends)
    .filter((d) => d.ex_date && safeNum(d.amount) != null)
    // Drop entitlement misparses that still carry a fake PHP "rate"
    .filter((d) => {
      const dtype = String(d.type || 'cash').trim().toLowerCase() || 'cash';
      const amount = safeNum(d.amount);
      if (dtype === 'cash' || dtype === '') return plausibleCashDps(amount);
      // Non-cash: hide large numeric rates (share counts / digit-concat junk)
      if (amount != null && amount >= 5) return false;
      return true;
    })
    .sort((a, b) => String(b.ex_date).localeCompare(String(a.ex_date)))
    .map((d) => {
      const dtype = String(d.type || 'cash').trim().toLowerCase() || 'cash';
      return {
        security: d.security || (isCommonDividend(d) ? 'COMMON' : '—'),
        isCommon: isCommonDividend(d),
        type: dtype,
        amount: safeNum(d.amount),
        exDate: d.ex_date,
        recordDate: d.record_date || null,
        paymentDate: d.payment_date || null,
      };
    });
}

export function sanitizePrice(price, marketCap, shares) {
  let p = safeNum(price);
  const cap = safeNum(marketCap);
  const sh = safeNum(shares);

  if (p != null && p > 100_000) p = null;
  if (p != null && sh && Math.abs(p - sh) / sh < 0.05) p = null;

  if (cap && sh) {
    const implied = cap / sh;
    if (implied > 0) {
      if (p == null) return implied;
      if (Math.abs(p - implied) / implied > 10) return implied;
    }
  }
  return p;
}

export function buildReport(company, thresholds) {
  const { peMax, pbMax, roeMin, deMax } = normalizeThresholds(thresholds);
  const financials = completeFinancials(company.financials || []);
  const dividends = company.dividends || [];

  const price = sanitizePrice(
    company.last_traded_price,
    company.market_cap,
    company.outstanding_shares,
  );
  const bv = seriesByKey(financials, 'book_value');
  const ni = seriesByKey(financials, 'net_income');
  const assets = seriesByKey(financials, 'total_assets');
  const liabilities = seriesByKey(financials, 'total_liabilities');
  const revenue = seriesByKey(financials, 'revenue');
  const epsSeries = seriesByKey(financials, 'eps');
  const divSeries = dividendsByYear(dividends, price);
  const roicResult = computeRoicSeries(financials, company);
  const roicSeries = roicResult.series || [];

  const balanceSheet = financials
    .map((f) => {
      const year = f.fiscal_year != null ? String(f.fiscal_year) : null;
      if (!year) return null;
      const a = safeNum(f.total_assets);
      const l = safeNum(f.total_liabilities);
      const cash = safeNum(f.cash_and_equivalents);
      const cl = safeNum(f.total_current_liabilities);
      let e = safeNum(f.stockholders_equity);
      if (e == null && a != null && l != null) e = a - l;
      if (a == null && l == null && e == null && cash == null) return null;
      return {
        year,
        assets: a != null ? a / 1e9 : null,
        liabilities: l != null ? l / 1e9 : null,
        cash: cash != null ? cash / 1e9 : null,
        currentLiabilities: cl != null ? cl / 1e9 : null,
        equity: e != null ? e / 1e9 : null,
      };
    })
    .filter(Boolean);

  const latest = financials.length ? financials[financials.length - 1] : null;
  const prev = financials.length >= 2 ? financials[financials.length - 2] : null;
  const shares = safeNum(company.outstanding_shares);
  const eps = metricValue(latest?.eps, 'eps');
  const bookValue = safeNum(latest?.book_value);
  const netIncome = safeNum(latest?.net_income);
  const equity = equityForRoe(latest, company);

  // Prefer PSE stock-page / disclosure-persisted ratios, else derive from filings
  const peScraped = safeNum(company.pe_ratio);
  const pbScraped = safeNum(company.pb_ratio);
  const roeScraped = safeNum(company.roe);
  const peComputed =
    price != null && earningsUsableForValuation(eps, netIncome)
      ? price / eps
      : null;
  const pbComputed = price != null && bookValue ? price / bookValue : null;
  const peRaw = (peScraped != null && Math.abs(peScraped) <= 1000 ? peScraped : null) ?? peComputed;
  const pb = (pbScraped != null && Math.abs(pbScraped) <= 1000 ? pbScraped : null) ?? pbComputed;
  // ROE: prefer NI/equity when FR looks double-scaled (SPC-style 0.19% vs 19%)
  const roeComputed =
    equity != null && netIncome != null && Math.abs(equity) > 0
      ? netIncome / equity
      : null;
  const roeRaw = preferRoe(roeScraped, roeComputed);
  const pe = sanitizePeDisplay(peRaw);
  const roe = sanitizeRoeDisplay(roeRaw, netIncome);

  const latestRoicPct =
    roicSeries.length > 0 ? roicSeries[roicSeries.length - 1].value : null;
  const roic =
    latestRoicPct != null && Number.isFinite(latestRoicPct)
      ? latestRoicPct / 100
      : null;
  const roicUsedCurrentLiab =
    roicSeries.length > 0
      ? Boolean(roicSeries[roicSeries.length - 1].usedCurrentLiab)
      : false;

  const latestYear = latest?.fiscal_year != null ? String(latest.fiscal_year) : null;
  const annualDps = trailingAnnualDividend(dividends, null, 365, price);
  const computedDivYield = computeDivYield(price, dividends);
  const divYield = safeNum(company.div_yield) ?? computedDivYield;
  const totalDivPaid =
    shares != null && annualDps ? annualDps * shares : null;
  const divCover =
    totalDivPaid && netIncome != null && totalDivPaid !== 0
      ? netIncome / totalDivPaid
      : null;

  // 3Y avg uses completed calendar years only — skip the current year
  // (it may not have all quarterly filings yet). Current run-rate = TTM yield.
  const thisCalendarYear = String(new Date().getUTCFullYear());
  const completedDivYears = divSeries.filter((d) => d.year < thisCalendarYear);
  const recentDivYears = completedDivYears.slice(-3);
  const avgDivPerShare =
    recentDivYears.length > 0
      ? recentDivYears.reduce((s, d) => s + d.value, 0) / recentDivYears.length
      : null;
  const avgYield3y = price && avgDivPerShare != null ? avgDivPerShare / price : null;

  const growth = {
    bookValue: computeCagr(bv),
    income: computeCagr(plGrowthSeries(financials, 'net_income')),
    assets: computeCagr(assets),
    liabilities: computeCagr(liabilities),
  };

  const latestAssets = safeNum(latest?.total_assets);
  const latestLiab = safeNum(latest?.total_liabilities);
  const latestCash = safeNum(latest?.cash_and_equivalents);
  const latestCL = safeNum(latest?.total_current_liabilities);
  let latestEquity = safeNum(latest?.stockholders_equity);
  if (latestEquity == null && latestAssets != null && latestLiab != null) {
    latestEquity = latestAssets - latestLiab;
  }
  const investedCapProper =
    latestAssets != null && latestCash != null && latestCL != null
      ? latestAssets - latestCash - latestCL
      : null;
  const bvpsDerived =
    latestEquity != null && shares != null && shares > 0
      ? latestEquity / shares
      : null;
  const bvDerivation = {
    assets: latestAssets,
    liabilities: latestLiab,
    cash: latestCash,
    currentLiabilities: latestCL,
    equity: latestEquity,
    investedCapital: investedCapProper,
    bookValueReported: bookValue,
    bookValueDerived: bvpsDerived,
    shares,
  };

  const latestShares = safeNum(latest?.outstanding_shares) ?? shares;
  const prevShares = safeNum(prev?.outstanding_shares);
  let dilutionPass = null;
  if (latestShares != null && prevShares != null && prevShares > 0) {
    dilutionPass = latestShares <= prevShares * 1.001;
  }

  const checklist = [
    {
      label: `P/E Ratio < ${Number(peMax)}`,
      pass: peCheckPass(peRaw, peMax),
    },
    {
      label: `P/B < ${Number(pbMax)}`,
      pass: pb != null ? pb < pbMax : null,
    },
    {
      label: 'Increasing BV',
      pass:
        prev && latest
          ? safeNum(latest.book_value) > safeNum(prev.book_value)
          : null,
    },
    {
      label: 'Increasing Income',
      pass:
        prev && latest
          ? safeNum(latest.net_income) > safeNum(prev.net_income)
          : null,
    },
    {
      label: 'Increasing Assets',
      pass:
        prev && latest
          ? safeNum(latest.total_assets) > safeNum(prev.total_assets)
          : null,
    },
    { label: 'NO Share Dilution', pass: dilutionPass },
    {
      label: 'Quick/Current R > 1',
      pass: liquidityRatioPass(latest?.current_ratio, latest?.quick_ratio),
    },
    {
      label: `Debt/Equity < ${Number(deMax)}`,
      pass: debtToEquityPass(debtToEquityRatio(latest, company), deMax),
    },
    {
      label: `ROE > ${Math.round(roeMin * 100)}%`,
      pass: roeRaw != null ? roeRaw > roeMin : null,
    },
  ];

  const debtEquitySeries = financials
    .map((f) => {
      const value = debtToEquityRatio(f, company);
      if (value == null) return null;
      return { year: String(f.fiscal_year), value };
    })
    .filter(Boolean);
  const debtEquityLatest =
    debtEquitySeries.length > 0
      ? debtEquitySeries[debtEquitySeries.length - 1].value
      : null;

  const incomeCagr = growth.income;
  const zeroGrowthFv = earningsUsableForValuation(eps, netIncome)
    ? eps / 0.1
    : null;
  const yoyGrowthFv =
    earningsUsableForValuation(eps, netIncome) && incomeCagr != null
      ? (eps * (1 + incomeCagr)) / 0.1
      : null;
  // No quarterly series in DB — approximate as blend between zero & YoY
  const quarterlyGrowthFv =
    zeroGrowthFv != null && yoyGrowthFv != null
      ? zeroGrowthFv * 0.4 + yoyGrowthFv * 0.6
      : null;

  let divCoverStatus = 'NA';
  if (divCover != null) {
    divCoverStatus = divCover >= 1 ? 'GOOD' : 'WEAK';
  }

  const score = checklistScore(checklist);

  return {
    displayTicker: company.ticker || company.symbol,
    companyName: company.name,
    companyId: company.id,
    price,
    marketCap: safeNum(company.market_cap),
    marketCapLabel: formatMarketCap(company.market_cap),
    capTier: marketCapTier(company.market_cap),
    sector: company.sector || null,
    subsector: company.subsector || null,
    divYield,
    asOf: company.last_updated
      ? new Date(company.last_updated)
      : new Date(),
    charts: {
      bookValue: bv,
      netIncome: ni.map((d) => ({ ...d, value: d.value / 1e9 })),
      assets: assets.map((d) => ({ ...d, value: d.value / 1e9 })),
      liabilities: liabilities.map((d) => ({ ...d, value: d.value / 1e9 })),
      balanceSheet,
      revenue: revenue.map((d) => ({ ...d, value: d.value / 1e9 })),
      eps: epsSeries,
      dividends: divSeries,
      roic: roicSeries,
      debtEquity: debtEquitySeries,
    },
    growth,
    bvDerivation,
    ratios: { pe, pb, roe, roic, debtEquity: debtEquityLatest },
    roicMeta: {
      usedCurrentLiab: roicUsedCurrentLiab,
      mode: roicResult.mode,
      statementScope: roicResult.statementScope,
      taxAssumed: roicResult.taxAssumed,
    },
    dividend: {
      avgYield3y,
      yield: divYield,
      cover: divCover,
      coverStatus: divCoverStatus,
      history: dividendHistoryRows(dividends),
    },
    valuation: {
      yoyGrowthFv,
      quarterlyGrowthFv,
      zeroGrowthFv,
    },
    checklist,
    checklistScore: score,
    latestYear,
    passesScreen: !company.info_incomplete && score.pass > 5,
  };
}

export function evaluableChecklist(checklist = []) {
  return checklist.filter((item) => item.pass !== null);
}

export function checklistScore(checklist = []) {
  const evaluable = evaluableChecklist(checklist);
  const pass = evaluable.filter((item) => item.pass === true).length;
  return { pass, total: evaluable.length };
}

/** Pass if either current or quick ratio exceeds 1. */
export function liquidityRatioPass(currentRatio, quickRatio) {
  const cr = safeNum(currentRatio);
  const qr = safeNum(quickRatio);
  if (cr == null && qr == null) return null;
  if ((cr != null && cr > 1) || (qr != null && qr > 1)) return true;
  return false;
}
