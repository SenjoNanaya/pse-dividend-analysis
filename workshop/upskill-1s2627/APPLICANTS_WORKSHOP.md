# UPSkill Applicants Workshop — 1st Sem AY 2026–2027

## Overview

### Program Description / Workshop Overview

| Field | Details |
|-------|---------|
| **Workshop Title** | UPSkill 1S2627 — Companies You Know, Data You Can Use |
| **Date & Time** | September 17, 2026 · AM 9:30–12:35 · PM 2:30–6:00 |
| **Venue** | 1st Option: [TBD – UPLB onsite] · 2nd Option: Zoom |
| **Org** | UPLB Data Science Guild |
| **Speaker** | Galvin M. Gonzales (Event Head; AM & PM) |

### Applicants Demographic

> **Fill once the applicant roster is locked.**

**Design assumption until then:** treat the room as **beginner-first** (many first-exposure; mixed programs). Stretch material is optional, never required to “keep up.”

### Objective

To give absolute beginners a friendly first look at Data Science using **real Philippine companies they already know**, while setting a baseline for future Guild workshops. Tangible outputs: a cleaned spreadsheet of familiar tickers (AM), and a simple Colab filter/shortlist (PM).

### Rationale

Applicants may be new to DS, come from adjacent majors, or simply have never touched Python. Mature applicants may want technical flavor — we give that as an optional glimpse, not as the main path.

**Why this speaker:** Galvin can connect the workshop to a real project (PSE disclosures → structured tables → screening ideas) in plain language. Applicants see that Guild work is about useful questions on real data, not only toy examples.

**Why this data:** Familiar names (SM, Jollibee, BDO, Globe, Meralco, etc.) make tables feel relevant immediately. We still use an **offline curated snapshot** (Sheet + CSV / Colab) so the session stays beginner-safe: no live scraping, no account hurdles beyond Colab, no advanced valuation theory.

**Beginner contract:**

1. No prior coding required.  
2. Google Colab for PM (browser only).  
3. Plain metrics first: price, dividend yield (%), missing/complete flag.  
4. Pair up allowed; completed fallback tabs provided.  
5. Educational use only — not investment advice.

Coverage mirrors a tiny DS pipeline:

1. **Clean & explore** (AM — spreadsheets)  
2. **Ask & filter** (PM — Colab / Pandas)

---

## Layout / How to read this packet

1. Program Flow  
2. Topic Outline  
3. Speaker Bio  
4. Resources  

Also see `BEGINNER_SPEAKER_NOTES.md` for dual-role and pedagogy guardrails.

---

## I. Applicants Workshop 1S2627: Program Flow

### Topics

1. **Spreadsheet Foundations with Companies You Know**  
2. **Your First Python Screen in Google Colab**

| | Session [1] | Session [2] |
|---|-------------|-------------|
| **Date** | Sep 17, 2026 | Sep 17, 2026 |
| **Time** | 9:30 AM – 12:35 PM | 2:30 PM – 6:00 PM |
| **Venue** | [TBD] / Zoom backup | [TBD] / Zoom backup |
| **Speaker** | Galvin M. Gonzales | Galvin M. Gonzales |

### Program Outline

- Ingress ~10–15 mins.  
- Incentives for attending **both**; makeup task if you miss one.  
- Questions anytime; PTC floater helps stuck participants so the speaker can keep the main thread.  
- **PM:** open the Colab link before the session starts (Google account). Local Python install is optional stretch only.  
- Bring water / snacks as needed.  

---

## Topic Outline

### What to expect!

\*paced for beginners; stretch notes marked optional

---

### Session [1] — SheetSkills: Companies You Already Recognize

**Working metaphor:** A slightly messy table of PH companies you know from malls, banks, telcos, and food — your job is to make it readable and find one honest insight.

#### Progression

1. **Start:** Uneven headers, blank yields, mixed formats  
2. **End:** Sorted/filtered sheet + one chart + one sentence (“Among complete rows, …”)

#### Guide Questions

1. Why is my formula showing as text?  
2. How do I fill a formula down without dragging forever?  
3. What does a blank dividend yield mean for my chart?  
4. How do I keep only rows marked complete?  
5. How do I chart yield for companies I actually know?  
6. When should a “very high yield” make me suspicious?

#### Topics (beginner core)

1. Spreadsheet interface & freeze panes  
2. Sort & filter  
3. Basic formatting (percents, readable headers)  
4. Simple formulas (`IF`, `IFERROR`, basic arithmetic)  
5. One chart  
6. Missing-data hygiene  

**Optional stretch:** `XLOOKUP` / split text to columns.

#### Workflow

1. Meet the familiar tickers (SM, JFC, BDO, GLO, MER, …)  
2. Clean labels & formats  
3. Filter to `data_complete = yes`  
4. Chart a small subset  
5. Write one careful insight (include a caveat)

#### Tangible output

Cleaned sheet tab + 1 chart + 1–2 bullet insights in plain Filipino or English.

---

### Session [2] — Colab Camp: Filter a Shortlist (No Install)

**Working metaphor:** Same companies, now in a notebook. You learn to run cells, count missing values, and apply a rule like “complete rows with yield above X.”

#### Progression

1. **Start:** Colab notebook + CSV already linked  
2. **End:** A shortlist table you can explain in one minute

#### Guide Questions

1. How do I run a cell?  
2. How do I see the first rows of a table?  
3. How do I count missing yields?  
4. How do I keep rows that match my rule?  
5. How do I sort the shortlist?  
6. What disclaimer should I remember before “ranking” companies?

#### Topics (beginner core)

1. Colab tour (runtime, cells, markdown)  
2. `read_csv` / `.head()` / `.shape`  
3. Missing values (`.isna().sum()`)  
4. Boolean filters  
5. Sort + simple bar chart  
6. Export or screenshot your shortlist  

**Optional stretch:** local VS Code setup; compare two tickers; one-slide glimpse of a fuller PSE → database pipeline.

#### Workflow

1. Open Colab · run setup cell  
2. Load familiar-ticker table  
3. Missingness check  
4. Apply a simple screen (speaker-led defaults first)  
5. Customize one threshold with a partner  
6. Optional 30–60s share-out  

#### Tangible output

Shortlist of recognizable companies + the rule you used + one data caveat.

#### Pedagogical guardrails

- Offline curated snapshot only.  
- No ROIC / ML in the main path.  
- Educational disclaimer on slide 1 and notebook top.  
- Completed notebook copy available if someone’s laptop fails.  
- Speaker ≠ MC; hosts handle transitions.

---

## Speaker Bio

### Galvin M. Gonzales — AM & PM Speaker / Event Head

Galvin M. Gonzales is the Event Head for UPSkill 1S2627 and the workshop speaker for both sessions. His teaching thread is grounded in building beginner-accessible workflows on **real Philippine listed-company data**: how messy public tables become something you can clean, question, and filter — without assuming prior coding experience.

On the day, logistics and MCing are handled by Hosts and the Program & Technical Committee so he can stay focused on instruction and Q&A.

> DCC may expand this bio with program, batch, and org roles before publication.

---

## Resources

### [1] Spreadsheet session

- Working file: `[TBD — publish Google Sheet starter]`  
- Starter columns match `resources/demo_company_metrics.csv` (familiar PSE names)  
- Include a second tab: **Answer key / completed example**

### [2] Colab mini screen

**Pre-work (5 minutes):**

1. Google account  
2. Open the published Colab link (target send date: Sep 15)  
3. Run the first cell once to confirm it works  

```text
Packages used in Colab: pandas, matplotlib
(No local pip required for the main path.)
```

**Dataset:** `workshop/upskill-1s2627/resources/demo_company_metrics.csv`  
Familiar tickers with simplified fields: `familiar_as`, `last_price`, `div_yield_pct`, `debt_to_equity`, `data_complete`, `notes`.

**Notebook sections:**

1. Welcome + disclaimer  
2. Load data  
3. Peek + missingness  
4. Speaker default filter  
5. Your turn  
6. Chart  
7. What we’d learn next in the Guild (optional)

---

## Alignment with Guild workshop ladder

| Applicants Workshop (this event) | Later Guild workshops (glimpse) |
|----------------------------------|----------------------------------|
| Familiar companies + plain metrics | Richer fundamentals & sector nuance |
| Sheets + Colab filters | SQL, dashboards, modeling tracks |
| Curated offline snapshots | Fuller ETL / warehouse thinking |
| One honest caveat | Deeper evaluation & storytelling |

---

## Sign-off (packet version)

Prepared for UPSkill 1S2627 Applicants Workshop · Event Head & Speaker: Galvin M. Gonzales · Updated: September 6, 2026  
