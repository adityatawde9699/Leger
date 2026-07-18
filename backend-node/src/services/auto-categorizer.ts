import { GoogleGenAI } from "@google/genai";
import { config } from "../config.js";
import { CATEGORIES, EXPENSE_CATEGORIES, ruleCategorize, extractUpiMerchant } from "./categorizer.js";

const RULES_CONFIDENCE = 0.95;

const CATEGORIZE_SYSTEM = `You are a financial transaction categorizer for an Indian personal finance app.
Given a transaction description, classify it into EXACTLY one of these categories:
{categories}

Few-shot examples (format: description -> JSON):
"UPI/DR/123/SWIGGY INDIA" -> {"category": "Dining", "confidence": 0.98, "merchant": "Swiggy", "reason": "Swiggy is a food delivery app"}
"NEFT/ZERODHA BROKING LTD" -> {"category": "Investments", "confidence": 0.97, "merchant": "Zerodha", "reason": "Zerodha is a stock broker"}
"AMAZON PAY ICICI" -> {"category": "Shopping", "confidence": 0.90, "merchant": "Amazon", "reason": "Amazon is an e-commerce platform"}
"IRCTC TICKET BOOKING" -> {"category": "Transport", "confidence": 0.99, "merchant": "IRCTC", "reason": "IRCTC handles Indian railway bookings"}
"NETFLIX SUBSCRIPTION" -> {"category": "Subscriptions", "confidence": 0.99, "merchant": "Netflix", "reason": "Netflix is a video streaming service"}

Rules:
- Return ONLY a JSON object: {"category": "...", "confidence": 0.0-1.0, "merchant": "...", "reason": "one sentence"}
- "merchant" is the normalized merchant name (e.g., "Swiggy", "Amazon", "PhonePe")
- "confidence" is your certainty from 0.0 to 1.0
- "reason" is a brief explanation (max 10 words)
- Use "Other" with low confidence only if truly ambiguous
- No explanation, no extra text. JSON only.`;

const BATCH_CATEGORIZE_SYSTEM = `You are a financial transaction categorizer for an Indian personal finance app.
Classify each transaction into EXACTLY one of these categories:
{categories}

Few-shot examples:
"UPI/DR/SWIGGY INDIA" -> Dining | "IRCTC BOOKING" -> Transport | "NETFLIX" -> Subscriptions
"ZERODHA" -> Investments | "STAR HEALTH" -> Insurance | "UDEMY COURSE" -> Education

Return ONLY a JSON array. Each element:
{"id": "...", "category": "...", "confidence": 0.0-1.0, "merchant": "...", "reason": "brief"}
No explanation. JSON only.`;

function extractJson(raw: string): any {
  if (!raw) return null;
  let text = raw.replace(/^\\s*\\x60\\x60\\x60(json)?/m, "").replace(/\\x60\\x60\\x60\\s*$/m, "").trim();
  try { return JSON.parse(text); } catch { }
  
  const m = text.match(/(\\{[\\s\\S]*\\}|\\[[\\s\\S]*\\])/);
  if (m) {
    try { return JSON.parse(m[1]); } catch { }
  }
  return null;
}

export async function categorizeSingle(description: string, txType: string = "expense", userOverrides?: Record<string, string>): Promise<any> {
  // 1. User Overrides
  if (userOverrides) {
    const crypto = await import("crypto");
    const key = crypto.createHash("sha256").update(description.toLowerCase().trim().replace(/\\s+/g, " ")).digest("hex");
    if (userOverrides[key]) {
      return {
        category: userOverrides[key],
        confidence: 1.0,
        merchant: extractUpiMerchant(description),
        source: "override",
        reason: "User manually corrected"
      };
    }
  }

  // 2. Rules
  const ruleResult = ruleCategorize(description, txType);
  if (ruleResult !== "Other") {
    return {
      category: ruleResult,
      confidence: RULES_CONFIDENCE,
      merchant: extractUpiMerchant(description),
      source: "rules",
      reason: "Matched keyword rule"
    };
  }

  // 3. LLM Fallback (Embedding cache skipped for Node without vector DB)
  if (!config.GEMINI_API_KEY) {
    return {
      category: "Other",
      confidence: 0.1,
      merchant: extractUpiMerchant(description),
      source: "fallback",
      reason: "No AI provider configured"
    };
  }

  try {
    const ai = new GoogleGenAI({ apiKey: config.GEMINI_API_KEY });
    const cats = (txType === "expense" ? EXPENSE_CATEGORIES : CATEGORIES).join(", ");
    
    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: [
        { role: "user", parts: [{ text: CATEGORIZE_SYSTEM.replace("{categories}", cats) }, { text: `Transaction: ${description}` }] }
      ]
    });

    const parsed = extractJson(response.text || "");
    if (parsed && typeof parsed === "object") {
      const cat = CATEGORIES.includes(parsed.category) ? parsed.category : "Other";
      return {
        category: cat,
        confidence: Math.min(1, Math.max(0, parseFloat(parsed.confidence || "0.5"))),
        merchant: parsed.merchant || extractUpiMerchant(description),
        source: "llm",
        reason: parsed.reason || "LLM classification"
      };
    }
  } catch (e) {
    console.warn("LLM categorizeSingle failed:", e);
  }

  return {
    category: "Other",
    confidence: 0.1,
    merchant: extractUpiMerchant(description),
    source: "fallback",
    reason: "Could not determine category"
  };
}

export async function categorizeBatch(transactions: any[], userOverrides?: Record<string, string>): Promise<any[]> {
  const results: Record<string, any> = {};
  const needsLlm: any[] = [];
  
  for (const tx of transactions) {
    const tid = tx.id;
    const desc = tx.description;
    const ttype = tx.type || "expense";
    
    // 1. User overrides
    if (userOverrides) {
      const crypto = await import("crypto");
      const key = crypto.createHash("sha256").update(desc.toLowerCase().trim().replace(/\\s+/g, " ")).digest("hex");
      if (userOverrides[key]) {
        results[tid] = {
          id: tid,
          category: userOverrides[key],
          confidence: 1.0,
          merchant: extractUpiMerchant(desc),
          reason: "User override"
        };
        continue;
      }
    }
    
    // 2. Rules
    const ruleResult = ruleCategorize(desc, ttype);
    if (ruleResult !== "Other") {
      results[tid] = {
        id: tid,
        category: ruleResult,
        confidence: RULES_CONFIDENCE,
        merchant: extractUpiMerchant(desc),
        reason: "Keyword rule match"
      };
      continue;
    }
    
    needsLlm.push(tx);
  }
  
  // 3. LLM Batch chunking
  if (needsLlm.length > 0 && config.GEMINI_API_KEY) {
    try {
      const BATCH_SIZE = 15;
      const ai = new GoogleGenAI({ apiKey: config.GEMINI_API_KEY });
      const cats = EXPENSE_CATEGORIES.join(", ");
      const sysPrompt = BATCH_CATEGORIZE_SYSTEM.replace("{categories}", cats);
      
      for (let i = 0; i < needsLlm.length; i += BATCH_SIZE) {
        const chunk = needsLlm.slice(i, i + BATCH_SIZE);
        const userContent = chunk.map(tx => `- id: ${tx.id}, description: ${tx.description}`).join("\\n");
        
        const response = await ai.models.generateContent({
          model: "gemini-2.5-flash",
          contents: [{ role: "user", parts: [{ text: sysPrompt }, { text: userContent }] }]
        });
        
        const parsed = extractJson(response.text || "");
        if (Array.isArray(parsed)) {
          for (const item of parsed) {
            if (!item.id || !chunk.find(c => c.id === item.id)) continue;
            results[item.id] = {
              id: item.id,
              category: CATEGORIES.includes(item.category) ? item.category : "Other",
              confidence: parseFloat(item.confidence || "0.5"),
              merchant: item.merchant || extractUpiMerchant(chunk.find(c => c.id === item.id)?.description || ""),
              reason: item.reason || "LLM batch"
            };
          }
        }
      }
    } catch (e) {
      console.warn("LLM batch classify failed:", e);
    }
  }
  
  // Fill remaining
  for (const tx of needsLlm) {
    if (!results[tx.id]) {
      results[tx.id] = {
        id: tx.id,
        category: "Other",
        confidence: 0.1,
        merchant: extractUpiMerchant(tx.description),
        reason: "Could not classify"
      };
    }
  }
  
  return transactions.map(tx => results[tx.id]);
}
