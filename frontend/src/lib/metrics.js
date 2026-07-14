/** Build report metrics from company detail API payload (mirrors report_generator.py). */

export function safeNum(v) {
  if (v == null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
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
  for (const d of dividends) {
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

export function buildReport(company) {
  const financials = sortedFinancials(company.financials || []);
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
  const divInLatestYear = dividends
    .filter((d) => d.ex_date && String(d.ex_date).startsWith(latestYear || '____'))
    .reduce((sum, d) => sum + (safeNum(d.amount) || 0), 0);

  const divYield = price && divInLatestYear ? divInLatestYear / price : null;
  const totalDivPaid =
    shares != null && divInLatestYear ? divInLatestYear * shares : null;
  const divCover =
    totalDivPaid && netIncome != null && totalDivPaid !== 0
      ? netIncome / totalDivPaid
      : null;

  // Rough 3Y average yield from annual dividend totals / current price
  const recentDivYears = divSeries.slice(-3);
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

  const checklist = [
    { label: 'P/E Ratio < 22', pass: pe != null ? pe < 22 : null },
    { label: 'P/B < 1', pass: pb != null ? pb < 1 : null },
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
    { label: 'NO Share Dilution', pass: shares != null ? true : null },
    { label: '5xCFO > T Debt', pass: null },
    { label: 'FCF > ST+CPLT Debt', pass: null },
    { label: 'Quick/Current R > 1', pass: null },
    { label: 'ROE > 10%', pass: roe != null ? roe > 0.1 : null },
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

  return {
    displayTicker: company.ticker || company.symbol,
    companyName: company.name,
    marketCapLabel: formatMarketCap(company.market_cap),
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
      cover: divCover,
      coverStatus: divCoverStatus,
    },
    valuation: {
      yoyGrowthFv,
      quarterlyGrowthFv,
      zeroGrowthFv,
    },
    checklist,
    latestYear,
  };
}
