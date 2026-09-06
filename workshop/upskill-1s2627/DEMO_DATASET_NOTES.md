# UPSkill 1S2627 — Demo dataset notes

Use these columns for the **PM Python** starter CSV and (optionally) the messy AM spreadsheet.

## Suggested schema

| Column | Type | Teaching use |
|--------|------|--------------|
| `ticker` | string | Identity |
| `company_name` | string | Split / clean demos |
| `sector` | string | Filter practice |
| `subsector` | string | Banks vs industrial framing |
| `last_price` | float | Charting |
| `div_yield` | float / blank | Missingness + screen threshold |
| `roic` | float / blank | Industrial return metric |
| `capital_return` | float / blank | Bank-friendly equity return (optional column) |
| `debt_to_equity` | float / blank | Second screen condition |
| `info_incomplete` | 0/1 | Data-quality flag |
| `fiscal_years_present` | int | Completeness story |

## Generation tips

- Include ~25–40 rows so filters feel meaningful but share-outs stay short.
- Intentionally leave ~15–20% blanks in ratio columns.
- Include 2–3 absurd outliers (e.g., yield > 100%) so speakers can teach “question the number.”
- Mark a few `subsector = Banks` rows; mention capital return vs ROIC only as a short aside.

## Disclaimer blurb (put on slide 1 of PM)

Educational workshop dataset. Not investment advice. Figures may be synthetic or simplified for teaching.
