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

function formatLabel(v) {
  if (v == null || Number.isNaN(v)) return '';
  const abs = Math.abs(v);
  if (abs >= 100) return v.toFixed(0);
  if (abs >= 10) return v.toFixed(1);
  return v.toFixed(2);
}

export default function MetricBarChart({
  title,
  data,
  color = '#abab8d',
  height = 200,
  showTrend = true,
}) {
  const hasData = Array.isArray(data) && data.some((d) => d.value != null);
  const axis = '#4d493e';
  const grid = '#bab5a1';
  const trend = '#8a7a4a';

  return (
    <div className="report-chart-card">
      <div className="report-chart-title">{title}</div>
      {!hasData ? (
        <div className="report-chart-empty">No data</div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <ComposedChart data={data} margin={{ top: 20, right: 10, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={grid} />
            <XAxis
              dataKey="year"
              tick={{ fontSize: 16, fill: axis }}
              axisLine={{ stroke: axis }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 14, fill: axis }}
              axisLine={false}
              tickLine={false}
              width={52}
            />
            <Tooltip
              formatter={(value) => formatLabel(Number(value))}
              contentStyle={{
                fontSize: 17,
                borderRadius: 0,
                border: `1px solid ${axis}`,
                background: '#dcd8c0',
                color: axis,
              }}
            />
            <Bar dataKey="value" fill={color} stroke={axis} strokeWidth={0.6} maxBarSize={32}>
              <LabelList
                dataKey="value"
                position="top"
                formatter={(v) => formatLabel(Number(v))}
                style={{ fontSize: 14, fill: axis, fontWeight: 600 }}
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
      )}
    </div>
  );
}
