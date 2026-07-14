"""Backfill companies.div_yield from strict TTM common cash DPS / price."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db
from src.report_metrics import compute_div_yield, trailing_annual_dividend


def main():
    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()

    # Retag obvious property dividends mis-stored as cash (share-of-security payouts)
    # GREEN-style: no payment date + tiny "rate" scraped from share exchange text.
    # Safer path: any row already labeled property stays; optionally retag by scanner.
    # For known unpaid property-like rows without payment, leave chart history but
    # yield ignores non-cash once type is fixed on re-scrape. Force GREEN fix:
    cur.execute(
        """
        UPDATE dividends
        SET type = 'property'
        WHERE type = 'cash'
          AND payment_date IS NULL
          AND company_id IN (SELECT id FROM companies WHERE ticker = 'GREEN')
        """
    )
    print(f"retagged GREEN rows: {cur.rowcount}")

    companies = cur.execute(
        "SELECT id, ticker, last_traded_price FROM companies"
    ).fetchall()
    updated = 0
    nulls = 0
    for row in companies:
        cid = row["id"]
        price = row["last_traded_price"]
        divs = cur.execute(
            """
            SELECT ex_date, amount, type, security, is_common
            FROM dividends WHERE company_id = ?
            """,
            (cid,),
        ).fetchall()
        dividends = [dict(d) for d in divs]
        y = compute_div_yield(price, dividends)
        cur.execute("UPDATE companies SET div_yield = ? WHERE id = ?", (y, cid))
        if y is None:
            nulls += 1
        else:
            updated += 1
    conn.commit()

    print(f"yields set: {updated}, null: {nulls}")
    for t in ("GREEN", "BDO", "MBT", "ALI", "JFC", "SMC"):
        c = cur.execute(
            "SELECT ticker, last_traded_price, div_yield FROM companies WHERE ticker=?",
            (t,),
        ).fetchone()
        if not c:
            continue
        divs = [
            dict(d)
            for d in cur.execute(
                """
                SELECT ex_date, amount, type, security, is_common
                FROM dividends WHERE company_id = (
                  SELECT id FROM companies WHERE ticker=?
                )
                """,
                (t,),
            )
        ]
        annual = trailing_annual_dividend(divs)
        y = c["div_yield"]
        print(
            f"{t}: price={c['last_traded_price']} ttm_dps={annual} "
            f"yield={None if y is None else round(y * 100, 2)}%"
        )
    conn.close()


if __name__ == "__main__":
    main()
