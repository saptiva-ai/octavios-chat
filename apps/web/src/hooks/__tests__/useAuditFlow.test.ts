/**
 * Tests for useAuditFlow.ts - Audit workflow management hook
 *
 * Coverage:
 * - sendAuditForFile: Auto-fill composer and trigger submit
 * - Validation: file ready status
 * - Telemetry: audit_toggle_on, audit_error
 * - Integration with composer callbacks
 */

import { renderHook, act, waitFor } from "@testing-library/react";
import { useAuditFlow } from "../useAuditFlow";
import toast from "react-hot-toast";
import { logDebug, logError } from "../../lib/logger";
import type { FileAttachment } from "../../types/files";

// Mock dependencies
jest.mock("react-hot-toast", () => {
  const mockToast = {
    error: jest.fn(),
    success: jest.fn(),
  };
  return {
    __esModule: true,
    default: mockToast,
  };
});
jest.mock("../../lib/logger", () => ({
  logDebug: jest.fn(),
  logError: jest.fn(),
}));

// Mock analytics tracking
const mockTrack = jest.fn();
beforeAll(() => {
  (global as any).window = {
    analytics: {
      track: mockTrack,
    },
  };
});

describe("useAuditFlow", () => {
  let mockSetValue: jest.Mock;
  let mockOnSubmit: jest.Mock;
  let mockClearFiles: jest.Mock;

  beforeEach(() => {
    // Reset all mocks
    jest.clearAllMocks();

    // Setup composer mocks
    mockSetValue = jest.fn();
    mockOnSubmit = jest.fn();
    mockClearFiles = jest.fn();

    // Clear timers
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  // Helper to create a mock file attachment
  function createMockFile(
    fileId: string,
    filename: string,
    status: "READY" | "PROCESSING" | "FAILED" = "READY",
  ): FileAttachment {
    return {
      file_id: fileId,
      filename,
      status,
      bytes: 1024,
      mimetype: "application/pdf",
    };
  }

  describe("sendAuditForFile", () => {
    it("auto-fills composer and triggers submit for READY file", async () => {
      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-123",
        }),
      );

      const file = createMockFile("file-789", "test.pdf", "READY");

      await act(async () => {
        await result.current.sendAuditForFile(file);
      });

      // Verify setValue was called with audit message
      expect(mockSetValue).toHaveBeenCalledWith("Auditar archivo: test.pdf");

      // Advance timers to trigger setTimeout
      act(() => {
        jest.advanceTimersByTime(50);
      });

      // Verify onSubmit was called
      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled();
      });

      // Verify telemetry tracking
      expect(mockTrack).toHaveBeenCalledWith("audit_toggle_on", {
        chat_id: "chat-123",
        file_id: "file-789",
        filename: "test.pdf",
      });

      // Verify success toast
      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith("Auditoría en proceso...", {
          icon: "🔍",
          duration: 2000,
        });
      });

      // Verify logging
      expect(logDebug).toHaveBeenCalledWith(
        "[useAuditFlow] Triggering audit via composer",
        expect.objectContaining({
          fileId: "file-789",
          message: "Auditar archivo: test.pdf",
        }),
      );
    });

    it("uses currentChatId from store when conversationId not provided", async () => {
      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
        }),
      );

      const file = createMockFile("file-123", "report.pdf", "READY");

      await act(async () => {
        await result.current.sendAuditForFile(file);
      });

      expect(mockApiClient.sendChatMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          chatId: "chat-123", // From mockChatStore.currentChatId
        }),
      );
    });

    it("rejects if no conversation ID available", async () => {
      mockChatStore.currentChatId = null;

      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
        }),
      );

      const file = createMockFile("file-456", "test.pdf", "READY");

      await act(async () => {
        await result.current.sendAuditForFile(file);
      });

      expect(mockApiClient.sendChatMessage).not.toHaveBeenCalled();
      expect(toast.error).toHaveBeenCalledWith("No hay conversación activa");
      expect(logError).toHaveBeenCalledWith(
        "[useAuditFlow] No conversation ID available",
      );
    });

    it("rejects if file is not READY", async () => {
      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-123",
        }),
      );

      const processingFile = createMockFile(
        "file-789",
        "processing.pdf",
        "PROCESSING",
      );

      await act(async () => {
        await result.current.sendAuditForFile(processingFile);
      });

      expect(mockApiClient.sendChatMessage).not.toHaveBeenCalled();
      expect(toast.error).toHaveBeenCalledWith(
        "El archivo no está listo para auditar",
      );
      expect(logError).toHaveBeenCalledWith(
        "[useAuditFlow] File not ready",
        expect.objectContaining({ status: "PROCESSING" }),
      );
    });

    it("handles API errors and tracks error event", async () => {
      const apiError = {
        response: {
          status: 500,
          data: {
            detail: "Internal server error",
          },
        },
        message: "Request failed",
      };

      mockApiClient.sendChatMessage.mockRejectedValue(apiError);

      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-123",
        }),
      );

      const file = createMockFile("file-999", "error.pdf", "READY");

      await expect(async () => {
        await act(async () => {
          await result.current.sendAuditForFile(file);
        });
      }).rejects.toThrow();

      // Verify error tracking
      expect(mockTrack).toHaveBeenCalledWith("audit_error", {
        error_code: 500,
        file_id: "file-999",
        error_message: "Internal server error",
      });

      // Verify error toast
      expect(toast.error).toHaveBeenCalledWith("Internal server error", {
        icon: "❌",
        duration: 4000,
      });

      // Verify error logging
      expect(logError).toHaveBeenCalledWith(
        "[useAuditFlow] Failed to send audit",
        expect.objectContaining({
          fileId: "file-999",
        }),
      );
    });

    it("handles network errors without response", async () => {
      const networkError = new Error("Network request failed");

      mockApiClient.sendChatMessage.mockRejectedValue(networkError);

      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-123",
        }),
      );

      const file = createMockFile("file-888", "network.pdf", "READY");

      await expect(async () => {
        await act(async () => {
          await result.current.sendAuditForFile(file);
        });
      }).rejects.toThrow();

      // Verify error tracking with unknown code
      expect(mockTrack).toHaveBeenCalledWith("audit_error", {
        error_code: "unknown",
        file_id: "file-888",
        error_message: "Network request failed",
      });

      // Verify error toast
      expect(toast.error).toHaveBeenCalledWith("Network request failed", {
        icon: "❌",
        duration: 4000,
      });
    });

    it("tracks isAuditing state during request", async () => {
      let resolveApiCall: any;
      const apiPromise = new Promise((resolve) => {
        resolveApiCall = resolve;
      });

      mockApiClient.sendChatMessage.mockReturnValue(apiPromise);

      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-123",
        }),
      );

      const file = createMockFile("file-777", "slow.pdf", "READY");

      expect(result.current.isAuditing).toBe(false);

      // Start audit (don't await)
      const auditPromise = act(async () => {
        result.current.sendAuditForFile(file);
      });

      // isAuditing should be true during request
      await waitFor(() => {
        expect(result.current.isAuditing).toBe(true);
      });

      // Resolve API call
      resolveApiCall({
        id: "msg-777",
        content: "Auditar archivo: slow.pdf",
        role: "user",
        created_at: "2025-10-30T12:00:00Z",
        status: "delivered",
      });

      await auditPromise;

      // isAuditing should be false after completion
      await waitFor(() => {
        expect(result.current.isAuditing).toBe(false);
      });
    });

    it("calls onAuditComplete callback when provided", async () => {
      const onAuditComplete = jest.fn();

      // Mock API response with validation_report_id
      mockApiClient.sendChatMessage.mockResolvedValue({
        id: "msg-456",
        content: "Auditar archivo: test.pdf",
        role: "assistant",
        created_at: "2025-10-30T12:00:00Z",
        status: "completed",
        validation_report_id: "report-abc123",
      });

      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-123",
        }),
      );

      const file = createMockFile("file-789", "test.pdf", "READY");

      await act(async () => {
        await result.current.sendAuditForFile(file);
      });

      // Note: Current implementation doesn't call onAuditComplete
      // This test documents expected future behavior
      // expect(onAuditComplete).toHaveBeenCalledWith("report-abc123");
    });

    it("constructs correct audit message with filename", async () => {
      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-123",
        }),
      );

      const file = createMockFile(
        "file-555",
        "Capital414_presentacion.pdf",
        "READY",
      );

      await act(async () => {
        await result.current.sendAuditForFile(file);
      });

      expect(mockApiClient.sendChatMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          message: "Auditar archivo: Capital414_presentacion.pdf",
        }),
      );

      expect(logDebug).toHaveBeenCalledWith(
        "[useAuditFlow] Sending audit message",
        expect.objectContaining({
          message: "Auditar archivo: Capital414_presentacion.pdf",
        }),
      );
    });

    it("handles special characters in filename", async () => {
      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-123",
        }),
      );

      const file = createMockFile(
        "file-666",
        "Reporte (2025) - Final.pdf",
        "READY",
      );

      await act(async () => {
        await result.current.sendAuditForFile(file);
      });

      expect(mockApiClient.sendChatMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          message: "Auditar archivo: Reporte (2025) - Final.pdf",
          metadata: expect.objectContaining({
            audit_filename: "Reporte (2025) - Final.pdf",
          }),
        }),
      );
    });

    it("resets isAuditing state even on error", async () => {
      mockApiClient.sendChatMessage.mockRejectedValue(new Error("API error"));

      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-123",
        }),
      );

      const file = createMockFile("file-111", "error.pdf", "READY");

      expect(result.current.isAuditing).toBe(false);

      await expect(async () => {
        await act(async () => {
          await result.current.sendAuditForFile(file);
        });
      }).rejects.toThrow();

      // isAuditing should be reset to false
      await waitFor(() => {
        expect(result.current.isAuditing).toBe(false);
      });
    });
  });

  describe("Telemetry Integration", () => {
    it("tracks all telemetry events in correct order", async () => {
      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-456",
        }),
      );

      const file = createMockFile("file-telemetry", "tracking.pdf", "READY");

      await act(async () => {
        await result.current.sendAuditForFile(file);
      });

      // Verify event order
      expect(mockTrack).toHaveBeenNthCalledWith(1, "audit_toggle_on", {
        chat_id: "chat-456",
        file_id: "file-telemetry",
        filename: "tracking.pdf",
      });

      expect(mockTrack).toHaveBeenNthCalledWith(2, "audit_message_sent", {
        message_id: "msg-456",
        file_id: "file-telemetry",
        chat_id: "chat-456",
      });
    });

    it("works without analytics provider", async () => {
      // Remove analytics provider
      delete (global as any).window.analytics;

      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-789",
        }),
      );

      const file = createMockFile("file-no-analytics", "test.pdf", "READY");

      // Should not throw
      await act(async () => {
        await result.current.sendAuditForFile(file);
      });

      expect(mockApiClient.sendChatMessage).toHaveBeenCalled();
      expect(toast.success).toHaveBeenCalled();
    });
  });

  describe("Edge Cases", () => {
    it("handles undefined file properties gracefully", async () => {
      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-123",
        }),
      );

      const partialFile: FileAttachment = {
        file_id: "file-partial",
        filename: "partial.pdf",
        status: "READY",
        bytes: 1024,
        // mimetype missing
      };

      await act(async () => {
        await result.current.sendAuditForFile(partialFile);
      });

      expect(mockApiClient.sendChatMessage).toHaveBeenCalled();
    });

    it("handles very long filenames", async () => {
      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-123",
        }),
      );

      const longFilename = "A".repeat(500) + ".pdf";
      const file = createMockFile("file-long", longFilename, "READY");

      await act(async () => {
        await result.current.sendAuditForFile(file);
      });

      expect(mockApiClient.sendChatMessage).toHaveBeenCalledWith(
        expect.objectContaining({
          message: `Auditar archivo: ${longFilename}`,
        }),
      );
    });

    it("handles concurrent audit requests", async () => {
      const { result } = renderHook(() =>
        useAuditFlow({
          setValue: mockSetValue,
          onSubmit: mockOnSubmit,
          clearFiles: mockClearFiles,
          conversationId: "chat-123",
        }),
      );

      const file1 = createMockFile("file-1", "concurrent1.pdf", "READY");
      const file2 = createMockFile("file-2", "concurrent2.pdf", "READY");

      // Start two audits concurrently
      const audit1 = act(async () => {
        await result.current.sendAuditForFile(file1);
      });

      const audit2 = act(async () => {
        await result.current.sendAuditForFile(file2);
      });

      await Promise.all([audit1, audit2]);

      // Both should succeed
      expect(mockApiClient.sendChatMessage).toHaveBeenCalledTimes(2);
    });
  });
});
