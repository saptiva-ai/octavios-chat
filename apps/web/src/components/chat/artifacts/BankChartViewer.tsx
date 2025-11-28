"use client";

import React from "react";
import dynamic from "next/dynamic";
import type { PlotParams } from "react-plotly.js";
import { cn } from "@/lib/utils";

// Dynamic import to avoid SSR issues with Plotly
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface TimeRange {
  start: string;
  end: string;
}

interface PlotlyTrace {
  x: string[];
  y: number[];
  type: string;
  name?: string;
  mode?: string;
  marker?: any;
  line?: any;
}

interface PlotlyLayout {
  title?: string;
  xaxis?: any;
  yaxis?: any;
  legend?: any;
  margin?: any;
  height?: number;
  showlegend?: boolean;
  [key: string]: any;
}

interface PlotlyConfig {
  responsive?: boolean;
  displayModeBar?: boolean;
  displaylogo?: boolean;
  [key: string]: any;
}

interface PlotlyChartSpec {
  data: PlotlyTrace[];
  layout: PlotlyLayout;
  config?: PlotlyConfig;
}

interface BankChartData {
  type: "bank_chart";
  metric_name: string;
  bank_names: string[];
  time_range: TimeRange;
  plotly_config: PlotlyChartSpec;
  data_as_of: string;
  source: string;
  title?: string;
  metadata?: {
    sql_generated?: string;
    [key: string]: any;
  };
}

interface BankChartViewerProps {
  data: BankChartData;
  className?: string;
}

export function BankChartViewer({ data, className }: BankChartViewerProps) {
  const {
    plotly_config,
    title,
    metric_name,
    bank_names,
    time_range,
    data_as_of,
    metadata,
  } = data;

  const [showSql, setShowSql] = React.useState(false);
  const sqlQuery = metadata?.sql_generated;

  // Default layout enhancements for dark theme
  const enhancedLayout: Partial<PlotlyLayout> = {
    ...plotly_config.layout,
    paper_bgcolor: "#232B3A",
    plot_bgcolor: "#1a212e",
    font: {
      color: "#ffffff",
      family: "Inter, system-ui, sans-serif",
    },
    xaxis: {
      ...plotly_config.layout?.xaxis,
      gridcolor: "#2d3748",
      color: "#a0aec0",
    },
    yaxis: {
      ...plotly_config.layout?.yaxis,
      gridcolor: "#2d3748",
      color: "#a0aec0",
    },
    legend: {
      ...plotly_config.layout?.legend,
      bgcolor: "#1a212e",
      bordercolor: "#2d3748",
      borderwidth: 1,
    },
  };

  const plotConfig: Partial<PlotParams["config"]> = {
    responsive: true,
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["toImage", "sendDataToCloud"],
    ...plotly_config.config,
  };

  // Format date for display
  const formatDate = (dateString: string) => {
    try {
      return new Date(dateString).toLocaleDateString("es-MX", {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return dateString;
    }
  };

  return (
    <div
      className={cn(
        "rounded-lg border border-white/10 overflow-hidden",
        className,
      )}
      style={{ backgroundColor: "#232B3A" }}
    >
      {/* Header */}
      <div className="p-4 border-b border-white/10">
        <h3 className="text-lg font-semibold text-white mb-1">
          {title || `${metric_name} - ${bank_names.join(" vs ")}`}
        </h3>
        <div className="flex flex-wrap items-center gap-4 text-xs text-white/60">
          <span className="flex items-center gap-1">
            <span className="text-base">📊</span>
            {metric_name.toUpperCase()}
          </span>
          <span className="flex items-center gap-1">
            <span className="text-base">🏦</span>
            {bank_names.join(", ")}
          </span>
          <span className="flex items-center gap-1">
            <span className="text-base">📅</span>
            {time_range.start} → {time_range.end}
          </span>
          <span className="ml-auto flex items-center gap-1">
            <span className="text-base">🔄</span>
            Actualizado: {formatDate(data_as_of)}
          </span>
        </div>
      </div>

      {/* SQL Query Section */}
      {sqlQuery && (
        <div className="border-b border-white/10">
          <button
            onClick={() => setShowSql(!showSql)}
            className="w-full px-4 py-2 flex items-center justify-between text-xs text-white/70 hover:text-white/90 hover:bg-white/5 transition-colors"
          >
            <span className="flex items-center gap-2">
              <span>🔍</span>
              <span className="font-medium">SQL Query Generada</span>
            </span>
            <span className="text-white/50">{showSql ? "▼" : "▶"}</span>
          </button>
          {showSql && (
            <div className="px-4 pb-3">
              <pre className="text-xs text-white/80 bg-black/30 p-3 rounded overflow-x-auto border border-white/5">
                <code>{sqlQuery}</code>
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Plotly Chart */}
      <div className="p-4">
        <Plot
          data={plotly_config.data as any}
          layout={enhancedLayout as any}
          config={plotConfig as any}
          style={{ width: "100%", height: "400px" }}
          useResizeHandler
        />
      </div>

      {/* Footer */}
      <div className="px-4 py-3 bg-white/5 border-t border-white/10 text-xs text-white/50">
        <div className="flex items-center justify-between">
          <span>
            Fuente: CNBV - Datos históricos 2017-2025 • Procesado por
            BankAdvisor NL2SQL
          </span>
          <span className="text-white/40">Interactivo: Zoom, Pan, Hover</span>
        </div>
      </div>
    </div>
  );
}
