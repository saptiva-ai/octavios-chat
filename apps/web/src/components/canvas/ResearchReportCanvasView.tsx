"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { ResearchReportData } from "@/lib/stores/canvas-store";
import { MarkdownRenderer } from "./markdown-renderer";
import {
  DocumentTextIcon,
  LinkIcon,
  CheckBadgeIcon,
  ClockIcon,
} from "@heroicons/react/24/outline";

interface ResearchReportCanvasViewProps {
  data: ResearchReportData;
}

const SUPPORT_LEVEL_CONFIG = {
  strong: {
    label: "Fuerte",
    color: "bg-green-500/20 text-green-300 border-green-500/30",
  },
  mixed: {
    label: "Mixto",
    color: "bg-yellow-500/20 text-yellow-300 border-yellow-500/30",
  },
  weak: {
    label: "Débil",
    color: "bg-red-500/20 text-red-300 border-red-500/30",
  },
};

export function ResearchReportCanvasView({
  data,
}: ResearchReportCanvasViewProps) {
  const { query, report, sources, evidences, completedAt } = data;
  const [activeTab, setActiveTab] = React.useState<
    "report" | "sources" | "evidence"
  >("report");

  const formattedDate = React.useMemo(() => {
    try {
      return new Date(completedAt).toLocaleString("es-MX", {
        dateStyle: "medium",
        timeStyle: "short",
      });
    } catch {
      return completedAt;
    }
  }, [completedAt]);

  const reportContent = React.useMemo(() => {
    if (!report) return null;

    // Build markdown content from report
    let content = "";

    if (report.tl_dr) {
      content += `## TL;DR\n\n${report.tl_dr}\n\n`;
    }

    if (report.summary) {
      content += `## Resumen\n\n${report.summary}\n\n`;
    }

    // Add findings if available
    if (report.findings && typeof report.findings === "object") {
      content += `## Hallazgos\n\n`;
      if (Array.isArray(report.findings)) {
        report.findings.forEach((finding: any, idx: number) => {
          content += `${idx + 1}. ${typeof finding === "string" ? finding : JSON.stringify(finding)}\n`;
        });
      } else {
        content += JSON.stringify(report.findings, null, 2);
      }
    }

    return content || "Reporte sin contenido disponible.";
  }, [report]);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="mb-4 border-b border-border pb-4">
        <div className="flex items-center gap-2 text-xs text-muted mb-2">
          <ClockIcon className="h-4 w-4" />
          <span>Completado: {formattedDate}</span>
        </div>
        <h2 className="text-lg font-semibold text-foreground line-clamp-2">
          {query}
        </h2>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-border">
        <TabButton
          active={activeTab === "report"}
          onClick={() => setActiveTab("report")}
          icon={<DocumentTextIcon className="h-4 w-4" />}
          label="Reporte"
        />
        <TabButton
          active={activeTab === "sources"}
          onClick={() => setActiveTab("sources")}
          icon={<LinkIcon className="h-4 w-4" />}
          label={`Fuentes (${sources.length})`}
        />
        <TabButton
          active={activeTab === "evidence"}
          onClick={() => setActiveTab("evidence")}
          icon={<CheckBadgeIcon className="h-4 w-4" />}
          label={`Evidencia (${evidences.length})`}
        />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === "report" && reportContent && (
          <MarkdownRenderer content={reportContent} />
        )}

        {activeTab === "sources" && (
          <div className="space-y-3">
            {sources.length === 0 ? (
              <EmptyState message="No se encontraron fuentes para esta investigación." />
            ) : (
              sources.map((source, idx) => (
                <SourceCard key={source.id || `source-${idx}`} source={source} />
              ))
            )}
          </div>
        )}

        {activeTab === "evidence" && (
          <div className="space-y-3">
            {evidences.length === 0 ? (
              <EmptyState message="No se recopiló evidencia para esta investigación." />
            ) : (
              evidences.map((evidence, idx) => (
                <EvidenceCard
                  key={evidence.id || `evidence-${idx}`}
                  evidence={evidence}
                />
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors border-b-2 -mb-px",
        active
          ? "border-primary text-primary"
          : "border-transparent text-muted hover:text-foreground hover:border-border"
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function SourceCard({
  source,
}: {
  source: { title?: string; url?: string; snippet?: string; relevance_score?: number };
}) {
  const hostname = React.useMemo(() => {
    if (!source.url) return null;
    try {
      return new URL(source.url).hostname.replace("www.", "");
    } catch {
      return source.url;
    }
  }, [source.url]);

  return (
    <article className="rounded-lg border border-border bg-surface-2 p-3">
      <h4 className="font-medium text-foreground line-clamp-2 mb-1">
        {source.title || "Fuente sin título"}
      </h4>
      {source.snippet && (
        <p className="text-sm text-muted line-clamp-3 mb-2">{source.snippet}</p>
      )}
      <div className="flex items-center justify-between">
        {source.url && (
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-primary hover:underline flex items-center gap-1"
          >
            <LinkIcon className="h-3 w-3" />
            {hostname}
          </a>
        )}
        {source.relevance_score !== undefined && (
          <span className="text-xs text-muted">
            Relevancia: {Math.round(source.relevance_score * 100)}%
          </span>
        )}
      </div>
    </article>
  );
}

function EvidenceCard({
  evidence,
}: {
  evidence: {
    claim?: string;
    support_level?: "weak" | "mixed" | "strong";
    confidence?: number;
  };
}) {
  const supportConfig = evidence.support_level
    ? SUPPORT_LEVEL_CONFIG[evidence.support_level]
    : null;

  return (
    <article className="rounded-lg border border-border bg-surface-2 p-3">
      <p className="text-sm text-foreground mb-2">
        {evidence.claim || "Hallazgo sin descripción"}
      </p>
      <div className="flex items-center gap-2">
        {supportConfig && (
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-xs font-medium border",
              supportConfig.color
            )}
          >
            {supportConfig.label}
          </span>
        )}
        {evidence.confidence !== undefined && (
          <span className="text-xs text-muted">
            Confianza: {Math.round(evidence.confidence * 100)}%
          </span>
        )}
      </div>
    </article>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <DocumentTextIcon className="h-12 w-12 text-muted/50 mb-3" />
      <p className="text-sm text-muted">{message}</p>
    </div>
  );
}
