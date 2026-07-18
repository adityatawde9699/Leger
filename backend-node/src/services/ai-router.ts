import { GoogleGenAI } from "@google/genai";
import { config } from "../config.js";

const TASK_TOKENS: Record<string, number> = {
  categorize: 150,
  insights: 400,
  advisor: 900,
  negotiate: 600,
  receipt: 300,
  default: 512,
};

export class AIRouter {
  async *stream(
    system: string,
    messages: { role: string; content: string }[],
    taskType: string = "default",
    maxTokens?: number
  ): AsyncGenerator<string, void, unknown> {
    const effectiveTokens = maxTokens || TASK_TOKENS[taskType] || 512;
    
    if (!config.GEMINI_API_KEY) {
      yield "\n[AI Error: No API keys configured. Set GEMINI_API_KEY in .env]";
      return;
    }

    try {
      const ai = new GoogleGenAI({ apiKey: config.GEMINI_API_KEY });
      
      const formattedMessages = messages.map(msg => ({
        role: msg.role === "user" ? "user" : "model",
        parts: [{ text: msg.content }]
      }));

      const responseStream = await ai.models.generateContentStream({
        model: "gemini-2.0-flash",
        contents: formattedMessages,
        config: {
          systemInstruction: system,
          maxOutputTokens: effectiveTokens,
          temperature: 0.1
        }
      });

      for await (const chunk of responseStream) {
        if (chunk.text) {
          yield chunk.text;
        }
      }
    } catch (e: any) {
      console.error("Gemini stream failed:", e);
      yield `\n[AI Error: Streaming failed - ${e.message}]`;
    }
  }

  async generate(
    system: string,
    messages?: { role: string; content: string }[],
    userMessage?: string,
    taskType: string = "default",
    maxTokens?: number
  ): Promise<string> {
    if (!messages) {
      messages = [{ role: "user", content: userMessage || "" }];
    }
    const effectiveTokens = maxTokens || TASK_TOKENS[taskType] || 512;

    if (!config.GEMINI_API_KEY) {
      throw new Error("No API keys configured");
    }

    try {
      const ai = new GoogleGenAI({ apiKey: config.GEMINI_API_KEY });
      
      const formattedMessages = messages.map(msg => ({
        role: msg.role === "user" ? "user" : "model",
        parts: [{ text: msg.content }]
      }));

      const response = await ai.models.generateContent({
        model: "gemini-2.0-flash",
        contents: formattedMessages,
        config: {
          systemInstruction: system,
          maxOutputTokens: effectiveTokens,
          temperature: 0.1
        }
      });

      return response.text || "";
    } catch (e: any) {
      console.error("Gemini generate failed:", e);
      throw new Error(`Generation failed: ${e.message}`);
    }
  }
}

export const aiRouter = new AIRouter();
