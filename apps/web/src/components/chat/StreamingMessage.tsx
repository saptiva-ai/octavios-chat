"use client";

import * as React from "react";
import { cn } from "../../lib/utils";
import { TypingIndicator, StreamingCursor } from "../ui/TypingIndicator";
import { MarkdownMessage } from "./MarkdownMessage";

interface StreamingMessageProps {
  content: string;
  isStreaming?: boolean;
  isComplete?: boolean;
  className?: string;
}

export function StreamingMessage({
  content,
  isStreaming = false,
  isComplete = false,
  className,
}: StreamingMessageProps) {
  // console.log("[DEBUG] StreamingMessage render - length:", content.length, "isStreaming:", isStreaming);

  // During real streaming from server, show content directly without artificial delays
  // The server already sends chunks token-by-token, no need to simulate it
  const displayedContent = content;
  const showCursor = isStreaming && !isComplete && content.length > 0;

  // Mostrar typing indicator si no hay contenido aún
  if (isStreaming && content.length === 0) {
    return (
      <div className={cn("py-2", className)}>
        <TypingIndicator size="sm" />
      </div>
    );
  }

  return (
    <div className={cn("relative", className)}>
      {/* Durante streaming, mostrar texto plano para mejor performance */}
      {/* Solo renderizar Markdown cuando termine el streaming */}
      {isStreaming && !isComplete ? (
        <div className="prose prose-sm max-w-none dark:prose-invert whitespace-pre-wrap text-white">
          {displayedContent}
        </div>
      ) : (
        <MarkdownMessage content={displayedContent} highlightCode={true} />
      )}
      {/* Cursor de streaming */}
      {showCursor && (
        <div className="pointer-events-none absolute bottom-0 left-full ml-2 translate-y-1/4">
          <StreamingCursor />
        </div>
      )}
    </div>
  );
}

export function MessageSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn("animate-pulse space-y-2", className)}>
      <div className="h-4 bg-surface rounded w-3/4"></div>
      <div className="h-4 bg-surface rounded w-1/2"></div>
      <div className="h-4 bg-surface rounded w-2/3"></div>
    </div>
  );
}
