import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { summarizeCompare } from '../lib/chartSummary';
import { CHART_SURFACE, CHART_TYPE, COMPARE_SERIES, NIER } from '../lib/nierPalette';

function formatLabel(v) {
  if (v == null || Number.isNaN(Number(v))) return '';
  const n = Number(v);
  const abs = Math.abs(n);
  if (abs >= 100) return n.toFixed(0);
  if (abs >= 10) return n.toFixed(1);
  return n.toFixed(2);
}

/** Align YoY series from multiple reports onto shared year rows. */
export function mergeChartSeries(reports, chartKey) {
  const yearSet = new Set();
  for (const r of reports) {
    for (const d of r.charts?.[chartKey] || []) {
      if (d?.year != null) yearSet.add(String(d.year));
    }
  }
  const years = [...yearSet].sort((a, b) => a.localeCompare(b));
  return years.map((year) => {
    const row = { year };
    for (const r of reports) {
      const pt = (r.charts?.[chartKey] || []).find((d) => String(d.year) === year);
      row[r.displayTicker] = pt?.value ?? null;
    }
    return row;
  });
}

export default function CompareChart({
  title,
  reports,
  chartKey,
  height = 280,
}) {
  const tickers = reports.map((r) => r.displayTicker);
  const data = mergeChartSeries(reports, chartKey);
  const hasData = data.some((row) => tickers.some((t) => row[t] != null));
  const { axis, grid, tooltipBg } = CHART_SURFACE;
  const summary = summarizeCompare(title, data, tickers);

  return (
    <div className="compare-chart-card" role="img" aria-label={summary}>
      <div className="compare-chart-title" aria-hidden="true">{title}</div>
      {!hasData ? (
        <div className="compare-chart-empty" aria-hidden="true">No data</div>
      ) : (
        <div aria-hidden="true">
          <ResponsiveContainer width="100%" height={height}>
            <LineChart data={data} margin={{ top: 12, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={grid} />
              <XAxis
                dataKey="year"
                tick={{ fontSize: CHART_TYPE.tick, fill: axis }}
                axisLine={{ stroke: axis }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: CHART_TYPE.tickSm, fill: axis }}
                axisLine={false}
                tickLine={false}
                width={60}
                tickFormatter={(v) => formatLabel(v)}
              />
              <Tooltip
                formatter={(value, name) => [formatLabel(Number(value)), name]}
                contentStyle={{
                  fontSize: CHART_TYPE.tooltip,
                  borderRadius: 0,
                  border: `1px solid ${axis}`,
                  background: tooltipBg,
                  color: axis,
                }}
              />
              <Legend
                wrapperStyle={{ fontSize: CHART_TYPE.legend, paddingTop: 4, color: NIER.dark }}
                iconType="plainline"
              />
              {tickers.map((ticker, i) => (
                <Line
                  key={ticker}
                  type="monotone"
                  dataKey={ticker}
                  stroke={COMPARE_SERIES[i % COMPARE_SERIES.length]}
                  strokeWidth={2.5}
                  dot={{ r: 4, strokeWidth: 1, stroke: axis }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export const COMPARE_CHART_DEFS = [
  { key: 'bookValue', title: 'Book Value — YoY' },
  { key: 'netIncome', title: 'Net Income — YoY (B PHP)' },
  { key: 'assets', title: 'Total Assets — YoY (B PHP)' },
  { key: 'liabilities', title: 'Total Liabilities — YoY (B PHP)' },
  { key: 'revenue', title: 'Revenue — YoY (B PHP)' },
  { key: 'eps', title: 'EPS — YoY' },
  { key: 'outstandingShares', title: 'Outstanding Shares — YoY (M)' },
  { key: 'roic', title: 'ROIC / bank capital return — YoY %' },
  { key: 'debtEquity', title: 'Debt / Equity — YoY' },
  { key: 'dividends', title: 'Common Dividends / Share — YoY' },
];
