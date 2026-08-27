"""
One-time script to backfill stmt_seq on existing transactions using the
actual CSV row order from Book1.csv. Run from the backend directory.
"""

import hashlib
import sys

sys.path.insert(0, ".")

from sqlalchemy import text

from app.db import engine
from app.services.statements import parse_csv

CSV_PATH = "../Book1.csv"

with open(CSV_PATH, "rb") as f:
    rows = parse_csv(f.read())

print(f"Parsed {len(rows)} rows from CSV")

# Build fingerprint -> seq map using the same logic as the importer
seq_map = {}
for seq, row in enumerate(rows):
    fp = hashlib.sha256(f"{row['date']}{row['amount']}{row['description']}".encode()).hexdigest()
    seq_map[fp] = seq

print(f"Built seq_map with {len(seq_map)} entries")

with engine.connect() as conn:
    updated = 0
    for fp, seq in seq_map.items():
        result = conn.execute(
            text("UPDATE transactions SET stmt_seq = :seq WHERE source_ref = :fp AND source = 'statement'"),
            {"seq": seq, "fp": fp},
        )
        updated += result.rowcount
    conn.commit()
    print(f"Updated {updated} transactions with correct stmt_seq")

# Verify: check May transactions
with engine.connect() as conn:
    rows_out = conn.execute(
        text(
            "SELECT date, type, amount, running_balance, stmt_seq "
            "FROM transactions "
            "WHERE stmt_seq IS NOT NULL AND date >= '2026-05-01' AND date <= '2026-05-19' "
            "ORDER BY stmt_seq DESC LIMIT 5"
        )
    ).fetchall()
    print("\nLast 5 May transactions by stmt_seq (closing):")
    for r in rows_out:
        print(f"  seq={r[4]:>4}  date={r[0]}  {r[1]:7}  amt={r[2]:>10}  bal={r[3]}")

    rows_out2 = conn.execute(
        text(
            "SELECT date, type, amount, running_balance, stmt_seq "
            "FROM transactions "
            "WHERE stmt_seq IS NOT NULL AND date >= '2026-05-01' AND date <= '2026-05-19' "
            "ORDER BY stmt_seq ASC LIMIT 3"
        )
    ).fetchall()
    print("\nFirst 3 May transactions by stmt_seq (opening):")
    for r in rows_out2:
        print(f"  seq={r[4]:>4}  date={r[0]}  {r[1]:7}  amt={r[2]:>10}  bal={r[3]}")
