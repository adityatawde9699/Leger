export function computeGst(amount: number, category: string, merchant: string | null): any {
  let rate = 0.0;
  let hsn = null;
  const lowerCat = category.toLowerCase();
  
  if (["dining", "restaurant", "food"].includes(lowerCat)) { rate = 5.0; hsn = "9963"; }
  else if (["shopping", "electronics", "gadgets"].includes(lowerCat)) { rate = 18.0; hsn = "85"; }
  else if (["health", "medical", "pharmacy"].includes(lowerCat)) { rate = 12.0; hsn = "30"; }
  else if (["transport", "fuel", "travel"].includes(lowerCat)) { rate = 5.0; hsn = "9964"; }
  else if (["housing", "rent"].includes(lowerCat)) { rate = 0.0; hsn = "9972"; }
  else if (["entertainment", "movies"].includes(lowerCat)) { rate = 18.0; hsn = "9996"; }
  else if (["groceries", "supermarket"].includes(lowerCat)) { rate = 5.0; hsn = "21"; }
  else if (["subscriptions", "software", "digital"].includes(lowerCat)) { rate = 18.0; hsn = "9973"; }
  
  const baseAmount = amount / (1 + rate / 100);
  const gstAmount = amount - baseAmount;
  
  return {
    gst_rate: rate,
    base_amount: Number(baseAmount.toFixed(2)),
    gst_amount: Number(gstAmount.toFixed(2)),
    hsn_code: hsn
  };
}

export function exportCsv(transactions: any[]): string {
  const headers = ["Date", "Type", "Category", "Amount", "Description", "Merchant", "Source", "Tags", "Notes", "GST Rate", "GST Amount", "HSN/SAC Code"];
  
  let csv = headers.join(",") + "\\n";
  for (const tx of transactions) {
    const amt = parseFloat(tx.amount || "0");
    const gst = computeGst(amt, tx.category, tx.merchantNormalized);
    const row = [
      tx.date,
      tx.type,
      tx.category,
      amt.toFixed(2),
      `"${(tx.description || "").replace(/"/g, '""')}"`,
      `"${(tx.merchantNormalized || "").replace(/"/g, '""')}"`,
      tx.source,
      `"${(tx.tags || "").replace(/"/g, '""')}"`,
      `"${(tx.notes || "").replace(/"/g, '""')}"`,
      gst.gst_rate,
      gst.gst_amount,
      gst.hsn_code || ""
    ];
    csv += row.join(",") + "\\n";
  }
  
  return csv;
}

export function exportJson(transactions: any[]): string {
  const rows = [];
  for (const tx of transactions) {
    const amt = parseFloat(tx.amount || "0");
    const gst = computeGst(amt, tx.category, tx.merchantNormalized);
    rows.push({
      id: tx.id,
      date: tx.date,
      type: tx.type,
      category: tx.category,
      amount: amt,
      description: tx.description,
      merchant: tx.merchantNormalized,
      source: tx.source,
      tags: tx.tags,
      notes: tx.notes,
      gst: {
        rate: gst.gst_rate,
        amount: gst.gst_amount,
        base_amount: gst.base_amount,
        hsn_code: gst.hsn_code
      },
      created_at: tx.createdAt
    });
  }
  return JSON.stringify({ transactions: rows, count: rows.length }, null, 2);
}

export function exportTallyXml(transactions: any[]): string {
  let xml = `<?xml version="1.0" encoding="utf-8"?>\\n<ENVELOPE>\\n  <HEADER>\\n    <TALLYREQUEST>Import Data</TALLYREQUEST>\\n  </HEADER>\\n  <BODY>\\n    <IMPORTDATA>\\n      <REQUESTDESC>\\n        <REPORTNAME>Vouchers</REPORTNAME>\\n      </REQUESTDESC>\\n      <REQUESTDATA>\\n`;
  
  for (const tx of transactions) {
    const amt = parseFloat(tx.amount || "0");
    const gst = computeGst(amt, tx.category, tx.merchantNormalized);
    const vchType = tx.type === "expense" ? "Payment" : "Receipt";
    const dateFormatted = tx.date.replace(/-/g, ""); // YYYYMMDD
    const party = (tx.merchantNormalized || tx.description || "Unknown").substring(0, 50).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const narration = (tx.description || "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const category = tx.category.replace(/&/g, "&amp;").replace(/</g, "&lt;");
    
    xml += `        <TALLYMESSAGE xmlns:UDF="TallyUDF">\\n          <VOUCHER VCHTYPE="${vchType}">\\n            <DATE>${dateFormatted}</DATE>\\n            <NARRATION>${narration}</NARRATION>\\n            <VOUCHERTYPENAME>${vchType}</VOUCHERTYPENAME>\\n            <PARTYLEDGERNAME>${party}</PARTYLEDGERNAME>\\n`;
    xml += `            <ALLLEDGERENTRIES.LIST>\\n              <LEDGERNAME>${category}</LEDGERNAME>\\n              <ISDEEMEDPOSITIVE>${tx.type === "expense" ? "Yes" : "No"}</ISDEEMEDPOSITIVE>\\n              <AMOUNT>${amt}</AMOUNT>\\n            </ALLLEDGERENTRIES.LIST>\\n`;
    
    if (gst.gst_rate > 0) {
      xml += `            <ALLLEDGERENTRIES.LIST>\\n              <LEDGERNAME>GST @ ${gst.gst_rate}%</LEDGERNAME>\\n              <ISDEEMEDPOSITIVE>${tx.type === "expense" ? "Yes" : "No"}</ISDEEMEDPOSITIVE>\\n              <AMOUNT>${gst.gst_amount}</AMOUNT>\\n            </ALLLEDGERENTRIES.LIST>\\n`;
    }
    
    xml += `          </VOUCHER>\\n        </TALLYMESSAGE>\\n`;
  }
  
  xml += `      </REQUESTDATA>\\n    </IMPORTDATA>\\n  </BODY>\\n</ENVELOPE>`;
  return xml;
}
