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
  const axis = '#4d493e';
  const grid = '#bab5a1';

  return (
    <div className="report-chart-card report-chart-card--wide">
      <div className="report-chart-title">{title}</div>
      {!hasData ? (
        <div className="report-chart-empty">No data</div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <ComposedChart data={data} margin={{ top: 16, right: 12, left: -8, bottom: 0 }}>
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
              tickFormatter={(v) => formatLabel(Number(v))}
            />
            <Tooltip
              formatter={(value, name) => [formatLabel(Number(value)), name]}
              contentStyle={{
                fontSize: 17,
                borderRadius: 0,
                border: `1px solid ${axis}`,
                background: '#dcd8c0',
                color: axis,
              }}
            />
            <Legend
              wrapperStyle={{ fontSize: 15, color: axis }}
              iconType="square"
            />
            <Bar
              dataKey="assets"
              name="Assets"
              fill="#7d8a6a"
              stroke={axis}
              strokeWidth={0.5}
              maxBarSize={22}
            />
            <Bar
              dataKey="cash"
              name="Cash"
              fill="#6a8a8a"
              stroke={axis}
              strokeWidth={0.5}
              maxBarSize={22}
            />
            <Bar
              dataKey="liabilities"
              name="Liabilities"
              fill="#8a6a5a"
              stroke={axis}
              strokeWidth={0.5}
              maxBarSize={22}
            />
            <Bar
              dataKey="equity"
              name="Equity (A−L)"
              fill="#9a9278"
              stroke={axis}
              strokeWidth={0.5}
              maxBarSize={22}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
