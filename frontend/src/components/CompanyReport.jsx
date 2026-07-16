import MetricBarChart from './MetricBarChart';
import BalanceSheetChart from './BalanceSheetChart';
import ChecklistPreview from './ChecklistPreview';
import TickerNews from './TickerNews';
import { buildReport, formatBillions, formatPct, formatPhp } from '../lib/metrics';

export default function CompanyReport({ company, onBack, thresholds }) {
  const report = buildReport(company, thresholds);
  const bvDer = report.bvDerivation || {};
  const dateLabel = report.asOf.toLocaleDateString('en-US', {
    month: 'numeric',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div className="report-page animate-fade-in">
      <header className="report-topbar">
        <div className="report-brand-row">
          <button type="button" className="report-back" onClick={onBack} aria-label="Back to registry">
            &lt; REGISTRY
          </button>
          <span className="report-unit">FUNDAMENTAL_METRICS_UNIT</span>
        </div>
        <span className="report-date">AS_OF: {dateLabel}</span>
      </header>

      <div className="report-title-bar">
        <h1 className="report-ticker">{report.displayTicker}</h1>
        <div className="report-title-center">
          <div className="report-name-inline">{report.companyName}</div>
          <ChecklistPreview report={report} compact showRatios />
        </div>
        <div className="report-mcap">
          <div className="report-mcap-label">Market Cap</div>
          <div className="report-mcap-value">{report.marketCapLabel}</div>
        </div>
      </div>

      <h2 className="report-section-label">Growth Overview</h2>

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
          title="Total Liabilities — YoY"
          data={report.charts.liabilities}
          color="#8a6a5a"
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
        <MetricBarChart
          title={
            report.roicMeta?.mode === 'proper'
              ? `ROIC${report.roicMeta?.statementScope ? ` (${report.roicMeta.statementScope})` : ''} — YoY %`
              : report.roicMeta?.mode === 'equity'
                ? 'Bank capital return (NI ÷ equity) — YoY %'
                : report.roicMeta?.mode === 'na'
                  ? 'ROIC — N/A (financials)'
                  : 'ROIC (proxy) — YoY %'
          }
          data={report.charts.roic}
          color="#6a7a5a"
        />
        <MetricBarChart
          title="Debt / Equity — YoY"
          data={report.charts.debtEquity}
          color="#8a5a6a"
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
              <tr>
                <td>Liabilities CAGR</td>
                <td className="num">{formatPct(report.growth.liabilities)}</td>
                <td>
                  {report.roicMeta?.mode === 'equity'
                    ? 'Bank ROE capital'
                    : 'ROIC'}
                </td>
                <td className="num">{formatPct(report.ratios.roic)}</td>
              </tr>
              <tr>
                <td>Debt / Equity</td>
                <td className="num">
                  {report.ratios.debtEquity != null
                    ? report.ratios.debtEquity.toFixed(2)
                    : '—'}
                </td>
                <td />
                <td />
              </tr>
            </tbody>
          </table>
          <p className="report-note">
            Income, assets, and liabilities scaled to billions PHP.
            {report.roicMeta?.mode === 'proper' && (
              <>
                {' '}Proper ROIC = NOPAT ÷ average (Assets − Cash − Current Liabilities)
                {report.roicMeta?.taxAssumed ? ' (tax rate assumed 25%).' : '.'}
              </>
            )}
            {report.roicMeta?.mode === 'proxy' && (
              <>
                {' '}Proxy ROIC = NI ÷ average invested capital
                {report.roicMeta?.usedCurrentLiab
                  ? ' (Assets − Current Liabilities).'
                  : ' (Total Assets — ROA-like).'}
              </>
            )}
            {report.roicMeta?.mode === 'equity' && (
              <>
                {' '}Banks / insurance: capital return = NI ÷ average stockholders&apos; equity
                (industrial ROIC is not applied). Closely related to ROE.
              </>
            )}
            {report.roicMeta?.mode === 'na' && (
              <> Classical ROIC is not applied to banks / insurance.</>
            )}
            {' '}
            Price and ratios sourced from EDGE stock data, Form 17-A disclosures, or derived values.
          </p>
        </div>
      </div>

      <h2 className="report-section-label">Book Value Derivation</h2>
      <p className="report-note report-note--section">
        Book equity ≈ Assets − Liabilities. Reported BVPS comes from the filing; derived BVPS uses
        equity ÷ outstanding shares when both are available.
      </p>
      <div className="report-bv-derivation">
        <BalanceSheetChart data={report.charts.balanceSheet} height={240} />
        <div className="report-side-panel report-bv-panel">
          <div className="report-panel-title">Latest year identity</div>
          <table className="report-table">
            <tbody>
              <tr>
                <td>Total Assets</td>
                <td className="num">
                  {bvDer.assets != null ? `${formatBillions(bvDer.assets)} B` : '—'}
                </td>
              </tr>
              <tr>
                <td>Total Liabilities</td>
                <td className="num">
                  {bvDer.liabilities != null
                    ? `${formatBillions(bvDer.liabilities)} B`
                    : '—'}
                </td>
              </tr>
              <tr>
                <td>Cash &amp; Equivalents</td>
                <td className="num">
                  {bvDer.cash != null ? `${formatBillions(bvDer.cash)} B` : '—'}
                </td>
              </tr>
              <tr>
                <td>Current Liabilities</td>
                <td className="num">
                  {bvDer.currentLiabilities != null
                    ? `${formatBillions(bvDer.currentLiabilities)} B`
                    : '—'}
                </td>
              </tr>
              <tr>
                <td>IC (A − Cash − CL)</td>
                <td className="num">
                  {bvDer.investedCapital != null
                    ? `${formatBillions(bvDer.investedCapital)} B`
                    : '—'}
                </td>
              </tr>
              <tr>
                <td>Equity (A − L)</td>
                <td className="num">
                  {bvDer.equity != null ? `${formatBillions(bvDer.equity)} B` : '—'}
                </td>
              </tr>
              <tr>
                <td>BVPS (reported)</td>
                <td className="num">
                  {bvDer.bookValueReported != null
                    ? formatPhp(bvDer.bookValueReported, 2)
                    : '—'}
                </td>
              </tr>
              <tr>
                <td>BVPS (equity ÷ shares)</td>
                <td className="num">
                  {bvDer.bookValueDerived != null
                    ? formatPhp(bvDer.bookValueDerived, 2)
                    : '—'}
                </td>
              </tr>
            </tbody>
          </table>
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
          <MetricBarChart
            title="Total Liabilities"
            data={report.charts.liabilities.slice(-4)}
            color="#8a6a5a"
            height={100}
          />
          <MetricBarChart
            title={
              report.roicMeta?.mode === 'equity'
                ? 'Bank capital return %'
                : report.roicMeta?.mode === 'proper'
                  ? 'ROIC %'
                  : 'ROIC (proxy) %'
            }
            data={report.charts.roic.slice(-4)}
            color="#6a7a5a"
            height={100}
          />
          <MetricBarChart
            title="Debt / Equity"
            data={(report.charts.debtEquity || []).slice(-4)}
            color="#8a5a6a"
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
                    <th>Type</th>
                    <th>Rate</th>
                    <th>Ex-Date</th>
                    <th>Record</th>
                    <th>Payment</th>
                  </tr>
                </thead>
                <tbody>
                  {report.dividend.history.slice(0, 12).map((row) => {
                    const dtype = String(row.type || 'cash').toLowerCase();
                    const isCash = dtype === 'cash';
                    return (
                      <tr
                        key={`${row.security}|${dtype}|${row.exDate}|${row.amount}|${row.recordDate || ''}`}
                        className={row.isCommon ? '' : 'report-div-pref'}
                      >
                        <td title={row.security}>
                          {row.isCommon ? 'COMMON' : row.security}
                        </td>
                        <td>{dtype}</td>
                        <td className="num">
                          {isCash ? formatPhp(row.amount, 4) : '—'}
                        </td>
                        <td>{row.exDate || '—'}</td>
                        <td>{row.recordDate || '—'}</td>
                        <td>{row.paymentDate || '—'}</td>
                      </tr>
                    );
                  })}
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
            <p className="report-note" style={{ marginTop: 0 }}>
              Average of completed calendar years (excludes current year until all quarters are in).
              Listed yield uses trailing 12 months cash dividends only.
            </p>
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

      <TickerNews companyId={company.id} ticker={report.displayTicker} />

      <footer className="report-footer">
        <div className="report-note-block">
          <strong>SYS_NOTE:</strong> Generated from PSE EDGE annual filings.
          Interim quarterly series will populate when available in the registry.
          News headlines are aggregated from Google News RSS and may be incomplete.
        </div>
        <div className="report-disclaimer">
          For informational use only — not investment advice.
          Confirm all figures against official company disclosures before acting on them.
        </div>
      </footer>
    </div>
  );
}
