"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import rehypeSanitize from "rehype-sanitize"; // FIX ISSUE-008: Prevent XSS attacks
import { cn } from "../../lib/utils";
import type { PluggableList } from "unified";
import "katex/dist/katex.min.css";

interface MarkdownMessageProps {
  content: string;
  className?: string;
  /**
   * Enable syntax highlighting when true. During streaming we can disable
   * this to avoid re-processing the markdown on every token.
   */
  highlightCode?: boolean;
}

const defaultComponents = {
  a: ({ node: _, ...props }: any) => (
    <a
      {...props}
      className={cn(
        "text-saptiva-mint underline decoration-dotted underline-offset-2 hover:text-saptiva-light transition-colors",
        props.className,
      )}
      target="_blank"
      rel="noreferrer"
    />
  ),
  code: ({
    inline,
    className,
    children,
    ...props
  }: React.HTMLAttributes<HTMLElement> & { inline?: boolean }) => {
    const languageMatch = /language-(\w+)/.exec(className || "");
    if (inline || !languageMatch) {
      return (
        <code
          {...props}
          className={cn(
            "rounded-md bg-white/10 px-1.5 py-0.5 font-mono text-[0.85em]",
            className,
          )}
        >
          {children}
        </code>
      );
    }

    return (
      <pre
        {...props}
        className={cn(
          "relative overflow-x-auto rounded-xl border border-white/10 bg-black/60 p-4 font-mono text-sm leading-relaxed",
          className,
        )}
      >
        <code>{children}</code>
      </pre>
    );
  },
  blockquote: ({ className, ...props }: React.HTMLAttributes<HTMLElement>) => (
    <blockquote
      {...props}
      className={cn(
        "border-l-2 border-saptiva-mint/50 pl-4 text-saptiva-light/90",
        className,
      )}
    />
  ),
  ul: ({ className, ...props }: React.HTMLAttributes<HTMLUListElement>) => (
    <ul
      {...props}
      className={cn(
        "list-disc space-y-2 pl-5 marker:text-saptiva-mint/80",
        className,
      )}
    />
  ),
  ol: ({ className, ...props }: React.HTMLAttributes<HTMLOListElement>) => (
    <ol
      {...props}
      className={cn(
        "list-decimal space-y-2 pl-5 marker:text-saptiva-mint/80",
        className,
      )}
    />
  ),
  table: ({ className, ...props }: React.HTMLAttributes<HTMLTableElement>) => (
    <div className="overflow-x-auto">
      <table
        {...props}
        className={cn(
          "w-full border-collapse border border-white/10 text-left text-sm",
          className,
        )}
      />
    </div>
  ),
  th: ({ className, ...props }: React.HTMLAttributes<HTMLTableCellElement>) => (
    <th
      {...props}
      className={cn("border border-white/10 bg-white/5 px-3 py-2", className)}
    />
  ),
  td: ({ className, ...props }: React.HTMLAttributes<HTMLTableCellElement>) => (
    <td
      {...props}
      className={cn("border border-white/10 px-3 py-2 align-top", className)}
    />
  ),
};

/**
 * Preprocessor to normalize LaTeX syntax to Markdown-compatible format.
 * Converts traditional LaTeX delimiters to remark-math compatible syntax:
 * - \[ ... \] -> $$ ... $$ (display math)
 * - \( ... \) -> $ ... $ (inline math)
 * - [ ... ] -> $$ ... $$ (display math, common LLM output)
 */
function normalizeLatexSyntax(content: string): string {
  let normalized = content;

  // Convert \[ ... \] to $$ ... $$ (display math)
  // Use a function to avoid issues with $ special characters in replacement string
  normalized = normalized.replace(/\\\[([\s\S]*?)\\\]/g, (_match, equation) => {
    return `$$${equation}$$`;
  });

  // Convert \( ... \) to $ ... $ (inline math)
  normalized = normalized.replace(/\\\(([\s\S]*?)\\\)/g, (_match, equation) => {
    return `$${equation}$`;
  });

  // Convert standalone [ ... ] to $$ ... $$ (display math)
  // VERY conservative: only match if at start of line (not after any other content)
  // and equation contains LaTeX commands
  normalized = normalized.replace(
    /^\s*\[([\s\S]*?)\]\s*$/gm,
    (match, equation) => {
      // Must contain LaTeX commands to be considered an equation
      // Look for: backslash commands (\frac, \alpha, etc), subscripts, superscripts, braces
      const hasLatexCommands = /\\[a-zA-Z]{2,}|[_^{]/.test(equation);
      const hasMultipleSymbols =
        (equation.match(/\\[a-zA-Z]+/g) || []).length >= 2;

      // Only convert if it clearly looks like a LaTeX equation
      if (hasLatexCommands && hasMultipleSymbols) {
        return `$$${equation}$$\n`;
      }

      // Otherwise keep original
      return match;
    },
  );

  return normalized;
}

export function MarkdownMessage({
  content,
  className,
  highlightCode = true,
}: MarkdownMessageProps) {
  // Normalize LaTeX syntax before rendering
  const normalizedContent = React.useMemo(() => {
    return normalizeLatexSyntax(content);
  }, [content]);

  const markdownPlugins = React.useMemo(() => {
    const remarkPlugins: PluggableList = [remarkGfm, remarkMath];
    const rehypePlugins: PluggableList = [];

    // FIX ISSUE-008: Sanitize HTML first to prevent XSS
    rehypePlugins.push(rehypeSanitize);

    if (highlightCode) {
      rehypePlugins.push(rehypeHighlight);
    }
    rehypePlugins.push(rehypeKatex);
    return {
      remark: remarkPlugins,
      rehype: rehypePlugins,
    };
  }, [highlightCode]);

  return (
    <div className={cn("prose prose-invert max-w-none text-sm", className)}>
      <ReactMarkdown
        remarkPlugins={markdownPlugins.remark}
        rehypePlugins={markdownPlugins.rehype}
        components={defaultComponents}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}

export default MarkdownMessage;
