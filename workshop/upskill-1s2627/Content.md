# UPSkill 1S2627. Slide Content (source of truth draft)

## Provenance. Read first

Data source of truth: `github.com/SenjoNanaya/pse-dividend-analysis`.
Teaching snapshot: `workshop/upskill-1s2627/resources/demo_company_metrics.csv`. 20 rows, frozen offline.
Schema rules: `workshop/upskill-1s2627/DEMO_DATASET_NOTES.md`.
Pipeline behind the snapshot: `src/scraper.py` reads EDGE `search.ax`, `dividends_and_rights_list.ax`, `stockData.do`. Then `src/parser.py` plus scale guard writes SQLite. Django serves `/api/companies/`. React renders the registry. The session uses the frozen CSV only.
Legal: `DISCLAIMER.md`. Educational use. No PSE affiliation. Verify figures against official filings before any real decision.

Schedule source for this file: the PDF single session program flow. Sep 17, 2026, 1:00 to 4:00 PM draft, onsite preferred with Zoom backup, speaker Galvin M. Gonzales. The repo `PROPOSAL.md` AM/PM split (9:30 to 12:35 plus 2:30 to 6:00) is superseded for slides. It stays for committee reference only.

How to use this file: each `## Slide N` is one PPT slide. `Beats` are the click sequence. One beat is one textbox and one Appear animation. Never merge two beats into one box. Slides hold 1 to 3 beats each.

Slide text rule: beats are keywords, not sentences. Fragments under 12 words. The speaker talks the ideas; the slide anchors them. Full sentences live in `Say` only. DCC archive readers get the narrative from `Say`, not from the slide.

Voice rules: concrete nouns and numbers, never adjectives about importance. Vary the rhythm so consecutive beats do not share a shape. Address the room as "you" when the beat asks for action. Keep every number exactly as listed under Frozen dataset facts.

Session arc: the first half builds curiosity before touching tools. Disclosures first (what companies publish), narrative second (the question you chase), data science third (the loop that answers it), cleaning last (the fuel). Sheets and Colab serve the narrative, not the other way around.

### Frozen dataset facts. Copy numbers exactly

20 rows. 17 with `data_complete=yes`. 3 with `no`: MPI, CNVRG, RRHI. All 3 have blank `div_yield_pct`.
Teaching rows with high yield: DMC 8.5, SCC 12.0. Question both before any ranking.
Banks with blank `debt_to_equity` on purpose: BDO (145.00, 3.1), BPI (120.00, 2.8). Industrial debt math misleads for banks.
BLOOM 0.0 is a real zero. Keep it. Blank is missing. Zero is data.
Reference prices: SM 850.00 at 1.8, JFC 230.00 at 1.2, BDO 145.00 at 3.1, GLO 2100.00 at 5.5, TEL 1450.00 at 6.2, MER 380.00 at 4.0, MPI 4.50 blank, CNVRG 12.80 blank, RRHI 40.00 blank.
Columns: `ticker, company_name, familiar_as, sector, last_price, div_yield_pct, debt_to_equity, data_complete, notes`.
Yield in the CSV is a precomputed percent. In the live warehouse it is TTM common cash DPS divided by last price. Property dividends are excluded.
Disclosure sources behind the warehouse: PSE EDGE `search.ax` (filing search), `openDiscViewer.do` (viewer), `dividends_and_rights_list.ax` (dividend history), `stockData.do` (price, market cap, shares). Filings state amounts in thousands, millions, or billions. Miss the scale note and every ratio breaks.

### Type, contrast, and emphasis rules for layout

Measured pairs. Dark `#4E4A3E` on beige `#D1CDB7` is 5.53 to 1. Beige on dark is the same. Both pass AA at any size. Use them for all reading text.
Accent `#B54A32` on beige is 3.29 to 1. Sage `#5F7152` on beige is 3.31 to 1. Both pass large text and graphics only. Never set body copy in them. Use them for glyphs at 18pt bold or larger, stripes, and shapes.
Minimum sizes. Titles uniform: 44pt title and section slides, 38pt content, 40pt closing. Keyword beats uniform 30pt. Detail beats 20 to 22pt: 22 on slides with 3 or fewer beats, 20 on 4-beat slides and in code and dark boxes. Side rails 16pt and never the sole carrier of a fact. Every fact in a rail repeats in a beat or the speaker script.
Grid. One left edge for text at 1.10 with beat text at 1.42 behind 0.16 square markers. Rails and figures always at 9.20. Tables start at 1.10 with middle anchored cells.
Emphasis. One emphasized token per beat at most. Bold or color, not both. The token is always a number, a ticker, or a filename.
Slide shapes vary. Keyword stacks, tables, code terminals, task cards, big figures, two column pairs, and single statements rotate so no three consecutive slides share a layout.

---

## Slide 1. Title (covers 1:00 to 1:40: ingress, assembly, hosts welcome, EIC remarks, speaker intro)

Lesson: applicants can state the session name, time, and speaker before content starts.
Beats:
- Beat 1 (title, static, no click): Companies You Know, Data You Can Use
- Beat 2 (click): Sep 17. 1:00 to 4:00. UPLB, Zoom backup. Galvin M. Gonzales.

Say:
- Hosts own this block. The speaker stays silent until 1:35.
- Leave this slide up through ingress and assembly. The details answer latecomer questions without interrupting.

Layout: title background. Beat in mono 20pt. No other text.

---

## Slide 2. Promise (covers 1:20 to 1:40: hosts welcome)

Lesson: every applicant can name both outputs before the work starts.
Beats:
- Beat 1 (click): Sheet. Chart. Insight.
- Beat 2 (click): Notebook. Shortlist. Rule.

Say (hosts):
- Translate on the mic: a cleaned spreadsheet tab with one chart and one insight sentence, then a Colab notebook holding a shortlist plus the rule that made it and one caveat.
- Tell pairs they share one laptop if seats run short. Tell the room no coding background is needed.

Layout: two keyword beats at 32pt. The sparsest content slide. Say carries the meaning.

---

## Slide 3. Hook: known names (covers 1:40 to 1:55)

Lesson: the companies in the file are already in the room's daily life.
Beats:
- Beat 1 (click): SM. Jollibee. BDO. Globe. Meralco.
- Beat 2 (click): Customers → investigators.

Say:
- Read the five names slowly. SM malls, Jollibee meals, BDO queues, Globe load, Meralco bills. Every applicant has touched at least three this month.
- Then flip the role. All semester they were customers. For three hours they investigate the same names. That flip is the workshop.

Layout: keyword stack at 32pt. Beat 2 in accent marker. The arrow is the only decoration.

---

## Slide 4. Disclosures (covers 1:40 to 1:55)

Lesson: listed companies publish, and EDGE collects what they publish.
Beats:
- Beat 1 (click): Reports. 17-C. Dividends.
- Beat 2 (click): EDGE collects. Pipeline reads. You get 20 rows.

Say:
- Name each source. Annual reports carry the financial statements. Form 17-C carries events as they happen. The dividend list carries payouts. All three live on EDGE, the PSE portal.
- Trace the chain in one breath: EDGE holds thousands of filings, the Guild pipeline reads them into tables, today you get 20 frozen rows sliced from those tables. Frozen means safe to break.

Layout: two keyword beats at 30pt. Say holds the portal and form names for the archive.

---

## Slide 5. Narrative (covers 1:40 to 1:55)

Lesson: a screen is a curious sentence before it is a filter.
Beats:
- Beat 1 (click): Which familiar name paid best?
- Beat 2 (click): Complete rows. Yield above 3.
- Beat 3 (click): Shortlist plus caveat.

Say:
- Walk the arc out loud. Curiosity asks which familiar name paid best. The rule answers with complete rows above a cutoff. The shortlist means nothing without the caveat, so the caveat ships with it.
- Promise the room they will run this exact arc twice: once with a mouse, once with code.

Layout: three beats, question then rule then answer. The whole day in miniature.

---

## Slide 6. The loop (covers 1:40 to 1:55)

Lesson: data science is ask, collect, clean, filter, caveat. Tools change, the loop does not.
Beats:
- Beat 1 (click): Ask. Collect. Clean.
- Beat 2 (click): Filter. Caveat. Repeat.

Say:
- Map the loop to the Guild repo so appreciation lands on something real. Ask is the screen idea. Collect is the EDGE scraper with its delays. Clean is the parser plus the scale guard that catches thousands against millions. Filter is the Django API thresholds. Caveat is the data quality flags the UI refuses to hide.
- Close with the line the day keeps proving: spreadsheets and notebooks are interchangeable hands for the same loop.

Layout: two keyword beats at 32pt. Say carries the repo mapping for DCC and returners.

---

## Slide 7. File and columns (covers 1:40 to 1:55 setup)

Lesson: one offline file, three working columns.
Beats:
- Beat 1 (click): `demo_company_metrics.csv`. Offline.
- Beat 2 (click): `last_price`. `div_yield_pct`. `data_complete`.

Say:
- Show both filenames on screen verbatim. Spelling matters for the 3:15 Colab load.
- Hold up one finger per column. Three columns is the whole vocabulary for the day.

Layout: two mono beats at 20pt. Short slide on purpose. Breathing room before the legal line.

---

## Slide 8. Legal and pairs (covers 1:40 to 1:55 setup)

Lesson: the room can recite what is off limits.
Beats:
- Beat 1 (click): Class exercise. Not advice.
- Beat 2 (click): Pairs welcome. Backups ready.

Say:
- Deliver Beat 1 flat and slow. Figures are rounded and dated, no PSE affiliation. The accent stripe marks the legal line.
- Beat 2 is the relief after it. Ask anytime. Finished Sheet and notebook backups exist if a laptop dies.

Layout: dark box with accent stripe for Beat 1, plain beat for Beat 2. Legal weight reads visually.

---

## Slide 9. Ticker and yield (covers 1:55 to 2:40 setup)

Lesson: a ticker is shorthand and yield is cash per price, already computed.
Beats:
- Beat 1 (click): Ticker. SM, JFC, BDO.
- Beat 2 (click): Yield. Cash per price. Precomputed.

Say:
- Point at SM on screen for Beat 1. Mall first, ticker second.
- For Beat 2, stress precomputed with figures: SM shows 1.8, GLO shows 5.5. Nobody divides anything today.

Layout: two beats at 28pt. Names first, numbers second.

---

## Slide 10. Missing and filter (covers 1:55 to 2:40 setup)

Lesson: blank means missing and a filter keeps rows that match a rule.
Beats:
- Beat 1 (click): Missing. Blank. Never zero.
- Beat 2 (click): Filter. Keep what matches.

Say:
- Say the MPI price slowly: four pesos fifty, no yield. Let the gap land.
- Preview the filter so the word sounds familiar when it returns: complete rows with a yield.

Layout: two beats at 28pt. Mirrors Slide 9, completing the four term set.

---

## Slide 11. Meet the table (covers 1:55 to 2:40 demo)

Lesson: the same 20 companies stay on screen all afternoon.
Beats:
- Beat 1 (static table, no click): three rows. SM malls, 850.00, 1.8%, yes. Globe, 2100.00, 5.5%, yes. Metro Pacific, 4.50, blank, no.
- Beat 2 (click): 20 rows. Raw tab stays raw.

Say:
- Name what each row is. SM you know from malls. Globe from telco. MPI is the broken row on purpose.
- Physically duplicate the tab in front of them. The habit matters more than the clicks.

Layout: table left, one instruction beat below it. Status words `yes` and `no` in dark bold. Glyphs are decor only.

---

## Slide 12. Blank against zero (covers 1:55 to 2:40 demo)

Lesson: MPI blank means missing. BLOOM 0.0 means real.
Beats:
- Beat 1 (click): MPI blank. Missing.
- Beat 2 (click): BLOOM 0.0. Real.

Say:
- This distinction returns twice: at the filter and the missingness check. Plant it now.
- Ask the room which one stays. Wait for "BLOOM" before advancing.

Layout: two short beats at 30pt, biggest whitespace on any teaching slide. One idea each, nowhere to hide.

---

## Slide 13. Freeze and formats (covers 1:55 to 2:40)

Lesson: frozen headers and correct formats come before any chart.
Beats:
- Beat 1 (click): Freeze the header.
- Beat 2 (click): Price to Number. Yield to Percent.

Say:
- Do each action live with the cursor visible. Pairs mirror on their screens.
- The PTC floater watches chat and raised hands. The speaker does not pause the thread for one laptop.

Layout: two mono beats at 20pt. White space reserved for the live cursor.

---

## Slide 14. Formulas (covers 1:55 to 2:40)

Lesson: text formatted cells fake you out, and IFERROR fills a column in seconds.
Beats:
- Beat 1 (click): Text cell? Set Number. Re-enter.
- Beat 2 (click, code): `=IFERROR(C2,"missing")`

Say:
- Break one cell on purpose so the room sees the symptom. Then fix it.
- Read the formula aloud character by character. Beginners copy it by ear. It fills 20 rows.

Layout: mono beat plus dark code terminal. Symptom first, tool second.

---

## Slide 15. Banks are different (covers 1:55 to 2:40)

Lesson: BDO and BPI blanks are correct because banks skip industrial debt math.
Beats:
- Beat 1 (click): BDO blank. BPI blank.
- Beat 2 (click): Correct. Banks differ.

Say:
- Name both tickers with figures: BDO at 145.00 with 3.1, BPI at 120.00 with 2.8. Real rows, deliberate blanks.
- One sentence on why, then move on. Bank capital structure is a later workshop, not this one.

Layout: two beats, second in a dark box. Second bank themed moment stays short because the judgment is the lesson.

---

## Slide 16. Filter: 20 becomes 17 (covers 1:55 to 2:40)

Lesson: the filter drops exactly the 3 blank rows.
Beats:
- Beat 1 (click): `data_complete` to `yes`.
- Beat 2 (click, figure): 20 → 17. MPI, CNVRG, RRHI out.

Say:
- Run the filter in front of the room. Say each dropped ticker by name.
- Count aloud with the room. Twenty, minus three, seventeen.

Layout: two beats plus the large `20 → 17` figure at right. The number is the slide.

---

## Slide 17. Sort and suspect (covers 1:55 to 2:40)

Lesson: sorting surfaces SCC 12.0 and DMC 8.5, and high rank is a question.
Beats:
- Beat 1 (click): Sort largest first.
- Beat 2 (click): SCC 12.0. DMC 8.5. Question, not pick.

Say:
- Foreshadow the task. The top of a sorted column still needs a caveat before anyone writes an insight.
- Say both yields with tickers attached. Twelve point oh belongs to Semirara. Eight point five to DMCI.

Layout: mono beat plus dark box with accent stripe. The stripe marks skepticism wherever it appears.

---

## Slide 18. Task: chart and sentence (covers 2:40 to 3:05, speaker plus PTC floater)

Lesson: the task is one chart plus one sentence starting with "Among complete rows".
Beats:
- Beat 1 (click): Chart 5 to 7 familiar names.
- Beat 2 (click): "Among complete rows..."

Say:
- Timebox 25 minutes. One laptop per pair is fine. The completed example tab is the fallback, not the starting point.
- Start the timer on screen with Beat 1. Complete rows only.

Layout: task card beats plus the `25:00` figure at right. No new concepts on this slide.

---

## Slide 19. Task: worked example (covers 2:40 to 3:05)

Lesson: a finished insight pairs a finding with its caveat.
Beats:
- Beat 1 (click, example): TEL 6.2% leads. SCC 12.0 needs a check.
- Beat 2 (click): One caveat per pair.

Say:
- Label the example as format only, not advice. Their numbers must come from their own sheet.
- Missing data, rounded figures, or high yield skepticism all count as caveats. Floaters read two aloud at 3:05.

Layout: dark example box plus one plain beat. Example is fenced off visually so nobody mistakes it for instruction.

---

## Slide 20. Break and Colab check (covers 3:05 to 3:15, hosts plus PTC)

Lesson: every laptop runs the first Colab cell before 3:15.
Beats:
- Beat 1 (click): Google account. Colab link. Run cell one.
- Beat 2 (click): Pandas. Matplotlib. Done.

Say (hosts):
- Confirm screens show a checkmark before the break ends. Anyone stuck pairs up now. Link went out Sep 15.
- VS Code on a local machine is stretch only. Nobody needs it for the main path.

Layout: dark section divider, two 24pt checkbox beats. Airiest slide in the deck.

---

## Slide 21. Colab: load and peek (covers 3:15 to 3:45, first half)

Lesson: two lines load the file and prove its shape.
Beats:
- Beat 1 (click, code): `df = pd.read_csv("demo_company_metrics.csv")`
- Beat 2 (click, code): `(20, 9)`. SM, JFC, BDO on top.

Say:
- Run each cell after its beat appears. Let the output sit before explaining it.
- Twenty rows, nine columns. Ask the room to confirm both numbers against their Sheets.

Layout: dark terminal, one line per beat. Code only, no prose on this slide.

---

## Slide 22. Colab: count the blanks (covers 3:15 to 3:45, first half)

Lesson: `isna` names the same 3 blanks the Sheet filter hid.
Beats:
- Beat 1 (click, code): `df.isna().sum()`
- Beat 2 (click): MPI. CNVRG. RRHI. Same three.

Say:
- Map the result to Sheets out loud. `isna` counts the blanks the 2:00 filter hid.
- Notebook order for the block: welcome plus disclaimer, load, peek plus missingness.

Layout: code terminal beat plus dark mapping beat. One function, one meaning.

---

## Slide 23. Shortlist: rule and sort (covers 3:15 to 3:45, second half)

Lesson: the shortlist is two lines. Mask, then sort.
Beats:
- Beat 1 (click, code): `df = df[df.data_complete == "yes"]`
- Beat 2 (click, code): `.dropna(subset=["div_yield_pct"])`
- Beat 3 (click, code): `short.sort_values("div_yield_pct", ascending=False)`

Say:
- Run the speaker default first so every screen matches. Narrate each line as it runs: keep the yes rows, drop the blank yields, order what remains. The joined spelling sits in the archive notes.
- Warn that the next slide tops with SCC. Let them anticipate it.

Layout: narrow terminal left. Code gets the full stage here. Full spellings: `df[df.data_complete == "yes"].dropna(subset=["div_yield_pct"])`, then `sort_values("div_yield_pct", ascending=False)`.

---

## Slide 24. Shortlist: table and partner turn (covers 3:15 to 3:45, second half)

Lesson: change the rule and the table changes.
Beats:
- Beat 1 (static table, no click): 4 rows. SCC 12.0, DMC 8.5, TEL 6.2, GLO 5.5. All marked yes.
- Beat 2 (click): Yield above 3. Screenshot. Top rank is the lesson.

Say:
- Pairs edit one number only: the cutoff. Everything else stays frozen so screens stay comparable.
- Repeat the warning with tickers attached. Topping proves the sort works. It does not recommend either company.

Layout: result table right, partner instruction as a full width dark strip below. Table is the slide.

---

## Slide 25. Share outs and next steps (covers 3:45 to 3:50, hosts plus speaker)

Lesson: later Guild work starts where this snapshot stops.
Beats:
- Beat 1 (click): Today: names, metrics, filters, snapshot.
- Beat 2 (click): Later: fundamentals, SQL, full ETL.
- Beat 3 (click): Rule first. Caveat second.

Say:
- Keep ROIC and ML to one sentence. They are a teaser per `BEGINNER_SPEAKER_NOTES.md`, not a second lecture.
- Share outs run 30 to 60 seconds and stay optional. Invite, do not assign. No grading in this block.

Layout: two column Today against Next, then the share format as a dark strip.

---

## Slide 26. Close (covers 3:50 to 4:00, event head and speaker plus hosts)

Lesson: each applicant names both outputs before leaving.
Beats:
- Beat 1 (click): Sheet. Chart. Insight.
- Beat 2 (click): Shortlist. Rule. Caveat.
- Beat 3 (click): Evaluation. Certificates. Links live on.

Say:
- Thank the PTC floaters, the hosts, and the EIC by role.
- Success bar to read aloud: I cleaned real PH company rows, filtered by yield and completeness, and I know missing data can lie.

Layout: title background variant. Three keyword beats at 28pt. Footer holds org and date.

---

## Appendix. Committee only, never on slides

Full schedule: 1:00 to 1:10 ingress PTC. 1:10 to 1:20 assembly EIC and hosts. 1:20 to 1:30 hosts welcome. 1:30 to 1:35 EIC remarks. 1:35 to 1:40 speaker intro. 1:40 to 1:55 curiosity arc plus vocab plus table. 1:55 to 2:40 Sheets. 2:40 to 3:05 task. 3:05 to 3:15 break. 3:15 to 3:45 Colab. 3:45 to 3:50 share plus teaser. 3:50 to 4:00 close.
Publish checklist for Sep 15: Sheet starter plus answer key tab, Colab link, `demo_company_metrics.csv` with date stamp.
Refresh rules for the CSV: keep 18 to 25 rows, keep 3 incomplete rows, keep 1 to 2 high yield rows, keep bank debt ratios blank, round figures, stamp the date, never imply advice.
Slide map for DCC: 1 title, 2 promise, 3 hook, 4 disclosures, 5 narrative, 6 loop, 7 to 8 contract, 9 to 10 vocab, 11 to 12 table, 13 to 15 cleanup, 16 to 17 filter, 18 to 19 task, 20 break, 21 to 24 Colab, 25 next, 26 close.
Full pandas spellings for the archive: mask `df[df.data_complete == "yes"].dropna(subset=["div_yield_pct"])`, sort `short.sort_values("div_yield_pct", ascending=False)`, missingness `df.isna().sum()`, shape `(20, 9)`.
