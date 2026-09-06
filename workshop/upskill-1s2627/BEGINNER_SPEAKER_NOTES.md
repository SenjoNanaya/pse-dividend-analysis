# Beginner-friendly design notes (speaker: Galvin)

## Why the Event Head as speaker works here

You built / maintain the PSE screening pipeline this theme is based on. For an Applicants Workshop, that is a **feature**, not a conflict: applicants meet a real Guild project and a person who can explain the *why*, not only the clicks.

**Do this so dual-role does not hurt the room:**

| Risk | Mitigation |
|------|------------|
| Head is busy with logistics | Hosts + PTC own ingress, attendance, Zoom, mic, certificates; you only speak and answer content Qs |
| Harder to “read the room” while presenting | Assign one floater (PTC) to watch chat / raised hands and interrupt you on blockers |
| Credibility vs facilitation | Opening remarks stay with EIC; hosts introduce you; you do not also MC |
| Energy across AM+PM | Same narrative voice is good; use a sharper AM→PM bridge (“same companies, now in code”) and a short lunch reset |

**Recommendation:** You speak **both** sessions for continuity. If load is too high, keep **PM (Python + real tickers)** as yours and co-opt an AM Sheets co-facilitator — still with you opening the day’s data story (10 mins).

## Beginner-first, real-world-appreciated

**Real-world appreciation** here means names applicants already know (SM, Jollibee, BDO, Globe, Meralco…), not live scraping or advanced valuation theory.

### Data rules

1. Offline CSV / Sheet only (export from your warehouse beforehand if you want fresher figures).  
2. Prefer **plain metrics**: price, dividend yield (%), simple debt flag / D/E when meaningful.  
3. Defer ROIC / capital-return / bank special cases to a **1-slide “later in the Guild” teaser**.  
4. Label every file: educational snapshot · not investment advice · figures may be rounded / dated.  
5. Plant a few **incomplete** and **too-good-to-be-true yield** rows so beginners practice skepticism.

### Teaching rules

1. Assume **zero** Sheets expertise and **zero** Python.  
2. AM is mouse + formulas; PM is **Google Colab** (no local install required; VS Code optional stretch).  
3. Every live demo has a **screenshot / completed tab** fallback if someone’s laptop fails.  
4. Pair programming encouraged; one laptop per pair is OK.  
5. Share-outs optional / short (30–60s), not graded presentations.  
6. Vocabulary card on slide 1: *ticker, yield, missing data, filter, screen*.

### Success bar (beginner)

An applicant who never coded should leave able to say:

> “I cleaned a table of real PH companies, then in Colab I filtered names by yield and completeness — and I know missing data can lie.”
