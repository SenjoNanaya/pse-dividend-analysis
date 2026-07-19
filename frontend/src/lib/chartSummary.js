/** Build a short screen-reader summary for a YoY value series. */
export function summarizeSeries(title, data, formatValue) {
  const pts = (Array.isArray(data) ? data : []).filter(
    (d) => d != null && d.value != null && Number.isFinite(Number(d.value)),
  );
  if (!pts.length) return `${title}: no data.`;

  const fmt = typeof formatValue === 'function'
    ? formatValue
    : (v) => {
      const n = Number(v);
      const abs = Math.abs(n);
      if (abs >= 100) return n.toFixed(0);
      if (abs >= 10) return n.toFixed(1);
      return n.toFixed(2);
    };

  const first = pts[0];
  const last = pts[pts.length - 1];
  const a = Number(first.value);
  const b = Number(last.value);
  let trend = 'flat';
  if (b > a * 1.02) trend = 'up';
  else if (b < a * 0.98) trend = 'down';

  return `${title}: ${pts.length} years, ${first.year} ${fmt(a)} to ${last.year} ${fmt(b)}, trend ${trend}.`;
}

/** Summarize multi-key balance-sheet rows (assets / liabilities / equity / cash). */
export function summarizeBalanceSheet(title, data) {
  const rows = Array.isArray(data) ? data : [];
  const years = rows.filter(
    (d) =>
      d
      && (d.assets != null || d.liabilities != null || d.equity != null || d.cash != null),
  );
  if (!years.length) return `${title}: no data.`;
  const last = years[years.length - 1];
  const bits = [];
  if (last.assets != null) bits.push(`assets ${Number(last.assets).toFixed(1)}`);
  if (last.liabilities != null) bits.push(`liabilities ${Number(last.liabilities).toFixed(1)}`);
  if (last.equity != null) bits.push(`equity ${Number(last.equity).toFixed(1)}`);
  if (last.cash != null) bits.push(`cash ${Number(last.cash).toFixed(1)}`);
  return `${title}: ${years.length} years ending ${last.year}; latest ${bits.join(', ') || '—'}.`;
}

/** Summarize multi-ticker compare chart rows. */
export function summarizeCompare(title, data, tickers) {
  const rows = Array.isArray(data) ? data : [];
  if (!rows.length || !tickers?.length) return `${title}: no data.`;
  const parts = tickers.map((t) => {
    const pts = rows.filter((r) => r[t] != null && Number.isFinite(Number(r[t])));
    if (!pts.length) return `${t} no data`;
    const first = pts[0];
    const last = pts[pts.length - 1];
    return `${t} ${first.year}–${last.year} ${Number(last[t]).toFixed(2)}`;
  });
  return `${title}: ${parts.join('; ')}.`;
}
