type CacheEntry = {
  description: string;
  normalizedDescription: string;
  tokens: Set<string>;
  category: string;
  confidence: number;
  merchant: string | null;
  updatedAt: number;
};

type SimilarMatch = {
  description: string;
  category: string;
  confidence: number;
  merchant: string | null;
  similarity: number;
};

const MAX_ENTRIES = 1000;
const MIN_SIMILARITY = 0.58;

function normalize(description: string): string {
  return (description || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

function tokenize(normalizedDescription: string): Set<string> {
  return new Set(
    normalizedDescription
      .split(" ")
      .map((token) => token.trim())
      .filter((token) => token.length >= 2),
  );
}

function similarityScore(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;

  let intersection = 0;
  for (const token of a) {
    if (b.has(token)) intersection += 1;
  }

  const union = new Set([...a, ...b]).size;
  return union === 0 ? 0 : intersection / union;
}

export class EmbeddingCache {
  private entries = new Map<string, CacheEntry>();

  isAvailable(): boolean {
    return this.entries.size > 0;
  }

  clear(): void {
    this.entries.clear();
  }

  findSimilar(description: string): SimilarMatch | null {
    const normalizedDescription = normalize(description);
    if (!normalizedDescription) return null;

    const queryTokens = tokenize(normalizedDescription);
    let bestMatch: SimilarMatch | null = null;

    for (const entry of this.entries.values()) {
      const exactMatch = entry.normalizedDescription === normalizedDescription;
      const similarity = exactMatch ? 1 : similarityScore(queryTokens, entry.tokens);

      if (similarity < MIN_SIMILARITY) continue;
      if (!bestMatch || similarity > bestMatch.similarity) {
        bestMatch = {
          description: entry.description,
          category: entry.category,
          confidence: entry.confidence,
          merchant: entry.merchant,
          similarity,
        };
      }
    }

    return bestMatch;
  }

  put(description: string, category: string, confidence: number, merchant: string | null): void {
    const normalizedDescription = normalize(description);
    if (!normalizedDescription) return;

    this.entries.set(normalizedDescription, {
      description,
      normalizedDescription,
      tokens: tokenize(normalizedDescription),
      category,
      confidence,
      merchant,
      updatedAt: Date.now(),
    });

    if (this.entries.size > MAX_ENTRIES) {
      const oldest = [...this.entries.entries()].sort((a, b) => a[1].updatedAt - b[1].updatedAt)[0];
      if (oldest) this.entries.delete(oldest[0]);
    }
  }
}

export const embeddingCache = new EmbeddingCache();
