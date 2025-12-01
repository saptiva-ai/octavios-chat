"use client";

import * as React from "react";
import { apiClient } from "@/lib/api-client";
import { useCanvasStore } from "@/lib/stores/canvas-store";
import { cn } from "@/lib/utils";
import type { ArtifactRecord } from "@/lib/types";
import { MarkdownRenderer } from "./markdown-renderer";
import { MermaidGraph } from "./mermaid-graph";
import { graphToMermaid } from "@/lib/utils/graph-to-mermaid";
import { AuditDetailView } from "./views/AuditDetailView";
import { BankChartCanvasView } from "./BankChartCanvasView";

interface CanvasPanelProps {
  className?: string;
  reportPdfUrl?: string;
}

function ArtifactSkeleton() {
  return (
    <div className="space-y-3">
      <div className="h-4 w-1/3 rounded-md bg-white/10 animate-pulse" />
      <div className="h-3 w-1/2 rounded-md bg-white/5 animate-pulse" />
      <div className="space-y-2">
        <div className="h-3 w-full rounded-md bg-white/5 animate-pulse" />
        <div className="h-3 w-5/6 rounded-md bg-white/5 animate-pulse" />
        <div className="h-3 w-4/6 rounded-md bg-white/5 animate-pulse" />
      </div>
    </div>
  );
}

function GraphFallback({ data }: { data: any }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-xs text-saptiva-light/80">
      <p className="mb-2 font-semibold text-saptiva-light">Vista de grafo</p>
      <pre className="overflow-auto text-[11px] leading-relaxed">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}

export function CanvasPanel({ className, reportPdfUrl }: CanvasPanelProps) {
  const activeArtifactId = useCanvasStore((state) => state.activeArtifactId);
  const isSidebarOpen = useCanvasStore((state) => state.isSidebarOpen);
  const toggleSidebar = useCanvasStore((state) => state.toggleSidebar);
  const activeArtifactData = useCanvasStore(
    (state) => state.activeArtifactData,
  );
  // 🆕 Bank chart state for canvas visualization
  const activeBankChart = useCanvasStore((state) => state.activeBankChart);
  const cacheRef = React.useRef(new Map<string, ArtifactRecord>());

  const [artifact, setArtifact] = React.useState<ArtifactRecord | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [width, setWidth] = React.useState<number>(480);
  const draggingRef = React.useRef(false);

  const handleMouseDown = React.useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
  }, []);

  React.useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current) return;
      const viewportWidth = window.innerWidth;
      const newWidth = Math.min(
        Math.max(viewportWidth - e.clientX, 400),
        Math.min(800, viewportWidth * 0.5),
      );
      setWidth(newWidth);
    };

    const onUp = () => {
      draggingRef.current = false;
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  React.useEffect(() => {
    let cancelled = false;

    // If showing PDF report, don't fetch artifact
    if (reportPdfUrl) {
      setArtifact(null);
      setError(null);
      setLoading(false);
      return;
    }

    // 🆕 If showing bank chart, don't fetch artifact (data already in activeBankChart)
    if (activeBankChart) {
      setArtifact(null);
      setError(null);
      setLoading(false);
      return;
    }

    if (!activeArtifactId) {
      setArtifact(null);
      setError(null);
      setLoading(false);
      return;
    }

    const cached = cacheRef.current.get(activeArtifactId);
    if (cached) {
      setArtifact(cached);
      return;
    }

    const fetchArtifact = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiClient.getArtifact(activeArtifactId);
        cacheRef.current.set(activeArtifactId, data);
        if (!cancelled) {
          setArtifact(data);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(
            err?.response?.data?.detail ||
              "No se pudo cargar el artefacto. Intenta nuevamente.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void fetchArtifact();

    return () => {
      cancelled = true;
    };
  }, [activeArtifactId, reportPdfUrl, activeBankChart]);

  const renderContent = () => {
    // 🆕 Priority 1: activeBankChart (bank chart visualizations)
    if (activeBankChart) {
      return <BankChartCanvasView data={activeBankChart} />;
    }

    // Priority 2: render audit detail directly if provided by store
    if (activeArtifactData) {
      // Accept plain payload or wrapped {type, payload}
      const payload = (activeArtifactData as any).payload || activeArtifactData;
      return <AuditDetailView report={payload} />;
    }

    if (reportPdfUrl) {
      return (
        <iframe
          src={reportPdfUrl}
          className="h-full w-full rounded-lg border-0 bg-white"
          title="Audit Report"
        />
      );
    }

    if (!activeArtifactId) {
      return (
        <div className="flex h-full items-center justify-center text-sm text-saptiva-light/70">
          Selecciona un artefacto desde el chat.
        </div>
      );
    }

    if (loading) {
      return <ArtifactSkeleton />;
    }

    if (error) {
      return (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
          {error}
        </div>
      );
    }

    if (!artifact) {
      return null;
    }

    const safeContent =
      typeof artifact.content === "string"
        ? artifact.content
        : JSON.stringify(artifact.content, null, 2);

    switch (artifact.type) {
      case "markdown":
      case "code":
        return <MarkdownRenderer content={safeContent} />;
      case "graph":
        try {
          let chart = safeContent;
          if (typeof artifact.content === "object") {
            chart = graphToMermaid(artifact.content as any);
          } else {
            try {
              const parsed = JSON.parse(artifact.content as string);
              chart = graphToMermaid(parsed);
            } catch {
              // Use raw content when parsing fails
            }
          }
          return <MermaidGraph chart={chart} />;
        } catch {
          return <GraphFallback data={artifact.content} />;
        }
      case "bank_chart": // 🆕 Case for persisted bank charts
        try {
          const chartData =
            typeof artifact.content === "string"
              ? JSON.parse(artifact.content)
              : artifact.content;
          return <BankChartCanvasView data={chartData} />;
        } catch {
          return (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
              Error al cargar gráfica. El formato de datos no es válido.
            </div>
          );
        }
      default:
        return (
          <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-sm text-saptiva-light">
            Tipo de artefacto no soportado.
          </div>
        );
    }
  };

  return (
    <div
      className={cn(
        "h-full bg-[#0b1021] border-l border-white/10 text-white transition-opacity duration-200 relative",
        isSidebarOpen ? "opacity-100" : "opacity-0 pointer-events-none",
        className,
      )}
      style={{ width }}
    >
      {/* Resize handle */}
      <div
        className="absolute left-0 top-0 bottom-0 w-1.5 cursor-col-resize hover:bg-primary/50 active:bg-primary transition-colors z-50"
        onMouseDown={handleMouseDown}
      />
      <Header
        reportPdfUrl={reportPdfUrl}
        artifact={artifact}
        activeArtifactData={activeArtifactData}
        onToggle={toggleSidebar}
        isSidebarOpen={isSidebarOpen}
      />

      <div className="h-[calc(100%-64px)] overflow-y-auto px-4 py-3">
        {renderContent()}
      </div>
    </div>
  );
}

function Header({
  reportPdfUrl,
  artifact,
  activeArtifactData,
  onToggle,
  isSidebarOpen,
}: {
  reportPdfUrl?: string;
  artifact: ArtifactRecord | null;
  activeArtifactData: any;
  onToggle: () => void;
  isSidebarOpen: boolean;
}) {
  const auditPayload = React.useMemo(() => {
    if (!activeArtifactData) return null;
    const payload = (activeArtifactData as any).payload || activeArtifactData;
    return payload && (payload as any).stats ? payload : null;
  }, [activeArtifactData]);

  const displayName = React.useMemo(() => {
    if (auditPayload) {
      const meta = (auditPayload as any).metadata || {};
      const base =
        meta.display_name || meta.filename || (auditPayload as any).doc_name;
      if (base && /^[0-9a-fA-F-]{20,}$/.test(base)) return "Documento auditado";
      return base || "Reporte de Auditoría";
    }
    if (reportPdfUrl) return "Reporte de Auditoría";
    if (artifact?.title) return artifact.title;
    return "Sin selección";
  }, [auditPayload, reportPdfUrl, artifact]);

  const summaryText = React.useMemo(() => {
    if (!auditPayload) return null;
    const meta = (auditPayload as any).metadata || {};
    const summary = meta.summary;
    if (!summary) return null;
    if (typeof summary === "string") return summary;
    if (typeof summary === "object") {
      return (
        summary.text ||
        summary.summary ||
        summary.overview ||
        summary.short ||
        null
      );
    }
    return null;
  }, [auditPayload]);

  const stats = (auditPayload as any)?.stats;
  const policy =
    (auditPayload as any)?.metadata?.policy_used?.name ||
    (auditPayload as any)?.metadata?.policy_used?.id ||
    null;

  const badges = stats && [
    {
      label: "Crítico",
      value: stats.critical,
      color: "bg-red-500/20 text-red-200",
    },
    {
      label: "Alto",
      value: stats.high,
      color: "bg-orange-500/20 text-orange-200",
    },
    {
      label: "Medio",
      value: stats.medium,
      color: "bg-yellow-500/20 text-yellow-200",
    },
    { label: "Bajo", value: stats.low, color: "bg-sky-500/20 text-sky-200" },
  ];

  return (
    <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
      <div className="min-w-0 space-y-1">
        <p className="text-xs uppercase tracking-wide text-saptiva-light/60">
          {auditPayload ? "Reporte de Auditoría" : "Canvas"}
        </p>
        <p className="text-sm font-semibold truncate">{displayName}</p>
        {auditPayload && (
          <>
            <p className="text-xs text-saptiva-light/60">
              {stats ? `${stats.total} hallazgos` : ""}{" "}
              {policy ? `• Política: ${policy}` : ""}
            </p>
            {summaryText && (
              <p className="text-xs text-saptiva-light line-clamp-2">
                {summaryText}
              </p>
            )}
            <div className="flex flex-wrap gap-1 pt-1 text-[11px] font-semibold">
              {badges?.map(
                (b: { label: string; value: number; color: string }) => (
                  <span
                    key={b.label}
                    className={cn("rounded-full px-2 py-1", b.color)}
                  >
                    {b.value} {b.label}
                  </span>
                ),
              )}
            </div>
          </>
        )}
      </div>
      <button
        type="button"
        onClick={onToggle}
        className="rounded-md border border-white/10 px-2 py-1 text-xs text-saptiva-light hover:border-white/30 hover:text-white"
      >
        {isSidebarOpen ? "Cerrar" : "Abrir"}
      </button>
    </div>
  );
}
