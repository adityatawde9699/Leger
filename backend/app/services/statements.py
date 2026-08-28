"""
statements.py — Bank statement parser (CSV + PDF).

PDF parsing strategy (in order of preference):
  1. pdfplumber structured table extraction (for digital/text PDFs)
  2. pdfplumber raw text extraction + regex row parser (for text PDFs with no tables)
  3. EasyOCR (for scanned/image-based PDFs — no external binary required)
     pip install easyocr
"""

import base64
import csv
import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from ..config import settings
from .categorizer import categorize

logger = logging.getLogger("ledger.statements")


def _money(value) -> Decimal:
    cleaned = str(value or "0").replace(",", "").strip()
    if not cleaned or cleaned.lower() == "nan":
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


class StatementRow(BaseModel):
    date: date
    description: str = Field(min_length=1, max_length=500)
    debit: Decimal = Field(default=Decimal("0"), ge=0)
    credit: Decimal = Field(default=Decimal("0"), ge=0)

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value):
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @model_validator(mode="after")
    def validate_amounts(self):
        if self.debit <= 0 and self.credit <= 0:
            raise ValueError("row has no debit or credit amount")
        if self.debit > 0 and self.credit > 0:
            raise ValueError("row has both debit and credit amounts")
        return self


def _parse_date_value(value) -> date | None:
    import pandas as pd

    raw = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d%b%Y", "%d%b%y"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            return parsed if parsed <= date.today() else None
        except ValueError:
            continue
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
    parsed_date = parsed.date()
    if parsed_date > date.today():
        logger.warning("Statement row skipped with future date=%s raw=%s", parsed_date, raw)
        return None
    return parsed_date


# ── Structured table parser ───────────────────────────────────────────────────


def _normalize_frame(df) -> list[dict]:

    df = df.dropna(how="all")
    normalized = {str(c).strip().lower().replace("\ufeff", ""): c for c in df.columns}
    date_col = next((normalized[c] for c in normalized if "date" in c or "timestamp" in c or "time" in c), None)
    desc_col = next(
        (
            normalized[c]
            for c in normalized
            if c
            in {
                "description",
                "details",
                "narration",
                "particulars",
                "receiver name",
                "recipient",
                "merchant",
                "vendor",
            }
            or any(
                token in c
                for token in (
                    "description",
                    "detail",
                    "narration",
                    "particular",
                    "remarks",
                    "receiver",
                    "recipient",
                    "merchant",
                    "vendor",
                )
            )
        ),
        None,
    )
    amount_col = next((normalized[c] for c in normalized if "amount" in c), None)
    debit_col = next((normalized[c] for c in normalized if "debit" in c or "withdraw" in c), None)
    credit_col = next((normalized[c] for c in normalized if "credit" in c or "deposit" in c), None)
    if not date_col or not desc_col or not (amount_col or debit_col or credit_col):
        return []

    # Detect the Balance column — must contain "balance" or equal "bal",
    # but must NOT be the debit or credit column itself.
    balance_col = next(
        (
            normalized[c]
            for c in normalized
            if ("balance" in c or c == "bal")
            and "debit" not in c
            and "credit" not in c
            and "withdraw" not in c
            and "deposit" not in c
        ),
        None,
    )

    rows: list[dict] = []
    for idx, row in df.iterrows():
        description = str(row.get(desc_col, "")).strip()
        parsed_date = _parse_date_value(row.get(date_col))
        if not description or not parsed_date:
            continue

        debit = _money(row.get(debit_col)) if debit_col else Decimal("0")
        credit = _money(row.get(credit_col)) if credit_col else Decimal("0")
        if amount_col:
            raw = _money(row.get(amount_col))
            debit = abs(raw) if raw < 0 else Decimal("0")
            credit = raw if raw > 0 else Decimal("0")
        try:
            valid = StatementRow(date=parsed_date, description=description, debit=debit, credit=credit)
        except ValidationError as exc:
            logger.warning("CSV row skipped idx=%s reason=%s", idx, exc.errors()[0]["msg"])
            continue

        tx_type = "income" if valid.credit > 0 else "expense"
        amount = valid.credit if valid.credit > 0 else valid.debit

        # Capture bank-reported running balance from the Balance column (e.g. SBI statement)
        running_balance: Decimal | None = None
        if balance_col is not None:
            bal_raw = row.get(balance_col)
            if bal_raw is not None:
                parsed_bal = _money(bal_raw)
                if parsed_bal != Decimal("0"):
                    running_balance = parsed_bal

        rows.append(
            {
                "date": valid.date,
                "type": tx_type,
                "amount": amount,
                "description": valid.description,
                "category": categorize(valid.description, tx_type),
                "source": "statement",
                "running_balance": running_balance,
            }
        )
    return rows


# ── Text-based regex row parser ───────────────────────────────────────────────

_DATE_RE = re.compile(r"\b(\d{1,2}[\/\-]\d{2}[\/\-]\d{4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{4}|\d{1,2}[A-Za-z]{3}\d{2,4})\b")
_AMOUNT_RE = re.compile(r"([0-9,]+\.[0-9]{2})")
_MARKDOWN_TABLE_RE = re.compile(r"^\s*\|.+\|\s*$")


def _parse_date_str(s: str) -> "datetime.date | None":
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d%b%Y", "%d%b%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_text_rows(text: str) -> list[dict]:
    """Regex row parser for raw text extracted from a PDF."""
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        date_m = _DATE_RE.search(line)
        if not date_m:
            continue
        tx_date = _parse_date_str(date_m.group(0))
        if not tx_date:
            continue
        amounts = _AMOUNT_RE.findall(line)
        if len(amounts) < 2:
            continue
        rest = line[date_m.end() :].strip()
        amount_positions = [m.start() for m in _AMOUNT_RE.finditer(rest)]
        if not amount_positions:
            continue
        description = rest[: amount_positions[0]].strip().strip("-").strip()
        if not description:
            description = "Bank transaction"
        lower_rest = rest.lower()
        is_credit = bool(re.search(r"\b(cr|credit|deposit|dep|salary|refund)\b|/cr/|\\bcr\\b", lower_rest))
        is_debit = bool(re.search(r"\b(dr|debit|withdraw|paid|wdl|atm|pos|fee|charges?)\b|/dr/|\\bdr\\b", lower_rest))
        try:
            amount = Decimal(amounts[0].replace(",", ""))
        except InvalidOperation:
            continue
        if amount <= 0:
            continue
        tx_type = "income" if is_credit and not is_debit else "expense"
        rows.append(
            {
                "date": tx_date,
                "type": tx_type,
                "amount": amount,
                "description": description,
                "category": categorize(description, tx_type),
                "source": "statement",
            }
        )
    return rows


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json|csv|markdown|md)?\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _rows_from_json_text(text: str) -> list[dict]:
    import pandas as pd

    raw = _strip_code_fence(text)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"(\[[\s\S]+\]|\{[\s\S]+\})", raw)
        if not match:
            return []
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return []

    if isinstance(payload, dict):
        payload = payload.get("transactions") or payload.get("rows") or []
    if not isinstance(payload, list):
        return []

    frame_rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        frame_rows.append(
            {
                "date": item.get("date") or item.get("txn_date") or item.get("transaction_date"),
                "details": item.get("description")
                or item.get("details")
                or item.get("narration")
                or item.get("particulars"),
                "debit": item.get("debit") or item.get("withdrawal") or item.get("withdrawals") or "",
                "credit": item.get("credit") or item.get("deposit") or item.get("deposits") or "",
                "balance": item.get("balance") or "",
            }
        )
    return _normalize_frame(pd.DataFrame(frame_rows))


def _rows_from_markdown_tables(text: str) -> list[dict]:
    import pandas as pd

    rows: list[dict] = []
    table_lines: list[str] = []

    def flush_table():
        if len(table_lines) < 2:
            table_lines.clear()
            return
        header = [cell.strip() for cell in table_lines[0].strip().strip("|").split("|")]
        data_lines = [
            line for line in table_lines[1:] if not re.match(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$", line)
        ]
        records = []
        for line in data_lines:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) != len(header):
                continue
            records.append(dict(zip(header, cells, strict=False)))
        if records:
            rows.extend(_normalize_frame(pd.DataFrame(records)))
        table_lines.clear()

    for line in text.splitlines():
        if _MARKDOWN_TABLE_RE.match(line):
            table_lines.append(line)
        elif table_lines:
            flush_table()
    if table_lines:
        flush_table()
    return rows


def _rows_from_csv_text(text: str) -> list[dict]:
    import pandas as pd

    raw = _strip_code_fence(text)
    sample = "\n".join(line for line in raw.splitlines() if line.strip())
    if "," not in sample or "date" not in sample.lower():
        return []
    try:
        dialect = csv.Sniffer().sniff(sample[:4096])
    except csv.Error:
        dialect = "excel"
    try:
        return _normalize_frame(pd.read_csv(StringIO(sample), dtype=str, keep_default_na=False, dialect=dialect))
    except Exception:
        return []


def _parse_ai_rows(text: str) -> list[dict]:
    if not text.strip():
        return []
    for parser in (_rows_from_json_text, _rows_from_csv_text, _rows_from_markdown_tables, _parse_text_rows):
        rows = parser(text)
        if rows:
            return rows
    return []


async def _gemini_parse_pdf(content: bytes) -> str:
    """Send the PDF to Gemini 1.5 Flash to extract transaction text."""
    if not settings.gemini_api_key:
        return ""

    logger.info("Sending PDF to Gemini for extraction...")
    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        pdf_part = {"mime_type": "application/pdf", "data": content}
        prompt = """Extract every bank statement transaction from this PDF.
Return only JSON with this shape:
{"transactions":[{"date":"DD/MM/YYYY","description":"...","debit":"0.00","credit":"0.00","balance":"0.00"}]}
Rules:
- Do not include statement summary, totals, opening balance, closing balance, or blank rows.
- Preserve full UPI narration/merchant text in description.
- Use debit for withdrawals/expenses and credit for deposits/income. Use empty string or 0.00 for the unused side."""

        response = await model.generate_content_async([pdf_part, prompt])
        return response.text
    except Exception as e:
        logger.warning("Gemini PDF extraction failed: %s", e)
        return ""


async def _mistral_ocr_pdf(content: bytes) -> str:
    """Send the PDF to Mistral OCR as a fallback."""
    if not settings.mistral_api_key:
        return ""

    logger.info("Sending PDF to Mistral OCR...")
    try:
        pdf_b64 = base64.b64encode(content).decode("utf-8")

        payload = {
            "model": "mistral-ocr-latest",
            "document": {
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{pdf_b64}",
            },
            "include_image_base64": False,
            "table_format": "markdown",
            "extract_header": False,
            "extract_footer": False,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.mistral.ai/v1/ocr",
                headers={
                    "Authorization": f"Bearer {settings.mistral_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
        texts = [page.get("markdown", "") for page in data.get("pages", [])]
        return "\n".join(texts)
    except Exception as e:
        logger.warning("Mistral OCR extraction failed: %s", e)
        return ""


# ── Public parsers ────────────────────────────────────────────────────────────


def parse_csv(content: bytes) -> list[dict]:
    import pandas as pd

    # Robust check: if content starts with PK ZIP magic bytes, it's actually an Excel workbook (.xlsx)
    if content.startswith(b"PK\x03\x04"):
        logger.info("parse_csv: Detected Excel magic signature. Redirecting to parse_excel.")
        return parse_excel(content)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    df = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)
    return _normalize_frame(df)


def parse_excel(content: bytes) -> list[dict]:
    import pandas as pd

    rows: list[dict] = []
    workbook = pd.read_excel(BytesIO(content), sheet_name=None, dtype=str, keep_default_na=False)
    for sheet_name, df in workbook.items():
        parsed = _normalize_frame(df)
        logger.info("Excel sheet parsed sheet=%s rows=%d", sheet_name, len(parsed))
        rows.extend(parsed)
    return rows


async def parse_pdf(content: bytes) -> list[dict]:
    import pandas as pd
    import pdfplumber

    rows: list[dict] = []
    full_text_lines: list[str] = []
    has_any_text = False

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            # ── 1. Structured table extraction ──
            for table in page.extract_tables() or []:
                if len(table) < 2:
                    continue
                non_empty = sum(1 for row in table for cell in row if cell and str(cell).strip())
                if non_empty > 4:
                    rows.extend(_normalize_frame(pd.DataFrame(table[1:], columns=table[0])))

            # ── Collect page text ──
            text = page.extract_text(x_tolerance=3, y_tolerance=3)
            if text and text.strip():
                has_any_text = True
                full_text_lines.append(text)

    # ── 2. Text-regex fallback (text PDF, no well-formed tables) ──
    if not rows and has_any_text:
        logger.info("PDF: no structured tables found, trying text-regex parser")
        rows = _parse_text_rows("\n".join(full_text_lines))

    # ── 3. AI Parsing fallback (image-based / scanned PDF) ──
    if not rows:
        logger.info("PDF local extraction found no rows; attempting Mistral OCR")
        ocr_text = await _mistral_ocr_pdf(content)
        rows = _parse_ai_rows(ocr_text)

        if not rows:
            logger.info("Mistral OCR empty/unparseable; attempting Gemini extraction")
            ocr_text = await _gemini_parse_pdf(content)
            rows = _parse_ai_rows(ocr_text)

        if not rows:
            logger.warning("PDF OCR providers returned no parseable transactions.")

    return rows
