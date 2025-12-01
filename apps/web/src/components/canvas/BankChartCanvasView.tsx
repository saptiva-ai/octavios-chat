"use client";

import React, { useState, useRef, useEffect, useMemo } from "react";
import {
  CodeBracketIcon,
  CalendarDaysIcon,
  BuildingOffice2Icon,
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
  const [activeTab, setActiveTab] = useState<"visualization" | "data">(
    "visualization",
  );
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

  // Saptiva Dual Theme: Chart configuration (uses CSS variable colors)
  // Note: Plotly requires explicit colors, so we use muted teal tones
  const plotlyLayout = {
    ...data.plotly_config.layout,
    autosize: true,
    height: 500, // Increased from 320px
    margin: { l: 50, r: 15, t: 15, b: 50 },
    paper_bgcolor: "rgba(0,0,0,0)", // Transparent
    plot_bgcolor: "rgba(0,0,0,0)", // Transparent
    font: { color: "hsl(var(--foreground))", size: 12 }, // White in dark mode
    xaxis: {
      ...data.plotly_config.layout.xaxis,
      showgrid: false, // No vertical grid
      linecolor: "hsl(var(--border))",
      tickfont: { color: "hsl(var(--foreground))" }, // White in dark mode
    },
    yaxis: {
      ...data.plotly_config.layout.yaxis,
      gridcolor: "hsl(var(--border))",
      linecolor: "hsl(var(--border))",
      tickfont: { color: "hsl(var(--foreground))" }, // White in dark mode
    },
    legend: {
      ...data.plotly_config.layout.legend,
      bgcolor: "rgba(0,0,0,0)",
      font: { color: "hsl(var(--foreground))" }, // White in dark mode
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
      {/* Compact Action Bar */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-border">
        <div className="flex items-center gap-3 text-xs text-muted">
          <span className="flex items-center gap-1">
            <BuildingOffice2Icon className="h-3.5 w-3.5 text-primary" />
            {data.bank_names.length} bancos
          </span>
          <span className="flex items-center gap-1">
            <CalendarDaysIcon className="h-3.5 w-3.5 text-primary" />
            {new Date(data.time_range.start).toLocaleDateString("es-MX", {
              month: "short",
              year: "2-digit",
            })}{" "}
            -{" "}
            {new Date(data.time_range.end).toLocaleDateString("es-MX", {
              month: "short",
              year: "2-digit",
            })}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleDownloadPNG}
            className="p-1.5 text-muted hover:text-foreground hover:bg-surface-2 rounded transition-colors"
            title="Descargar PNG"
          >
            <ArrowDownTrayIcon className="h-4 w-4" />
          </button>
          <button
            onClick={handleExportCSV}
            className="p-1.5 text-muted hover:text-foreground hover:bg-surface-2 rounded transition-colors"
            title="Exportar CSV"
          >
            <TableCellsIcon className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Compact Tabs */}
      <div className="flex gap-4 border-b border-border mb-4">
        <button
          onClick={() => setActiveTab("visualization")}
          className={cn(
            "pb-2 text-xs font-medium transition-colors border-b-2",
            activeTab === "visualization"
              ? "border-primary text-primary"
              : "border-transparent text-muted hover:text-foreground",
          )}
        >
          Gráfica
        </button>
        <button
          onClick={() => setActiveTab("data")}
          className={cn(
            "pb-2 text-xs font-medium transition-colors border-b-2",
            activeTab === "data"
              ? "border-primary text-primary"
              : "border-transparent text-muted hover:text-foreground",
          )}
        >
          Datos
        </button>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto space-y-4">
        {activeTab === "visualization" && (
          <>
            {/* Compact KPI Row */}
            <div className="flex items-center gap-4 text-xs mb-4 pb-3 border-b border-border/50">
              <div>
                <span className="text-muted">Bancos: </span>
                <span className="text-foreground font-medium">
                  {data.bank_names.join(", ")}
                </span>
              </div>
              <div className="text-muted">|</div>
              <div>
                <span className="text-muted">Actualizado: </span>
                <span className="text-foreground font-medium">
                  {(() => {
                    const asOfDate = new Date(data.data_as_of);
                    return isNaN(asOfDate.getTime())
                      ? "—"
                      : asOfDate.toLocaleDateString("es-MX", {
                          day: "numeric",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        });
                  })()}
                </span>
              </div>
            </div>

            {/* Chart - Larger */}
            <div ref={plotContainerRef} className="w-full h-[500px]">
              <Plot
                key={plotKey}
                data={data.plotly_config.data as any}
                layout={plotlyLayout as any}
                config={{
                  responsive: true,
                  displayModeBar: false, // Hide toolbar
                  displaylogo: false,
                }}
                className="w-full"
                useResizeHandler
                style={{ width: "100%", height: "100%" }}
              />
            </div>

            {/* SQL Query Section - Below Chart */}
            {sanitizedSQL && (
              <div className="space-y-3 pt-4 border-t border-border">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm">
                    <CodeBracketIcon className="h-4 w-4 text-primary" />
                    <span className="font-medium text-foreground">
                      Consulta SQL
                    </span>
                  </div>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(sanitizedSQL);
                    }}
                    className="px-3 py-1.5 text-xs font-medium text-muted hover:text-foreground bg-surface-2 hover:bg-surface rounded transition-colors"
                  >
                    Copiar
                  </button>
                </div>
                <pre className="overflow-x-auto bg-surface border border-border p-4 text-xs text-foreground dark:text-white font-mono rounded leading-relaxed">
                  {sanitizedSQL}
                </pre>
              </div>
            )}
          </>
        )}

        {activeTab === "data" && (
          <div className="rounded-lg border border-border bg-transparent overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-surface-2 border-b border-border">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium text-primary uppercase tracking-wide text-xs">
                      Banco
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-primary uppercase tracking-wide text-xs">
                      Periodo
                    </th>
                    <th className="px-4 py-3 text-right font-medium text-primary uppercase tracking-wide text-xs">
                      {data.metric_name}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.plotly_config.data.map(
                    (trace: any, traceIdx: number) => {
                      const bankName = trace.name || `Banco ${traceIdx + 1}`;
                      const xValues = trace.x || [];
                      const yValues = trace.y || [];

                      return xValues.map((period: string, idx: number) => (
                        <tr
                          key={`${traceIdx}-${idx}`}
                          className="hover:bg-surface-2/50 transition-colors"
                        >
                          <td className="px-4 py-2.5 text-foreground font-medium">
                            {bankName}
                          </td>
                          <td className="px-4 py-2.5 text-muted">{period}</td>
                          <td className="px-4 py-2.5 text-right text-foreground font-mono">
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
      </div>
    </div>
  );
}
