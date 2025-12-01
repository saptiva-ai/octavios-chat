"use client";

import React from "react";
import { ChartBarIcon, ArrowsPointingOutIcon } from "@heroicons/react/24/outline";
import { cn } from "@/lib/utils";
import { useCanvasStore } from "@/lib/stores/canvas-store";
import type { BankChartData } from "@/lib/types";
import dynamic from "next/dynamic";

// Lazy load Plotly for performance
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface BankChartPreviewProps {
  data: BankChartData;
  artifactId: string;
  messageId: string;
  className?: string;
}

/**
 * BankChartPreview - Mini visualization of bank chart in chat
 *
 * Features:
 * - Reduced preview (200px height)
 * - "View in Canvas" button to open in sidebar
 * - Visual highlight when active in canvas
 * - Reuses Plotly rendering logic from BankChartMessage
 *
 * Usage:
 *   <BankChartPreview
 *     data={bankChartData}
 *     artifactId="artifact_123"
 *     messageId="msg_456"
 *   />
 */
export function BankChartPreview({
  data,
  artifactId,
  messageId,
  className,
}: BankChartPreviewProps) {
  const openBankChart = useCanvasStore((state) => state.openBankChart);
  const activeMessageId = useCanvasStore((state) => state.activeMessageId);

  const isActive = activeMessageId === messageId;

  const handleOpenInCanvas = () => {
    openBankChart(data, artifactId, messageId, false);

    // Optional: Scroll canvas into view
    const canvasPanel = document.querySelector("[data-canvas-panel]");
    if (canvasPanel) {
      canvasPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  // Dark theme simplified for preview
  const plotlyLayout = {
    ...data.plotly_config.layout,
    autosize: true,
    height: 200, // Reduced preview
    margin: { l: 40, r: 20, t: 30, b: 30 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(255,255,255,0.02)",
    font: { color: "rgba(255,255,255,0.7)", size: 10 },
    xaxis: {
      ...data.plotly_config.layout.xaxis,
      gridcolor: "rgba(255,255,255,0.08)",
      showticklabels: false, // Hide labels in preview
    },
    yaxis: {
      ...data.plotly_config.layout.yaxis,
      gridcolor: "rgba(255,255,255,0.08)",
    },
    showlegend: false, // No legend in preview
  };

  return (
    <div
      className={cn(
        "relative rounded-lg border bg-gradient-to-br from-slate-900/50 to-slate-800/30 p-3 transition-all",
        isActive
          ? "border-primary/60 ring-2 ring-primary/20" // Highlight when active
          : "border-white/10 hover:border-white/20",
        className
      )}
    >
      {/* Compact header */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ChartBarIcon className="h-4 w-4 text-primary" />
          <span className="text-xs font-semibold text-white">
            {data.metric_name.toUpperCase()}
          </span>
          <span className="text-xs text-white/50">
            {data.bank_names.join(", ")}
          </span>
        </div>

        {isActive && (
          <span className="rounded-full bg-primary/20 px-2 py-0.5 text-[10px] font-medium text-primary">
            Activo en Canvas
          </span>
        )}
      </div>

      {/* Mini chart */}
      <div className="relative">
        <Plot
          data={data.plotly_config.data as any}
          layout={plotlyLayout as any}
          config={{
            displayModeBar: false, // No toolbar in preview
            staticPlot: true, // Non-interactive
          }}
          className="w-full"
        />

        {/* Overlay with "View in Canvas" button */}
        <div className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-opacity hover:bg-black/40 hover:opacity-100">
          <button
            onClick={handleOpenInCanvas}
            className="flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-white shadow-lg transition-transform hover:scale-105"
          >
            <ArrowsPointingOutIcon className="h-4 w-4" />
            Ver en Canvas
          </button>
        </div>
      </div>

      {/* Footer with time range */}
      <div className="mt-2 flex items-center justify-between text-[10px] text-white/40">
        <span>
          {new Date(data.time_range.start).toLocaleDateString()} -{" "}
          {new Date(data.time_range.end).toLocaleDateString()}
        </span>
        <span>Fuente: {data.source}</span>
      </div>
    </div>
  );
}
