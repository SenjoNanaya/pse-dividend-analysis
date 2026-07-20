import {
  Bar,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { summarizeSeries } from '../lib/chartSummary';
import { formatChartNumber, formatChartValue } from '../lib/chartUnits';
import { CHART_SURFACE, CHART_TYPE, METRIC_COLORS } from '../lib/nierPalette';

export default function MetricBarChart({
  title,
  unit,
  data,
  color = METRIC_COLORS.bookValue,
  height = 200,
  showTrend = true,
}) {
  const hasData = Array.isArray(data) && data.some((d) => d.value != null);
  const { axis, grid, tooltipBg, trend } = CHART_SURFACE;
  const summary = summarizeSeries(
    unit ? `${title} (${unit})` : title,
    data,
    (v) => formatChartValue(v, unit),
  );

  return (
    <div className="report-chart-card" role="img" aria-label={summary}>
      <div className="report-chart-head" aria-hidden="true">
        <div className="report-chart-title">{title}</div>
        {unit ? (
          <div className="report-chart-unit">
            Values in <span className="report-chart-unit-value">{unit}</span>
          </div>
        ) : null}
      </div>
      {!hasData ? (
        <div className="report-chart-empty" aria-hidden="true">No data</div>
      ) : (
        <div aria-hidden="true">
          <ResponsiveContainer width="100%" height={height}>
            <ComposedChart data={data} margin={{ top: 20, right: 10, left: -12, bottom: 0 }}>
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
                tickFormatter={(v) => formatChartNumber(v)}
              />
              <Tooltip
                formatter={(value) => [formatChartValue(Number(value), unit), unit || 'Value']}
                contentStyle={{
                  fontSize: CHART_TYPE.tooltip,
                  borderRadius: 0,
                  border: `1px solid ${axis}`,
                  background: tooltipBg,
                  color: axis,
                }}
              />
              <Bar dataKey="value" fill={color} stroke={axis} strokeWidth={0.6} maxBarSize={32}>
                <LabelList
                  dataKey="value"
                  position="top"
                  formatter={(v) => formatChartValue(Number(v), unit)}
                  style={{ fontSize: CHART_TYPE.label, fill: axis, fontWeight: 600 }}
                />
              </Bar>
              {showTrend && (
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke={trend}
                  strokeWidth={2}
                  dot={{ r: 3, fill: trend, stroke: axis, strokeWidth: 0.5 }}
                  isAnimationActive={false}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
