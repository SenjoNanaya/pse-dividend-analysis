import { useLayoutEffect } from 'react';
import MetricBarChart from './MetricBarChart';
import BalanceSheetChart from './BalanceSheetChart';
import ChecklistPreview from './ChecklistPreview';
import DataQualityPanel from './DataQualityPanel';
import TickerNews from './TickerNews';
import WatchToggle from './WatchToggle';
import { buildReport, formatBillions, formatPct, formatPhp } from '../lib/metrics';
import { METRIC_COLORS } from '../lib/nierPalette';
import { WATCHLIST_MAX } from '../lib/watchlist';

function RatioLabel({ children }) {
  return <th scope="row">{children}</th>;
}

export default function CompanyReport({
  company,
  onBack,
  thresholds,
  watched = false,
  watchDisabled = false,
  onToggleWatch,
}) {
  const report = buildReport(company, thresholds);
  const bvDer = report.bvDerivation || {};
  const dateLabel = report.asOf.toLocaleDateString('en-US', {
    month: 'numeric',
    day: 'numeric',
    year: 'numeric',
  });

  useLayoutEffect(() => {
    window.scrollTo(0, 0);
  }, [company?.id]);

  return (
    <main id="main-content" className="report-page nier-view-settle">
      <header className="report-topbar">
        <div className="report-topbar-nav">
          <button type="button" className="nier-btn nier-btn--compact" onClick={onBack} aria-label="Back to company list">
            Back to list
          </button>
          {onToggleWatch ? (
            <WatchToggle
              ticker={report.displayTicker}
              watched={watched}
              disabled={watchDisabled}
              max={WATCHLIST_MAX}
              showLabel
              className="report-watch-btn"
              onClick={() => onToggleWatch(company)}
            />
          ) : null}
        </div>
        <div className="report-topbar-meta">
          <span className="report-unit">Company report</span>
          <span className="report-date">As of {dateLabel}</span>
        </div>
      </header>

      <div className="report-title-bar">
        <h1 className="report-ticker">{report.displayTicker}</h1>
        <div className="report-title-center">
          <div className="report-name-inline nier-proper-name">{report.companyName}</div>
          <ChecklistPreview report={report} compact showRatios failsFirst />
        </div>
        <div className="report-mcap">
          <div className="report-mcap-label">Market Cap</div>
          <div className="report-mcap-value">{report.marketCapLabel}</div>
        </div>
      </div>

      <DataQualityPanel quality={report.dataQuality} />

      <h2 className="report-section-label">Growth &amp; Ratios</h2>
      <div className="report-side-panel report-ratios-lead">
        <table className="report-table">
          <tbody>
            {report.bankMode ? (
              <>
                <tr>
                  <RatioLabel>Loans CAGR</RatioLabel>
                  <td className="num">{formatPct(report.growth.loans)}</td>
                  <RatioLabel>P/E</RatioLabel>
                  <td className="num">
                    {report.ratios.pe != null ? report.ratios.pe.toFixed(2) : '—'}
                  </td>
                </tr>
                <tr>
                  <RatioLabel>Deposits CAGR</RatioLabel>
                  <td className="num">{formatPct(report.growth.deposits)}</td>
                  <RatioLabel>P/B</RatioLabel>
                  <td className="num">
                    {report.ratios.pb != null ? report.ratios.pb.toFixed(2) : '—'}
                  </td>
                </tr>
                <tr>
                  <RatioLabel>NII CAGR</RatioLabel>
                  <td className="num">{formatPct(report.growth.nii)}</td>
                  <RatioLabel>ROE</RatioLabel>
                  <td className="num">{formatPct(report.ratios.roe)}</td>
                </tr>
                <tr>
                  <RatioLabel>Loans / Deposits</RatioLabel>
                  <td className="num">
                    {report.ratios.ldr != null ? report.ratios.ldr.toFixed(2) : '—'}
                  </td>
                  <RatioLabel>Capital return</RatioLabel>
                  <td className="num">{formatPct(report.ratios.roic)}</td>
                </tr>
                <tr>
                  <RatioLabel>NPL ratio</RatioLabel>
                  <td className="num">{formatPct(report.ratios.nplRatio)}</td>
                  <RatioLabel>Equity / Assets</RatioLabel>
                  <td className="num">{formatPct(report.ratios.equityAssets)}</td>
                </tr>
                <tr>
                  <RatioLabel>Income CAGR</RatioLabel>
                  <td className="num">{formatPct(report.growth.income)}</td>
                  <RatioLabel>Book Value CAGR</RatioLabel>
                  <td className="num">{formatPct(report.growth.bookValue)}</td>
                </tr>
              </>
            ) : (
              <>
                <tr>
                  <RatioLabel>Book Value CAGR</RatioLabel>
                  <td className="num">{formatPct(report.growth.bookValue)}</td>
                  <RatioLabel>P/E</RatioLabel>
                  <td className="num">
                    {report.ratios.pe != null ? report.ratios.pe.toFixed(2) : '—'}
                  </td>
                </tr>
                <tr>
                  <RatioLabel>Income CAGR</RatioLabel>
                  <td className="num">{formatPct(report.growth.income)}</td>
                  <RatioLabel>P/B</RatioLabel>
                  <td className="num">
                    {report.ratios.pb != null ? report.ratios.pb.toFixed(2) : '—'}
                  </td>
                </tr>
                <tr>
                  <RatioLabel>Assets CAGR</RatioLabel>
                  <td className="num">{formatPct(report.growth.assets)}</td>
                  <RatioLabel>ROE</RatioLabel>
                  <td className="num">{formatPct(report.ratios.roe)}</td>
                </tr>
                <tr>
                  <RatioLabel>Liabilities CAGR</RatioLabel>
                  <td className="num">{formatPct(report.growth.liabilities)}</td>
                  <RatioLabel>
                    {report.roicMeta?.mode === 'equity'
                      ? 'Capital return'
                      : report.roicMeta?.mode === 'proxy'
                        ? 'ROIC (proxy)'
                        : 'ROIC'}
                  </RatioLabel>
                  <td className="num">{formatPct(report.ratios.roic)}</td>
                </tr>
                <tr>
                  <RatioLabel>Debt / Equity</RatioLabel>
                  <td className="num">
                    {report.ratios.debtEquity != null
                      ? report.ratios.debtEquity.toFixed(2)
                      : '—'}
                  </td>
                  <td />
                  <td />
                </tr>
              </>
            )}
          </tbody>
        </table>
        <details className="report-method-disclosure">
          <summary>Method notes</summary>
          <p className="report-note">
            {report.bankMode
              ? 'Loans, deposits, and NII scaled to billions PHP. Ratio charts match the bank checklist (LDR, NPL, equity/assets).'
              : 'Income, assets, and liabilities scaled to billions PHP.'}
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
        </details>
      </div>

      <details className="report-section-disclosure">
        <summary>Growth charts</summary>
        <p className="report-chart-scale-note nier-msg-plain">
          Each chart states its unit. Money series use billions of pesos (B PHP) unless marked
          PHP/share or otherwise.
        </p>
        <div className="report-grid-charts">
          <MetricBarChart
            title="Book Value — YoY"
            unit="PHP/share"
            data={report.charts.bookValue}
            color={METRIC_COLORS.bookValue}
          />
          <MetricBarChart
            title="Net Income — YoY"
            unit="B PHP"
            data={report.charts.netIncome}
            color={METRIC_COLORS.netIncome}
          />
          <MetricBarChart
            title="Total Assets — YoY"
            unit="B PHP"
            data={report.charts.assets}
            color={METRIC_COLORS.assets}
          />
          {report.chartVisibility?.liabilities !== false && (
            <MetricBarChart
              title="Total Liabilities — YoY"
              unit="B PHP"
              data={report.charts.liabilities}
              color={METRIC_COLORS.liabilities}
            />
          )}
          {report.chartVisibility?.revenue !== false && (
            <MetricBarChart
              title="Revenue — YoY"
              unit="B PHP"
              data={report.charts.revenue}
              color={METRIC_COLORS.revenue}
            />
          )}
          {report.chartVisibility?.eps !== false && (
            <MetricBarChart
              title="EPS — YoY"
              unit="PHP/share"
              data={report.charts.eps}
              color={METRIC_COLORS.eps}
            />
          )}
          {report.chartVisibility?.loans && (
            <MetricBarChart
              title="Total Loans — YoY"
              unit="B PHP"
              data={report.charts.loans}
              color={METRIC_COLORS.loans}
            />
          )}
          {report.chartVisibility?.deposits && (
            <MetricBarChart
              title="Total Deposits — YoY"
              unit="B PHP"
              data={report.charts.deposits}
              color={METRIC_COLORS.deposits}
            />
          )}
          {report.chartVisibility?.ldr && (
            <MetricBarChart
              title="Loans / Deposits — YoY"
              unit="×"
              data={report.charts.ldr}
              color={METRIC_COLORS.ldr}
            />
          )}
          {report.chartVisibility?.nplRatio && (
            <MetricBarChart
              title="NPL Ratio — YoY"
              unit="%"
              data={report.charts.nplRatio}
              color={METRIC_COLORS.nplRatio}
            />
          )}
          {report.chartVisibility?.equityAssets && (
            <MetricBarChart
              title="Equity / Assets — YoY"
              unit="%"
              data={report.charts.equityAssets}
              color={METRIC_COLORS.equityAssets}
            />
          )}
          {report.chartVisibility?.nii && (
            <MetricBarChart
              title="Net Interest Income — YoY"
              unit="B PHP"
              data={report.charts.nii}
              color={METRIC_COLORS.nii}
            />
          )}
          {report.chartVisibility?.outstandingShares && (
            <MetricBarChart
              title="Outstanding Shares — YoY"
              unit="M shares"
              data={report.charts.outstandingShares}
              color={METRIC_COLORS.outstandingShares}
            />
          )}
          {report.chartVisibility?.roic && (
            <MetricBarChart
              title={
                report.roicMeta?.mode === 'proper'
                  ? `ROIC${report.roicMeta?.statementScope ? ` (${report.roicMeta.statementScope})` : ''} — YoY`
                  : report.roicMeta?.mode === 'equity'
                    ? 'Capital return (NI / equity) — YoY'
                    : report.roicMeta?.mode === 'na'
                      ? 'Capital return — N/A'
                      : 'ROIC (proxy) — YoY'
              }
              unit="%"
              data={report.charts.roic}
              color={METRIC_COLORS.roic}
            />
          )}
          {report.chartVisibility?.debtEquity !== false && (
            <MetricBarChart
              title="Debt / Equity — YoY"
              unit="×"
              data={report.charts.debtEquity}
              color={METRIC_COLORS.debtEquity}
            />
          )}
        </div>
      </details>

      <details className="report-section-disclosure">
        <summary>Book value derivation</summary>
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
                    {bvDer.assets != null ? `${formatBillions(bvDer.assets)} B PHP` : '—'}
                  </td>
                </tr>
                <tr>
                  <td>Total Liabilities</td>
                  <td className="num">
                    {bvDer.liabilities != null
                      ? `${formatBillions(bvDer.liabilities)} B PHP`
                      : '—'}
                  </td>
                </tr>
                <tr>
                  <td>Cash &amp; Equivalents</td>
                  <td className="num">
                    {bvDer.cash != null ? `${formatBillions(bvDer.cash)} B PHP` : '—'}
                  </td>
                </tr>
                <tr>
                  <td>Current Liabilities</td>
                  <td className="num">
                    {bvDer.currentLiabilities != null
                      ? `${formatBillions(bvDer.currentLiabilities)} B PHP`
                      : '—'}
                  </td>
                </tr>
                <tr>
                  <td>IC (A − Cash − CL)</td>
                  <td className="num">
                    {bvDer.investedCapital != null
                      ? `${formatBillions(bvDer.investedCapital)} B PHP`
                      : '—'}
                  </td>
                </tr>
                <tr>
                  <td>Equity (A − L)</td>
                  <td className="num">
                    {bvDer.equity != null ? `${formatBillions(bvDer.equity)} B PHP` : '—'}
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
      </details>

      <details className="report-section-disclosure">
        <summary>Dividends &amp; fair value</summary>
        <div className="report-bottom-grid">
          <div className="report-dividends-block">
            <MetricBarChart
              title="Common Dividends / Year"
              unit="PHP/share"
              data={report.charts.dividends}
              color={METRIC_COLORS.dividends}
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
      </details>

      <details className="report-section-disclosure">
        <summary>News — headlines for this ticker</summary>
        <TickerNews companyId={company.id} ticker={report.displayTicker} embedded />
      </details>

      <footer className="report-footer">
        <div className="report-note-block">
          <strong>SYS_NOTE:</strong> Built from PSE EDGE annual filings. Quarterly figures
          appear when they are in the registry. News is optional depth and may be incomplete.
        </div>
        <div className="report-disclaimer">
          For research only — not investment advice. Confirm figures against official
          company disclosures before acting on them.
        </div>
      </footer>
    </main>
  );
}
