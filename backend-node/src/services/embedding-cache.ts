export class EmbeddingCache {
  // Simple stub for node since we don't have LanceDB configured in the Node project yet
  // In the future this should be backed by a vector database.
  
  isAvailable(): boolean {
    return false;
  }
  
  findSimilar(description: string): any {
    return null;
  }
  
  put(description: string, category: string, confidence: number, merchant: string | null): void {
    // No-op
  }
}

export const embeddingCache = new EmbeddingCache();
