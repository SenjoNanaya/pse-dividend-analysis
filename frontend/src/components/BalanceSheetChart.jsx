import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { summarizeBalanceSheet } from '../lib/chartSummary';
import { CHART_SURFACE, CHART_TYPE, METRIC_COLORS } from '../lib/nierPalette';

function formatLabel(v) {
  if (v == null || Number.isNaN(v)) return '';
  const abs = Math.abs(v);
  if (abs >= 100) return v.toFixed(0);
  if (abs >= 10) return v.toFixed(1);
  return v.toFixed(2);
}

/** Grouped Assets / Liabilities / Equity (₱B) for BV identity: A − L ≈ E. */
export default function BalanceSheetChart({
  title = 'Balance Sheet — Assets, Liabilities, Equity',
  data,
  height = 220,
}) {
  const hasData =
    Array.isArray(data) &&
    data.some(
      (d) =>
        d.assets != null
        || d.liabilities != null
        || d.equity != null
        || d.cash != null,
    );
  const { axis, grid, tooltipBg } = CHART_SURFACE;
  const summary = summarizeBalanceSheet(title, data);

  return (
    <div className="report-chart-card report-chart-card--wide" role="img" aria-label={summary}>
      <div className="report-chart-title" aria-hidden="true">{title}</div>
      {!hasData ? (
        <div className="report-chart-empty" aria-hidden="true">No data</div>
      ) : (
        <div aria-hidden="true">
          <ResponsiveContainer width="100%" height={height}>
            <ComposedChart data={data} margin={{ top: 16, right: 12, left: -8, bottom: 0 }}>
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
                width={52}
                tickFormatter={(v) => formatLabel(Number(v))}
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
                wrapperStyle={{ fontSize: CHART_TYPE.legend, color: axis }}
                iconType="square"
              />
              <Bar
                dataKey="assets"
                name="Assets"
                fill={METRIC_COLORS.assets}
                stroke={axis}
                strokeWidth={0.5}
                maxBarSize={22}
              />
              <Bar
                dataKey="cash"
                name="Cash"
                fill={METRIC_COLORS.cash}
                stroke={axis}
                strokeWidth={0.5}
                maxBarSize={22}
              />
              <Bar
                dataKey="liabilities"
                name="Liabilities"
                fill={METRIC_COLORS.liabilities}
                stroke={axis}
                strokeWidth={0.5}
                maxBarSize={22}
              />
              <Bar
                dataKey="equity"
                name="Equity (A−L)"
                fill={METRIC_COLORS.equity}
                stroke={axis}
                strokeWidth={0.5}
                maxBarSize={22}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
