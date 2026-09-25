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

    def kv(self, key: str, value: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(20, 20, 20)
        label = f"{key}: "
        self.cell(self.get_string_width(label) + 1, 5, label)
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5, value)


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
            "Companies You Know, Data You Can Use: Beginner DS with Real PSE Names",
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
        ("Speaker (AM & PM)", "Galvin M. Gonzales"),
        ("EIC", "[TBD]"),
        ("Program & Technical Committee", "[TBD] - owns logistics / floater support"),
        ("Hosts", "[TBD] - MC / transitions (not the speaker)"),
        ("Documentation & Communications", "[TBD]"),
    ]:
        pdf.kv(k, v)

    pdf.heading("III. Objectives")
    pdf.para(
        "1. Encourage absolute beginners to explore data science using Philippine "
        "companies they already recognize (SM, Jollibee, BDO, Globe, Meralco, ...)."
    )
    pdf.para(
        "2. Preview Guild workshops via a simple pipeline: clean a table -> ask a "
        "question -> filter an answer (no prior coding required)."
    )
    pdf.para(
        "3. Hands-on with an offline real-world snapshot: spreadsheet hygiene (AM) "
        "and a guided Google Colab mini-screen (PM)."
    )

    pdf.heading("IV. Dual-role / Committee Task")
    pdf.para(
        "Because the Event Head is also the speaker, PTC + Hosts fully own logistics "
        "and MCing. During the event the speaker only teaches and answers content Qs.",
        style="B",
    )
    pdf.heading("Program & Technical Committee", level=2)
    pdf.para(
        "Pre: tech, hosts, venue/Zoom, script, forms, Colab access check, floater. "
        "During: tech, attendance, catch raised hands/chat. Post: tear-down."
    )
    pdf.heading("Documentation & Communications", level=2)
    pdf.para(
        "Pre: speaker credentials, PPT packaging, certificates. "
        "During: evaluation / documentation. Post: financial report, archive."
    )

    pdf.add_page()
    pdf.heading("V. Program Preparation Timeline")
    timeline = [
        ("Finish Proposal", "Sep 7", "Head/Speaker", "In progress"),
        ("Present to Exec", "Sep 8", "Event Head", "Not started"),
        ("Hosts+PTC dual-role sync", "Sep 9", "Head, EIC, PTC", "Not started"),
        ("Lock beginner PSE dataset", "Sep 10", "Speaker", "Not started"),
        ("Speaker credentials sheet", "Sep 11", "DCC", "Not started"),
        ("Draft AM+PM slides", "Sep 10-12", "Speaker", "Not started"),
        ("Beginner clarity review", "Sep 12", "PTC / EIC", "Not started"),
        ("Practice with PTC", "Sep 13", "Speaker, PTC", "Not started"),
        ("PPT + script deadline", "Sep 13", "DCC / PTC", "Not started"),
        ("Publish Sheet + Colab links", "Sep 15", "DCC, Speaker", "Not started"),
        ("Dry run (exec as applicants)", "Sep 16", "EIC, Speaker, Hosts, PTC", "Not started"),
    ]
    headers = ("Activity", "Date", "In-Charge", "Status")
    widths = (68, 28, 52, 32)
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

    pdf.heading("VI. Program Flow")
    pdf.para(
        "Speaker: Galvin M. Gonzales (both sessions). "
        "AM = Spreadsheet foundations with familiar PSE names. "
        "PM = First Python screen in Google Colab (no local install)."
    )

    pdf.heading("AM - Spreadsheet Foundations", level=2)
    for line in [
        "9:30-10:00 Ingress + applicant assembly",
        "10:00-10:15 Hosts + Opening Remarks (EIC)",
        "10:15-10:20 Introduce speaker",
        "10:20-10:35 Soft landing: DS intro + vocabulary + why these companies",
        "10:35-11:15 Follow-along Sheets skills",
        "11:15-11:25 Q&A",
        "11:25-12:15 Guided clean -> chart -> one-sentence insight",
        "12:15-12:35 Certificate moment + Colab reminder",
    ]:
        pdf.bullet(line)

    pdf.heading("PM - Colab Mini Screen", level=2)
    for line in [
        "2:30-3:00 Ingress + Colab open-check",
        "3:00-3:15 Hosts welcome-back + speaker re-intro",
        "3:15-3:35 Gentle Colab/Pandas intro",
        "3:35-4:20 Follow-along filter by yield + completeness",
        "4:20-4:30 Q&A",
        "4:30-5:00 Applicant rule activity (pairs OK)",
        "5:00-5:30 Optional 30-60s share-outs",
        "5:30-5:40 Guild teaser (pipeline glimpse only)",
        "5:40-6:00 Closing + evaluation",
    ]:
        pdf.bullet(line)

    pdf.ln(3)
    pdf.para(
        "Created By: Galvin M. Gonzales, Event Head & Speaker - September 6, 2026",
        style="B",
    )
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
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(
        0,
        6,
        "1S2627 | Companies You Know, Data You Can Use",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    pdf.heading("Overview")
    for k, v in [
        ("Workshop Title", "UPSkill 1S2627 - Companies You Know, Data You Can Use"),
        ("Date & Time", "Sep 17, 2026 | AM 9:30-12:35 | PM 2:30-6:00"),
        ("Venue", "[TBD onsite] / Zoom backup"),
        ("Speaker", "Galvin M. Gonzales (Event Head; AM & PM)"),
        ("Org", "UPLB Data Science Guild"),
    ]:
        pdf.kv(k, v)

    pdf.heading("Objective", level=2)
    pdf.para(
        "Absolute-beginner first look at Data Science using real Philippine companies "
        "applicants already know. Outputs: cleaned familiar-ticker sheet (AM) and a "
        "simple Colab shortlist (PM)."
    )

    pdf.heading("Rationale", level=2)
    pdf.para(
        "Beginner-first room. Speaker can connect the session to a real Guild-adjacent "
        "project in plain language. Familiar tickers (SM, Jollibee, BDO, Globe, Meralco...) "
        "create relevance; offline curated snapshot keeps setup safe. Colab removes local "
        "install friction. Educational use only - not investment advice."
    )

    pdf.heading("Program Flow")
    pdf.para(
        "[1] Spreadsheet foundations with familiar PSE names (AM) | "
        "[2] First Python screen in Google Colab (PM)."
    )
    pdf.para(
        "Pairs allowed. PTC floater catches blockers. Share-outs optional (30-60s). "
        "Open Colab before PM starts."
    )

    pdf.add_page()
    pdf.heading("Topic Outline - Session 1 (Sheets)")
    pdf.para(
        "Progression: messy familiar-company table -> readable sheet + one careful insight.",
        style="B",
    )
    pdf.para(
        "Core topics: interface, sort/filter, formatting, IF/IFERROR, one chart, "
        "missing-data hygiene. Plain metrics only (price, dividend yield %, completeness)."
    )
    pdf.para("Output: cleaned tab + 1 chart + 1-2 bullet insights.")

    pdf.heading("Topic Outline - Session 2 (Colab)")
    pdf.para(
        "Progression: linked CSV in Colab -> shortlist you can explain in one minute.",
        style="B",
    )
    pdf.para(
        "Core topics: run cells, head/shape, count missing, boolean filters, sort, "
        "simple bar chart. No ROIC/ML on the main path. Completed notebook fallback provided."
    )
    pdf.para("Output: shortlist + rule used + one data caveat.")

    pdf.heading("Resources")
    pdf.para("AM Sheet: [TBD publish link] + answer-key tab")
    pdf.para("PM: Google Colab (browser only) + demo_company_metrics.csv")
    pdf.para("CSV path: workshop/upskill-1s2627/resources/demo_company_metrics.csv")
    pdf.para("See BEGINNER_SPEAKER_NOTES.md for dual-role and pedagogy guardrails.")

    pdf.heading("Speaker Bio")
    pdf.para(
        "Galvin M. Gonzales - Event Head and AM/PM speaker. Teaching thread: "
        "beginner-accessible workflows on real Philippine listed-company snapshots - "
        "clean, question, and filter without assuming prior coding experience. "
        "Hosts/PTC handle logistics and MCing."
    )

    pdf.ln(3)
    pdf.para(
        "Prepared for UPSkill 1S2627 | Event Head & Speaker: Galvin M. Gonzales | Updated: Sep 6, 2026",
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
