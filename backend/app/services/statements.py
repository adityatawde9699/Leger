from decimal import Decimal
from io import BytesIO, StringIO

import pandas as pd
import pdfplumber

from .categorizer import categorize


def _money(value) -> Decimal:
    cleaned = str(value or "0").replace(",", "").strip()
    if not cleaned or cleaned.lower() == "nan":
        return Decimal("0")
    return Decimal(cleaned)


def _normalize_frame(df: pd.DataFrame) -> list[dict]:
    normalized = {str(c).strip().lower(): c for c in df.columns}
    date_col = next((normalized[c] for c in normalized if "date" in c), None)
    desc_col = next((normalized[c] for c in normalized if c in {"description", "details", "narration", "particulars"}), None)
    amount_col = next((normalized[c] for c in normalized if "amount" in c), None)
    debit_col = next((normalized[c] for c in normalized if "debit" in c or "withdraw" in c), None)
    credit_col = next((normalized[c] for c in normalized if "credit" in c or "deposit" in c), None)
    if not date_col or not desc_col or not (amount_col or debit_col or credit_col):
        return []

    rows: list[dict] = []
    for _, row in df.iterrows():
        description = str(row.get(desc_col, "")).strip()
        parsed_date = pd.to_datetime(row.get(date_col), errors="coerce")
        if not description or pd.isna(parsed_date):
            continue

        debit = _money(row.get(debit_col)) if debit_col else Decimal("0")
        credit = _money(row.get(credit_col)) if credit_col else Decimal("0")
        if amount_col:
            raw = _money(row.get(amount_col))
            tx_type = "income" if raw > 0 else "expense"
            amount = abs(raw)
        else:
            tx_type = "income" if credit > 0 else "expense"
            amount = credit if credit > 0 else debit
        if amount <= 0:
            continue
        rows.append({
            "date": parsed_date.date(),
            "type": tx_type,
            "amount": amount,
            "description": description,
            "category": categorize(description, tx_type),
            "source": "statement",
        })
    return rows


def parse_csv(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig")
    return _normalize_frame(pd.read_csv(StringIO(text)))


def parse_pdf(content: bytes) -> list[dict]:
    rows = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if len(table) < 2:
                    continue
                rows.extend(_normalize_frame(pd.DataFrame(table[1:], columns=table[0])))
    return rows
