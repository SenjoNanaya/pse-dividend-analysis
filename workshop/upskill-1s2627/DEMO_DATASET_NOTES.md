# Demo dataset notes — beginner / real-world appreciation

## Goal

Applicants should recognize most rows without a finance background. Metrics stay plain.

## Schema

| Column | Teaching use |
|--------|----------------|
| `ticker` | Market shorthand (SM, JFC, BDO…) |
| `company_name` | Formal name |
| `familiar_as` | “Why I know this” blurb |
| `sector` | Filter practice |
| `last_price` | Charting / sorting |
| `div_yield_pct` | Main beginner metric (already in %) |
| `debt_to_equity` | Optional second filter; blank for banks on purpose |
| `data_complete` | `yes` / `no` — missing-data hygiene |
| `notes` | Speaker prompts (high yield skepticism, etc.) |

## Curation tips

- Prefer household names over obscure tickers.  
- Keep ~18–25 rows.  
- Include 3 incomplete rows and 1–2 “suspiciously high yield” rows.  
- If refreshing from the live warehouse, **round** and **date-stamp** the snapshot; never imply trading advice.  
- Banks: leave `debt_to_equity` blank and explain in one sentence why industrial debt shortcuts mislead.

## Slide / notebook disclaimer (required)

Educational workshop dataset for UPLB Data Science Guild applicants. Not investment advice. Figures are a simplified snapshot for teaching and may be rounded or outdated. Not affiliated with the PSE.
