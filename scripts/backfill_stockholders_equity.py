"""
Backfill stockholders_equity from Assets − Liabilities when missing.

Usage (from repo root):
  python scripts/backfill_stockholders_equity.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src import db
from src.field_sources import merge_source_tags, sources_from_json, sources_to_json


def main():
    db.init_db()
    conn = db.get_connection()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT id, total_assets, total_liabilities, stockholders_equity, field_sources
        FROM financials
        WHERE stockholders_equity IS NULL
          AND total_assets IS NOT NULL
          AND total_liabilities IS NOT NULL
        """
    ).fetchall()
    updated = 0
    for row in rows:
        equity = row["total_assets"] - row["total_liabilities"]
        sources = merge_source_tags(
            sources_from_json(row["field_sources"]),
            ["stockholders_equity"],
            "backfill",
        )
        cur.execute(
            """
            UPDATE financials
            SET stockholders_equity = ?, field_sources = ?
            WHERE id = ?
            """,
            (equity, sources_to_json(sources), row["id"]),
        )
        updated += 1
    conn.commit()
    conn.close()
    print(f"Backfilled stockholders_equity on {updated} financial row(s).")


if __name__ == "__main__":
    main()
