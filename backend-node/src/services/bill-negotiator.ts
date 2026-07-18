import { aiRouter } from "./ai-router.js";

const NEGOTIATOR_SYSTEM = `You are an expert bill negotiation advisor for Indian consumers.
Analyze the user's recurring payments and suggest specific, actionable negotiation strategies.

For each recurring payment, provide:
1. Whether it can be negotiated
2. Estimated savings potential (monthly INR amount)
3. A specific negotiation script/approach
4. Alternative services at lower cost

Return ONLY a JSON array:
[
  {
    "merchant": "...",
    "current_cost": 0.00,
    "negotiable": true/false,
    "savings_potential": 0.00,
    "strategy": "Step-by-step negotiation approach...",
    "alternatives": ["Alternative 1 at ₹X", "Alternative 2 at ₹Y"],
    "difficulty": "easy|medium|hard"
  }
]

JSON only. No commentary.`;

function ruleBasedAnalysis(payments: any[]): any[] {
  const results = [];
  
  const NEGOTIABLE_CATEGORIES: Record<string, any> = {
    "Subscriptions": {
      negotiable: true, savings_pct: 0.20,
      strategy: "Check for annual plans (typically 15-40% cheaper). Look for family/group plans. Use cashback portals for renewals.",
      alternatives: ["Annual plan", "Shared subscription", "Cashback portal renewal"],
      difficulty: "easy"
    },
    "Utilities": {
      negotiable: true, savings_pct: 0.10,
      strategy: "Compare tariff plans on your provider's website. Switch to time-of-use plans. Consider prepaid meters for electricity.",
      alternatives: ["Alternative provider", "Prepaid plan"],
      difficulty: "medium"
    },
    "Insurance": {
      negotiable: true, savings_pct: 0.15,
      strategy: "Compare premiums on PolicyBazaar. Increase deductible to lower premium. Ask for no-claim bonus discount.",
      alternatives: ["PolicyBazaar comparison", "Higher deductible plan"],
      difficulty: "medium"
    },
    "Health": {
      negotiable: true, savings_pct: 0.12,
      strategy: "Switch to generic medicines. Use Tata 1mg/PharmEasy for 20-40% discounts. Negotiate lab test rates.",
      alternatives: ["Tata 1mg", "PharmEasy", "Generic medicines"],
      difficulty: "easy"
    },
    "Housing": {
      negotiable: true, savings_pct: 0.08,
      strategy: "Negotiate rent during renewal citing market rates. Offer longer lease for discount. Maintain property well for leverage.",
      alternatives: ["Market rate negotiation", "Longer lease deal"],
      difficulty: "hard"
    }
  };

  for (const payment of payments) {
    const category = payment.category || "Other";
    const amount = parseFloat(payment.average_amount || payment.amount || "0");
    const merchant = payment.description || payment.merchant || "Unknown";
    
    const rule = NEGOTIABLE_CATEGORIES[category];
    if (rule) {
      results.push({
        merchant,
        current_cost: amount,
        negotiable: rule.negotiable,
        savings_potential: Number((amount * rule.savings_pct).toFixed(2)),
        strategy: rule.strategy,
        alternatives: rule.alternatives || [],
        difficulty: rule.difficulty
      });
    } else if (amount > 500) {
      results.push({
        merchant,
        current_cost: amount,
        negotiable: false,
        savings_potential: 0,
        strategy: "Review if this service is still needed. Consider downgrading to a basic plan.",
        alternatives: [],
        difficulty: "easy"
      });
    }
  }
  
  return results;
}

export async function analyzeBills(recurringPayments: any[]): Promise<any[]> {
  if (!recurringPayments || recurringPayments.length === 0) return [];
  
  try {
    const prompt = `Analyze these recurring payments from an Indian user and suggest negotiations:\n\n${JSON.stringify(recurringPayments, null, 2)}\n\nFocus on subscriptions, utilities, insurance, and services where negotiation or switching is viable.`;
    const response = await aiRouter.generate(NEGOTIATOR_SYSTEM, undefined, prompt, "negotiate");
    
    let parsed;
    try {
      parsed = JSON.parse(response);
    } catch (e) {
      const match = response.match(/\[[\s\S]*\]/);
      if (match) parsed = JSON.parse(match[0]);
    }
    
    if (Array.isArray(parsed)) return parsed;
  } catch (e) {
    console.warn("LLM negotiator failed, using rules:", e);
  }
  
  return ruleBasedAnalysis(recurringPayments);
}
