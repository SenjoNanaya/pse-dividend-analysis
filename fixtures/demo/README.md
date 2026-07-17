# Demo SQLite fixture

`pse_demo.db` is a small carve-out of live PSE Edge scrape data for the one-command demo.

Rebuild from your local scrape:

```bash
python scripts/export_demo_db.py
```

Tickers included by default: AB, AC, ALI, AUB, BDO, CNVRG, DMC, GLO, JFC, MBT, MER, PGOLD, SM, SMC, TEL.

Run the demo:

```bash
python scripts/run_demo.py
```
