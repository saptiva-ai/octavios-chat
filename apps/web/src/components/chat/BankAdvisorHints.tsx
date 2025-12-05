"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { XMarkIcon } from "@heroicons/react/24/outline";
import { cn } from "@/lib/utils";

interface BankAdvisorHintsProps {
  visible: boolean;
  questions: string[];
  onSelectQuestion: (question: string) => void;
  onClose: () => void;
  className?: string;
}

/**
 * BankAdvisorHints Component
 *
 * Displays suggested questions as pill buttons when the BankAdvisor tool
 * is activated for the first time in a conversation.
 *
 * Features:
 * - Horizontal scrollable pills
 * - Fade-in + slide-up animation
 * - Click to prefill input
 * - Close button to dismiss
 */
export function BankAdvisorHints({
  visible,
  questions,
  onSelectQuestion,
  onClose,
  className,
}: BankAdvisorHintsProps) {
  return (
    <AnimatePresence>
      {visible && questions.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 10 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
          className={cn(
            "relative w-full px-4 py-3 bg-surface/50 border-t border-border",
            className,
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-primary">
                💡 Preguntas sugeridas
              </span>
              <span className="text-xs text-muted">BankAdvisor</span>
            </div>
            <button
              onClick={onClose}
              className="p-1 text-muted hover:text-foreground transition-colors rounded-md hover:bg-surface-2"
              aria-label="Cerrar sugerencias"
            >
              <XMarkIcon className="h-4 w-4" />
            </button>
          </div>

          {/* Scrollable Pills */}
          <div className="overflow-x-auto scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
            <div className="flex gap-2 pb-2">
              {questions.map((question, index) => (
                <motion.button
                  key={index}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{
                    duration: 0.2,
                    delay: index * 0.05,
                    ease: "easeOut",
                  }}
                  onClick={() => onSelectQuestion(question)}
                  className={cn(
                    "shrink-0 px-4 py-2 rounded-full text-sm",
                    "border border-border bg-surface hover:bg-surface-2",
                    "text-foreground hover:text-primary hover:border-primary/40",
                    "transition-all duration-200",
                    "focus:outline-none focus:ring-2 focus:ring-primary/30",
                    "whitespace-nowrap",
                  )}
                >
                  {question}
                </motion.button>
              ))}
            </div>
          </div>

          {/* Helper text */}
          <p className="text-xs text-muted mt-1 px-1">
            Haz clic en una pregunta para usarla como punto de partida
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// Default questions for BankAdvisor
// TODO: In the future, fetch from /bank-advisor/suggestions endpoint
export const DEFAULT_BANK_ADVISOR_QUESTIONS = [
  "¿Cómo ha evolucionado la cartera vencida de INVEX en los últimos 12 meses?",
  "Compárame la cartera vencida de INVEX contra el promedio del sistema bancario.",
  "¿Cuál es la tendencia del IMOR de INVEX en 2024?",
  "Muéstrame las principales métricas de riesgo de crédito para INVEX.",
  "¿Qué tan concentrada está la cartera comercial de INVEX en 2024?",
];
