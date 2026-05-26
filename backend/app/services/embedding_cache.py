"""
Transaction Cache — lightweight local cache for transaction categorization.
Acts as a high-performance memory cache of transaction descriptions to categories
to prevent repeating LLM categorization for identical transactions.

This replaces the heavy sentence-transformers embedding cache to eliminate
unnecessary model downloads, startup latency, and memory consumption.
"""

import logging
import threading
from collections import OrderedDict
from typing import Any

logger = logging.getLogger("ledger.transaction_cache")

# ── Constants ────────────────────────────────────────────────────────────────
EMBEDDING_CACHE_SIZE = 2048   # Max number of descriptions to cache
SIMILARITY_THRESHOLD = 1.0    # Exact match similarity threshold


class EmbeddingCache:
    """
    Thread-safe LRU cache of description -> (category, confidence, merchant).
    Uses simple case-insensitive exact string match.
    """

    def __init__(self, maxsize: int = EMBEDDING_CACHE_SIZE):
        self.maxsize = maxsize
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._cache_lock = threading.Lock()

    def is_available(self) -> bool:
        """Returns True since the lightweight memory cache is always available."""
        return True

    def put(self, description: str, category: str, confidence: float, merchant: str | None = None) -> None:
        """Store a description's categorization result in the cache."""
        if not description:
            return

        key = description.lower().strip()
        entry = {
            "description": description,
            "category": category,
            "confidence": confidence,
            "merchant": merchant,
        }

        with self._cache_lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = entry
            if len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)

    def find_similar(self, description: str, threshold: float = SIMILARITY_THRESHOLD) -> dict[str, Any] | None:
        """
        Search cache for the description. Since embedding model is removed,
        this performs an exact match (case-insensitive, trimmed).
        """
        if not description:
            return None

        key = description.lower().strip()

        with self._cache_lock:
            match = self._cache.get(key)
            if match:
                self._cache.move_to_end(key)

        if match:
            logger.debug(
                "Transaction cache hit: '%s' (cat=%s)",
                description[:40], match["category"]
            )
            return {
                "category": match["category"],
                "confidence": match["confidence"],
                "merchant": match["merchant"],
                "similarity": 1.0,
                "source": "embedding_cache",
            }

        return None

    def get_stats(self) -> dict:
        """Returns cache statistics."""
        with self._cache_lock:
            return {
                "size": len(self._cache),
                "maxsize": self.maxsize,
                "model_loaded": True,
                "model_available": False,
            }


# Singleton instance — shared across the application
embedding_cache = EmbeddingCache()
