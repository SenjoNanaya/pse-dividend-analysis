/** Format a chart numeric for labels/tooltips, optionally with a unit suffix. */
export function formatChartNumber(v) {
  if (v == null || Number.isNaN(Number(v))) return '';
  const n = Number(v);
  const abs = Math.abs(n);
  if (abs >= 100) return n.toFixed(0);
  if (abs >= 10) return n.toFixed(1);
  return n.toFixed(2);
}

/** e.g. 12.3 + "B PHP" → "12.3 B PHP"; "%" → "12.3%" */
export function formatChartValue(v, unit) {
  const n = formatChartNumber(v);
  if (!n) return '';
  if (!unit) return n;
  if (unit === '%') return `${n}%`;
  return `${n} ${unit}`;
}
