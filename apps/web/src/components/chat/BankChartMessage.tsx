"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import { cn } from "../../lib/utils";
import type { BankChartData } from "../../lib/types";

// Dynamic import to avoid SSR issues with Plotly
const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-64 bg-white/5 rounded-lg">
      <div className="animate-pulse text-white/60">Cargando gráfica...</div>
    </div>
  ),
});

export interface BankChartMessageProps {
  data: BankChartData;
  className?: string;
}

/**
 * BankChartMessage - Renders bank analytics visualizations in chat (BA-P0-002)
 *
 * This component receives Plotly configuration from the bank-advisor MCP server
 * and renders it inline in the chat message flow.
 */
export function BankChartMessage({ data, className }: BankChartMessageProps) {
  const [isExpanded, setIsExpanded] = React.useState(false);

  console.log("[📊 BANK_CHART_MESSAGE] Rendering with data:", {
    hasPlotlyConfig: !!data.plotly_config,
    plotlyDataLength: data.plotly_config?.data?.length,
    plotlyData: data.plotly_config?.data,
    plotlyLayout: data.plotly_config?.layout,
    metricName: data.metric_name,
    fullData: data
  });

  // Extract chart config with defaults
  const plotlyData = data.plotly_config?.data || [];

  // Merge backend layout with frontend theme overrides
  const backendLayout = data.plotly_config?.layout || {};
  const plotlyLayout = {
    ...backendLayout,
    autosize: true,
    height: isExpanded ? 500 : 350,
    margin: { l: 50, r: 30, t: 50, b: 50 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(255,255,255,0.02)",
    font: { color: "rgba(255,255,255,0.8)", size: 12 },
    xaxis: {
      ...(backendLayout.xaxis || {}),  // Preserve backend xaxis config (type, title, etc.)
      gridcolor: "rgba(255,255,255,0.1)",
      linecolor: "rgba(255,255,255,0.2)",
    },
    yaxis: {
      ...(backendLayout.yaxis || {}),  // Preserve backend yaxis config
      gridcolor: "rgba(255,255,255,0.1)",
      linecolor: "rgba(255,255,255,0.2)",
    },
    legend: {
      ...(backendLayout.legend || {}),  // Preserve backend legend config
      bgcolor: "rgba(0,0,0,0)",
      font: { color: "rgba(255,255,255,0.8)" },
    },
  };

  const plotlyConfig = {
    responsive: true,
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
    ...data.plotly_config?.config,
  };

  // Format time range for display
  const timeRangeDisplay = React.useMemo(() => {
    if (!data.time_range?.start || !data.time_range?.end) return null;
    const start = new Date(data.time_range.start).toLocaleDateString("es-MX", {
      month: "short",
      year: "numeric",
    });
    const end = new Date(data.time_range.end).toLocaleDateString("es-MX", {
      month: "short",
      year: "numeric",
    });
    return `${start} - ${end}`;
  }, [data.time_range]);

  return (
    <div
      className={cn(
        "mt-3 rounded-xl overflow-hidden",
        "bg-gradient-to-br from-white/5 to-white/[0.02]",
        "border border-white/10",
        "shadow-lg",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 bg-white/5">
        <div className="flex items-center gap-3">
          {/* Chart icon */}
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/20">
            <svg
              className="w-4 h-4 text-primary"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-white">
              {data.title || data.metric_name || "Análisis Bancario"}
            </h3>
            <div className="flex items-center gap-2 text-xs text-white/60">
              {data.bank_names?.length > 0 && (
                <span>{data.bank_names.join(" vs ")}</span>
              )}
              {timeRangeDisplay && (
                <>
                  <span className="text-white/30">|</span>
                  <span>{timeRangeDisplay}</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Expand/Collapse button */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-2 rounded-lg hover:bg-white/10 transition-colors"
          aria-label={isExpanded ? "Contraer gráfica" : "Expandir gráfica"}
        >
          <svg
            className={cn(
              "w-4 h-4 text-white/60 transition-transform",
              isExpanded && "rotate-180"
            )}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </button>
      </div>

      {/* Chart */}
      <div className="p-2">
        {plotlyData.length > 0 ? (
          <Plot
            data={plotlyData as any}
            layout={plotlyLayout as any}
            config={plotlyConfig as any}
            style={{ width: "100%", height: isExpanded ? 500 : 350 }}
            useResizeHandler
          />
        ) : (
          <div className="flex items-center justify-center h-64 text-white/40">
            No hay datos disponibles para mostrar
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-4 py-2 border-t border-white/10 bg-white/[0.02]">
        <div className="flex items-center gap-2 text-xs text-white/40">
          <span>Fuente: {data.source || "BankAdvisor"}</span>
          {data.data_as_of && (
            <>
              <span className="text-white/20">|</span>
              <span>
                Datos al:{" "}
                {new Date(data.data_as_of).toLocaleDateString("es-MX")}
              </span>
            </>
          )}
        </div>

        {/* CNBV badge */}
        <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-white/5 text-xs text-white/50">
          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
          <span>CNBV</span>
        </div>
      </div>
    </div>
  );
}

export default BankChartMessage;
