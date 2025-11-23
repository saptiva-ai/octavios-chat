"use client";

import * as React from "react";
import { useCanvasStore } from "@/lib/stores/canvas-store";
import type { AuditReportResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

interface AuditSummaryCardProps {
  data: AuditReportResponse;
  className?: string;
}

export function AuditSummaryCard({ data, className }: AuditSummaryCardProps) {
  const openCanvas = useCanvasStore((state) => state.openArtifact);
  const displayName =
    data.metadata?.display_name ||
    data.metadata?.filename ||
    (data.doc_name && /^[0-9a-fA-F-]{20,}$/.test(data.doc_name)
      ? "Documento auditado"
      : data.doc_name);

  const stats = data?.stats || {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
  };

  const handleOpen = () => {
    openCanvas("audit_report_ui", { type: "audit_report_ui", payload: data });
  };

  return (
    <div
      className={cn(
        "rounded-lg border border-white/10 bg-white/5 p-4 shadow-md text-white",
        className,
      )}
    >
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-red-500/20 text-lg">
          📄
        </div>
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-saptiva-light/60">
            Reporte de Auditoría
          </p>
          <p className="truncate text-sm font-semibold">{displayName}</p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs font-semibold">
        <span className="rounded-full bg-red-500/20 px-3 py-1 text-red-200">
          🔴 {stats.critical} Crítico
        </span>
        <span className="rounded-full bg-orange-500/20 px-3 py-1 text-orange-200">
          🟠 {stats.high} Alto
        </span>
        <span className="rounded-full bg-yellow-500/20 px-3 py-1 text-yellow-200">
          🟡 {stats.medium} Medio
        </span>
        <span className="rounded-full bg-sky-500/20 px-3 py-1 text-sky-200">
          🔵 {stats.low} Bajo
        </span>
      </div>

      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={handleOpen}
          className="rounded-md border border-saptiva px-4 py-2 text-sm font-semibold text-saptiva bg-saptiva/10 hover:bg-saptiva/20 transition-colors"
        >
          Ver Análisis Detallado
        </button>
      </div>
    </div>
  );
}
