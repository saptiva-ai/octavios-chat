"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  CodeBracketIcon,
  ChartBarIcon,
  CalendarDaysIcon,
  BuildingOffice2Icon,
  CircleStackIcon,
} from "@heroicons/react/24/outline";
import { cn } from "@/lib/utils";
import type { BankChartData } from "@/lib/types";
import dynamic from "next/dynamic";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface BankChartCanvasViewProps {
  data: BankChartData;
  className?: string;
}

/**
 * BankChartCanvasView - Full visualization of bank chart in canvas sidebar
 *
 * Features:
 * - Full-size chart with complete Plotly controls
 * - Tabs: Chart | SQL Query | Interpretation
 * - Enriched metadata (banks, time range, source)
 * - Reuses Plotly rendering logic optimized for canvas
 *
 * Usage:
 *   <BankChartCanvasView data={bankChartData} />
 */
export function BankChartCanvasView({
  data,
  className,
}: BankChartCanvasViewProps) {
  const [activeTab, setActiveTab] = useState<
    "chart" | "sql" | "interpretation"
  >("chart");
  const plotContainerRef = useRef<HTMLDivElement>(null);
  const [plotKey, setPlotKey] = useState(0);

  // Force re-render of Plotly when container size changes
  useEffect(() => {
    if (!plotContainerRef.current) return;

    const resizeObserver = new ResizeObserver(() => {
      // Force Plotly to recalculate layout
      setPlotKey((prev) => prev + 1);
    });

    resizeObserver.observe(plotContainerRef.current);

    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  // Extract enriched metadata
  const sqlQuery = data.metadata?.sql_generated;
  const metricInterpretation = data.metadata?.metric_interpretation;

  // Dark theme optimized for canvas (more space)
  const plotlyLayout = {
    ...data.plotly_config.layout,
    autosize: true,
    height: 500, // Full-size in canvas
    margin: { l: 60, r: 40, t: 60, b: 60 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(255,255,255,0.02)",
    font: { color: "rgba(255,255,255,0.8)", size: 12 },
    xaxis: {
      ...data.plotly_config.layout.xaxis,
      gridcolor: "rgba(255,255,255,0.1)",
      linecolor: "rgba(255,255,255,0.2)",
    },
    yaxis: {
      ...data.plotly_config.layout.yaxis,
      gridcolor: "rgba(255,255,255,0.1)",
      linecolor: "rgba(255,255,255,0.2)",
    },
    legend: {
      ...data.plotly_config.layout.legend,
      bgcolor: "rgba(0,0,0,0)",
      font: { color: "rgba(255,255,255,0.8)" },
    },
  };

  return (
    <div className={cn("flex h-full flex-col space-y-4", className)}>
      {/* Metadata Header */}
      <div className="space-y-3 rounded-lg border border-white/10 bg-white/5 p-4">
        <div className="flex items-center gap-2">
          <ChartBarIcon className="h-5 w-5 text-primary" />
          <h3 className="text-lg font-bold text-white">
            {data.metric_name.toUpperCase()}
          </h3>
        </div>

        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="flex items-center gap-2 text-white/60">
            <BuildingOffice2Icon className="h-4 w-4" />
            <span>{data.bank_names.join(", ")}</span>
          </div>
          <div className="flex items-center gap-2 text-white/60">
            <CalendarDaysIcon className="h-4 w-4" />
            <span>
              {new Date(data.time_range.start).toLocaleDateString()} -{" "}
              {new Date(data.time_range.end).toLocaleDateString()}
            </span>
          </div>
          <div className="flex items-center gap-2 text-white/60">
            <CircleStackIcon className="h-4 w-4" />
            <span>
              Actualizado: {new Date(data.data_as_of).toLocaleString()}
            </span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-white/10">
        <button
          onClick={() => setActiveTab("chart")}
          className={cn(
            "px-4 py-2 text-sm font-medium transition-colors",
            activeTab === "chart"
              ? "border-b-2 border-primary text-primary"
              : "text-white/60 hover:text-white",
          )}
        >
          Gráfica
        </button>
        {sqlQuery && (
          <button
            onClick={() => setActiveTab("sql")}
            className={cn(
              "flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors",
              activeTab === "sql"
                ? "border-b-2 border-primary text-primary"
                : "text-white/60 hover:text-white",
            )}
          >
            <CodeBracketIcon className="h-4 w-4" />
            SQL Query
          </button>
        )}
        {metricInterpretation && (
          <button
            onClick={() => setActiveTab("interpretation")}
            className={cn(
              "px-4 py-2 text-sm font-medium transition-colors",
              activeTab === "interpretation"
                ? "border-b-2 border-primary text-primary"
                : "text-white/60 hover:text-white",
            )}
          >
            Interpretación
          </button>
        )}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === "chart" && (
          <div
            ref={plotContainerRef}
            className="rounded-lg border border-white/10 bg-white/5 p-4"
          >
            <Plot
              key={plotKey}
              data={data.plotly_config.data as any}
              layout={plotlyLayout as any}
              config={{
                responsive: true,
                displayModeBar: true, // Show toolbar in canvas
                modeBarButtonsToRemove: ["sendDataToCloud"],
                displaylogo: false,
              }}
              className="w-full"
              useResizeHandler
              style={{ width: "100%", height: "100%" }}
            />
          </div>
        )}

        {activeTab === "sql" && sqlQuery && (
          <div className="rounded-lg border border-white/10 bg-slate-900/50 p-4">
            <div className="mb-2 flex items-center gap-2 text-sm text-white/60">
              <CodeBracketIcon className="h-4 w-4" />
              <span>Query SQL Generado</span>
            </div>
            <pre className="overflow-x-auto rounded bg-black/40 p-3 text-xs text-green-400">
              {sqlQuery}
            </pre>
          </div>
        )}

        {activeTab === "interpretation" && metricInterpretation && (
          <div className="rounded-lg border border-white/10 bg-white/5 p-4">
            <div className="mb-3 flex items-center gap-2 text-sm text-white/60">
              <ChartBarIcon className="h-4 w-4" />
              <span>Interpretación de Métrica</span>
            </div>
            <div className="prose prose-invert prose-sm max-w-none text-white/80">
              {metricInterpretation.split("\n").map((line, i) => (
                <p key={i} className="mb-2">
                  {line}
                </p>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
