#!/usr/bin/env python3
"""Generate printable PDFs for UPSkill 1S2627 workshop proposal docs."""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "pdf"


class ProposalPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(90, 90, 90)
        self.cell(0, 8, f"Page {self.page_no()}/{{nb}}", align="C")

    def kv(self, key: str, value: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(20, 20, 20)
        label = f"{key}: "
        self.cell(self.get_string_width(label) + 1, 5, label)
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5, value)

    def para(self, text: str, size: int = 10, style: str = "") -> None:
        self.set_x(self.l_margin)
        self.set_font("Helvetica", style, size)
        self.set_text_color(20, 20, 20)
        self.multi_cell(0, 5, text)
        self.ln(1)

    def bullet(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(20, 20, 20)
        self.multi_cell(0, 4.5, f"- {text}")

    def heading(self, text: str, level: int = 1) -> None:
        self.set_x(self.l_margin)
        self.ln(2)
        if level == 1:
            self.set_font("Helvetica", "B", 13)
            self.set_text_color(15, 55, 95)
            self.multi_cell(0, 7, text)
        else:
            self.set_font("Helvetica", "B", 11)
            self.set_text_color(25, 70, 110)
            self.multi_cell(0, 6, text)
        self.set_text_color(20, 20, 20)
        self.ln(1)


def build_official_proposal(path: Path) -> None:
    pdf = ProposalPDF(format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(15, 55, 95)
    pdf.cell(0, 8, "UPLB DATA SCIENCE GUILD", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(
        0,
        5,
        "University of the Philippines Los Banos",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(0, 5, "College, Laguna 4031", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.heading("I. Event Details")
    for k, v in [
        ("Event Title", "UPSkill"),
        (
            "Theme",
            "From Filings to Insight: Hands-on Data Science with Real Market Data",
        ),
        ("Nature of Event", "Educational and Informative"),
        ("Date & Time", "September 17, 2026 | AM 9:30-12:35 | PM 2:30-6:00"),
        ("Type of Activity", "External Workshop (Applicants Workshop)"),
        ("Venue", "1st Option: [TBD onsite] | 2nd Option: Zoom"),
    ]:
        pdf.kv(k, v)

    pdf.heading("II. Event Team")
    for k, v in [
        ("Event Head", "Galvin M. Gonzales"),
        ("EIC", "[TBD]"),
        ("Program & Technical Committee", "[TBD]"),
        ("Documentation & Communications", "[TBD]"),
    ]:
        pdf.kv(k, v)

    pdf.heading("III. Objectives")
    pdf.para(
        "1. Encourage applicants to know more about data science - what it is, "
        "what problems it solves, and how it shows up in real Philippine datasets."
    )
    pdf.para(
        "2. Give applicants a glimpse of Guild workshops using a pipeline-shaped "
        "activity (collect -> clean -> analyze -> communicate)."
    )
    pdf.para(
        "3. Provide hands-on experience: wrangling tabular data and building a "
        "small stock screen from prepared PSE-style financial metrics."
    )

    pdf.heading("IV. Work Distribution / Committee Task")
    pdf.heading("Program & Technical Committee", level=2)
    pdf.para(
        "Pre: tech, back-up tech, hosts, venue/Zoom, script, evaluation & attendance forms. "
        "During: tech support, hosting, attendance, evaluation collection. "
        "Post: tech tear-down / venue clean-up."
    )
    pdf.heading("Documentation & Communications Committee", level=2)
    pdf.para(
        "Pre: speaker certificates & credentials, PPT packaging, optional onsite food/holders. "
        "During: evaluation forms, speaker food/tokens. "
        "Post: financial report, docs archive, certificate follow-through."
    )

    pdf.add_page()
    pdf.heading("V. Program Preparation Timeline")
    timeline = [
        ("Finish Proposal", "Sep 7, 2026", "Event Head", "In progress"),
        ("Present Proposal to Exec", "Sep 8, 2026", "Event Head", "Not started"),
        ("Speakers Meeting", "Sep 10, 2026", "Event Head, EIC", "Not started"),
        ("Speaker credentials sheet", "Sep 11, 2026", "DCC", "Not started"),
        ("Speakers Draft Presentation", "Sep 10, 2026", "Speakers", "Not started"),
        ("Review Presentation", "Sep 11, 2026", "PTC", "Not started"),
        ("Practice with PTC", "Sep 13, 2026", "Speaker, PTC", "Not started"),
        ("Powerpoint deadline", "Sep 13, 2026", "DCC", "Not started"),
        ("Script deadline", "Sep 13, 2026", "PTC", "Not started"),
        ("Certificates for Speakers", "Sep 13, 2026", "DCC", "Not started"),
        ("Attendance Forms", "Sep 14, 2026", "PTC", "Not started"),
        ("Evaluation Forms", "Sep 15, 2026", "DCC", "Not started"),
        ("Dry Run (exec as applicants)", "Sep 16, 2026", "EIC/Speaker/Head/PTC", "Not started"),
    ]
    headers = ("Activity", "Date", "In-Charge", "Status")
    widths = (68, 30, 58, 24)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(230, 238, 246)
    for h, w in zip(headers, widths):
        pdf.cell(w, 6, h, border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 7.5)
    for row in timeline:
        for val, w in zip(row, widths):
            pdf.cell(w, 5, val, border=1)
        pdf.ln()
    pdf.set_x(pdf.l_margin)
    pdf.ln(2)
    pdf.para(
        "Note: Single-day AM+PM format gives breadth (foundations) then depth (Python). "
        "Dry run is the day before the event."
    )

    pdf.heading("VI. Program Flow")
    pdf.para(
        "Topics: [1] AM Spreadsheet Foundations; [2] PM Python Mini Stock Screen. "
        "Date: Sep 17, 2026. Mode: onsite preferred with Zoom backup."
    )

    pdf.heading("AM Workshop - Spreadsheet Foundations", level=2)
    for line in [
        "9:30-9:45 Ingress / PTC assembly",
        "9:45-10:00 Assembly of Applicants (EIC, Head)",
        "10:00-10:10 Hosts introduction & workshop purpose",
        "10:10-10:15 Opening Remarks (EIC)",
        "10:15-10:20 Introduce AM speaker",
        "10:20-10:30 Intro to Data Science & pipeline story",
        "10:30-11:20 Spreadsheet foundations proper",
        "11:20-11:30 Q&A",
        "11:30-12:20 Guided activity (clean extract -> chart)",
        "12:20-12:30 Certificate for speaker",
        "12:30-12:35 Close AM / PM tool-install reminder",
    ]:
        pdf.bullet(line)

    pdf.heading("PM Workshop - Python Mini Stock Screen", level=2)
    for line in [
        "2:30-2:45 Ingress / PTC assembly",
        "2:45-3:00 Assembly of Applicants",
        "3:00-3:10 Hosts welcome-back",
        "3:10-3:15 Introduce PM speaker",
        "3:15-3:30 Jupyter + Pandas discussion",
        "3:30-4:20 Hands-on load/clean/screen",
        "4:20-4:30 Q&A",
        "4:30-4:50 Applicant threshold activity",
        "4:50-5:30 Short share-outs",
        "5:30-5:40 Q&A",
        "5:40-5:45 Certificate for speaker",
        "5:45-5:55 Closing Remarks (Head)",
        "5:55-6:00 Hosts closing",
    ]:
        pdf.bullet(line)

    pdf.ln(4)
    pdf.para("Created By: Galvin M. Gonzales, Event Head - September 6, 2026", style="B")
    pdf.para("Noted By: ________________________  Executive-in-Charge  Date: ________")
    pdf.para("Approved By: ________________________  Head Chairperson  Date: ________")

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def build_applicants_packet(path: Path) -> None:
    pdf = ProposalPDF(format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(15, 55, 95)
    pdf.cell(0, 7, "UPSkill Applicants Workshop", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(
        0,
        6,
        "1st Sem AY 2026-2027 | From Filings to Insight",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    pdf.heading("Overview")
    for k, v in [
        ("Workshop Title", "UPSkill 1S2627 - From Filings to Insight"),
        ("Date & Time", "Sep 17, 2026 | AM 9:30-12:35 | PM 2:30-6:00"),
        ("Venue", "[TBD onsite] / Zoom backup"),
        ("Org", "UPLB Data Science Guild"),
    ]:
        pdf.kv(k, v)

    pdf.heading("Objective", level=2)
    pdf.para(
        "Give participants an initial look into Data Science using prepared Philippine "
        "company financial metrics as the running example, while setting a baseline for "
        "future Guild workshops. Tangible outputs: a cleaned spreadsheet table (AM) and "
        "a personal mini stock screen notebook (PM)."
    )

    pdf.heading("Rationale", level=2)
    pdf.para(
        "Applicants may be new to DS or come from adjacent backgrounds; some will want "
        "more technical depth. Keep coverage broad, spark interest, and deliver hands-on "
        "takeaways. Theme is inspired by turning public market disclosures into structured "
        "tables - without live scraping. Applicants use curated demo CSVs/sheets only."
    )

    pdf.heading("Program Flow")
    pdf.para(
        "[1] Spreadsheet cleaning & exploration (AM)  |  [2] Python/Pandas mini stock screen (PM)."
    )
    pdf.para(
        "Ingress ~10-15 mins. Incentives for attending both sessions. Install Python tools "
        "before PM. Questions welcome anytime. If applicants present, reserve 15-20 mins."
    )

    pdf.add_page()
    pdf.heading("Topic Outline - Session 1 (Sheets)")
    pdf.para(
        "Progression: messy financial extract -> organized, chart-ready sheet.",
        style="B",
    )
    pdf.para(
        "Topics: interface, shortcuts, sort/filter, formatting, essential formulas, charts, "
        "light data-quality habits (blanks, duplicates, scale notes)."
    )
    pdf.para(
        "Guide Qs: formula showing as text; fill-down; #VALUE!; split ticker/name; flag missing "
        "ratios; chart top 10 by metric."
    )
    pdf.para("Output: cleaned sheet + 2-3 bullet insights.")

    pdf.heading("Topic Outline - Session 2 (Python)")
    pdf.para(
        "Progression: prepared company-metrics CSV + blank notebook -> filtered shortlist with plot.",
        style="B",
    )
    pdf.para(
        "Topics: notebook workflow, DataFrames, CSV import, missingness, filters, derived metrics, "
        "Matplotlib, communicating thresholds and caveats."
    )
    pdf.para(
        "Guide Qs: count nulls; run a cell; why DataFrames; multi-condition filters; absurd ratios; export CSV."
    )
    pdf.para(
        "Pedagogy: offline demo data only; interpretable metrics; educational disclaimer "
        "(not investment advice); ML optional/out of scope for applicants workshop."
    )
    pdf.para("Output: screening notebook + 5-10 name shortlist with rationale.")

    pdf.heading("Resources")
    pdf.para("AM working file: [TBD Google Sheet / Excel starter]")
    pdf.para("PM pre-install: Python 3.10+, VS Code or Jupyter, demo CSV")
    pdf.para("pip install matplotlib numpy pandas")
    pdf.para(
        "Demo CSV path in repo: workshop/upskill-1s2627/resources/demo_company_metrics.csv"
    )

    pdf.heading("Speakers Bio")
    pdf.para("AM Speaker: [TBD after Sep 10 Speakers Meeting]")
    pdf.para("PM Speaker: [TBD after Sep 10 Speakers Meeting]")

    pdf.ln(3)
    pdf.para(
        "Prepared for UPSkill 1S2627 | Event Head: Galvin M. Gonzales | Draft: Sep 6, 2026",
        style="I",
        size=9,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    official = OUT / "UPSkill_1S2627_Official_Proposal.pdf"
    packet = OUT / "UPSkill_1S2627_Applicants_Workshop.pdf"
    build_official_proposal(official)
    build_applicants_packet(packet)
    print(f"Wrote {official}")
    print(f"Wrote {packet}")


if __name__ == "__main__":
    main()
