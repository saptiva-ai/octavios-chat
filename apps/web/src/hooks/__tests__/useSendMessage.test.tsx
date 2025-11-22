/**
 * Tests for useSendMessage - Optimistic updates
 */

import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useSendMessage } from "../useSendMessage";

// Mock dependencies
jest.mock("react-hot-toast", () => ({
  __esModule: true,
  default: {
    error: jest.fn(),
  },
}));

jest.mock("../../lib/logger", () => ({
  logDebug: jest.fn(),
  logError: jest.fn(),
}));

describe("useSendMessage", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    jest.clearAllMocks();
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  it("should create optimistic message on mutate", async () => {
    const chatId = "test-chat";
    const { result } = renderHook(() => useSendMessage(chatId), { wrapper });

    act(() => {
      result.current.mutate({ content: "Hello world" });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Check that cache was updated
    const cachedMessages = queryClient.getQueryData<any[]>([
      "chat",
      chatId,
      "messages",
    ]);
    expect(cachedMessages).toBeDefined();
    expect(cachedMessages?.[0]?.content).toBe("Hello world");
  });

  it("should include file metadata when provided", async () => {
    const chatId = "test-chat-files";
    const { result } = renderHook(() => useSendMessage(chatId), { wrapper });

    act(() => {
      result.current.mutate({
        content: "Message with files",
        fileIds: ["file-1", "file-2"],
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const cachedMessages = queryClient.getQueryData<any[]>([
      "chat",
      chatId,
      "messages",
    ]);
    expect(cachedMessages?.[0]?.metadata?.file_ids).toEqual([
      "file-1",
      "file-2",
    ]);
  });

  it("should generate unique temp IDs", async () => {
    const chatId = "test-temp-ids";
    const { result } = renderHook(() => useSendMessage(chatId), { wrapper });

    act(() => {
      result.current.mutate({ content: "Message 1" });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const firstId = queryClient.getQueryData<any[]>([
      "chat",
      chatId,
      "messages",
    ])?.[0]?.id;

    act(() => {
      result.current.mutate({ content: "Message 2" });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const cachedMessages = queryClient.getQueryData<any[]>([
      "chat",
      chatId,
      "messages",
    ]);
    const secondId = cachedMessages?.[1]?.id;

    expect(firstId).toBeTruthy();
    expect(secondId).toBeTruthy();
    expect(firstId).not.toBe(secondId);
    expect(firstId).toMatch(/^temp-/);
    expect(secondId).toMatch(/^temp-/);
  });

  it("should handle null chatId gracefully", async () => {
    const { result } = renderHook(() => useSendMessage(null), { wrapper });

    act(() => {
      result.current.mutate({ content: "Test" });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error?.message).toBe("Chat ID is required");
  });

  it("should set message status to sending", async () => {
    const chatId = "status-test";
    const { result } = renderHook(() => useSendMessage(chatId), { wrapper });

    act(() => {
      result.current.mutate({ content: "Test message" });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const cachedMessages = queryClient.getQueryData<any[]>([
      "chat",
      chatId,
      "messages",
    ]);
    expect(cachedMessages?.[0]?.status).toBe("sending");
  });

  it("should include enriched file attachments for instant display", async () => {
    const chatId = "test-enriched-files";
    const { result } = renderHook(() => useSendMessage(chatId), { wrapper });

    const mockFiles = [
      {
        file_id: "file-1",
        filename: "document.pdf",
        bytes: 1024,
        mimetype: "application/pdf",
        status: "READY" as const,
      },
    ];

    act(() => {
      result.current.mutate({
        content: "Message with enriched files",
        fileIds: ["file-1"],
        files: mockFiles,
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const cachedMessages = queryClient.getQueryData<any[]>([
      "chat",
      chatId,
      "messages",
    ]);
    expect(cachedMessages?.[0]?.metadata?.files).toBeDefined();
    expect(cachedMessages?.[0]?.metadata?.files[0].filename).toBe(
      "document.pdf",
    );
    expect(cachedMessages?.[0]?.metadata?.files[0].bytes).toBe(1024);
  });

  it("should include tools configuration when provided", async () => {
    const chatId = "test-tools";
    const { result } = renderHook(() => useSendMessage(chatId), { wrapper });

    act(() => {
      result.current.mutate({
        content: "Message with tools",
        toolsEnabled: {
          web_search: true,
          code_interpreter: true,
        },
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const cachedMessages = queryClient.getQueryData<any[]>([
      "chat",
      chatId,
      "messages",
    ]);
    expect(cachedMessages?.[0]?.metadata?.tools_enabled).toEqual({
      web_search: true,
      code_interpreter: true,
    });
  });

  it("should handle message with files, tools, and content together", async () => {
    const chatId = "test-complete";
    const { result } = renderHook(() => useSendMessage(chatId), { wrapper });

    const mockFiles = [
      {
        file_id: "file-1",
        filename: "data.csv",
        bytes: 512,
        mimetype: "text/csv",
        status: "READY" as const,
      },
    ];

    act(() => {
      result.current.mutate({
        content: "Analyze this data",
        fileIds: ["file-1"],
        files: mockFiles,
        toolsEnabled: { code_interpreter: true },
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const cachedMessages = queryClient.getQueryData<any[]>([
      "chat",
      chatId,
      "messages",
    ]);
    const message = cachedMessages?.[0];

    expect(message?.content).toBe("Analyze this data");
    expect(message?.status).toBe("sending");
    expect(message?.metadata?.file_ids).toEqual(["file-1"]);
    expect(message?.metadata?.files[0].filename).toBe("data.csv");
    expect(message?.metadata?.tools_enabled).toEqual({
      code_interpreter: true,
    });
  });
});
