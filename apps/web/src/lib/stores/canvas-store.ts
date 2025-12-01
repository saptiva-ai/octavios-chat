import { create } from "zustand";
import type { BankChartData, CanvasChartSync } from "@/lib/types";

interface CanvasState {
  isSidebarOpen: boolean;
  activeArtifactId: string | null;
  activeArtifactData: any | null;

  // 🆕 Bank chart specific state (Phase 2)
  activeBankChart: BankChartData | null;
  activeMessageId: string | null;
  chartHistory: CanvasChartSync[];

  // Existing methods
  setArtifact: (id: string | null) => void;
  openArtifact: (type: string, data: any) => void;
  toggleSidebar: () => void;
  reset: () => void;

  // 🆕 Bank chart methods (Phase 2)
  openBankChart: (
    chartData: BankChartData,
    artifactId: string,
    messageId: string,
    autoOpen?: boolean,
  ) => void;
  setActiveMessage: (messageId: string | null) => void;
  addToChartHistory: (sync: CanvasChartSync) => void;
  clearChartHistory: () => void;
}

export const useCanvasStore = create<CanvasState>((set, get) => ({
  isSidebarOpen: false,
  activeArtifactId: null,
  activeArtifactData: null,
  activeBankChart: null,
  activeMessageId: null,
  chartHistory: [],

  setArtifact: (id) =>
    set((state) => ({
      activeArtifactId: id,
      activeArtifactData: null,
      activeBankChart: null, // Clear chart when setting artifact
      isSidebarOpen: id ? true : state.isSidebarOpen,
    })),

  openArtifact: (_type, data) =>
    set(() => ({
      activeArtifactId: null,
      activeArtifactData: data,
      activeBankChart: null, // Clear chart when opening artifact
      isSidebarOpen: true,
    })),

  toggleSidebar: () =>
    set((state) => {
      const newOpenState = !state.isSidebarOpen;

      // If closing, clear active message and deactivate all charts
      if (!newOpenState) {
        return {
          isSidebarOpen: false,
          activeMessageId: null,
          chartHistory: state.chartHistory.map((c) => ({
            ...c,
            isActive: false,
          })),
        };
      }

      return { isSidebarOpen: true };
    }),

  reset: () =>
    set(() => ({
      isSidebarOpen: false,
      activeArtifactId: null,
      activeArtifactData: null,
      activeBankChart: null,
      activeMessageId: null,
      chartHistory: [],
    })),

  // 🆕 Open bank chart in canvas (main method)
  openBankChart: (chartData, artifactId, messageId, autoOpen = false) => {
    const { chartHistory, addToChartHistory } = get();

    set({
      activeBankChart: chartData,
      // Don't set activeArtifactId for temp artifacts or when we have chartData
      // This prevents canvas-panel from trying to fetch the artifact
      activeArtifactId: artifactId !== "temp" ? artifactId : null,
      activeMessageId: messageId,
      isSidebarOpen: true,
      activeArtifactData: null, // Clear audit data if present
    });

    // Add to history if not already present
    if (!chartHistory.find((c) => c.artifactId === artifactId)) {
      addToChartHistory({
        artifactId,
        messageId,
        isActive: true,
      });
    } else {
      // Update existing entry to mark as active
      set((state) => ({
        chartHistory: state.chartHistory.map((c) =>
          c.artifactId === artifactId
            ? { ...c, isActive: true }
            : { ...c, isActive: false },
        ),
      }));
    }

    if (process.env.NODE_ENV === "development") {
      console.warn("[Canvas] Opened bank chart:", {
        artifactId,
        messageId,
        metric: chartData.metric_name,
        autoOpen,
      });
    }
  },

  // 🆕 Set active message (for highlight synchronization)
  setActiveMessage: (messageId) =>
    set((state) => ({
      activeMessageId: messageId,
      chartHistory: state.chartHistory.map((c) => ({
        ...c,
        isActive: c.messageId === messageId,
      })),
    })),

  // 🆕 Add chart to history (with max limit of 20 charts)
  addToChartHistory: (sync) =>
    set((state) => {
      const MAX_CHART_HISTORY = 20;
      const updatedHistory = [
        ...state.chartHistory.map((c) => ({ ...c, isActive: false })),
        sync,
      ];

      // Keep only the last 20 charts
      const limitedHistory =
        updatedHistory.length > MAX_CHART_HISTORY
          ? updatedHistory.slice(-MAX_CHART_HISTORY)
          : updatedHistory;

      return { chartHistory: limitedHistory };
    }),

  // 🆕 Clear chart history (on session change)
  clearChartHistory: () =>
    set(() => ({
      chartHistory: [],
      activeBankChart: null,
      activeMessageId: null,
    })),
}));
