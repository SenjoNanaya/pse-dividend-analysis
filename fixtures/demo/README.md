# Demo SQLite fixture

`pse_demo.db` is a small carve-out of live PSE Edge scrape data for the one-command demo.

Rebuild from your local scrape:

```bash
python scripts/export_demo_db.py
```

Default tickers: AB, AC, ALI, AUB, BDO, BPI, CNVRG, DMC, GLO, JFC, MBT, MER, PGOLD, SM, SMC, TEL.

Open **BPI** for the bank story: equity capital return, loan/deposit/NPL/NII checklist, and data-quality columns Loans / Dep / NII / NPL / ACL (PDF-tagged). AUB and BDO remain as thinner bank peers.

Run the demo:

```bash
python scripts/run_demo.py
```
