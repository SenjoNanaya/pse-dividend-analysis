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
};

export function normalizeThresholds(thresholds) {
  const peMax = safeNum(thresholds?.peMax);
  const pbMax = safeNum(thresholds?.pbMax);
  const roeMin = safeNum(thresholds?.roeMin);
  return {
    peMax: peMax != null ? peMax : DEFAULT_THRESHOLDS.peMax,
    pbMax: pbMax != null ? pbMax : DEFAULT_THRESHOLDS.pbMax,
    roeMin: roeMin != null ? roeMin : DEFAULT_THRESHOLDS.roeMin,
  };
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
    || safeNum(f?.revenue) != null
    || safeNum(f?.eps) != null
  );
}

function completeFinancials(financials = []) {
  return sortedFinancials(financials).filter(hasCoreMetrics);
}

export function seriesByKey(financials, key) {
  return sortedFinancials(financials)
    .map((f) => ({
      year: String(f.fiscal_year),
      value: safeNum(f[key]),
    }))
    .filter((d) => d.value != null);
}

export function computeCagr(series) {
  if (!series || series.length < 2) return null;
  const first = series[0].value;
  const last = series[series.length - 1].value;
  if (!first || last == null || first === 0) return null;
  const periods = series.length - 1;
  if (first < 0 || last < 0) return null;
  return (last / first) ** (1 / periods) - 1;
}

export function dividendsByYear(dividends = []) {
  const map = new Map();
  for (const d of dedupeDividends(dividends)) {
    if (!isCommonDividend(d) || !isCashDividend(d)) continue;
    const amount = safeNum(d.amount);
    if (amount == null || !d.ex_date) continue;
    const year = String(d.ex_date).slice(0, 4);
    if (!/^\d{4}$/.test(year)) continue;
    map.set(year, (map.get(year) || 0) + amount);
  }
  return [...map.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([year, value]) => ({ year, value }));
}

/** Strict TTM common cash DPS ending at asOf (default: today). No older-year fallback. */
export function trailingAnnualDividend(dividends = [], asOf = null, windowDays = 365) {
  const rows = [];
  for (const d of dedupeDividends(dividends)) {
    if (!isCommonDividend(d) || !isCashDividend(d)) continue;
    const amount = safeNum(d.amount);
    const ex = parseExDate(d.ex_date);
    if (amount == null || !ex) continue;
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
  const annual = trailingAnnualDividend(dividends, asOf);
  if (annual == null || annual <= 0) return null;
  return annual / p;
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

function dedupeDividends(dividends = []) {
  const stockKeys = new Set();
  for (const d of dividends) {
    const amount = safeNum(d.amount);
    if (amount == null || !d.ex_date) continue;
    const dtype = String(d.type || 'cash').trim().toLowerCase() || 'cash';
    if (dtype === 'stock') stockKeys.add(`${d.ex_date}|${amount}`);
  }

  const best = new Map();
  for (const d of dividends) {
    const amount = safeNum(d.amount);
    if (amount == null || !d.ex_date) continue;
    const dtype = String(d.type || 'cash').trim().toLowerCase() || 'cash';
    // Drop cash rows that duplicate a stock dividend at the same date/amount
    if (dtype === 'cash' && stockKeys.has(`${d.ex_date}|${amount}`)) continue;
    const key = `${d.ex_date}|${amount}|${dtype}`;
    const flagged =
      d.is_common === 1
      || d.is_common === true
      || String(d.security || '').toUpperCase().startsWith('COMMON');
    const prev = best.get(key);
    if (!prev) {
      best.set(key, d);
      continue;
    }
    const prevFlagged =
      prev.is_common === 1
      || prev.is_common === true
      || String(prev.security || '').toUpperCase().startsWith('COMMON');
    if (flagged && !prevFlagged) best.set(key, d);
  }
  return [...best.values()];
}

export function dividendHistoryRows(dividends = []) {
  return [...dividends]
    .filter((d) => d.ex_date && safeNum(d.amount) != null)
    .sort((a, b) => String(b.ex_date).localeCompare(String(a.ex_date)))
    .map((d) => ({
      security: d.security || (isCommonDividend(d) ? 'COMMON' : '—'),
      isCommon: isCommonDividend(d),
      type: d.type || 'cash',
      amount: safeNum(d.amount),
      exDate: d.ex_date,
      recordDate: d.record_date || null,
      paymentDate: d.payment_date || null,
    }));
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
  const { peMax, pbMax, roeMin } = normalizeThresholds(thresholds);
  const financials = completeFinancials(company.financials || []);
  const dividends = company.dividends || [];

  const bv = seriesByKey(financials, 'book_value');
  const ni = seriesByKey(financials, 'net_income');
  const assets = seriesByKey(financials, 'total_assets');
  const revenue = seriesByKey(financials, 'revenue');
  const epsSeries = seriesByKey(financials, 'eps');
  const divSeries = dividendsByYear(dividends);

  const latest = financials.length ? financials[financials.length - 1] : null;
  const prev = financials.length >= 2 ? financials[financials.length - 2] : null;

  const price = sanitizePrice(
    company.last_traded_price,
    company.market_cap,
    company.outstanding_shares,
  );
  const shares = safeNum(company.outstanding_shares);
  const eps = safeNum(latest?.eps);
  const bookValue = safeNum(latest?.book_value);
  const netIncome = safeNum(latest?.net_income);
  const equity =
    bookValue != null && shares != null ? bookValue * shares : null;

  // Prefer PSE stock-page / disclosure-persisted ratios, else derive from filings
  const peScraped = safeNum(company.pe_ratio);
  const pbScraped = safeNum(company.pb_ratio);
  const roeScraped = safeNum(company.roe);
  const peComputed = price != null && eps ? price / eps : null;
  const pbComputed = price != null && bookValue ? price / bookValue : null;
  const pe = (peScraped != null && Math.abs(peScraped) <= 1000 ? peScraped : null) ?? peComputed;
  const pb = (pbScraped != null && Math.abs(pbScraped) <= 1000 ? pbScraped : null) ?? pbComputed;
  // ROE: disclosure FR → NI/equity when shares available
  const roeComputed = equity && netIncome != null ? netIncome / equity : null;
  const roe = roeScraped ?? roeComputed;

  const latestYear = latest?.fiscal_year != null ? String(latest.fiscal_year) : null;
  const annualDps = trailingAnnualDividend(dividends);
  const computedDivYield = price && annualDps ? annualDps / price : null;
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
    income: computeCagr(ni),
    assets: computeCagr(assets),
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
      pass: pe != null ? pe < peMax : null,
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
      label: `ROE > ${Math.round(roeMin * 100)}%`,
      pass: roe != null ? roe > roeMin : null,
    },
  ];

  const incomeCagr = growth.income;
  const zeroGrowthFv = eps != null ? eps / 0.1 : null;
  const yoyGrowthFv =
    eps != null && incomeCagr != null
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
      revenue: revenue.map((d) => ({ ...d, value: d.value / 1e9 })),
      eps: epsSeries,
      dividends: divSeries,
    },
    growth,
    ratios: { pe, pb, roe },
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
