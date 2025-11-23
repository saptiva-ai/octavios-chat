"use client";

import React, { createContext, useContext, useState, useCallback } from "react";
import type { AuditReportResponse } from "@/lib/types";

interface CanvasState {
  isOpen: boolean;
  content: AuditReportResponse | null;
  activeTab?: string;
}

interface CanvasContextType extends CanvasState {
  openCanvas: (data: AuditReportResponse, tab?: string) => void;
  closeCanvas: () => void;
  toggleCanvas: () => void;
  setActiveTab: (tab: string) => void;
}

const CanvasContext = createContext<CanvasContextType | undefined>(undefined);

export function CanvasProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<CanvasState>({
    isOpen: false,
    content: null,
    activeTab: undefined,
  });

  const openCanvas = useCallback((data: AuditReportResponse, tab?: string) => {
    setState({
      isOpen: true,
      content: data,
      activeTab: tab,
    });
  }, []);

  const closeCanvas = useCallback(() => {
    setState((prev) => ({
      ...prev,
      isOpen: false,
    }));
  }, []);

  const toggleCanvas = useCallback(() => {
    setState((prev) => ({
      ...prev,
      isOpen: !prev.isOpen,
    }));
  }, []);

  const setActiveTab = useCallback((tab: string) => {
    setState((prev) => ({
      ...prev,
      activeTab: tab,
    }));
  }, []);

  return (
    <CanvasContext.Provider
      value={{
        ...state,
        openCanvas,
        closeCanvas,
        toggleCanvas,
        setActiveTab,
      }}
    >
      {children}
    </CanvasContext.Provider>
  );
}

export function useCanvas() {
  const context = useContext(CanvasContext);
  if (context === undefined) {
    throw new Error("useCanvas must be used within a CanvasProvider");
  }
  return context;
}
