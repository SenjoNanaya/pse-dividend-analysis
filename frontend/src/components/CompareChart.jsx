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
import { formatChartNumber, formatChartValue } from '../lib/chartUnits';
import { CHART_SURFACE, CHART_TYPE, COMPARE_SERIES, NIER } from '../lib/nierPalette';

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
  unit,
  reports,
  chartKey,
  height = 280,
}) {
  const tickers = reports.map((r) => r.displayTicker);
  const data = mergeChartSeries(reports, chartKey);
  const hasData = data.some((row) => tickers.some((t) => row[t] != null));
  const { axis, grid, tooltipBg } = CHART_SURFACE;
  const summary = summarizeCompare(
    unit ? `${title} (${unit})` : title,
    data,
    tickers,
  );

  return (
    <div className="compare-chart-card" role="img" aria-label={summary}>
      <div className="compare-chart-head" aria-hidden="true">
        <div className="compare-chart-title">{title}</div>
        {unit ? (
          <div className="report-chart-unit">
            Values in <span className="report-chart-unit-value">{unit}</span>
          </div>
        ) : null}
      </div>
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
                tickFormatter={(v) => formatChartNumber(v)}
              />
              <Tooltip
                formatter={(value, name) => [
                  formatChartValue(Number(value), unit),
                  name,
                ]}
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
  { key: 'bookValue', title: 'Book Value — YoY', unit: 'PHP/share' },
  { key: 'netIncome', title: 'Net Income — YoY', unit: 'B PHP' },
  { key: 'assets', title: 'Total Assets — YoY', unit: 'B PHP' },
  { key: 'liabilities', title: 'Total Liabilities — YoY', unit: 'B PHP' },
  { key: 'revenue', title: 'Revenue — YoY', unit: 'B PHP' },
  { key: 'eps', title: 'EPS — YoY', unit: 'PHP/share' },
  { key: 'outstandingShares', title: 'Outstanding Shares — YoY', unit: 'M shares' },
  { key: 'roic', title: 'ROIC / bank capital return — YoY', unit: '%' },
  { key: 'debtEquity', title: 'Debt / Equity — YoY', unit: '×' },
  { key: 'dividends', title: 'Common Dividends / Share — YoY', unit: 'PHP/share' },
];
