import { GoogleGenAI } from "@google/genai";
import OpenAI from "openai";
import { config } from "../config.js";

const TASK_TOKENS: Record<string, number> = {
  categorize: 150,
  insights: 400,
  advisor: 900,
  negotiate: 600,
  receipt: 300,
  default: 512,
};

type ChatMessage = { role: string; content: string };
type ProviderName = "gemini" | "openrouter" | "groq" | "cerebras" | "mistral";

type ProviderConfig = {
  name: ProviderName;
  available: boolean;
  model: string;
  baseURL?: string;
  extraHeaders?: Record<string, string>;
};

function toChatMessages(messages: ChatMessage[], system: string) {
  return [
    { role: "system" as const, content: system },
    ...messages.map((msg) => ({
      role: msg.role === "assistant" ? "assistant" as const : "user" as const,
      content: msg.content,
    })),
  ];
}

function providerErrorMessage(err: any): string {
  return err?.message || String(err) || "Unknown AI provider error";
}

function shouldFallback(err: any): boolean {
  const status = err?.status || err?.response?.status || err?.cause?.status;
  return status === 405 || status === 429 || status === 500 || status === 502 || status === 503 || status === 504;
}

function getProviders(): ProviderConfig[] {
  return [
    { name: "gemini", available: !!config.GEMINI_API_KEY, model: "gemini-2.5-flash" },
    {
      name: "openrouter",
      available: !!config.OPENROUTER_API_KEY,
      model: "openai/gpt-4o-mini",
      baseURL: "https://openrouter.ai/api/v1",
      extraHeaders: {
        "HTTP-Referer": "https://github.com/adityatawde9699/Leger",
        "X-Title": "Leger",
      },
    },
    {
      name: "groq",
      available: !!config.GROQ_API_KEY,
      model: "llama-3.1-70b-versatile",
      baseURL: "https://api.groq.com/openai/v1",
    },
    {
      name: "cerebras",
      available: !!config.CEREBRAS_API_KEY,
      model: "llama-3.3-70b",
      baseURL: "https://api.cerebras.ai/v1",
    },
    {
      name: "mistral",
      available: !!config.MISTRAL_API_KEY,
      model: "mistral-small-latest",
      baseURL: "https://api.mistral.ai/v1",
    },
  ];
}

function openAIClient(provider: ProviderConfig): OpenAI {
  const apiKey =
    provider.name === "openrouter"
      ? config.OPENROUTER_API_KEY
      : provider.name === "groq"
        ? config.GROQ_API_KEY
        : provider.name === "cerebras"
          ? config.CEREBRAS_API_KEY
          : config.MISTRAL_API_KEY;

  if (!apiKey) {
    throw new Error(`No API key configured for ${provider.name}`);
  }

  return new OpenAI({
    apiKey,
    baseURL: provider.baseURL,
    defaultHeaders: provider.extraHeaders,
  });
}

export class AIRouter {
  async *stream(
    system: string,
    messages: ChatMessage[],
    taskType: string = "default",
    maxTokens?: number
  ): AsyncGenerator<string, void, unknown> {
    const effectiveTokens = maxTokens || TASK_TOKENS[taskType] || 512;

    const providers = getProviders().filter((provider) => provider.available);
    if (providers.length === 0) {
      yield "\n[AI Error: No API keys configured. Set at least one AI provider key in .env]";
      return;
    }

    let lastError: any = null;
    for (const provider of providers) {
      let emitted = false;
      try {
        if (provider.name === "gemini") {
          const ai = new GoogleGenAI({ apiKey: config.GEMINI_API_KEY! });
          const formattedMessages = messages.map((msg) => ({
            role: msg.role === "user" ? "user" : "model",
            parts: [{ text: msg.content }],
          }));

          const responseStream = await ai.models.generateContentStream({
            model: provider.model,
            contents: formattedMessages,
            config: {
              systemInstruction: system,
              maxOutputTokens: effectiveTokens,
              temperature: 0.1,
            },
          });

          for await (const chunk of responseStream) {
            if (chunk.text) {
              emitted = true;
              yield chunk.text;
            }
          }
          return;
        }

        const client = openAIClient(provider);
        const responseStream = await client.chat.completions.create({
          model: provider.model,
          messages: toChatMessages(messages, system),
          max_tokens: effectiveTokens,
          temperature: 0.1,
          stream: true,
        });

        for await (const chunk of responseStream) {
          const delta = chunk.choices[0]?.delta?.content;
          if (delta) {
            emitted = true;
            yield delta;
          }
        }
        return;
      } catch (e: any) {
        console.error(`${provider.name} stream failed:`, e);
        lastError = e;
        if (emitted || !shouldFallback(e)) {
          break;
        }
      }
    }

    const message = providerErrorMessage(lastError);
    yield `\n[AI Error: Streaming failed - ${message}]`;
  }

  async generate(
    system: string,
    messages?: ChatMessage[],
    userMessage?: string,
    taskType: string = "default",
    maxTokens?: number
  ): Promise<string> {
    if (!messages) {
      messages = [{ role: "user", content: userMessage || "" }];
    }
    const effectiveTokens = maxTokens || TASK_TOKENS[taskType] || 512;

    const providers = getProviders().filter((provider) => provider.available);
    if (providers.length === 0) {
      throw new Error("No API keys configured");
    }

    let lastError: any = null;
    for (const provider of providers) {
      try {
        if (provider.name === "gemini") {
          const ai = new GoogleGenAI({ apiKey: config.GEMINI_API_KEY! });
          const formattedMessages = messages.map((msg) => ({
            role: msg.role === "user" ? "user" : "model",
            parts: [{ text: msg.content }],
          }));

          const response = await ai.models.generateContent({
            model: provider.model,
            contents: formattedMessages,
            config: {
              systemInstruction: system,
              maxOutputTokens: effectiveTokens,
              temperature: 0.1,
            },
          });

          return response.text || "";
        }

        const client = openAIClient(provider);
        const response = await client.chat.completions.create({
          model: provider.model,
          messages: toChatMessages(messages, system),
          max_tokens: effectiveTokens,
          temperature: 0.1,
        });

        return response.choices[0]?.message?.content || "";
      } catch (e: any) {
        console.error(`${provider.name} generate failed:`, e);
        lastError = e;
        if (!shouldFallback(e)) {
          break;
        }
      }
    }

    const message = providerErrorMessage(lastError);
    throw new Error(`Generation failed: ${message}`);
  }
}

export const aiRouter = new AIRouter();
