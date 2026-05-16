"""
Data export — CSV, JSON, and Tally-compatible XML export for transactions.
"""
import csv
import io
import json
from datetime import date
from decimal import Decimal
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from ..models import Transaction
from .gst import compute_gst


def export_csv(transactions: list[Transaction]) -> str:
    """Export transactions as CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Type", "Category", "Amount", "Description",
        "Merchant", "Source", "Tags", "Notes",
        "GST Rate", "GST Amount", "HSN/SAC Code",
    ])
    for tx in transactions:
        gst = compute_gst(tx.amount, tx.category, tx.merchant_normalized)
        writer.writerow([
            tx.date.isoformat(),
            tx.type,
            tx.category,
            str(tx.amount),
            tx.description,
            tx.merchant_normalized or "",
            tx.source,
            tx.tags or "",
            tx.notes or "",
            gst["gst_rate"],
            str(gst["gst_amount"]),
            gst["hsn_code"] or "",
        ])
    return output.getvalue()


def export_json(transactions: list[Transaction]) -> str:
    """Export transactions as JSON string."""
    rows = []
    for tx in transactions:
        gst = compute_gst(tx.amount, tx.category, tx.merchant_normalized)
        rows.append({
            "id": tx.id,
            "date": tx.date.isoformat(),
            "type": tx.type,
            "category": tx.category,
            "amount": float(tx.amount),
            "description": tx.description,
            "merchant": tx.merchant_normalized,
            "source": tx.source,
            "tags": tx.tags,
            "notes": tx.notes,
            "gst": {
                "rate": gst["gst_rate"],
                "amount": float(gst["gst_amount"]),
                "base_amount": float(gst["base_amount"]),
                "hsn_code": gst["hsn_code"],
            },
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        })
    return json.dumps({"transactions": rows, "count": len(rows)}, indent=2)


def export_tally_xml(transactions: list[Transaction], company_name: str = "Ledger User") -> str:
    """
    Export transactions as Tally-compatible XML (ENVELOPE format).
    Compatible with Tally Prime / Tally ERP 9 import.
    """
    envelope = Element("ENVELOPE")
    header = SubElement(envelope, "HEADER")
    SubElement(header, "TALLYREQUEST").text = "Import Data"

    body = SubElement(envelope, "BODY")
    import_data = SubElement(body, "IMPORTDATA")
    request_desc = SubElement(import_data, "REQUESTDESC")
    SubElement(request_desc, "REPORTNAME").text = "Vouchers"

    request_data = SubElement(import_data, "REQUESTDATA")

    for tx in transactions:
        gst = compute_gst(tx.amount, tx.category, tx.merchant_normalized)

        voucher = SubElement(request_data, "TALLYMESSAGE", xmlns_UDF="TallyUDF")
        v = SubElement(voucher, "VOUCHER", VCHTYPE="Payment" if tx.type == "expense" else "Receipt")
        SubElement(v, "DATE").text = tx.date.strftime("%Y%m%d")
        SubElement(v, "NARRATION").text = tx.description
        SubElement(v, "VOUCHERTYPENAME").text = "Payment" if tx.type == "expense" else "Receipt"
        SubElement(v, "PARTYLEDGERNAME").text = tx.merchant_normalized or tx.description[:50]

        # Ledger entries
        entry = SubElement(v, "ALLLEDGERENTRIES.LIST")
        SubElement(entry, "LEDGERNAME").text = tx.category
        SubElement(entry, "ISDEEMEDPOSITIVE").text = "Yes" if tx.type == "expense" else "No"
        SubElement(entry, "AMOUNT").text = str(tx.amount)

        # GST entry if applicable
        if gst["gst_rate"] > 0:
            gst_entry = SubElement(v, "ALLLEDGERENTRIES.LIST")
            SubElement(gst_entry, "LEDGERNAME").text = f"GST @ {gst['gst_rate']}%"
            SubElement(gst_entry, "AMOUNT").text = str(gst["gst_amount"])

    return tostring(envelope, encoding="unicode", xml_declaration=True)
