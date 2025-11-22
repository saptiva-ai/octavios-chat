/**
 * useSendMessage.ts - Optimistic updates for message sending
 *
 * This hook provides instant UI feedback when sending messages by:
 * 1. Immediately adding user message to UI (0ms latency)
 * 2. Automatically rolling back on errors
 * 3. Syncing with server response when complete
 *
 * IMPORTANT: This hook handles ONLY the optimistic UI update.
 * The actual API call and streaming still happens via sendOptimizedMessage.
 *
 * This is a HYBRID pattern:
 * - User messages: Optimistic (instant UI)
 * - Assistant responses: Streaming (existing flow)
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { v4 as uuidv4 } from "uuid";
import type { ChatMessage } from "../lib/types";
import { logDebug, logError } from "../lib/logger";

interface SendMessageVariables {
  content: string;
  fileIds?: string[];
}

interface SendMessageContext {
  previousMessages?: ChatMessage[];
  tempId: string;
}

/**
 * Hook for sending messages with optimistic updates
 *
 * @param chatId - Chat ID to send message to
 * @returns React Query mutation object
 *
 * @example
 * ```tsx
 * function ChatInput({ chatId }: { chatId: string }) {
 *   const sendMessage = useSendMessage(chatId);
 *
 *   const handleSend = async (content: string) => {
 *     // This triggers optimistic update immediately
 *     await sendMessage.mutateAsync({ content });
 *
 *     // Then call your existing streaming logic
 *     await sendOptimizedMessage(content);
 *   };
 * }
 * ```
 */
export function useSendMessage(chatId: string | null) {
  const queryClient = useQueryClient();
  const queryKey = ["chat", chatId, "messages"];

  return useMutation<ChatMessage, Error, SendMessageVariables, SendMessageContext>({
    // Mutation function (returns optimistic message)
    mutationFn: async (variables) => {
      if (!chatId) {
        throw new Error("Chat ID is required");
      }

      logDebug("[useSendMessage] Mutation triggered", {
        chatId,
        contentLength: variables.content.length,
        hasFiles: !!variables.fileIds?.length,
      });

      // Return optimistic message (actual API call happens externally)
      return {
        id: `temp-${uuidv4()}`,
        role: "user",
        content: variables.content,
        timestamp: new Date().toISOString(),
        status: "sending",
      } as ChatMessage;
    },

    // OPTIMISTIC UPDATE: Instant UI feedback (0ms latency)
    onMutate: async (variables) => {
      logDebug("[useSendMessage] onMutate - Applying optimistic update");

      // 1. Cancel outgoing queries (prevent race conditions)
      await queryClient.cancelQueries({ queryKey });

      // 2. Snapshot current messages (for rollback)
      const previousMessages = queryClient.getQueryData<ChatMessage[]>(queryKey);

      // 3. Generate temporary ID
      const tempId = `temp-${uuidv4()}`;

      // 4. Create optimistic user message
      const optimisticMessage: ChatMessage = {
        id: tempId,
        role: "user",
        content: variables.content,
        timestamp: new Date().toISOString(),
        status: "sending",
        // Include file metadata if present
        metadata: variables.fileIds
          ? { file_ids: variables.fileIds }
          : undefined,
      };

      // 5. Update React Query cache immediately (triggers UI update)
      queryClient.setQueryData<ChatMessage[]>(queryKey, (old = []) => {
        return [...old, optimisticMessage];
      });

      logDebug("[useSendMessage] Optimistic message added", {
        tempId,
        messagesCount: (old: ChatMessage[] = []) => old.length + 1,
      });

      // 6. Return context for rollback
      return { previousMessages, tempId };
    },

    // ERROR HANDLING: Rollback on failure
    onError: (error, variables, context) => {
      logError("[useSendMessage] Error - Rolling back optimistic update", error);

      // Restore previous messages
      if (context?.previousMessages) {
        queryClient.setQueryData(queryKey, context.previousMessages);
      }

      // Show error to user
      toast.error("No se pudo enviar el mensaje. Intenta de nuevo.");
    },

    // SYNC: Invalidate cache to refetch from server
    onSettled: () => {
      logDebug("[useSendMessage] onSettled - Invalidating cache");

      // Trigger refetch to sync with server
      queryClient.invalidateQueries({ queryKey });
    },
  });
}
