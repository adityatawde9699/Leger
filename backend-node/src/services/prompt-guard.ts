import { HttpError } from "../lib/http-error.js";

const INJECTION_PATTERNS = [
  /ignore\s+(previous|all|prior)\s+instructions?/i,
  /you\s+are\s+now\s+/i,
  /forget\s+everything/i,
  /disregard\s+(all|your|previous)/i,
  /system\s+prompt/i,
  /<\|.*?\|>/, // Llama/Qwen special tokens
  /\[INST\]/, // Legacy Mistral
  /###\s*system/i,
  /act\s+as\s+/i,
  /pretend\s+(you|to)\s+/i,
];

const MAX_INPUT_LENGTH = 1000;

export function sanitizeUserInput(text: string): string {
  if (!text) return "";
  if (text.length > MAX_INPUT_LENGTH) {
    throw new HttpError(400, `Question too long. Maximum ${MAX_INPUT_LENGTH} characters.`);
  }

  for (const pattern of INJECTION_PATTERNS) {
    if (pattern.test(text)) {
      throw new HttpError(400, "Invalid input detected.");
    }
  }

  return text.trim();
}

export function buildSafeMessages(
  systemPrompt: string,
  financialContext: string,
  userQuestion: string,
  history?: { role: string; content: string }[]
): { role: string; content: string }[] {
  const messages = [
    { role: "user", content: financialContext },
    { role: "assistant", content: "I have reviewed your financial data and I'm ready to help." }
  ];

  if (history && history.length > 0) {
    // Keep last 12
    const recent = history.slice(-12);
    messages.push(...recent);
  }

  messages.push({ role: "user", content: userQuestion });
  return messages;
}
