# UPSkill Applicants Workshop — 1st Sem AY 2026–2027

## Overview

### Program Description / Workshop Overview

| Field | Details |
|-------|---------|
| **Workshop Title** | UPSkill 1S2627 — From Filings to Insight |
| **Date & Time** | September 17, 2026 · AM 9:30–12:35 · PM 2:30–6:00 |
| **Venue** | 1st Option: [TBD – UPLB onsite] · 2nd Option: Zoom |
| **Org** | UPLB Data Science Guild |

### Applicants Demographic

> **Fill once the applicant roster is locked.** Template based on the prior Applicants Workshop format.

**Applicants Profile (placeholder)**  
Summarize degree programs (counts + %), university batches (counts + %), and any notable mix (e.g., CS-heavy vs adjacent fields). Call out whether the pool is mostly first-exposure DS applicants or includes more mature technical applicants.

### Objective

To give participants an initial look into Data Science: its breadth, fundamental skills, and practical applications — using **prepared Philippine company financial metrics** as the running example — while setting a baseline for future Guild workshops. The goal is to build appreciation and engage applicants through a **tangible output**: a cleaned spreadsheet table in the morning, and a personal mini stock screen in the afternoon.

### Rationale

We assume applicants are possibly new to actual exposure with DS; some coming from adjacent backgrounds, others younger batches in technical programs. There may also be mature applicants expecting technical insight. This workshop therefore stays **broad rather than deep**, focuses on sparking interest, and delivers hands-on takeaways that match a mixed experience range.

The theme is inspired by a real Guild-adjacent data problem: turning public market disclosures into structured tables you can actually reason over (clean labels, missing values, simple ratios, and a screen). We will **not** scrape live websites during the workshop. Applicants work on **curated demo CSVs / sheets** so setup friction stays low and the learning stays on methods, not infrastructure.

Coverage intentionally mirrors the DS pipeline Guild members use later:

1. **Clean & explore** messy tabular data (AM — spreadsheets)  
2. **Analyze & decide** with Python/Pandas on the same domain (PM — mini screen)

---

## Layout / How to read this packet

1. Program Flow — schedule, norms, and what to bring  
2. Topic Outline — progression, guide questions, topics, workflow per session  
3. Speakers Bio — [to be filled after speakers meeting]  
4. Resources — files, installs, and pre-work  

---

## I. Applicants Workshop 1S2627: Program Flow

### Topics

1. **Data Cleaning and Exploration in Spreadsheets** (Google Sheets or Excel)  
2. **Python, Pandas, and a Mini Stock Screen**

| | Session [1] | Session [2] |
|---|-------------|-------------|
| **Date** | Sep 17, 2026 | Sep 17, 2026 |
| **Time** | 9:30 AM – 12:35 PM | 2:30 PM – 6:00 PM |
| **Venue** | [TBD] / Zoom backup | [TBD] / Zoom backup |

### Program Outline

- Ingress is ~10–15 mins so we can start and end on time.  
- Expect makeup / asynchronous tasks if you miss a session; incentives for applicants present in **both**.  
- Aim to attend at least one session for the process; if your schedule allows both, take full advantage.  

**Please anticipate the following:**

1. Workshop proper includes presentation, activity, and Q&As. Questions can be raised at any point; resident members or speakers can address them.  
   - **Speaker note:** If applicants will present, reserve ~15–20 mins leeway inside the allotted block.  
2. Midday gap is lunch; PM session pause can double as a short snack break. Applicants, please bring water (and snacks if staying onsite).  
3. **Reminders:** Install tools and open resource links **before** the PM session. Technical-check windows exist so every applicant’s environment is ready and blockers are fixed early.

---

## Topic Outline

### What to expect!

\*also subject to speakers’ preference

---

### Session [1] — SheetSkills: From Messy Extract to Readable Table

**Working metaphor:** You received a “disclosure dump” — uneven headers, blank cells, mixed number formats. By the end, you have a sorted, filtered, chart-ready sheet.

#### Progression

1. **Start:** A blank-ish worksheet and an unorganized set of company/financial rows  
2. **End:** A well-organized, sorted, and formatted worksheet with at least one chart and a short written observation

#### Guide Questions

1. Why is my formula showing on the cell instead of the result?  
2. How do I copy a formula down hundreds of rows without dragging forever?  
3. What does `#VALUE!` / `#DIV/0!` mean and how do I fix it?  
4. How do I split a ticker + company name cell into two columns?  
5. How do I flag rows with missing ROIC / yield / debt figures?  
6. How do I chart the top 10 names by a chosen metric?

#### Topics

1. Spreadsheet interface and data entry  
2. Essential shortcut keys  
3. Sorting and filtering  
4. Formatting for readability  
5. Essential formulas (`IF`, `IFERROR`, `VLOOKUP`/`XLOOKUP` or `INDEX`/`MATCH`, basic arithmetic)  
6. Charts and simple dashboards  
7. Light data-quality habits (blanks, duplicates, scale notes like “in thousands”)

#### Workflow

1. **Introduction to Sheets and interface mapping** — tabs, ranges, freeze panes  
2. **Essential shortcuts** — reduce mouse overreliance  
3. **Sorting and filtering** — isolate a sector or incomplete rows  
4. **Formatting** — consistent decimals, percent columns, header emphasis  
5. **Operators and formulas** — compute a simple yield or margin column from provided fields  
6. **Visual output** — bar/line chart of a filtered set  
7. **Interactive application** — short graded-style problem (clean → summarize → one insight)

#### Tangible output

A cleaned sheet (or tab) plus 2–3 bullet insights an applicant could explain to a non-technical friend.

---

### Session [2] — Python Data Camp: Build Your First Mini Stock Screen

**Working metaphor:** Same domain as the morning, now in code. You start from a prepared CSV of company snapshots (demo metrics in the spirit of a PSE screening warehouse: yield, ROIC/capital return, debt-to-equity, incompleteness flags). You end with a notebook that filters a shortlist.

#### Progression

1. **Start:** A CSV and a blank Jupyter notebook (or VS Code notebook)  
2. **End:** A notebook that imports data, profiles missingness, computes or refines a metric column, filters a screen, and plots a simple comparison

#### Guide Questions

1. How do I find and count missing / null values in my dataset?  
2. How do you run a cell in a Jupyter notebook?  
3. Why use a DataFrame instead of nested lists for tabular work?  
4. How do you filter rows by multiple conditions (e.g., yield above X and debt below Y)?  
5. What should you do when a ratio looks absurd (data-quality instinct)?  
6. How do you export your shortlist back to CSV?

#### Topics

1. Jupyter / notebook workflow for analysis  
2. Pandas Series and DataFrames  
3. Importing CSV data  
4. Profiling and handling missing values  
5. Filtering and subsetting  
6. Simple derived metrics (illustrative only — e.g., a proxy return or screen score)  
7. Basic visualization with Matplotlib  
8. Communicating a screen: thresholds, caveats, and “why these names”

#### Workflow

1. **Environment check** — Python, packages, open the starter notebook  
2. **Load the demo company table** — `read_csv`, `.head()`, `.info()`, `.describe()`  
3. **Data quality pass** — count nulls; drop or flag incomplete rows (mirrors real `info_incomplete` thinking, without live scraping)  
4. **Derived columns** — one teaching metric applicants can explain  
5. **Build a screen** — applicant-chosen thresholds  
6. **Visualize** — bar chart of screened tickers on one metric  
7. **Share-out** — 1–2 minute explanation of screen logic and caveats  
8. **Optional stretch** — compare two tickers side-by-side from the same table

#### Tangible output

A personal screening notebook + a 5–10 name shortlist with written rationale and at least one data-quality caveat.

#### Pedagogical guardrails (for speakers)

- Use **offline demo data** only (no EDGE/live scraping in-session).  
- Prefer **interpretable** metrics over black-box models.  
- Call out that market research is educational — not investment advice (align with project disclaimer culture).  
- Keep ML optional/out-of-scope for this applicants workshop; point to future Guild workshops for modeling depth.

---

## Speakers Bio

> Complete after Speakers Meeting (target Sep 10, 2026).

### AM Speaker — [Name TBD]

[Short bio: program, DS experience, prior workshop/teaching, relevant projects.]

### PM Speaker — [Name TBD]

[Short bio: program, Python/Pandas experience, relevant analytics or tooling work.]

---

## Resources

### [1] Spreadsheet session

- Working file: `[TBD — publish Google Sheet / Excel starter, e.g. tinyurl]`  
- Suggested columns for the messy starter: `ticker`, `company_name`, `sector`, `last_price`, `div_yield`, `roic_or_capital_return`, `debt_to_equity`, `notes` (with intentional blanks / formatting traps)

### [2] Python mini stock screen

**Pre-install (before PM):**

1. Python 3.10+  
2. VS Code **or** Jupyter Lab / Notebook  
3. Demo dataset: `[TBD — attach CSV under workshop resources]`  

```bash
pip install matplotlib numpy pandas
```

**Starter notebook sections (suggested):**

1. Setup & imports  
2. Load CSV  
3. Missingness report  
4. Clean / flag incomplete rows  
5. Define screen thresholds  
6. Filter + sort  
7. Plot  
8. Export shortlist  

**Optional stretch resources (for curious applicants; not required):**

- High-level story of a PSE EDGE → SQLite → screening UI pipeline (architecture diagram only)  
- Difference between industrial ROIC and bank capital-return framing (1–2 slides max)

---

## Alignment with Guild workshop ladder

| Applicants Workshop (this event) | Later Guild workshops (glimpse) |
|----------------------------------|----------------------------------|
| Spreadsheet hygiene & charts | Deeper wrangling, SQL, dashboards |
| Pandas filters & simple screens | Feature work, modeling, ML tracks |
| Offline curated tables | Full ETL, APIs, production-minded tooling |
| Explainable shortlists | Richer evaluation, storytelling, deployment |

---

## Sign-off (packet version)

Prepared for UPSkill 1S2627 Applicants Workshop · Event Head: Galvin M. Gonzales · Draft date: September 6, 2026  
