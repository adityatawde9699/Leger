"""CSV export must not let statement or SMS text execute as spreadsheet formulas."""

import csv
import io
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.export import export_csv


def _tx(**overrides):
    base = dict(
        date=date(2026, 3, 1), type="expense", status="posted", category="Food", amount=Decimal("120.50"),
        description="Lunch", merchant_normalized=None, source="statement", tags=None, notes=None,
    )
    return SimpleNamespace(**{**base, **overrides})


def _rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def test_csv_export_neutralises_formula_cells():
    payloads = ['=HYPERLINK("http://evil.example","x")', "+1+1", "-2+3", "@SUM(A1)", "\tTAB", "\rCR"]
    exported = _rows(export_csv([
        _tx(description=payload, merchant_normalized=payload, notes=payload, tags=payload) for payload in payloads
    ]))

    for row, payload in zip(exported, payloads, strict=True):
        for column in ("Description", "Merchant", "Notes", "Tags"):
            assert row[column] == "'" + payload


def test_csv_export_keeps_ordinary_values_and_numbers():
    row = _rows(export_csv([_tx(description="UPI/Swiggy order", notes="Team lunch")]))[0]

    assert row["Description"] == "UPI/Swiggy order"
    assert row["Notes"] == "Team lunch"
    assert row["Amount"] == "120.50"
    assert row["Merchant"] == ""
