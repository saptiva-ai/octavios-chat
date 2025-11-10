/**
 * useAuditFlow - Hook for managing audit workflow
 *
 * Handles:
 * - Auto-filling composer with audit command
 * - Triggering audit execution via normal message flow
 * - Telemetry tracking
 *
 * Usage:
 * ```tsx
 * const { sendAuditForFile, isAuditing } = useAuditFlow({
 *   setValue: (msg) => setInputValue(msg),
 *   onSubmit: () => handleSubmit()
 * });
 * await sendAuditForFile(fileAttachment);
 * ```
 */

import { useCallback, useState } from "react";
import toast from "react-hot-toast";
import { logDebug, logError } from "../lib/logger";
import type { FileAttachment } from "../types/files";

// Telemetry function - to be implemented with actual analytics
function track(event: string, data: Record<string, any>) {
  logDebug(`[Telemetry] ${event}`, data);
  // TODO: Integrate with actual analytics (e.g., PostHog, Mixpanel)
  if (typeof window !== "undefined" && (window as any).analytics) {
    (window as any).analytics.track(event, data);
  }
}

interface UseAuditFlowOptions {
  /** Callback to set the composer input value */
  setValue: (value: string) => void;
  /** Callback to trigger message submission */
  onSubmit: () => void | Promise<void>;
  /** Optional conversation ID for telemetry */
  conversationId?: string;
}

export function useAuditFlow(options: UseAuditFlowOptions) {
  const { setValue, onSubmit, conversationId } = options;
  const [isAuditing, setIsAuditing] = useState(false);

  /**
   * Send audit message for a file
   *
   * Workflow:
   * 1. Track "audit_toggle_on" event
   * 2. Auto-fill composer with audit command
   * 3. Trigger submit (uses normal chat flow with SSE/streaming)
   * 4. Receive audit report as assistant message
   */
  const sendAuditForFile = useCallback(
    async (file: FileAttachment): Promise<void> => {
      if (file.status !== "READY") {
        logError("[useAuditFlow] File not ready", { status: file.status });
        toast.error("El archivo no está listo para auditar");
        return;
      }

      setIsAuditing(true);

      try {
        // Telemetry: Track toggle activation
        track("audit_toggle_on", {
          chat_id: conversationId || "unknown",
          file_id: file.file_id,
          filename: file.filename,
        });

        // Construct audit message
        const auditMessage = `Auditar archivo: ${file.filename}`;

        logDebug("[useAuditFlow] Triggering audit via composer", {
          fileId: file.file_id,
          message: auditMessage,
        });

        // Auto-fill composer input
        setValue(auditMessage);

        // Trigger submit after a brief delay to ensure setValue has taken effect
        setTimeout(async () => {
          await onSubmit();

          // Success notification
          toast.success("Auditoría en proceso...", {
            icon: "🔍",
            duration: 2000,
          });

          logDebug("[useAuditFlow] Audit triggered successfully");
        }, 50);
      } catch (error: any) {
        const errorMessage = error?.message || "Error al iniciar auditoría";

        logError("[useAuditFlow] Failed to trigger audit", {
          error,
          fileId: file.file_id,
        });

        // Telemetry: Error tracking
        track("audit_error", {
          error_code: "trigger_failed",
          file_id: file.file_id,
          error_message: errorMessage,
        });

        toast.error(errorMessage, {
          icon: "❌",
          duration: 4000,
        });

        throw error;
      } finally {
        setIsAuditing(false);
      }
    },
    [setValue, onSubmit, conversationId],
  );

  return {
    sendAuditForFile,
    isAuditing,
  };
}
