import { useState, useCallback, useRef, useEffect } from "react";
import { flushSync } from "react-dom";
import { useAppStore } from "../lib/store";
import type { ChatMessage } from "../lib/types";
import { logDebug } from "../lib/logger";

interface UseOptimizedChatOptions {
  enablePredictiveLoading?: boolean;
  enableResponseCache?: boolean;
  streamingChunkSize?: number;
}

export function useOptimizedChat(options: UseOptimizedChatOptions = {}) {
  const {
    enablePredictiveLoading = true,
    enableResponseCache = true,
    streamingChunkSize = 3,
  } = options;

  const [isTyping, setIsTyping] = useState(false);
  const [predictedResponse, setPredictedResponse] = useState<string | null>(
    null,
  );
  const responseCache = useRef(new Map<string, string>());
  const currentRequestController = useRef<AbortController | null>(null);

  // Throttling refs para evitar bloquear el navegador con demasiados flushSync
  const lastUpdateTime = useRef<number>(0);
  const pendingUpdate = useRef<{ messageId: string; content: string } | null>(
    null,
  );
  const throttleTimer = useRef<NodeJS.Timeout | null>(null);

  const { addMessage, updateMessage } = useAppStore();

  // Cache de respuestas comunes para velocidad instantánea
  const initializeResponseCache = useCallback(() => {
    const commonResponses = [
      { q: "hola", a: "¡Hola! ¿En qué puedo ayudarte hoy?" },
      { q: "hello", a: "Hello! How can I help you today?" },
      { q: "gracias", a: "¡De nada! ¿Hay algo más en lo que pueda asistirte?" },
      {
        q: "thank you",
        a: "You're welcome! Is there anything else I can help with?",
      },
      { q: "adios", a: "¡Hasta luego! Que tengas un excelente día." },
      { q: "goodbye", a: "Goodbye! Have a great day!" },
    ];

    commonResponses.forEach(({ q, a }) => {
      responseCache.current.set(q.toLowerCase().trim(), a);
    });
  }, []);

  // Inicializar cache al montar
  useEffect(() => {
    if (enableResponseCache) {
      initializeResponseCache();
    }
  }, [enableResponseCache, initializeResponseCache]);

  // Función para obtener respuesta cacheada
  const getCachedResponse = useCallback(
    (message: string): string | null => {
      if (!enableResponseCache) return null;

      const normalized = message.toLowerCase().trim();
      return responseCache.current.get(normalized) || null;
    },
    [enableResponseCache],
  );

  // Función para finalizar streaming (DEFINIDA ANTES para evitar ReferenceError)
  const completeStreaming = useCallback(
    (messageId: string, finalData: Partial<ChatMessage>) => {
      // Limpiar cualquier throttle timer pendiente
      if (throttleTimer.current !== null) {
        clearTimeout(throttleTimer.current);
        throttleTimer.current = null;
      }

      // Si hay contenido pendiente, aplicarlo antes de completar
      if (
        pendingUpdate.current &&
        pendingUpdate.current.messageId === messageId
      ) {
        flushSync(() => {
          updateMessage(pendingUpdate.current!.messageId, {
            content: pendingUpdate.current!.content,
            status: "streaming",
            isStreaming: true,
          });
        });
        pendingUpdate.current = null;
      }

      // Completar el streaming
      updateMessage(messageId, {
        ...finalData,
        status: finalData.status ?? "delivered",
        isStreaming: false,
      });

      // Reset throttle state
      lastUpdateTime.current = 0;
    },
    [updateMessage],
  );

  // Función para actualizar contenido de streaming de forma optimizada
  const updateStreamingContent = useCallback(
    (messageId: string, newContent: string) => {
      const now = Date.now();
      const timeSinceLastUpdate = now - lastUpdateTime.current;
      const THROTTLE_MS = 50;

      // console.log("[DEBUG] updateStreamingContent - length:", newContent.length, "timeSince:", timeSinceLastUpdate, "hasTimer:", throttleTimer.current !== null);

      // Siempre guardar el último contenido
      pendingUpdate.current = { messageId, content: newContent };

      // Actualizar inmediatamente si:
      // 1. Es el primer chunk (lastUpdateTime === 0)
      // 2. Han pasado >= THROTTLE_MS desde la última actualización
      if (lastUpdateTime.current === 0 || timeSinceLastUpdate >= THROTTLE_MS) {
        // console.log("[DEBUG] IMMEDIATE UPDATE - length:", newContent.length);
        // Actualizar inmediatamente
        flushSync(() => {
          updateMessage(messageId, {
            content: newContent,
            status: "streaming",
            isStreaming: true,
          });
        });
        lastUpdateTime.current = now;
        pendingUpdate.current = null;

        // Limpiar timer si existe
        if (throttleTimer.current !== null) {
          clearTimeout(throttleTimer.current);
          throttleTimer.current = null;
        }
      } else {
        // Programar actualización para el próximo intervalo si no hay timer activo
        if (throttleTimer.current === null) {
          const delay = THROTTLE_MS - timeSinceLastUpdate;
          // console.log("[DEBUG] SCHEDULING TIMER - delay:", delay, "ms");
          throttleTimer.current = setTimeout(() => {
            // console.log("[DEBUG] TIMER FIRED - pendingLength:", pendingUpdate.current?.content.length);
            if (pendingUpdate.current) {
              flushSync(() => {
                updateMessage(pendingUpdate.current!.messageId, {
                  content: pendingUpdate.current!.content,
                  status: "streaming",
                  isStreaming: true,
                });
              });
              lastUpdateTime.current = Date.now();
              pendingUpdate.current = null;
            }
            throttleTimer.current = null;
          }, delay);
        } else {
          // console.log("[DEBUG] TIMER ALREADY EXISTS - just updating pending");
        }
      }
    },
    [updateMessage],
  );

  // Función optimizada para enviar mensajes
  // MVP-LOCK: Added metadata parameter to attach file_ids to user messages
  const sendOptimizedMessage = useCallback(
    async (
      message: string,
      sendMessage: (
        msg: string,
        placeholderId: string,
        abortController?: AbortController,
      ) => Promise<Partial<ChatMessage> | void>,
      metadata?: Record<string, any>,
    ) => {
      // 1. Agregar mensaje del usuario inmediatamente
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user" as const,
        content: message,
        timestamp: new Date(),
        status: "delivered" as const,
        ...(metadata && { metadata }), // MVP-LOCK: Include metadata if provided
      };

      // DEBUG: Log user message with metadata before adding to store
      logDebug("[useOptimizedChat] Creating user message", {
        hasMetadata: !!metadata,
        metadata,
        userMessage,
        metadataInMessage: userMessage.metadata,
      });

      addMessage(userMessage);

      // 2. Verificar cache para respuesta instantánea
      const cachedResponse = getCachedResponse(message);

      if (cachedResponse) {
        // Respuesta instantánea con simulación de typing para naturalidad
        const assistantId = `assistant-${Date.now()}`;

        // Agregar mensaje vacío con indicador de typing
        addMessage({
          id: assistantId,
          role: "assistant",
          content: "",
          timestamp: new Date(),
          status: "streaming",
          isStreaming: true,
        });

        // Simular typing durante un corto tiempo para naturalidad
        setTimeout(
          () => {
            updateMessage(assistantId, {
              content: cachedResponse,
              status: "delivered",
              isStreaming: false,
            });
          },
          300 + Math.random() * 500,
        ); // 300-800ms de typing simulado

        return;
      }

      // 3. Para respuestas no cacheadas, mostrar typing indicator inmediato
      setIsTyping(true);
      const assistantId = `assistant-${Date.now()}`;

      // Crear AbortController para este request
      currentRequestController.current = new AbortController();

      addMessage({
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        status: "streaming",
        isStreaming: true,
      });

      try {
        // 4. Enviar mensaje real con AbortController
        const finalMessage = await sendMessage(
          message,
          assistantId,
          currentRequestController.current,
        );

        if (finalMessage) {
          completeStreaming(assistantId, finalMessage);
        } else {
          completeStreaming(assistantId, { status: "delivered" });
        }
      } catch (error) {
        // Verificar si fue cancelado
        if (error instanceof Error && error.name === "AbortError") {
          completeStreaming(assistantId, {
            content: "Mensaje cancelado",
            status: "error",
          });
        } else {
          // Manejar otros errores
          completeStreaming(assistantId, {
            content: "Lo siento, hubo un error al procesar tu mensaje.",
            status: "error",
          });
        }
      } finally {
        setIsTyping(false);
        currentRequestController.current = null;
      }
    },
    [addMessage, completeStreaming, getCachedResponse, updateMessage],
  );

  // Función para precarga predictiva (experimental)
  const startPredictiveLoading = useCallback(
    (partialMessage: string) => {
      if (!enablePredictiveLoading || partialMessage.length < 3) return;

      // Predicciones simples basadas en patrones comunes
      const predictions = {
        "como ": "Como puedo ayudarte con eso...",
        "what ": "What would you like to know...",
        "how ": "How can I assist you...",
        "why ": "Why do you ask...",
      };

      const prediction = Object.entries(predictions).find(([prefix]) =>
        partialMessage.toLowerCase().includes(prefix),
      );

      if (prediction) {
        setPredictedResponse(prediction[1]);
      }
    },
    [enablePredictiveLoading],
  );

  // Función para cancelar streaming
  const cancelCurrentRequest = useCallback(() => {
    if (currentRequestController.current) {
      currentRequestController.current.abort();
      currentRequestController.current = null;
      setIsTyping(false);
    }
  }, []);

  // Limpiar el controlador y timers cuando se desmonte
  useEffect(() => {
    return () => {
      if (currentRequestController.current) {
        currentRequestController.current.abort();
      }
      if (throttleTimer.current !== null) {
        clearTimeout(throttleTimer.current);
      }
    };
  }, []);

  return {
    // Estado
    isTyping,
    predictedResponse,

    // Funciones optimizadas
    sendOptimizedMessage,
    updateStreamingContent,
    completeStreaming,
    startPredictiveLoading,
    cancelCurrentRequest,

    // Utilidades
    getCachedResponse,

    // Configuración
    cacheSize: responseCache.current.size,
  };
}
