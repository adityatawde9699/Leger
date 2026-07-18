import { GoogleGenAI } from "@google/genai";
import { config } from "../config.js";

const EXTRACTION_PROMPT = `Extract the following information from this receipt image:
- merchant_name: string
- date: YYYY-MM-DD (if visible, else null)
- total_amount: number (the total/grand total)
- items: list of {name: string, price: number} (top 5 items max)
- category: one of [Dining, Groceries, Shopping, Health, Transport, Utilities, Entertainment, Subscriptions, Housing, Other]

Return ONLY valid JSON. No explanation.`;

export async function parseReceiptImage(imageBytes: Buffer): Promise<any | null> {
  if (!config.GEMINI_API_KEY) {
    console.warn("No Gemini API key found. Cannot parse receipt image.");
    return null;
  }
  
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
                data: imageBytes.toString("base64"),
                mimeType: "image/jpeg"
              }
            },
            { text: EXTRACTION_PROMPT }
          ]
        }
      ]
    });
    
    let text = response.text || "";
    text = text.replace(/^\\s*\\x60\\x60\\x60(json)?/m, "").replace(/\\x60\\x60\\x60\\s*$/m, "").trim();
    
    const parsedData = JSON.parse(text);
    const amount = parsedData.total_amount;
    if (!amount || parseFloat(amount) <= 0) return null;
    
    const merchant = parsedData.merchant_name || "Unknown";
    const category = parsedData.category || "Other";
    
    return {
      description: merchant,
      amount: parseFloat(amount).toFixed(2),
      category,
      date: parsedData.date || new Date().toISOString().split("T")[0],
      type: "expense",
      source: "receipt",
      items: parsedData.items || [],
      merchant_normalized: merchant,
      confidence: 0.8
    };
  } catch (e) {
    console.error("Gemini receipt extraction failed:", e);
    return null;
  }
}
