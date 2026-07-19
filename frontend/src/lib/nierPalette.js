/**
 * Chart / SVG palette — JS mirror of frontend/src/index.css @theme.
 * CSS is canonical for UI; keep hex here identical when tokens change.
 * Recharts and SVG need concrete color strings (cannot resolve var() alone).
 */

export const NIER = {
  bg: '#c8c2aa',
  dark: '#3f3b32',
  darkMuted: '#4a453c',
  light: '#dcd8c0',
  gray: '#bab5a1',
  orange: '#a67c52',
  orangeInk: '#5c4024',
  chartAxis: '#4d493e',
  chartTrend: '#8a7a4a',
  chartOlive: '#7d8a6a',
  chartTeal: '#6a8a8a',
  chartRust: '#8a6a5a',
  chartSand: '#9a9278',
  chartSlate: '#6e7f8d',
  /** --color-nier-chart-compare-slate */
  chartCompareSlate: '#3d4a52',
  /** --color-nier-chart-compare-olive */
  chartCompareOlive: '#3f4a36',
};

/** Compare line series — darker strokes for ≥3:1 on beige (thin lines). */
export const COMPARE_SERIES = [
  NIER.dark,
  NIER.orangeInk,
  NIER.chartCompareSlate,
  NIER.chartCompareOlive,
];

export const CHART_SURFACE = {
  axis: NIER.chartAxis,
  grid: NIER.gray,
  tooltipBg: NIER.light,
  trend: NIER.chartTrend,
};

/**
 * Recharts needs numeric CSS px. Values track the product rem scale at
 * html { font-size: 125% } (1rem ≈ 20px): dense≈15, ui≈16, label≈17–18.
 */
export const CHART_TYPE = {
  tick: 16,
  tickSm: 15,
  label: 15,
  tooltip: 17,
  legend: 16,
};

/** Named metric fills — restrained series set, shared across report charts. */
export const METRIC_COLORS = {
  bookValue: NIER.chartSand,
  netIncome: NIER.chartSlate,
  assets: NIER.chartOlive,
  liabilities: NIER.chartRust,
  revenue: NIER.chartTeal,
  eps: NIER.chartRust,
  loans: NIER.chartSlate,
  deposits: NIER.chartTeal,
  ldr: NIER.chartTrend,
  nplRatio: NIER.chartRust,
  equityAssets: NIER.chartOlive,
  nii: NIER.chartSlate,
  outstandingShares: NIER.chartSlate,
  roic: NIER.chartOlive,
  debtEquity: NIER.chartRust,
  dividends: NIER.chartSand,
  cash: NIER.chartTeal,
  equity: NIER.chartSand,
};
