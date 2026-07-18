import crypto from "crypto";

const AMOUNT_PREFIX_RE = /(?:rs\.?|inr|₹)\s*([0-9,]+(?:\.[0-9]{1,2})?)/i;
const AMOUNT_BARE_RE = /(?:debited\s+by|credited\s+by|for|of)\s+([0-9,]+(?:\.[0-9]{1,2})?)/i;

const MERCHANT_PATTERNS = [
  /trf\s+to\s+([a-z0-9 .&_\-]{2,50}?)(?:\s+refno|\s+ref|\s+upi|$)/i,
  /(?:to|at|for)\s+([a-z0-9 .&_\-]{2,40}?)(?:\s+via|\s+on|\s+ref|\s+upi|$)/i,
  /(?:from)\s+([a-z0-9 .&_\-]{2,40}?)(?:\s+via|\s+on|\s+ref|\s+upi|$)/i
];

const TRIGGER_WORDS = ["debited", "credited", "spent", "received", "paid", "deducted", "transferred"];

function extractAmount(message: string): number | null {
  let m = AMOUNT_PREFIX_RE.exec(message);
  if (m) {
    const val = parseFloat(m[1].replace(/,/g, ""));
    if (!isNaN(val)) return val;
  }
  
  m = AMOUNT_BARE_RE.exec(message);
  if (m) {
    const val = parseFloat(m[1].replace(/,/g, ""));
    if (!isNaN(val)) return val;
  }
  
  return null;
}

function extractDate(message: string): Date | null {
  // Simplistic matching for Node since Native Date parses Indian formats poorly sometimes
  // e.g. 17May26
  const p1 = /\\b(\\d{2})([a-zA-Z]{3})(\\d{2,4})\\b/.exec(message);
  if (p1) {
    let year = p1[3].length === 2 ? `20${p1[3]}` : p1[3];
    const d = new Date(`${p1[2]} ${p1[1]} ${year}`);
    if (!isNaN(d.getTime())) return d;
  }
  
  const p2 = /\\b(\\d{2})[-/](\\d{2})[-/](\\d{4})\\b/.exec(message);
  if (p2) {
    // try DD/MM/YYYY
    const d = new Date(`${p2[3]}-${p2[2]}-${p2[1]}`);
    if (!isNaN(d.getTime())) return d;
  }
  
  const p3 = /\\b(\\d{2})[-]([a-zA-Z]{3})[-](\\d{4})\\b/.exec(message);
  if (p3) {
    const d = new Date(`${p3[2]} ${p3[1]} ${p3[3]}`);
    if (!isNaN(d.getTime())) return d;
  }
  
  return null;
}

export function parseSms(message: string, fallbackDate: Date = new Date()): any | null {
  const lower = message.toLowerCase();
  
  if (!TRIGGER_WORDS.some(w => lower.includes(w))) return null;
  
  const amount = extractAmount(message);
  if (amount === null || amount <= 0) return null;
  
  const isCredit = lower.includes("credited") || lower.includes("received");
  const txType = isCredit ? "income" : "expense";
  
  let merchant = "UPI transaction";
  for (const pattern of MERCHANT_PATTERNS) {
    const match = pattern.exec(message);
    if (match) {
      const candidate = match[1].replace(/\\s+/g, " ").replace(/^[ .-]+|[ .-]+$/g, "");
      if (candidate) {
        merchant = candidate;
        break;
      }
    }
  }
  
  let txDate = extractDate(message) || fallbackDate;
  
  return {
    date: txDate.toISOString().split("T")[0],
    type: txType,
    amount: amount.toFixed(2),
    description: merchant,
    category: "uncategorized",
    source: "sms",
    source_ref: crypto.createHash("sha256").update(message).digest("hex")
  };
}
