import { QueryClient } from "@tanstack/react-query";

// apiFetch (lib.js) already retries GETs through cold starts with its own
// backoff, so query-level retries are capped at 1 to avoid stacking retries
// on top of retries.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      gcTime: 10 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
