/**
 * BankChartSkeleton - Loading skeleton for bank chart
 *
 * Displays animated placeholders while chart data is loading.
 */

export function BankChartSkeleton() {
  return (
    <div className="flex h-full flex-col space-y-4 animate-pulse">
      {/* Metadata Header Skeleton */}
      <div className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-4">
        <div className="flex items-center gap-2">
          <div className="h-5 w-5 rounded bg-white/10" />
          <div className="h-6 w-32 rounded bg-white/10" />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded bg-white/5" />
            <div className="h-3 w-40 rounded bg-white/5" />
          </div>
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded bg-white/5" />
            <div className="h-3 w-32 rounded bg-white/5" />
          </div>
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded bg-white/5" />
            <div className="h-3 w-36 rounded bg-white/5" />
          </div>
        </div>
      </div>

      {/* Tabs Skeleton */}
      <div className="flex gap-2 border-b border-white/10">
        <div className="h-10 w-24 rounded-t bg-white/5" />
        <div className="h-10 w-28 rounded-t bg-white/5" />
        <div className="h-10 w-32 rounded-t bg-white/5" />
      </div>

      {/* Chart Content Skeleton */}
      <div className="flex-1 rounded-lg border border-white/10 bg-white/5 p-4">
        <div className="space-y-3">
          {/* Chart title */}
          <div className="h-6 w-48 rounded bg-white/10" />

          {/* Chart area */}
          <div className="h-64 rounded bg-white/5 relative overflow-hidden">
            {/* Animated bars */}
            <div className="absolute bottom-0 left-8 h-32 w-12 bg-primary/20 rounded-t" />
            <div className="absolute bottom-0 left-24 h-40 w-12 bg-primary/20 rounded-t" />
            <div className="absolute bottom-0 left-40 h-36 w-12 bg-primary/20 rounded-t" />
            <div className="absolute bottom-0 left-56 h-44 w-12 bg-primary/20 rounded-t" />

            {/* Loading shimmer effect */}
            <div
              className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent animate-shimmer"
              style={{
                backgroundSize: "200% 100%",
                animation: "shimmer 2s infinite",
              }}
            />
          </div>

          {/* Legend */}
          <div className="flex gap-4">
            <div className="h-4 w-24 rounded bg-white/5" />
            <div className="h-4 w-28 rounded bg-white/5" />
            <div className="h-4 w-20 rounded bg-white/5" />
          </div>
        </div>
      </div>

      <style jsx>{`
        @keyframes shimmer {
          0% {
            background-position: -200% 0;
          }
          100% {
            background-position: 200% 0;
          }
        }
      `}</style>
    </div>
  );
}
