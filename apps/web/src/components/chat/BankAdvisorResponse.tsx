"use client";

/**
 * BankAdvisorResponse Component
 *
 * Displays structured responses from Bank Advisor queries with:
 * - SQL query code block (collapsible)
 * - "Abrir Canvas Panel" button to visualize the chart
 */

import React, { useEffect } from "react";
import { cn } from "@/lib/utils";
import { useCanvasStore } from "@/lib/stores/canvas-store";
import {
  ChartBarIcon,
  ArrowsPointingOutIcon,
} from "@heroicons/react/24/outline";
import type { BankChartData } from "@/lib/types";

interface BankAdvisorResponseProps {
  bankChartData: BankChartData;
  messageId: string;
  metadata?: {
    artifact_id?: string;
    bank_chart_artifact_id?: string;
    [key: string]: any;
  };
  className?: string;
}

/**
 * Structured response component for Bank Advisor queries
 * Shows:
 * 1. SQL Query section (collapsible with copy button)
 * 2. "Abrir Canvas Panel" button
 */
export function BankAdvisorResponse({
  bankChartData,
  messageId,
  metadata,
  className,
}: BankAdvisorResponseProps) {
  // Debug: Log the bankChartData to see if metadata.sql_generated exists
  useEffect(() => {
    console.warn("[📊 BankAdvisorResponse] Data received:", {
      metric_name: bankChartData.metric_name,
      has_metadata: !!bankChartData.metadata,
      metadata_keys: bankChartData.metadata
        ? Object.keys(bankChartData.metadata)
        : [],
      sql_generated: bankChartData.metadata?.sql_generated,
      full_metadata: bankChartData.metadata,
    });
  }, [bankChartData]);

  const artifactId =
    metadata?.artifact_id || metadata?.bank_chart_artifact_id || "temp";

  const handleOpenCanvas = () => {
    useCanvasStore
      .getState()
      .openBankChart(bankChartData, artifactId, messageId, false);
  };

  return (
    <div className={cn("mt-4 space-y-3", className)}>
      {/* Open Canvas Button */}
      <button
        data-testid="bank-chart-button"
        onClick={handleOpenCanvas}
        className="group relative w-full overflow-hidden rounded-xl border border-primary/20 bg-gradient-to-br from-primary/5 via-primary/10 to-primary/5 p-4 text-left transition-all duration-300 hover:border-primary/40 hover:shadow-xl hover:shadow-primary/20 hover:scale-[1.02]"
        aria-label={`Abrir gráfica de ${bankChartData.metric_name.toUpperCase()} en canvas`}
      >
        {/* Background decoration */}
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />

        {/* Content */}
        <div className="relative flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/20 transition-colors group-hover:bg-primary/30">
            <ChartBarIcon className="h-5 w-5 text-primary" />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-foreground">
                {bankChartData.metric_name.toUpperCase()}
              </span>
              <span className="rounded-full bg-primary/20 px-2 py-0.5 text-[10px] font-medium text-primary">
                {bankChartData.bank_names.length}{" "}
                {bankChartData.bank_names.length === 1 ? "banco" : "bancos"}
              </span>
            </div>
            <p className="text-xs text-muted truncate">
              {bankChartData.bank_names.join(", ")}
            </p>
          </div>

          <div className="flex items-center gap-2 text-primary/80 transition-transform group-hover:translate-x-1">
            <span className="text-xs font-medium hidden sm:inline">
              Abrir en Canvas
            </span>
            <ArrowsPointingOutIcon className="h-4 w-4" />
          </div>
        </div>
      </button>

      {/* Additional metadata if available */}
      {bankChartData.metadata?.metric_interpretation && (
        <div className="px-4 py-2 bg-surface/50 rounded-lg border border-border">
          <p className="text-xs text-muted">
            <span className="font-medium text-foreground">
              Interpretación:{" "}
            </span>
            {bankChartData.metadata.metric_interpretation}
          </p>
        </div>
      )}

      {/* Execution time */}
      {bankChartData.metadata?.execution_time_ms && (
        <div className="flex items-center gap-2 text-xs text-muted">
          <span>
            ⚡ Ejecutado en {bankChartData.metadata.execution_time_ms}ms
          </span>
        </div>
      )}
    </div>
  );
}

export default BankAdvisorResponse;
