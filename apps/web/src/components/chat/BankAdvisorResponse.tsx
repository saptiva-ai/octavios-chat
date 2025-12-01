"use client";

/**
 * BankAdvisorResponse Component
 *
 * Displays the "Abrir Canvas Panel" button for bank chart visualizations.
 * SQL query is shown directly in the LLM's response text.
 */

import React from "react";
import { cn } from "@/lib/utils";
import { useCanvasStore } from "@/lib/stores/canvas-store";
import { ChartBarIcon } from "@heroicons/react/24/outline";
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
 * Structured response component for Bank Advisor queries.
 * Shows the "Abrir Canvas Panel" button.
 * SQL query is displayed directly in the LLM's response text.
 */
export function BankAdvisorResponse({
  bankChartData,
  messageId,
  metadata,
  className,
}: BankAdvisorResponseProps) {
  const artifactId =
    metadata?.artifact_id || metadata?.bank_chart_artifact_id || "temp";

  const handleOpenCanvas = () => {
    useCanvasStore
      .getState()
      .openBankChart(bankChartData, artifactId, messageId, false);
  };

  return (
    <div className={cn("mt-4", className)}>
      {/* Open Canvas Button */}
      <button
        data-testid="bank-chart-button"
        onClick={handleOpenCanvas}
        className="group relative w-full overflow-hidden rounded-lg border border-border bg-surface/50 hover:bg-surface px-4 py-3 text-left transition-all duration-200 hover:border-primary/40"
        aria-label={`Abrir gráfica de ${bankChartData.metric_name.toUpperCase()} en canvas`}
      >
        {/* Content */}
        <div className="relative flex items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 transition-colors group-hover:bg-primary/20">
            <ChartBarIcon className="h-4 w-4 text-primary" />
          </div>

          <div className="flex-1 min-w-0">
            <span className="font-medium text-sm text-foreground">
              {bankChartData.metric_name.toUpperCase()}
            </span>
            <p className="text-xs text-muted truncate">
              {bankChartData.bank_names.join(", ")}
            </p>
          </div>

          <div className="flex items-center gap-1.5 text-muted transition-colors group-hover:text-primary">
            <span className="text-xs font-medium hidden sm:inline">Abrir</span>
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
              />
            </svg>
          </div>
        </div>
      </button>
    </div>
  );
}

export default BankAdvisorResponse;
