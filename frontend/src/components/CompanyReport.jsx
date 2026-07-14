import MetricBarChart from './MetricBarChart';
import ChecklistPreview from './ChecklistPreview';
import { buildReport, formatPct, formatPhp } from '../lib/metrics';

export default function CompanyReport({ company, onBack }) {
  const report = buildReport(company);
  const dateLabel = report.asOf.toLocaleDateString('en-US', {
    month: 'numeric',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div className="report-page animate-fade-in">
      <header className="report-topbar">
        <div className="report-brand-row">
          <button type="button" className="report-back" onClick={onBack}>
            &lt; REGISTRY
          </button>
          <span className="report-unit">FUNDAMENTAL_METRICS_UNIT</span>
        </div>
        <span className="report-date">AS_OF: {dateLabel}</span>
      </header>

      <div className="report-title-bar">
        <div className="report-ticker">{report.displayTicker}</div>
        <div className="report-title-center">
          <div className="report-name-inline">{report.companyName}</div>
          <ChecklistPreview report={report} compact showRatios />
        </div>
        <div className="report-mcap">
          <div className="report-mcap-label">Market Cap</div>
          <div className="report-mcap-value">{report.marketCapLabel}</div>
        </div>
      </div>

      <section className="report-section-label">Growth Overview</section>

      <div className="report-grid-charts">
        <MetricBarChart
          title="Book Value — YoY"
          data={report.charts.bookValue}
          color="#9a9278"
        />
        <MetricBarChart
          title="Net Income — YoY"
          data={report.charts.netIncome}
          color="#6e7f8d"
        />
        <MetricBarChart
          title="Total Assets — YoY"
          data={report.charts.assets}
          color="#7d8a6a"
        />
        <MetricBarChart
          title="Revenue — YoY"
          data={report.charts.revenue}
          color="#6a8a8a"
        />
        <MetricBarChart
          title="EPS — YoY"
          data={report.charts.eps}
          color="#8a6a5a"
        />
        <div className="report-side-panel">
          <div className="report-panel-title">Growth &amp; Ratios</div>
          <table className="report-table">
            <tbody>
              <tr>
                <td>Book Value CAGR</td>
                <td className="num">{formatPct(report.growth.bookValue)}</td>
                <td>P/E</td>
                <td className="num">
                  {report.ratios.pe != null ? report.ratios.pe.toFixed(2) : '—'}
                </td>
              </tr>
              <tr>
                <td>Income CAGR</td>
                <td className="num">{formatPct(report.growth.income)}</td>
                <td>P/B</td>
                <td className="num">
                  {report.ratios.pb != null ? report.ratios.pb.toFixed(2) : '—'}
                </td>
              </tr>
              <tr>
                <td>Assets CAGR</td>
                <td className="num">{formatPct(report.growth.assets)}</td>
                <td>ROE</td>
                <td className="num">{formatPct(report.ratios.roe)}</td>
              </tr>
            </tbody>
          </table>
          <p className="report-note">
            Income and assets scaled to billions PHP. Per-share metrics from annual filings.
            Price and ratios sourced from EDGE stock data, Form 17-A disclosures, or derived values.
          </p>
        </div>
      </div>

      <div className="report-bottom-grid">
        <div className="report-snapshot-block">
          <div className="report-panel-title light">Recent Years</div>
          <MetricBarChart
            title="Book Value"
            data={report.charts.bookValue.slice(-4)}
            color="#9a9278"
            height={100}
          />
          <MetricBarChart
            title="Net Income"
            data={report.charts.netIncome.slice(-4)}
            color="#6e7f8d"
            height={100}
          />
          <MetricBarChart
            title="Total Assets"
            data={report.charts.assets.slice(-4)}
            color="#7d8a6a"
            height={100}
          />
        </div>

        <div className="report-dividends-block">
          <MetricBarChart
            title="Common Dividends / Year"
            data={report.charts.dividends}
            color="#ab9d72"
            height={140}
          />
          <div className="report-panel-title">Dividend History</div>
          {report.dividend.history.length === 0 ? (
            <div className="report-chart-empty" style={{ height: 80 }}>No data</div>
          ) : (
            <div className="report-div-table-wrap">
              <table className="report-table report-div-table">
                <thead>
                  <tr>
                    <th>Security</th>
                    <th>Rate</th>
                    <th>Ex-Date</th>
                    <th>Record</th>
                    <th>Payment</th>
                  </tr>
                </thead>
                <tbody>
                  {report.dividend.history.slice(0, 12).map((row) => (
                    <tr
                      key={`${row.security}-${row.exDate}-${row.amount}`}
                      className={row.isCommon ? '' : 'report-div-pref'}
                    >
                      <td title={row.security}>
                        {row.isCommon ? 'COMMON' : row.security}
                      </td>
                      <td className="num">{formatPhp(row.amount, 4)}</td>
                      <td>{row.exDate || '—'}</td>
                      <td>{row.recordDate || '—'}</td>
                      <td>{row.paymentDate || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="report-valuation">
          <div className="report-yield-block">
            <div className="report-yield-label">3Y Avg Dividend Yield</div>
            <div className="report-yield-value">
              {formatPct(report.dividend.avgYield3y)}
            </div>
            <div className="report-cover-row">
              <span>Dividend Cover</span>
              <span
                className={`report-cover-badge status-${report.dividend.coverStatus.toLowerCase()}`}
              >
                {report.dividend.coverStatus}
              </span>
            </div>
          </div>

          <div className="report-panel-title">Fair Value Scenarios</div>
          <table className="report-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Est. Value</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>YoY Growth</td>
                <td className="num">{formatPhp(report.valuation.yoyGrowthFv)}</td>
              </tr>
              <tr>
                <td>Blended Growth</td>
                <td className="num">{formatPhp(report.valuation.quarterlyGrowthFv)}</td>
              </tr>
              <tr>
                <td>Zero Growth</td>
                <td className="num">{formatPhp(report.valuation.zeroGrowthFv)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <footer className="report-footer">
        <div className="report-note-block">
          <strong>SYS_NOTE:</strong> Generated from PSE EDGE annual filings.
          Interim quarterly series will populate when available in the registry.
        </div>
        <div className="report-disclaimer">
          For informational use only — not investment advice.
          Confirm all figures against official company disclosures before acting on them.
        </div>
      </footer>
    </div>
  );
}
