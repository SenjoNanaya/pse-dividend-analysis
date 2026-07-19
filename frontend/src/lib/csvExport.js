export const COMPANY_CSV_COLUMNS = [
  { key: 'ticker', header: 'ticker', get: (c) => c.ticker || c.symbol || '' },
  { key: 'name', header: 'name', get: (c) => c.name || '' },
  { key: 'price', header: 'price', get: (c) => c.last_traded_price },
  { key: 'market_cap', header: 'market_cap', get: (c) => c.market_cap },
  { key: 'div_yield', header: 'div_yield', get: (c) => c.div_yield },
  { key: 'sector', header: 'sector', get: (c) => c.sector || '' },
  { key: 'subsector', header: 'subsector', get: (c) => c.subsector || '' },
  { key: 'pe_ratio', header: 'pe_ratio', get: (c) => c.pe_ratio },
  { key: 'pb_ratio', header: 'pb_ratio', get: (c) => c.pb_ratio },
  { key: 'roe', header: 'roe', get: (c) => c.roe },
  { key: 'debt_to_equity', header: 'debt_to_equity', get: (c) => c.debt_to_equity },
  { key: 'roic', header: 'roic', get: (c) => c.roic },
  {
    key: 'check_pass_count',
    header: 'check_pass_count',
    get: (c) => c.check_pass_count,
  },
  {
    key: 'check_evaluable_total',
    header: 'check_evaluable_total',
    get: (c) => c.check_evaluable_total,
  },
  {
    key: 'info_incomplete',
    header: 'info_incomplete',
    get: (c) => c.info_incomplete,
  },
  {
    key: 'dilution_pass',
    header: 'dilution_pass',
    get: (c) => (c.dilution_pass === undefined ? '' : c.dilution_pass),
  },
];

function csvEscape(value) {
  if (value == null) return '';
  const s = String(value);
  if (/[",\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function toCsv(rows, columns = COMPANY_CSV_COLUMNS) {
  const header = columns.map((c) => csvEscape(c.header)).join(',');
  const lines = rows.map((row) =>
    columns.map((c) => csvEscape(c.get(row))).join(','),
  );
  return [header, ...lines].join('\r\n');
}

export function downloadCsv(filename, text) {
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function csvDateStamp(d = new Date()) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}${m}${day}`;
}

/** Fetch every page of a DRF list URL. */
export async function fetchAllListPages(startUrl, { headers } = {}) {
  let url = startUrl;
  const rows = [];
  let count = null;
  while (url) {
    const res = await fetch(url, { headers });
    if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
    const data = await res.json();
    if (count == null && data.count != null) count = data.count;
    rows.push(...(data.results || []));
    url = data.next || null;
  }
  return { rows, count };
}
