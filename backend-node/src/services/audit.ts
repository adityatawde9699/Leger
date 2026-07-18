import fs from "fs";
import path from "path";

// Simple file-based audit logger
export function logAudit(action: string, userId: string, details: any): void {
  const timestamp = new Date().toISOString();
  const logEntry = JSON.stringify({ timestamp, action, userId, details });
  
  try {
    const logDir = path.resolve(process.cwd(), "logs");
    if (!fs.existsSync(logDir)) {
      fs.mkdirSync(logDir, { recursive: true });
    }
    fs.appendFileSync(path.join(logDir, "audit.log"), logEntry + "\\n");
  } catch (e) {
    console.error("Failed to write audit log:", e);
  }
}
