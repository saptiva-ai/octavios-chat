"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import {
  CodeBracketIcon,
  ChartBarIcon,
  CalendarDaysIcon,
  BuildingOffice2Icon,
  CircleStackIcon,
  ArrowDownTrayIcon,
  TableCellsIcon,
} from "@heroicons/react/24/outline";
import { cn } from "@/lib/utils";
import type { BankChartData } from "@/lib/types";
import dynamic from "next/dynamic";
import DOMPurify from "dompurify";
import { BankChartSkeleton } from "./BankChartSkeleton";
import { BankChartError } from "./BankChartError";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => <BankChartSkeleton />,
});

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
    "visualization" | "data" | "query"
  >("visualization");
  const plotContainerRef = useRef<HTMLDivElement>(null);
  const [plotKey, setPlotKey] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  // Validate chart data immediately (not in useEffect)
  const validateData = (): string | null => {
    if (!data?.plotly_config?.data || !Array.isArray(data.plotly_config.data)) {
      return "Datos de gráfica inválidos o faltantes";
    }

    if (!data?.metric_name) {
      return "Nombre de métrica faltante";
    }

    if (!data?.bank_names || data.bank_names.length === 0) {
      return "No se especificaron bancos";
    }

    return null;
  };

  const validationError = validateData();

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

  // Sanitize user-generated content to prevent XSS attacks
  const sanitizedSQL = useMemo(() => {
    if (!sqlQuery) return null;
    // SQL queries should only contain plain text, no HTML tags
    return DOMPurify.sanitize(sqlQuery, {
      ALLOWED_TAGS: [],
      ALLOWED_ATTR: [],
    });
  }, [sqlQuery]);

  const sanitizedInterpretation = useMemo(() => {
    if (!metricInterpretation) return null;
    // Allow basic formatting tags for interpretation text
    return DOMPurify.sanitize(metricInterpretation, {
      ALLOWED_TAGS: ["p", "br", "strong", "em", "code", "ul", "ol", "li"],
      ALLOWED_ATTR: [],
    });
  }, [metricInterpretation]);

  // Retry handler
  const handleRetry = () => {
    setIsLoading(true);
    setPlotKey((prev) => prev + 1);
    setTimeout(() => setIsLoading(false), 1000);
  };

  // Download chart as PNG
  const handleDownloadPNG = async () => {
    if (typeof window === "undefined") return;

    try {
      const Plotly = await import("plotly.js-dist-min" as any);
      const plotElement = plotContainerRef.current?.querySelector(".plotly");

      if (plotElement) {
        await (Plotly as any).downloadImage(plotElement as any, {
          format: "png",
          width: 1200,
          height: 800,
          filename: `${data.metric_name}_${data.bank_names.join("_")}`,
        });
      }
    } catch (error) {
      // Silently handle error
    }
  };

  // Export data to CSV
  const handleExportCSV = () => {
    try {
      // Extract data from Plotly config
      const plotlyData = data.plotly_config.data;
      if (!Array.isArray(plotlyData) || plotlyData.length === 0) return;

      // Create CSV header
      const headers = ["Banco", "Periodo", data.metric_name.toUpperCase()];
      const rows: string[][] = [headers];

      // Extract rows from each trace
      plotlyData.forEach((trace: any) => {
        const bankName = trace.name || "Unknown";
        const xValues = trace.x || [];
        const yValues = trace.y || [];

        xValues.forEach((period: string, index: number) => {
          rows.push([bankName, period, String(yValues[index] || "")]);
        });
      });

      // Convert to CSV string
      const csvContent = rows.map((row) => row.join(",")).join("\n");

      // Download
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      const url = URL.createObjectURL(blob);

      link.setAttribute("href", url);
      link.setAttribute(
        "download",
        `${data.metric_name}_${data.bank_names.join("_")}.csv`,
      );
      link.style.visibility = "hidden";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      // Silently handle error
    }
  };

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

  // Early return for loading state
  if (isLoading) {
    return <BankChartSkeleton />;
  }

  // Early return for validation error
  if (validationError) {
    return <BankChartError message={validationError} onRetry={handleRetry} />;
  }

  return (
    <div className={cn("flex h-full flex-col space-y-4", className)}>
      {/* Metadata Header */}
      <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-950 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ChartBarIcon className="h-5 w-5 text-primary" />
            <h3 className="text-lg font-bold text-white">
              {data.metric_name.toUpperCase()}
            </h3>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownloadPNG}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-md transition-colors"
              title="Descargar como PNG"
            >
              <ArrowDownTrayIcon className="h-4 w-4" />
              <span>PNG</span>
            </button>
            <button
              onClick={handleExportCSV}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-md transition-colors"
              title="Exportar a CSV"
            >
              <TableCellsIcon className="h-4 w-4" />
              <span>CSV</span>
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="flex items-center gap-2 text-slate-400">
            <BuildingOffice2Icon className="h-4 w-4 text-teal-500" />
            <span>{data.bank_names.join(", ")}</span>
          </div>
          <div className="flex items-center gap-2 text-slate-400">
            <CalendarDaysIcon className="h-4 w-4 text-teal-500" />
            <span>
              {new Date(data.time_range.start).toLocaleDateString()} -{" "}
              {new Date(data.time_range.end).toLocaleDateString()}
            </span>
          </div>
          <div className="flex items-center gap-2 text-slate-400">
            <CircleStackIcon className="h-4 w-4 text-teal-500" />
            <span>
              Actualizado: {new Date(data.data_as_of).toLocaleString()}
            </span>
          </div>
        </div>
      </div>

      {/* Saptiva AI Segmented Control */}
      <div className="flex gap-1 p-1 bg-slate-900/50 rounded-lg border border-slate-800">
        <button
          onClick={() => setActiveTab("visualization")}
          className={cn(
            "flex-1 px-4 py-2 text-sm font-medium transition-all rounded-md",
            activeTab === "visualization"
              ? "bg-slate-800 text-white shadow-sm"
              : "text-slate-400 hover:text-slate-200",
          )}
        >
          Visualización
        </button>
        <button
          onClick={() => setActiveTab("data")}
          className={cn(
            "flex-1 px-4 py-2 text-sm font-medium transition-all rounded-md",
            activeTab === "data"
              ? "bg-slate-800 text-white shadow-sm"
              : "text-slate-400 hover:text-slate-200",
          )}
        >
          Datos
        </button>
        {sanitizedSQL && (
          <button
            onClick={() => setActiveTab("query")}
            className={cn(
              "flex-1 px-4 py-2 text-sm font-medium transition-all rounded-md",
              activeTab === "query"
                ? "bg-slate-800 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200",
            )}
          >
            Query Inspector
          </button>
        )}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto space-y-4">
        {activeTab === "visualization" && (
          <>
            {/* KPI Cards Row */}
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
                <div className="text-xs font-medium text-teal-500 uppercase tracking-wide mb-1">
                  Bancos
                </div>
                <div className="text-2xl font-bold text-white">
                  {data.bank_names.length}
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  {data.bank_names.join(", ")}
                </div>
              </div>
              <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
                <div className="text-xs font-medium text-teal-500 uppercase tracking-wide mb-1">
                  Periodo
                </div>
                <div className="text-lg font-bold text-white">
                  {new Date(data.time_range.start).toLocaleDateString("es-MX", {
                    month: "short",
                    year: "numeric",
                  })}
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  hasta{" "}
                  {new Date(data.time_range.end).toLocaleDateString("es-MX", {
                    month: "short",
                    year: "numeric",
                  })}
                </div>
              </div>
              <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
                <div className="text-xs font-medium text-teal-500 uppercase tracking-wide mb-1">
                  Datos
                </div>
                <div className="text-lg font-bold text-white">
                  {new Date(data.data_as_of).toLocaleDateString("es-MX", {
                    day: "numeric",
                    month: "short",
                  })}
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  {new Date(data.data_as_of).toLocaleTimeString("es-MX", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
              </div>
            </div>

            {/* Chart */}
            <div
              ref={plotContainerRef}
              className="rounded-lg border border-slate-800 bg-slate-950 p-4"
            >
              <Plot
                key={plotKey}
                data={data.plotly_config.data as any}
                layout={plotlyLayout as any}
                config={{
                  responsive: true,
                  displayModeBar: true,
                  modeBarButtonsToRemove: ["sendDataToCloud"],
                  displaylogo: false,
                }}
                className="w-full"
                useResizeHandler
                style={{ width: "100%", height: "100%" }}
              />
            </div>
          </>
        )}

        {activeTab === "data" && (
          <div className="rounded-lg border border-slate-800 bg-slate-950 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-slate-900 border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium text-teal-500 uppercase tracking-wide text-xs">
                      Banco
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-teal-500 uppercase tracking-wide text-xs">
                      Periodo
                    </th>
                    <th className="px-4 py-3 text-right font-medium text-teal-500 uppercase tracking-wide text-xs">
                      {data.metric_name}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {data.plotly_config.data.map(
                    (trace: any, traceIdx: number) => {
                      const bankName = trace.name || `Banco ${traceIdx + 1}`;
                      const xValues = trace.x || [];
                      const yValues = trace.y || [];

                      return xValues.map((period: string, idx: number) => (
                        <tr
                          key={`${traceIdx}-${idx}`}
                          className="hover:bg-slate-800/30 transition-colors"
                        >
                          <td className="px-4 py-2.5 text-white font-medium">
                            {bankName}
                          </td>
                          <td className="px-4 py-2.5 text-slate-300">
                            {period}
                          </td>
                          <td className="px-4 py-2.5 text-right text-white font-mono">
                            {typeof yValues[idx] === "number"
                              ? yValues[idx].toLocaleString("es-MX", {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                })
                              : yValues[idx]}
                          </td>
                        </tr>
                      ));
                    },
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === "query" && sanitizedSQL && (
          <div className="rounded-lg border border-slate-800 bg-slate-950 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <CodeBracketIcon className="h-4 w-4" />
                <span>Query SQL Generado</span>
              </div>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(sanitizedSQL);
                }}
                className="px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-md transition-colors"
              >
                Copiar
              </button>
            </div>
            <pre className="overflow-x-auto rounded-lg bg-slate-900 p-4 text-xs text-green-400 font-mono border border-slate-800">
              {sanitizedSQL}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
