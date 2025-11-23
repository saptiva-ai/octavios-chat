"use client";

import { ReactNode, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CanvasProvider } from "@/context/CanvasContext";

/**
 * React Query configuration for the application
 *
 * Optimized settings:
 * - staleTime: 60s (data fresh for 1 minute before refetch)
 * - refetchOnWindowFocus: false (prevents unnecessary refetches)
 * - retry: 1 (single retry on failure)
 * - refetchOnMount: false (uses cached data on mount if available)
 */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000, // 60 seconds
            refetchOnWindowFocus: false,
            retry: 1,
            refetchOnMount: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <CanvasProvider>{children}</CanvasProvider>
    </QueryClientProvider>
  );
}
