"use client";

import * as React from "react";
import { apiClient } from "@/lib/api-client";
import { useCanvasStore } from "@/lib/stores/canvas-store";
import { cn } from "@/lib/utils";
import type { ArtifactRecord } from "@/lib/types";
import { MarkdownRenderer } from "./markdown-renderer";
import { MermaidGraph } from "./mermaid-graph";
import { graphToMermaid } from "@/lib/utils/graph-to-mermaid";

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
  const cacheRef = React.useRef(new Map<string, ArtifactRecord>());

  const [artifact, setArtifact] = React.useState<ArtifactRecord | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;

    // If showing PDF report, don't fetch artifact
    if (reportPdfUrl) {
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
  }, [activeArtifactId, reportPdfUrl]);

  const renderContent = () => {
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
        "h-full bg-[#0b1021] border-l border-white/10 text-white transition-opacity duration-200",
        isSidebarOpen ? "opacity-100" : "opacity-0 pointer-events-none",
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-saptiva-light/60">
            Canvas
          </p>
          <p className="text-sm font-semibold">
            {reportPdfUrl
              ? "Reporte de Auditoría"
              : artifact?.title || "Sin selección"}
          </p>
        </div>
        <button
          type="button"
          onClick={toggleSidebar}
          className="rounded-md border border-white/10 px-2 py-1 text-xs text-saptiva-light hover:border-white/30 hover:text-white"
        >
          {isSidebarOpen ? "Cerrar" : "Abrir"}
        </button>
      </div>

      <div className="h-[calc(100%-64px)] overflow-y-auto px-4 py-3">
        {renderContent()}
      </div>
    </div>
  );
}
