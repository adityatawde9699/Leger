import Papa from "papaparse";
import * as xlsx from "xlsx";
import { extractText } from "unpdf";
import { GoogleGenAI } from "@google/genai";
import { config } from "../config.js";
import { Decimal } from "decimal.js";
import { z } from "zod";

const dateRegex = /\b(\d{1,2}[\/\-]\d{2}[\/\-]\d{4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{4}|\d{1,2}[A-Za-z]{3}\d{2,4})\b/;
const amountRegex = /([0-9,]+\.[0-9]{2})/;

function parseDateStr(s: string): Date | null {
  s = s.trim();
  const parts = s.split(/[\/\-\s]/);
  if (parts.length === 3) {
    // Basic heuristics: if length 3, assume DD-MM-YYYY or DD-MMM-YYYY
    // Native Date handles many formats. Let's try parsing directly if it's alphanumeric
    const d = new Date(s);
    if (!isNaN(d.getTime())) return d;
    // Try DD/MM/YYYY
    const d2 = new Date(`${parts[2]}-${parts[1]}-${parts[0]}`);
    if (!isNaN(d2.getTime())) return d2;
  }
  return null;
}

function parseMoney(value: any): Decimal {
  if (value === null || value === undefined) return new Decimal(0);
  const cleaned = String(value).replace(/,/g, "").trim();
  if (!cleaned || cleaned.toLowerCase() === "nan") return new Decimal(0);
  try {
    return new Decimal(cleaned);
  } catch {
    return new Decimal(0);
  }
}

function normalizeFrame(rows: any[]): any[] {
  if (!rows || rows.length === 0) return [];

  // find header row if first few rows are garbage
  let headerIdx = 0;
  for (let i = 0; i < Math.min(20, rows.length); i++) {
    const row = rows[i];
    const keys = Object.keys(row).map(k => String(k).toLowerCase());
    const vals = Object.values(row).map(v => String(v).toLowerCase());
    const text = keys.join(" ") + " " + vals.join(" ");
    if (text.includes("date") && (text.includes("description") || text.includes("particulars") || text.includes("narration"))) {
      headerIdx = i;
      break;
    }
  }

  // Flatten based on header
  const dataRows = rows.slice(headerIdx);
  const results = [];

  for (const row of dataRows) {
    const normRow: Record<string, string> = {};
    for (const [k, v] of Object.entries(row)) {
      normRow[String(k).toLowerCase().trim()] = String(v);
    }
    
    // Find columns
    const dateCol = Object.keys(normRow).find(k => k.includes("date") || k.includes("time"));
    const descCol = Object.keys(normRow).find(k => k.includes("description") || k.includes("particulars") || k.includes("narration") || k.includes("details"));
    const debitCol = Object.keys(normRow).find(k => k.includes("debit") || k.includes("withdrawal"));
    const creditCol = Object.keys(normRow).find(k => k.includes("credit") || k.includes("deposit"));
    const amountCol = Object.keys(normRow).find(k => k.includes("amount") && !k.includes("debit") && !k.includes("credit"));
    const balanceCol = Object.keys(normRow).find(k => (k.includes("balance") || k === "bal") && !k.includes("debit") && !k.includes("credit"));

    if (!dateCol || !descCol || !(debitCol || creditCol || amountCol)) continue;

    const parsedDate = parseDateStr(normRow[dateCol]);
    if (!parsedDate) continue;

    const desc = normRow[descCol].trim();
    if (!desc) continue;

    let debit = parseMoney(debitCol ? normRow[debitCol] : 0);
    let credit = parseMoney(creditCol ? normRow[creditCol] : 0);

    if (amountCol) {
      const raw = parseMoney(normRow[amountCol]);
      if (raw.lt(0)) {
        debit = raw.abs();
        credit = new Decimal(0);
      } else {
        credit = raw;
        debit = new Decimal(0);
      }
    }

    if (debit.eq(0) && credit.eq(0)) continue;
    if (debit.gt(0) && credit.gt(0)) continue;

    const txType = credit.gt(0) ? "income" : "expense";
    const amount = credit.gt(0) ? credit : debit;

    let runningBalance: string | null = null;
    if (balanceCol) {
      const bal = parseMoney(normRow[balanceCol]);
      if (!bal.eq(0)) runningBalance = bal.toFixed(2);
    }

    results.push({
      date: parsedDate.toISOString().split("T")[0],
      type: txType,
      amount: amount.toFixed(2),
      description: desc,
      category: "uncategorized", // We can hook up categorizer later
      source: "statement",
      running_balance: runningBalance,
    });
  }
  return results;
}

export function parseCsv(content: Buffer): any[] {
  // If it's a ZIP/Excel disguised as CSV
  if (content.subarray(0, 4).toString('hex') === '504b0304') {
    return parseExcel(content);
  }
  
  const text = content.toString("utf8");
  const parsed = Papa.parse(text, { header: true, skipEmptyLines: true });
  return normalizeFrame(parsed.data);
}

export function parseExcel(content: Buffer): any[] {
  const workbook = xlsx.read(content, { type: "buffer" });
  const results = [];
  for (const sheetName of workbook.SheetNames) {
    const sheet = workbook.Sheets[sheetName];
    const data = xlsx.utils.sheet_to_json(sheet, { raw: false, defval: "" });
    results.push(...normalizeFrame(data));
  }
  return results;
}

async function geminiParsePdf(content: Buffer): Promise<any[]> {
  if (!config.GEMINI_API_KEY) return [];
  
  try {
    const ai = new GoogleGenAI({ apiKey: config.GEMINI_API_KEY });
    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: [
        {
          role: "user",
          parts: [
            {
              inlineData: {
                data: content.toString("base64"),
                mimeType: "application/pdf"
              }
            },
            {
              text: `Extract every bank statement transaction from this PDF.
Return only JSON with this shape:
{"transactions":[{"date":"YYYY-MM-DD","description":"...","debit":"0.00","credit":"0.00","balance":"0.00"}]}
Rules:
- Do not include statement summary, totals, opening balance, closing balance, or blank rows.
- Preserve full UPI narration/merchant text in description.
- Use debit for withdrawals/expenses and credit for deposits/income. Use empty string or 0.00 for the unused side.`
            }
          ]
        }
      ]
    });
    
    let text = response.text || "";
    text = text.replace(/^\\s*\\x60\\x60\\x60(json)?/m, "").replace(/\\x60\\x60\\x60\\s*$/m, "").trim();
    
    const data = JSON.parse(text);
    const rows = data.transactions || data.rows || [];
    
    const results = [];
    for (const r of rows) {
      if (!r.date || !r.description) continue;
      const debit = parseMoney(r.debit || r.withdrawal || 0);
      const credit = parseMoney(r.credit || r.deposit || 0);
      if (debit.eq(0) && credit.eq(0)) continue;
      
      results.push({
        date: r.date,
        type: credit.gt(0) ? "income" : "expense",
        amount: credit.gt(0) ? credit.toFixed(2) : debit.toFixed(2),
        description: r.description,
        category: "uncategorized",
        source: "statement",
        running_balance: r.balance ? parseMoney(r.balance).toFixed(2) : null
      });
    }
    return results;
  } catch (e) {
    console.error("Gemini PDF extraction failed:", e);
    return [];
  }
}

export async function parsePdf(content: Buffer): Promise<any[]> {
  // First try text extraction
  try {
    const pdf = await extractText(content);
    const pdfText = Array.isArray(pdf?.text) ? pdf.text.join("\\n") : String(pdf?.text || "");
    if (pdfText && pdfText.trim().length > 100) {
      // Basic text parser
      const rows = [];
      const lines = pdfText.split("\\n");
      for (const line of lines) {
        const match = dateRegex.exec(line);
        if (!match) continue;
        const txDate = parseDateStr(match[0]);
        if (!txDate) continue;
        
        const rest = line.substring(match.index + match[0].length).trim();
        const amounts = [];
        let amatch;
        const areg = new RegExp(amountRegex, "g");
        while ((amatch = areg.exec(rest)) !== null) {
          amounts.push({ val: amatch[1], idx: amatch.index });
        }
        
        if (amounts.length < 2) continue;
        
        const desc = rest.substring(0, amounts[0].idx).replace(/^[-]+/, "").trim();
        if (!desc) continue;
        
        const lowerRest = rest.toLowerCase();
        const isCredit = /\\b(cr|credit|deposit|dep|salary|refund)\\b|\/cr\//.test(lowerRest);
        const isDebit = /\\b(dr|debit|withdraw|paid|wdl|atm|pos|fee|charges?)\\b|\/dr\//.test(lowerRest);
        
        const amount = parseMoney(amounts[0].val);
        if (amount.lte(0)) continue;
        
        rows.push({
          date: txDate.toISOString().split("T")[0],
          type: (isCredit && !isDebit) ? "income" : "expense",
          amount: amount.toFixed(2),
          description: desc,
          category: "uncategorized",
          source: "statement",
          running_balance: null
        });
      }
      if (rows.length > 0) return rows;
    }
  } catch (e) {
    console.warn("Text extraction failed, falling back to OCR", e);
  }
  
  // OCR fallback
  return geminiParsePdf(content);
}
