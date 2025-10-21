/**
 * Tests for useFiles.ts - File upload and attachment management hook
 *
 * Coverage:
 * - uploadFile: Validation, upload, idempotency, error handling
 * - uploadFiles: Batch uploads
 * - Attachment management: add, remove, clear
 * - Rate limiting: Client-side checks
 * - Persistence: Integration with files-store
 * - Progress tracking
 */

import { renderHook, act, waitFor } from "@testing-library/react";
import { useFiles } from "../useFiles";
import { useFilesStore } from "../../lib/stores/files-store";
import { useApiClient } from "../../lib/api-client";
import toast from "react-hot-toast";
import { sha256Hex } from "../../lib/hash";
import type { FileAttachment, FileIngestBulkResponse } from "../../types/files";

// Mock dependencies
jest.mock("../../lib/api-client");
jest.mock("../../lib/hash");
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

// Mock crypto.randomUUID
Object.defineProperty(global, "crypto", {
  value: {
    randomUUID: jest.fn(() => "test-uuid-123"),
  },
  writable: true,
});

// Mock fetch
global.fetch = jest.fn();

describe("useFiles", () => {
  let mockApiClient: any;
  let filesStore: ReturnType<typeof useFilesStore.getState>;

  beforeEach(() => {
    // Reset all mocks
    jest.clearAllMocks();

    // Setup API client mock
    mockApiClient = {
      getToken: jest.fn().mockReturnValue("test-token"),
    };
    (useApiClient as jest.Mock).mockReturnValue(mockApiClient);

    // Setup hash mock
    (sha256Hex as jest.Mock).mockResolvedValue("abc123def456");

    // Setup fetch mock
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () =>
        ({
          files: [
            {
              file_id: "file-123",
              filename: "test.pdf",
              status: "READY",
              bytes: 1024,
              mimetype: "application/pdf",
            },
          ],
        }) as FileIngestBulkResponse,
    });

    // Clear files store
    filesStore = useFilesStore.getState();
    filesStore.clearAll();
  });

  // Helper to create a mock File with arrayBuffer support
  function createMockFile(content: string, name: string, type: string): File {
    const file = new File([content], name, { type });
    // Add arrayBuffer method for Node environment
    (file as any).arrayBuffer = jest
      .fn()
      .mockResolvedValue(new ArrayBuffer(content.length));
    return file;
  }

  describe("uploadFile", () => {
    it("successfully uploads a valid file", async () => {
      const { result } = renderHook(() => useFiles());

      const file = createMockFile("content", "test.pdf", "application/pdf");

      let attachment: FileAttachment | null = null;

      await act(async () => {
        attachment = await result.current.uploadFile(file);
      });

      expect(attachment).toEqual({
        file_id: "file-123",
        filename: "test.pdf",
        status: "READY",
        bytes: 1024,
        mimetype: "application/pdf",
      });

      expect(global.fetch).toHaveBeenCalledWith(
        "/api/files/upload",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({
            Authorization: "Bearer test-token",
            "X-Trace-Id": "test-uuid-123",
            "Idempotency-Key": expect.stringContaining("abc123def456"),
          }),
        }),
      );

      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining("test.pdf listo"),
        { duration: 2500 },
      );
    });

    it("validates file size", async () => {
      const { result } = renderHook(() => useFiles());

      // Create file larger than 50MB (default limit)
      const largeContent = "x".repeat(51 * 1024 * 1024);
      const largeFile = createMockFile(
        largeContent,
        "large.pdf",
        "application/pdf",
      );
      // Override size for validation
      Object.defineProperty(largeFile, "size", {
        value: 51 * 1024 * 1024,
      });

      let attachment: FileAttachment | null = null;

      await act(async () => {
        attachment = await result.current.uploadFile(largeFile);
      });

      expect(attachment).toBeNull();
      expect(result.current.error).toContain("demasiado grande");
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("validates file type", async () => {
      const { result } = renderHook(() => useFiles());

      const unsupportedFile = createMockFile(
        "content",
        "test.exe",
        "application/x-msdownload",
      );

      let attachment: FileAttachment | null = null;

      await act(async () => {
        attachment = await result.current.uploadFile(unsupportedFile);
      });

      expect(attachment).toBeNull();
      expect(result.current.error).toContain("no soportado");
      expect(global.fetch).not.toHaveBeenCalled();
    });

    it("enforces client-side rate limiting", async () => {
      const { result } = renderHook(() => useFiles());

      const file = createMockFile("content", "test.pdf", "application/pdf");

      // Upload 5 files quickly (rate limit)
      for (let i = 0; i < 5; i++) {
        await act(async () => {
          await result.current.uploadFile(file);
        });
      }

      // 6th upload should be rate limited
      let attachment: FileAttachment | null = null;

      await act(async () => {
        attachment = await result.current.uploadFile(file);
      });

      expect(attachment).toBeNull();
      expect(result.current.error).toContain("Demasiados archivos");
    });

    it("generates idempotency key from file hash", async () => {
      const { result } = renderHook(() => useFiles());

      const file = createMockFile("content", "test.pdf", "application/pdf");

      await act(async () => {
        await result.current.uploadFile(file, "chat-123");
      });

      expect(sha256Hex).toHaveBeenCalled();
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/files/upload",
        expect.objectContaining({
          headers: expect.objectContaining({
            "Idempotency-Key": "abc123def456:chat-123",
          }),
        }),
      );
    });

    it("tracks upload progress", async () => {
      const { result } = renderHook(() => useFiles());

      const file = createMockFile("content", "test.pdf", "application/pdf");

      expect(result.current.isUploading).toBe(false);
      expect(result.current.uploadProgress).toBeNull();

      const uploadPromise = act(async () => {
        await result.current.uploadFile(file);
      });

      // During upload, isUploading should be true
      // (Note: This is tricky to test due to async timing)

      await uploadPromise;

      // After upload, should be reset
      expect(result.current.isUploading).toBe(false);
      expect(result.current.uploadProgress).toBeNull();
    });

    it("handles 413 (file too large) error", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 413,
        json: async () => ({}),
      });

      const { result } = renderHook(() => useFiles());

      const file = createMockFile("content", "test.pdf", "application/pdf");

      let attachment: FileAttachment | null = null;

      await act(async () => {
        attachment = await result.current.uploadFile(file);
      });

      expect(attachment).toBeNull();
      expect(result.current.error).toContain("demasiado grande");
    });

    it("handles 415 (unsupported format) error", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 415,
        json: async () => ({}),
      });

      const { result } = renderHook(() => useFiles());

      const file = createMockFile("content", "test.pdf", "application/pdf");

      let attachment: FileAttachment | null = null;

      await act(async () => {
        attachment = await result.current.uploadFile(file);
      });

      expect(attachment).toBeNull();
      expect(result.current.error).toContain("Formato no soportado");
    });

    it("handles 429 (rate limit) error", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 429,
        json: async () => ({}),
      });

      const { result } = renderHook(() => useFiles());

      const file = createMockFile("content", "test.pdf", "application/pdf");

      let attachment: FileAttachment | null = null;

      await act(async () => {
        attachment = await result.current.uploadFile(file);
      });

      expect(attachment).toBeNull();
      expect(result.current.error).toContain("Demasiados archivos");
    });

    it("handles 500 (server error) error", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({}),
      });

      const { result } = renderHook(() => useFiles());

      const file = createMockFile("content", "test.pdf", "application/pdf");

      let attachment: FileAttachment | null = null;

      await act(async () => {
        attachment = await result.current.uploadFile(file);
      });

      expect(attachment).toBeNull();
      expect(result.current.error).toContain("Error del servidor");
    });

    it("handles FAILED processing status", async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({
          files: [
            {
              file_id: "file-123",
              filename: "test.pdf",
              status: "FAILED",
              bytes: 1024,
              error: {
                code: "EXTRACTION_FAILED",
                detail: "Processing failed",
              },
            },
          ],
        }),
      });

      const { result } = renderHook(() => useFiles());

      const file = createMockFile("content", "test.pdf", "application/pdf");

      let attachment: FileAttachment | null = null;

      await act(async () => {
        attachment = await result.current.uploadFile(file);
      });

      expect(attachment).toBeNull();
      expect(result.current.error).toContain("procesar el archivo");
    });

    it("persists attachment to store after successful upload", async () => {
      const { result } = renderHook(() => useFiles("chat-123"));

      const file = createMockFile("content", "test.pdf", "application/pdf");

      await act(async () => {
        await result.current.uploadFile(file);
      });

      const storedFiles = filesStore.getForChat("chat-123");
      expect(storedFiles).toHaveLength(1);
      expect(storedFiles[0].file_id).toBe("file-123");
    });
  });

  describe("uploadFiles (batch)", () => {
    it("uploads multiple files successfully", async () => {
      const { result } = renderHook(() => useFiles());

      const files = [
        createMockFile("content1", "test1.pdf", "application/pdf"),
        createMockFile("content2", "test2.pdf", "application/pdf"),
      ];

      // Mock different responses for each file
      (global.fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            files: [
              {
                file_id: "file-1",
                filename: "test1.pdf",
                status: "READY",
                bytes: 1024,
              },
            ],
          }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            files: [
              {
                file_id: "file-2",
                filename: "test2.pdf",
                status: "READY",
                bytes: 2048,
              },
            ],
          }),
        });

      let attachments: FileAttachment[] = [];

      await act(async () => {
        attachments = await result.current.uploadFiles(files);
      });

      expect(attachments).toHaveLength(2);
      expect(attachments[0].file_id).toBe("file-1");
      expect(attachments[1].file_id).toBe("file-2");
    });

    it("handles empty files array", async () => {
      const { result } = renderHook(() => useFiles());

      let attachments: FileAttachment[] = [];

      await act(async () => {
        attachments = await result.current.uploadFiles([]);
      });

      expect(attachments).toEqual([]);
    });

    it("handles partial failures", async () => {
      const { result } = renderHook(() => useFiles());

      const files = [
        createMockFile("content1", "test1.pdf", "application/pdf"),
        createMockFile("content2", "test2.txt", "text/plain"), // Invalid
      ];

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          files: [
            {
              file_id: "file-1",
              filename: "test1.pdf",
              status: "READY",
              bytes: 1024,
            },
          ],
        }),
      });

      let attachments: FileAttachment[] = [];

      await act(async () => {
        attachments = await result.current.uploadFiles(files);
      });

      expect(attachments).toHaveLength(1);
      expect(result.current.error).toContain("1 de 2 archivos fallaron");
    });
  });

  describe("Attachment Management", () => {
    it("adds attachment to local state and store", async () => {
      const { result } = renderHook(() => useFiles("chat-123"));

      const attachment: FileAttachment = {
        file_id: "file-456",
        filename: "manual.pdf",
        status: "READY",
        bytes: 2048,
      };

      act(() => {
        result.current.addAttachment(attachment);
      });

      expect(result.current.attachments).toHaveLength(1);
      expect(result.current.attachments[0].file_id).toBe("file-456");

      // Check store
      const storedFiles = filesStore.getForChat("chat-123");
      expect(storedFiles).toHaveLength(1);
    });

    it("removes attachment from local state and store", async () => {
      const { result } = renderHook(() => useFiles("chat-123"));

      const attachment: FileAttachment = {
        file_id: "file-789",
        filename: "remove-me.pdf",
        status: "READY",
        bytes: 1024,
      };

      act(() => {
        result.current.addAttachment(attachment);
      });

      expect(result.current.attachments).toHaveLength(1);

      act(() => {
        result.current.removeAttachment("file-789");
      });

      expect(result.current.attachments).toHaveLength(0);

      // Check store
      const storedFiles = filesStore.getForChat("chat-123");
      expect(storedFiles).toHaveLength(0);
    });

    it("clears all attachments", async () => {
      const { result } = renderHook(() => useFiles("chat-123"));

      const attachments: FileAttachment[] = [
        {
          file_id: "file-1",
          filename: "test1.pdf",
          status: "READY",
          bytes: 1024,
        },
        {
          file_id: "file-2",
          filename: "test2.pdf",
          status: "READY",
          bytes: 2048,
        },
      ];

      act(() => {
        attachments.forEach((att) => result.current.addAttachment(att));
      });

      expect(result.current.attachments).toHaveLength(2);

      act(() => {
        result.current.clearAttachments();
      });

      expect(result.current.attachments).toHaveLength(0);

      // Check store
      const storedFiles = filesStore.getForChat("chat-123");
      expect(storedFiles).toHaveLength(0);
    });

    it("loads attachments from store on mount", () => {
      // Pre-populate store
      filesStore.addToChat("chat-existing", {
        file_id: "file-stored",
        filename: "stored.pdf",
        status: "READY",
        bytes: 1024,
      });

      const { result } = renderHook(() => useFiles("chat-existing"));

      expect(result.current.attachments).toHaveLength(1);
      expect(result.current.attachments[0].file_id).toBe("file-stored");
    });

    it("syncs attachments when chatId changes", () => {
      // Pre-populate stores
      filesStore.addToChat("chat-A", {
        file_id: "file-A",
        filename: "a.pdf",
        status: "READY",
        bytes: 1024,
      });

      filesStore.addToChat("chat-B", {
        file_id: "file-B",
        filename: "b.pdf",
        status: "READY",
        bytes: 2048,
      });

      const { result, rerender } = renderHook(
        ({ chatId }) => useFiles(chatId),
        {
          initialProps: { chatId: "chat-A" },
        },
      );

      expect(result.current.attachments).toHaveLength(1);
      expect(result.current.attachments[0].file_id).toBe("file-A");

      // Switch chat
      rerender({ chatId: "chat-B" });

      expect(result.current.attachments).toHaveLength(1);
      expect(result.current.attachments[0].file_id).toBe("file-B");
    });

    it("uses 'draft' as default chatId", () => {
      const { result } = renderHook(() => useFiles());

      const attachment: FileAttachment = {
        file_id: "file-draft",
        filename: "draft.pdf",
        status: "READY",
        bytes: 1024,
      };

      act(() => {
        result.current.addAttachment(attachment);
      });

      // Check store uses "draft" key
      const storedFiles = filesStore.getForChat("draft");
      expect(storedFiles).toHaveLength(1);
    });
  });

  describe("Error Management", () => {
    it("clears error", async () => {
      const { result } = renderHook(() => useFiles());

      // Trigger an error by uploading invalid file
      const invalidFile = createMockFile(
        "content",
        "test.exe",
        "application/x-msdownload",
      );

      await act(async () => {
        await result.current.uploadFile(invalidFile);
      });

      // Verify error was set
      expect(result.current.error).not.toBeNull();

      // Clear the error
      act(() => {
        result.current.clearError();
      });

      expect(result.current.error).toBeNull();
    });
  });
});
