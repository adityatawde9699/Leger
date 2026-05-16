import React from "react";
import { apiFetch, money } from "../lib";
import { useToast } from "../components/ui";
import {
  Download, FileText, FileJson, FileSpreadsheet,
  Receipt, TrendingUp, IndianRupee, Percent,
} from "lucide-react";

export default function ExportGST() {
  const toast = useToast();
  const [gstReport, setGstReport] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [exporting, setExporting] = React.useState(null);

  React.useEffect(() => {
    apiFetch("/gst/report")
      .then(setGstReport)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function handleExport(fmt) {
    setExporting(fmt);
    try {
      const res = await fetch(`http://127.0.0.1:8000/export/${fmt}`, {
        headers: { Authorization: `Bearer dev-user` },
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Export failed" }));
        throw new Error(err.detail);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ledger_export.${fmt === "tally" ? "xml" : fmt}`;
      a.click();
      URL.revokeObjectURL(url);
      toast(`Exported as ${fmt.toUpperCase()}`, "success");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setExporting(null);
    }
  }

  const slabs = gstReport?.slabs || [];
  const hasData = slabs.length > 0;

  return (
    <div className="view-export">
      <div className="page-title-block">
        <h1 className="page-title">Export & GST</h1>
        <p className="page-subtitle">Download your data or view GST breakdown</p>
      </div>

      {/* Export buttons */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="form-section-title">Export Transactions</div>
        <p style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 20 }}>
          Download all your transactions in your preferred format.
        </p>
        <div className="export-grid">
          <button
            className="export-card card"
            onClick={() => handleExport("csv")}
            disabled={exporting === "csv"}
          >
            <FileSpreadsheet size={24} className="export-icon csv" />
            <div className="export-card-name">CSV</div>
            <div className="export-card-desc">Spreadsheet format</div>
            {exporting === "csv" ? "Exporting…" : <Download size={14} />}
          </button>
          <button
            className="export-card card"
            onClick={() => handleExport("json")}
            disabled={exporting === "json"}
          >
            <FileJson size={24} className="export-icon json" />
            <div className="export-card-name">JSON</div>
            <div className="export-card-desc">Developer format</div>
            {exporting === "json" ? "Exporting…" : <Download size={14} />}
          </button>
          <button
            className="export-card card"
            onClick={() => handleExport("tally")}
            disabled={exporting === "tally"}
          >
            <FileText size={24} className="export-icon tally" />
            <div className="export-card-name">Tally XML</div>
            <div className="export-card-desc">Tally Prime / ERP 9</div>
            {exporting === "tally" ? "Exporting…" : <Download size={14} />}
          </button>
        </div>
      </div>

      {/* GST Report */}
      <div className="card">
        <div className="form-section-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Receipt size={18} /> GST Report
        </div>
        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[1,2,3].map(i => <div key={i} className="skeleton" style={{ height: 40, borderRadius: 8 }} />)}
          </div>
        ) : !hasData ? (
          <div className="empty-state">
            <div className="empty-state-icon">📋</div>
            <div className="empty-state-title">No GST data</div>
            <div className="empty-state-sub">Add transactions to see your GST breakdown</div>
          </div>
        ) : (
          <>
            {/* Summary cards */}
            <div className="account-grid" style={{ marginBottom: 20 }}>
              <div className="card account-card">
                <div className="account-card-header">
                  <span className="account-label">Base Amount</span>
                  <IndianRupee size={18} className="icon-accent" />
                </div>
                <div className="account-amount">{money(gstReport.total_base)}</div>
                <div className="account-change muted">Excl. GST</div>
              </div>
              <div className="card account-card">
                <div className="account-card-header">
                  <span className="account-label">Total GST</span>
                  <Percent size={18} className="icon-negative" />
                </div>
                <div className="account-amount">{money(gstReport.total_gst)}</div>
                <div className="account-change negative">Tax paid</div>
              </div>
              <div className="card account-card">
                <div className="account-card-header">
                  <span className="account-label">Grand Total</span>
                  <TrendingUp size={18} className="icon-positive" />
                </div>
                <div className="account-amount">{money(gstReport.total_with_gst)}</div>
                <div className="account-change positive">Incl. GST</div>
              </div>
            </div>

            {/* Slab table */}
            <div className="gst-table-wrap">
              <table className="gst-table">
                <thead>
                  <tr>
                    <th>GST Slab</th>
                    <th>Transactions</th>
                    <th>Base Amount</th>
                    <th>GST Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {slabs.map((slab) => (
                    <tr key={slab.rate}>
                      <td>
                        <span className={`gst-slab-badge slab-${slab.rate === 0 ? "exempt" : slab.rate <= 5 ? "low" : slab.rate <= 18 ? "mid" : "high"}`}>
                          {slab.rate === 0 ? "Exempt" : `${slab.rate}%`}
                        </span>
                      </td>
                      <td>{slab.count}</td>
                      <td>{money(slab.base_total)}</td>
                      <td>{money(slab.gst_total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
