"use client";

/**
 * PreviewAttachment Component
 *
 * Portado desde: Vercel AI Chatbot
 * Fuente: /home/jazielflo/Proyects/ai-chatbot/components/preview-attachment.tsx
 *
 * Adaptaciones para Octavio's Chat:
 * - Usa tipos FileAttachment de Octavio's Chat
 * - Mantiene compatibilidad con sistema Files V1
 * - Integrado con design system existente (Tailwind + CSS variables)
 * - Soporte para múltiples MIME types
 * - Thumbnails reales desde backend (PDFs + imágenes)
 */

import * as React from "react";
import type { FileAttachment } from "@/types/files";
import { cn } from "@/lib/utils";
import { ThumbnailImage } from "./ThumbnailImage";
import { logDebug, logError } from "@/lib/logger";

interface PreviewAttachmentProps {
  attachment: FileAttachment;
  isUploading?: boolean;
  onRemove?: () => void;
  onAudit?: () => void;
  showAuditButton?: boolean;
  className?: string;
}

/**
 * Componente para preview de archivos adjuntos
 *
 * Características:
 * - Muestra thumbnail para imágenes
 * - Icono genérico para otros tipos de archivos
 * - Indicador de carga durante upload
 * - Botón de eliminar en hover
 * - Label con nombre de archivo en gradient
 */
export function PreviewAttachment({
  attachment,
  isUploading = false,
  onRemove,
  onAudit,
  showAuditButton = false,
  className,
}: PreviewAttachmentProps) {
  const { filename, mimetype, status } = attachment;

  // Determinar estado visual (DEBE ir ANTES del useEffect)
  const isProcessing = status === "PROCESSING" || isUploading;
  const isFailed = status === "FAILED";
  const isReady = status === "READY";

  // Debug: Log prop values on render (disabled in production)
  React.useEffect(() => {
    if (process.env.NODE_ENV === "development") {
      // eslint-disable-next-line no-console
      console.log("[PreviewAttachment] Rendered with props", {
        filename,
        mimetype,
        status,
        file_id: attachment.file_id,
        isProcessing,
        isFailed,
        isReady,
        shouldShowFallback:
          isProcessing ||
          isFailed ||
          !(
            (mimetype?.startsWith("image/") || mimetype?.includes("pdf")) &&
            status === "READY"
          ),
      });
    }
  }, [
    filename,
    mimetype,
    status,
    attachment.file_id,
    isProcessing,
    isFailed,
    isReady,
  ]);

  // Determinar si es imagen basado en MIME type
  const isImage = mimetype?.startsWith("image/");
  const isPdf = mimetype?.includes("pdf");

  // SIEMPRE mostrar fallback primero, luego ThumbnailImage intenta cargar cuando READY
  // Esto asegura que el usuario vea algo inmediatamente
  const canShowThumbnail = (isImage || isPdf) && isReady;

  // Durante PROCESSING, forzar fallback para feedback inmediato
  const shouldShowFallback = isProcessing || isFailed || !canShowThumbnail;

  return (
    <div
      className={cn(
        "group relative w-32 h-48 overflow-hidden rounded-xl border shadow-sm transition-all duration-200 hover:shadow-md",
        isFailed ? "border-red-500/50 bg-red-500/10" : "border-border bg-muted",
        className,
      )}
      data-testid="preview-attachment"
    >
      {/* Content: Thumbnail or File Icon Preview */}
      {shouldShowFallback ? (
        <div className="relative flex size-full flex-col items-center justify-center gap-2 bg-gradient-to-br from-zinc-800 to-zinc-900 p-3">
          {/* File icon SVG - Fallback cuando no hay thumbnail */}
          {isPdf ? (
            // PDF Preview - Simula documento con efecto de página
            <div className="flex size-full flex-col items-center justify-center gap-1">
              {/* PDF Document Icon - Más realista */}
              <div className="relative flex h-16 w-12 flex-col items-center justify-center rounded-sm bg-white shadow-lg">
                {/* Corner fold effect */}
                <div className="absolute top-0 right-0 h-0 w-0 border-[8px] border-t-zinc-300 border-r-zinc-300 border-b-transparent border-l-transparent"></div>
                {/* PDF Lines simulation */}
                <div className="flex flex-col gap-0.5 px-1.5">
                  <div className="h-0.5 w-8 rounded-full bg-zinc-300"></div>
                  <div className="h-0.5 w-6 rounded-full bg-zinc-300"></div>
                  <div className="h-0.5 w-7 rounded-full bg-zinc-300"></div>
                  <div className="h-0.5 w-5 rounded-full bg-zinc-300"></div>
                </div>
                {/* PDF Label */}
                <div className="absolute bottom-1 flex items-center justify-center rounded-sm bg-red-500 px-1 py-0.5">
                  <span className="text-[8px] font-bold text-white">PDF</span>
                </div>
              </div>
              {/* Filename */}
              <span className="mt-1 truncate text-[9px] font-medium text-zinc-400 w-full text-center px-1">
                {filename}
              </span>
            </div>
          ) : isImage ? (
            // Image Preview - Icono de imagen con diseño atractivo
            <div className="flex size-full flex-col items-center justify-center gap-1">
              {/* Frame simulando una foto polaroid */}
              <div className="relative flex h-16 w-16 flex-col items-center justify-center rounded-md bg-gradient-to-br from-blue-500 to-indigo-600 p-2 shadow-lg">
                {/* Icono de imagen */}
                <svg
                  className="h-10 w-10 text-white"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={1.5}
                  viewBox="0 0 24 24"
                >
                  <rect
                    x="3"
                    y="3"
                    width="18"
                    height="18"
                    rx="2"
                    ry="2"
                    strokeWidth={2}
                  />
                  <circle cx="8.5" cy="8.5" r="1.5" fill="currentColor" />
                  <polyline points="21 15 16 10 5 21" strokeWidth={2} />
                </svg>
              </div>
              {/* Filename */}
              <span className="mt-1 truncate text-[9px] font-medium text-zinc-400 w-full text-center px-1">
                {filename}
              </span>
            </div>
          ) : (
            // Generic file icon con diseño mejorado
            <div className="flex size-full flex-col items-center justify-center gap-2">
              <svg
                className="h-12 w-12 text-zinc-500"
                fill="none"
                stroke="currentColor"
                strokeWidth={1.5}
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
                />
              </svg>
              {/* Extension label */}
              <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                {getFileExtension(filename)}
              </span>
            </div>
          )}
        </div>
      ) : (
        <>
          {/* Real thumbnail from backend with auth */}
          <ThumbnailImage
            fileId={attachment.file_id}
            alt={filename ?? "Archivo adjunto"}
            className="size-full object-cover"
          />
          {/* Filename overlay - White text with black outline */}
          <div className="absolute bottom-0 left-0 right-0 flex items-center justify-center bg-gradient-to-t from-black/70 to-transparent px-2 py-3">
            <span
              className="truncate text-xs font-semibold text-white"
              style={{
                textShadow:
                  "0 0 4px rgba(0,0,0,0.9), 0 0 2px rgba(0,0,0,0.8), 1px 1px 2px rgba(0,0,0,0.9), -1px -1px 2px rgba(0,0,0,0.9)",
              }}
            >
              {filename}
            </span>
          </div>
        </>
      )}

      {/* Loading Overlay */}
      {isProcessing && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-black/50"
          data-testid="attachment-loader"
        >
          <svg
            className="h-4 w-4 animate-spin text-white"
            fill="none"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              fill="currentColor"
            />
          </svg>
        </div>
      )}

      {/* Error Overlay */}
      {isFailed && (
        <div
          className="absolute inset-0 flex items-center justify-center bg-red-500/20"
          data-testid="attachment-error"
        >
          <svg
            className="h-5 w-5 text-red-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </div>
      )}

      {/* Audit Button hidden for open-source build */}
      {/* onAudit && showAuditButton && !isProcessing && isReady && (
        <button ...>...</button>
      ) */}

      {/* Remove Button - Superior derecha, dentro del thumbnail */}
      {onRemove && !isProcessing && (
        <button
          className="absolute top-1 right-1 flex size-6 items-center justify-center rounded-full bg-red-500 opacity-0 shadow-lg transition-all hover:scale-110 hover:bg-red-600 group-hover:opacity-100"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onRemove();
          }}
          type="button"
          aria-label={`Eliminar ${filename}`}
        >
          <svg
            className="h-3.5 w-3.5 text-white"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      )}
    </div>
  );
}

/**
 * Helper: Extraer extensión de archivo
 */
function getFileExtension(filename?: string): string {
  if (!filename) return "FILE";
  const parts = filename.split(".");
  if (parts.length === 1) return "FILE";
  const ext = parts[parts.length - 1].toUpperCase();
  return ext.length <= 4 ? ext : "FILE";
}
