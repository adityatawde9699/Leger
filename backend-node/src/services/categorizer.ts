export const CATEGORIES = [
  "Housing", "Groceries", "Transport", "Dining", "Subscriptions",
  "Shopping", "Health", "Utilities", "Entertainment", "Education",
  "Insurance", "Investments", "Transfers", "Taxes", "Fees", "Other",
  "Salary", "Freelance"
];

export const EXPENSE_CATEGORIES = CATEGORIES.filter(c => !["Salary", "Freelance"].includes(c));
export const INCOME_CATEGORIES = ["Salary", "Freelance", "Other"];

const RULES: [string, string][] = [
  ["salary", "Salary"], ["payroll", "Salary"], ["ctc", "Salary"], ["stipend", "Salary"],
  ["freelance", "Freelance"], ["upwork", "Freelance"], ["fiverr", "Freelance"], ["toptal", "Freelance"],
  ["zerodha", "Investments"], ["groww", "Investments"], ["kuvera", "Investments"], ["coin", "Investments"],
  ["nse", "Investments"], ["bse", "Investments"], ["ipo", "Investments"], ["mutual fund", "Investments"],
  ["sip", "Investments"], ["demat", "Investments"], ["smallcase", "Investments"], ["angel one", "Investments"],
  ["angel broking", "Investments"], ["dhan", "Investments"], ["5paisa", "Investments"], ["upstox", "Investments"],
  ["fyers", "Investments"], ["motilaloswal", "Investments"], ["icicidirect", "Investments"],
  ["hdfc securit", "Investments"], ["sbisec", "Investments"],
  ["insurance", "Insurance"], ["lic ", "Insurance"], ["policybazaar", "Insurance"], ["premium", "Insurance"],
  ["term plan", "Insurance"], ["health insur", "Insurance"], ["bajaj allianz", "Insurance"],
  ["star health", "Insurance"], ["hdfc life", "Insurance"], ["icici lombard", "Insurance"],
  ["new india assu", "Insurance"], ["tata aig", "Insurance"], ["niva bupa", "Insurance"],
  ["income tax", "Taxes"], ["tds", "Taxes"], ["gst", "Taxes"], ["advance tax", "Taxes"],
  ["nsdl", "Taxes"], ["traces", "Taxes"], ["itr", "Taxes"],
  ["neft", "Transfers"], ["rtgs", "Transfers"], ["imps", "Transfers"], ["self transfer", "Transfers"], ["own account", "Transfers"],
  ["bank charge", "Fees"], ["processing fee", "Fees"], ["annual fee", "Fees"], ["late fee", "Fees"],
  ["penalty", "Fees"], ["bank fee", "Fees"], ["service charge", "Fees"], ["atm charge", "Fees"], ["convenience fee", "Fees"],
  ["college", "Education"], ["university", "Education"], ["school", "Education"], ["tuition", "Education"],
  ["udemy", "Education"], ["coursera", "Education"], ["byju", "Education"], ["unacademy", "Education"],
  ["vedantu", "Education"], ["toppr", "Education"], ["khan academy", "Education"], ["edx", "Education"],
  ["skillshare", "Education"], ["duolingo", "Education"], ["exam fee", "Education"], ["books", "Education"], ["stationery", "Education"],
  ["electricity", "Utilities"], ["airtel", "Utilities"], ["jio", "Utilities"], ["bsnl", "Utilities"],
  ["broadband", "Utilities"], ["recharge", "Utilities"], ["rech", "Utilities"], ["vi p", "Utilities"],
  ["billpay", "Utilities"], ["utility", "Utilities"], ["utilities", "Utilities"], ["dth", "Utilities"],
  ["water bill", "Utilities"], ["gas bill", "Utilities"], ["ebzauranga", "Utilities"], ["tata sky", "Utilities"],
  ["dish tv", "Utilities"], ["sun direct", "Utilities"], ["mahadiscom", "Utilities"], ["bescom", "Utilities"],
  ["tpddl", "Utilities"], ["msedcl", "Utilities"], ["piped gas", "Utilities"], ["indane", "Utilities"], ["mahanagar gas", "Utilities"],
  ["netflix", "Subscriptions"], ["spotify", "Subscriptions"], ["hotstar", "Subscriptions"], ["prime video", "Subscriptions"],
  ["googleclou", "Subscriptions"], ["google cloud", "Subscriptions"], ["playstore", "Subscriptions"],
  ["dashreels", "Subscriptions"], ["github", "Subscriptions"], ["cursor", "Subscriptions"], ["youtube", "Subscriptions"],
  ["zee5", "Subscriptions"], ["sonyliv", "Subscriptions"], ["jiocinema", "Subscriptions"], ["mx player", "Subscriptions"],
  ["apple music", "Subscriptions"], ["gaana", "Subscriptions"], ["jiosaavn", "Subscriptions"], ["microsoft 365", "Subscriptions"],
  ["adobe", "Subscriptions"], ["canva", "Subscriptions"], ["notion", "Subscriptions"], ["slack", "Subscriptions"],
  ["zoom", "Subscriptions"], ["aws", "Subscriptions"], ["azure", "Subscriptions"], ["cloudflare", "Subscriptions"],
  ["vercel", "Subscriptions"], ["figma", "Subscriptions"],
  ["uber", "Transport"], ["ola", "Transport"], ["rapido", "Transport"], ["metro", "Transport"],
  ["petrol", "Transport"], ["chalo", "Transport"], ["irctc", "Transport"], ["confirmtkt", "Transport"],
  ["confirm tkt", "Transport"], ["railway", "Transport"], ["flight", "Transport"], ["cab", "Transport"],
  ["auto", "Transport"], ["toll", "Transport"], ["fastag", "Transport"], ["bus", "Transport"],
  ["train", "Transport"], ["travel", "Transport"], ["indian r", "Transport"], ["indigo", "Transport"],
  ["spicejet", "Transport"], ["air india", "Transport"], ["makemytrip", "Transport"], ["goibibo", "Transport"],
  ["cleartrip", "Transport"], ["redbus", "Transport"], ["paytm travel", "Transport"], ["park+", "Transport"],
  ["parkplus", "Transport"], ["diesel", "Transport"],
  ["pharmacy", "Health"], ["medical", "Health"], ["hospital", "Health"], ["clinic", "Health"],
  ["dental", "Health"], ["doctor", "Health"], ["medicine", "Health"], ["druggist", "Health"],
  ["chemist", "Health"], ["wellness", "Health"], ["healthcare", "Health"], ["tata 1mg", "Health"],
  ["apollo pharm", "Health"], ["pharmeasy", "Health"], ["netmeds", "Health"], ["cult.fit", "Health"],
  ["cult fit", "Health"], ["gym", "Health"], ["yoga", "Health"],
  ["swiggy", "Dining"], ["zomato", "Dining"], ["restaurant", "Dining"], ["cafe", "Dining"],
  ["hotel", "Dining"], ["domino", "Dining"], ["dimono", "Dining"], ["pizza", "Dining"],
  ["mcdonald", "Dining"], ["mc donalds", "Dining"], ["kfc", "Dining"], ["burger king", "Dining"],
  ["burger k", "Dining"], ["subway", "Dining"], ["starbucks", "Dining"], ["dunkin", "Dining"],
  ["sf food", "Dining"], ["sana fat", "Dining"], ["shiraaz", "Dining"], ["koyla", "Dining"],
  ["aarambh", "Dining"], ["treat me", "Dining"], ["cool bev", "Dining"], ["orange j", "Dining"],
  ["roll n r", "Dining"], ["raps bir", "Dining"], ["bakery", "Dining"], ["sweets", "Dining"],
  ["dhaba", "Dining"], ["kitchen", "Dining"], ["caterers", "Dining"], ["kabab", "Dining"],
  ["eats", "Dining"], ["bites", "Dining"], ["food", "Dining"], ["lucky juice", "Dining"],
  ["dosa plaza", "Dining"], ["bholes r", "Dining"], ["bholes restaurant", "Dining"], ["tirupati", "Dining"],
  ["gaavaran", "Dining"], ["saikripa", "Dining"], ["maa durg", "Dining"], ["shree sa", "Dining"],
  ["shri swa", "Dining"], ["kalyani", "Dining"], ["jijau me", "Dining"], ["suprassa", "Dining"],
  ["mess", "Dining"], ["canteen", "Dining"], ["cateen", "Dining"], ["mgm spor", "Dining"],
  ["gajanan", "Dining"], ["biryani", "Dining"], ["haldiram", "Dining"], ["barbeque", "Dining"],
  ["barbeque nation", "Dining"], ["chai point", "Dining"], ["chaayos", "Dining"], ["box8", "Dining"],
  ["faasos", "Dining"], ["freshmenu", "Dining"],
  ["blinkit", "Groceries"], ["zepto", "Groceries"], ["instamart", "Groceries"], ["dunzo", "Groceries"],
  ["dmart", "Groceries"], ["reliance fresh", "Groceries"], ["bigbasket", "Groceries"], ["milk", "Groceries"],
  ["dairy", "Groceries"], ["groceries", "Groceries"], ["grocery", "Groceries"], ["supermarket", "Groceries"],
  ["mart", "Groceries"], ["neel kir", "Groceries"], ["tarte ki", "Groceries"], ["shree ga", "Groceries"],
  ["kirana", "Groceries"], ["nature's basket", "Groceries"], ["nature basket", "Groceries"],
  ["smart bazaar", "Groceries"], ["more megastore", "Groceries"], ["easyday", "Groceries"], ["spencers", "Groceries"],
  ["movie", "Entertainment"], ["bookmyshow", "Entertainment"], ["district", "Entertainment"],
  ["sports", "Entertainment"], ["cinema", "Entertainment"], ["theater", "Entertainment"],
  ["insider", "Entertainment"], ["pvr", "Entertainment"], ["inox", "Entertainment"], ["carnival", "Entertainment"],
  ["amusement", "Entertainment"], ["theme park", "Entertainment"], ["gaming", "Entertainment"],
  ["steam", "Entertainment"], ["playstation", "Entertainment"], ["xbox", "Entertainment"], ["nintendo", "Entertainment"],
  ["rent", "Housing"], ["maintenance", "Housing"], ["society", "Housing"], ["flat", "Housing"],
  ["apartment", "Housing"], ["housing", "Housing"], ["landlord", "Housing"],
  ["amazon", "Shopping"], ["flipkart", "Shopping"], ["myntra", "Shopping"], ["croma", "Shopping"],
  ["mr diy", "Shopping"], ["ekart", "Shopping"], ["shopping", "Shopping"], ["clothing", "Shopping"],
  ["dress", "Shopping"], ["mall", "Shopping"], ["fashion", "Shopping"], ["boutique", "Shopping"],
  ["retail", "Shopping"], ["footwear", "Shopping"], ["shoes", "Shopping"], ["prozone", "Shopping"],
  ["samsung", "Shopping"], ["saketboo", "Shopping"], ["appaji k", "Shopping"], ["amazonpayr", "Shopping"],
  ["a mazonpayr", "Shopping"], ["nykaa", "Shopping"], ["meesho", "Shopping"], ["snapdeal", "Shopping"],
  ["ajio", "Shopping"], ["tatacliq", "Shopping"], ["reliance digit", "Shopping"], ["vijay sales", "Shopping"],
  ["decathlon", "Shopping"], ["ikea", "Shopping"], ["urban ladder", "Shopping"], ["pepperfry", "Shopping"]
];

const UPI_GENERIC_RE = /\\b(upi|ybl|oksbi|okaxis|okhdfcbank|paytm|gpay|phonepe|bhim)\\b/i;
const UPI_MERCHANT_RE = /UPI\/(?:DR|CR)\/[^\/]+\/([^\/]+)/i;
const VIA_MERCHANT_RE = /(?:To|From)\s+([A-Za-z][A-Za-z0-9\s&'.]+?)\s+via/i;
const NEFT_MERCHANT_RE = /(?:NEFT|RTGS|IMPS)[/-]?[A-Z0-9]*\/([^\/]{3,40})/i;

export function extractUpiMerchant(description: string): string | null {
  const text = description || "";
  let m = UPI_MERCHANT_RE.exec(text);
  if (m) {
    const merchant = m[1].replace(/\\s+/g, " ").replace(/^[ .-/]+|[ .-/]+$/g, "");
    if (merchant) return merchant;
  }
  
  m = VIA_MERCHANT_RE.exec(text);
  if (m) {
    const merchant = m[1].trim();
    if (merchant.length >= 3) return merchant;
  }
  
  m = NEFT_MERCHANT_RE.exec(text);
  if (m) {
    const merchant = m[1].trim();
    if (merchant.length >= 3) return merchant;
  }
  
  return null;
}

export function isGenericUpi(description: string, category: string): boolean {
  const text = description || "";
  const merchant = extractUpiMerchant(text);
  return category === "Other" && (UPI_GENERIC_RE.test(text) || !!merchant);
}

export function ruleCategorize(description: string, txType: string = "expense"): string {
  const text = (description || "").toLowerCase();
  
  for (const [needle, category] of RULES) {
    if (text.includes(needle)) return category;
  }
  
  const spacelessText = text.replace(/\\s/g, "");
  for (const [needle, category] of RULES) {
    const needleSpaceless = needle.replace(/\\s/g, "");
    if (needleSpaceless.length >= 5 && spacelessText.includes(needleSpaceless)) return category;
  }
  
  const merchant = extractUpiMerchant(description);
  if (merchant) {
    const merchantText = merchant.toLowerCase();
    for (const [needle, category] of RULES) {
      if (merchantText.includes(needle)) return category;
    }
    const merchantSpaceless = merchantText.replace(/\\s/g, "");
    for (const [needle, category] of RULES) {
      const needleSpaceless = needle.replace(/\\s/g, "");
      if (needleSpaceless.length >= 4 && merchantSpaceless.includes(needleSpaceless)) return category;
    }
  }
  
  return txType === "expense" ? "Other" : "Salary";
}
