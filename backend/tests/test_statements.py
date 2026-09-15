from decimal import Decimal
from io import BytesIO

import pandas as pd

from app.services.statements import parse_excel


def test_parse_ods_statement():
    statement = pd.DataFrame(
        [
            {
                "Date": "15/08/2025",
                "Narration": "UPI grocery store",
                "Debit": "1250.50",
                "Credit": "",
                "Balance": "8750.50",
            },
            {
                "Date": "16/08/2025",
                "Narration": "Monthly salary",
                "Debit": "",
                "Credit": "50000.00",
                "Balance": "58750.50",
            },
        ]
    )
    content = BytesIO()
    statement.to_excel(content, index=False, engine="odf")

    rows = parse_excel(content.getvalue(), "ods")

    assert len(rows) == 2
    assert rows[0]["type"] == "expense"
    assert rows[0]["amount"] == Decimal("1250.50")
    assert rows[0]["running_balance"] == Decimal("8750.50")
    assert rows[1]["type"] == "income"
    assert rows[1]["amount"] == Decimal("50000.00")


def test_parse_ods_reads_all_sheets():
    content = BytesIO()
    with pd.ExcelWriter(content, engine="odf") as writer:
        pd.DataFrame(
            [{"Date": "01/07/2025", "Description": "Rent", "Debit": "12000", "Credit": ""}]
        ).to_excel(writer, sheet_name="July", index=False)
        pd.DataFrame(
            [{"Date": "01/08/2025", "Description": "Rent", "Debit": "12000", "Credit": ""}]
        ).to_excel(writer, sheet_name="August", index=False)

    rows = parse_excel(content.getvalue(), "ods")

    assert len(rows) == 2
    assert [row["date"].month for row in rows] == [7, 8]
