/**
 * useChatMessages.ts - React Query hook for chat messages
 *
 * This hook is the KEY to eliminating race conditions.
 *
 * How it works:
 * 1. React Query fetches messages from backend and manages caching
 * 2. Synchronizes server data with Zustand chat-store for UI consumption
 * 3. Marks chat as "hydrated" when data arrives (enables file restoration policies)
 *
 * Benefits:
 * - Automatic request deduplication (multiple components can call this for same chat)
 * - Stale-while-revalidate pattern (instant UI updates on navigation)
 * - Eliminates race conditions between file restoration and message loading
 * - Centralized error handling
 */

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useChatStore } from "../lib/stores/chat-store";
import { apiClient } from "../lib/api-client";
import type { ChatMessage } from "../lib/types";
import { logDebug, logError } from "../lib/logger";

export function useChatMessages(chatId: string | null) {
  // Zustand store selectors
  const setMessages = useChatStore((state) => state.setMessages);
  const setHydratedStatus = useChatStore((state) => state.setHydratedStatus);
  const setLoading = useChatStore((state) => state.setLoading);

  // React Query manages the server state
  const {
    data: serverMessages,
    isLoading,
    isError,
    error,
  } = useQuery<ChatMessage[]>({
    queryKey: ["chat", chatId, "messages"],

    queryFn: async () => {
      if (!chatId || chatId === "draft") return [];

      logDebug("[useChatMessages] Fetching messages", { chatId });

      try {
        const historyData = await apiClient.getUnifiedChatHistory(
          chatId,
          50,
          0,
          true,
          false,
        );

        // Convert history events to chat messages
        const messages: ChatMessage[] = [];

        for (const event of historyData.events) {
          if (event.event_type === "chat_message" && event.chat_data) {
            // Merge file data into metadata for UI compatibility
            const enrichedMetadata: Record<string, any> = {
              ...(event.chat_data.metadata || {}),
            };

            if (
              event.chat_data.file_ids &&
              event.chat_data.file_ids.length > 0
            ) {
              enrichedMetadata.file_ids = event.chat_data.file_ids;
            }
            if (event.chat_data.files && event.chat_data.files.length > 0) {
              enrichedMetadata.files = event.chat_data.files;
            }

            messages.push({
              id: event.chat_data.id,
              content: event.chat_data.content,
              role: event.chat_data.role as "user" | "assistant" | "system",
              timestamp: event.chat_data.timestamp || event.created_at,
              status: "delivered",
              metadata: enrichedMetadata,
              model: event.chat_data.model,
              tokens: event.chat_data.tokens,
              latency: event.chat_data.latency_ms,
            });
          }
        }

        return messages;
      } catch (err) {
        logError("[useChatMessages] Failed to fetch messages", err);
        throw err;
      }
    },

    // Only run query for real chats (not draft/temp)
    enabled:
      !!chatId &&
      chatId !== "draft" &&
      !chatId.startsWith("temp-") &&
      !chatId.startsWith("creating"),

    // Cache configuration
    staleTime: 30 * 1000, // 30 seconds (messages can change frequently)
    gcTime: 5 * 60 * 1000, // Keep in cache for 5 minutes after unmount
  });

  // Synchronize React Query data → Zustand store
  useEffect(() => {
    if (serverMessages) {
      logDebug("[useChatMessages] Syncing messages to Zustand", {
        chatId,
        count: serverMessages.length,
      });

      // ⚠️ CRITICAL FIX: Only sync server messages if they're non-empty
      // During optimistic creation, backend returns empty array for new chats
      // We must NOT overwrite optimistic messages with empty server response
      const currentMessages = useChatStore.getState().messages;

      // 🚨 CRITICAL: Check if any message is currently streaming
      // If streaming is active, NEVER overwrite with server data (it's stale)
      const hasStreamingMessage = currentMessages.some(
        (msg) => msg.isStreaming === true,
      );

      // console.log("[🔍 useChatMessages] Server sync decision", {
      //   chatId,
      //   serverCount: serverMessages.length,
      //   currentCount: currentMessages.length,
      //   hasStreamingMessage,
      //   willSync: !hasStreamingMessage && (serverMessages.length > 0 || currentMessages.length === 0),
      // });

      if (hasStreamingMessage) {
        // 🚨 STREAMING ACTIVE: NEVER overwrite, server data is stale
        // console.log("[🔍 useChatMessages] BLOCKING sync - streaming in progress", {
        //   chatId,
        //   currentCount: currentMessages.length,
        // });
        return; // Don't sync anything while streaming
      }

      if (serverMessages.length > 0) {
        // Server has messages → sync them (user navigated to existing chat)
        // console.log("[🔍 useChatMessages] Syncing server messages (server has data)");
        setMessages(serverMessages);
      } else if (currentMessages.length === 0) {
        // Server has no messages AND store is empty → safe to sync empty array
        // console.log("[🔍 useChatMessages] Syncing empty array (store is empty)");
        setMessages(serverMessages);
      } else {
        // Server has no messages BUT store has optimistic messages → preserve them
        // console.log("[🔍 useChatMessages] PRESERVING optimistic messages", {
        //   chatId,
        //   optimisticCount: currentMessages.length,
        // });
        logDebug("[useChatMessages] Preserving optimistic messages", {
          chatId,
          optimisticCount: currentMessages.length,
        });
      }

      // Mark chat as hydrated (enables file restoration policies)
      if (chatId && chatId !== "draft") {
        setHydratedStatus(chatId, true);
      }
    }
  }, [serverMessages, chatId, setMessages, setHydratedStatus]);

  // Handle draft/temp/null chats (no backend fetch needed) - MUST run before loading sync
  useEffect(() => {
    const isDraftOrTemp =
      !chatId ||
      chatId === "draft" ||
      chatId.startsWith("temp-") ||
      chatId.startsWith("creating");

    if (isDraftOrTemp) {
      // ⚠️ CRITICAL FIX: Only clear messages if transitioning FROM a real chat TO draft/temp
      // DO NOT clear messages during optimistic creation flow (temp → real ID transition)
      // This preserves optimistic user messages and streaming assistant responses
      const currentMessages = useChatStore.getState().messages;
      if (currentMessages.length === 0) {
        setMessages([]);
      }

      setLoading(false); // Ensure loading is false for draft/temp/null
      if (chatId && chatId !== "draft") {
        setHydratedStatus(chatId, true);
      }

      logDebug("[useChatMessages] Draft/temp/null chat - skipping fetch", {
        chatId,
        preservingMessages: currentMessages.length > 0,
      });
    }
  }, [chatId, setMessages, setHydratedStatus, setLoading]);

  // Synchronize loading state for real chats
  useEffect(() => {
    const isDraftOrTemp =
      !chatId ||
      chatId === "draft" ||
      chatId.startsWith("temp-") ||
      chatId.startsWith("creating");

    // Only sync loading state for real chats (not draft/temp/null)
    if (!isDraftOrTemp) {
      setLoading(isLoading);
    }
  }, [isLoading, setLoading, chatId]);

  return {
    messages: serverMessages ?? [],
    isLoading,
    isError,
    error,
  };
}
