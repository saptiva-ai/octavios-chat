"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useCanvas } from "@/context/CanvasContext";
import { AuditDetailView } from "@/components/canvas/views/AuditDetailView";

const MIN_WIDTH = 350;
const MAX_WIDTH = 800;
const DEFAULT_WIDTH = 400;

export function ResizableCanvas() {
  const { isOpen, content, closeCanvas } = useCanvas();
  const [width, setWidth] = React.useState<number>(DEFAULT_WIDTH);
  const [isDragging, setIsDragging] = React.useState(false);

  // Restore width from localStorage on mount
  React.useEffect(() => {
    const savedWidth = localStorage.getItem("canvas-width");
    if (savedWidth) {
      const parsedWidth = parseInt(savedWidth, 10);
      if (parsedWidth >= MIN_WIDTH && parsedWidth <= MAX_WIDTH) {
        setWidth(parsedWidth);
      }
    }
  }, []);

  // Persist width to localStorage when changed
  React.useEffect(() => {
    if (width !== DEFAULT_WIDTH) {
      localStorage.setItem("canvas-width", width.toString());
    }
  }, [width]);

  // Mouse event handlers for resize
  const handleMouseDown = React.useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleMouseMove = React.useCallback(
    (e: MouseEvent) => {
      if (!isDragging) return;

      const newWidth = window.innerWidth - e.clientX;
      const clampedWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, newWidth));
      setWidth(clampedWidth);
    },
    [isDragging],
  );

  const handleMouseUp = React.useCallback(() => {
    setIsDragging(false);
  }, []);

  // Double-click to expand to 50% width
  const handleDoubleClick = React.useCallback(() => {
    const halfWidth = window.innerWidth * 0.5;
    const targetWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, halfWidth));
    setWidth(targetWidth);
  }, []);

  // Attach global mouse listeners when dragging
  React.useEffect(() => {
    if (isDragging) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    } else {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    }

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  return (
    <AnimatePresence>
      {isOpen && content && (
        <motion.div
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "spring", damping: 30, stiffness: 300 }}
          className="fixed right-0 top-0 h-full bg-slate-900 border-l border-white/10 z-50 shadow-2xl"
          style={{ width: `${width}px` }}
        >
          {/* Resize Handle */}
          <div
            onMouseDown={handleMouseDown}
            onDoubleClick={handleDoubleClick}
            className={`
              absolute left-0 top-0 h-full w-1.5
              cursor-col-resize hover:bg-saptiva/50 transition-colors
              ${isDragging ? "bg-saptiva" : "bg-transparent"}
            `}
            title="Arrastra para redimensionar. Doble clic para expandir al 50%."
          />

          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
            <h2 className="text-lg font-semibold text-white">Canvas</h2>
            <button
              onClick={closeCanvas}
              className="rounded-md p-2 hover:bg-white/10 transition-colors text-xl"
              aria-label="Cerrar canvas"
            >
              ✕
            </button>
          </div>

          {/* Content */}
          <div className="h-[calc(100%-4rem)] overflow-auto p-6">
            <AuditDetailView report={content} />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
