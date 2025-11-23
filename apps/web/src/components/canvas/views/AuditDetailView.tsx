"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { AuditReportResponse } from "@/lib/types";

interface AuditDetailViewProps {
  report: AuditReportResponse;
  className?: string;
}

function DonutChart({
  critical,
  high,
  low,
  medium,
}: {
  critical: number;
  high: number;
  low: number;
  medium: number;
}) {
  const total = critical + high + medium + low || 1;
  const pct = (n: number) => Math.round((n / total) * 100);

  const segments = [
    { color: "#ef4444", value: pct(critical) },
    { color: "#f97316", value: pct(high) },
    { color: "#eab308", value: pct(medium) },
    { color: "#38bdf8", value: pct(low) },
  ];

  const conic = segments
    .reduce(
      (acc, seg) => {
        const start = acc.offset;
        const end = start + seg.value;
        acc.offset = end;
        acc.stops.push(`${seg.color} ${start}% ${end}%`);
        return acc;
      },
      { offset: 0, stops: [] as string[] },
    )
    .stops.join(", ");

  return (
    <div className="flex items-center gap-4">
      <div
        className="relative h-24 w-24 rounded-full"
        style={{ background: `conic-gradient(${conic})` }}
      >
        <div className="absolute inset-3 rounded-full bg-slate-950" />
        <div className="absolute inset-5 flex items-center justify-center text-sm font-semibold text-white">
          {total}
        </div>
      </div>
      <div className="space-y-1 text-sm text-saptiva-light">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[#ef4444]" />
          <span>Crítico: {critical}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[#f97316]" />
          <span>Alto: {high}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[#eab308]" />
          <span>Medio: {medium}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[#38bdf8]" />
          <span>Bajo: {low}</span>
        </div>
      </div>
    </div>
  );
}

export function AuditDetailView({ report, className }: AuditDetailViewProps) {
  const categories = Object.entries(report.categories || {});
  const displayName =
    report.metadata?.display_name ||
    report.metadata?.filename ||
    (report.doc_name && /^[0-9a-fA-F-]{20,}$/.test(report.doc_name)
      ? "Documento auditado"
      : report.doc_name);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(report, null, 2));
  };

  const handleDownload = () => {
    const url =
      report.metadata?.report_url ||
      report.metadata?.pdf_url ||
      report.metadata?.report_pdf_url;
    if (url) {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <div
      className={cn(
        "flex h-full flex-col gap-4 bg-slate-900 text-white",
        className,
      )}
    >
      <header className="flex items-start justify-between gap-3 border-b border-white/10 pb-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-saptiva-light/60">
            Reporte de Auditoría
          </p>
          <h2 className="text-lg font-semibold">{displayName}</h2>
          <p className="text-xs text-saptiva-light/60">
            Policy: {report.metadata?.policy_used?.name || "N/D"}
          </p>
        </div>
      </header>

      <section>
        <DonutChart
          critical={report.stats.critical}
          high={report.stats.high}
          medium={report.stats.medium}
          low={report.stats.low}
        />
      </section>

      <section className="flex-1 overflow-auto rounded-lg border border-white/5 bg-slate-950/60 p-3">
        <div className="space-y-3">
          {categories.length === 0 && (
            <div className="text-sm text-saptiva-light/70">Sin hallazgos.</div>
          )}
          {categories.map(([cat, findings]) => (
            <details
              key={cat}
              className="group rounded-md border border-white/5 bg-white/5 p-3"
              open
            >
              <summary className="flex cursor-pointer items-center justify-between text-sm font-semibold">
                <span>{cat}</span>
                <span className="text-xs text-saptiva-light/70">
                  {findings.length} hallazgos
                </span>
              </summary>
              <div className="mt-2 space-y-2 text-sm text-saptiva-light">
                {findings.map((f, idx) => (
                  <div
                    key={`${f.id || idx}-${f.message.slice(0, 20)}`}
                    className="rounded border border-white/5 bg-slate-900/70 p-2"
                  >
                    <div className="flex items-center justify-between text-xs uppercase tracking-tight">
                      <span
                        className={cn(
                          "font-semibold",
                          f.severity === "critical"
                            ? "text-red-400"
                            : f.severity === "high"
                              ? "text-orange-400"
                              : f.severity === "medium"
                                ? "text-yellow-300"
                                : "text-sky-300",
                        )}
                      >
                        {f.severity}
                      </span>
                      {f.page && (
                        <span className="text-[11px] text-saptiva-light/60">
                          Página {f.page}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-sm text-white">{f.message}</p>
                    {f.suggestion && (
                      <p className="text-xs text-saptiva-light/70">
                        Sugerencia: {f.suggestion}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </details>
          ))}
        </div>
      </section>

      <footer className="flex gap-2">
        <button
          type="button"
          onClick={handleCopy}
          className="flex-1 rounded-md border border-white/10 bg-white/10 px-3 py-2 text-sm font-semibold text-white hover:border-white/30"
        >
          Copiar JSON
        </button>
        <button
          type="button"
          onClick={handleDownload}
          className="flex-1 rounded-md border border-saptiva px-3 py-2 text-sm font-semibold text-saptiva bg-saptiva/20 hover:bg-saptiva/30"
        >
          Descargar
        </button>
      </footer>
    </div>
  );
}
