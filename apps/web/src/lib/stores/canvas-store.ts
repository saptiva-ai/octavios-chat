import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AuditReportResponse } from "@/lib/types";

interface CanvasState {
  // UI state
  isSidebarOpen: boolean;
  isOpen: boolean;
  width?: number;

  // Data
  activeArtifactId: string | null;
  activeArtifactData: any | null;
  content: AuditReportResponse | null;
  activeTab?: string;
  sessionId: string | null;
  reportPdfUrl: string | null;

  // Actions
  setArtifact: (id: string | null) => void;
  openArtifact: (type: string, data: any) => void;
  toggleSidebar: () => void;
  setActiveTab: (tab: string) => void;
  openCanvas: (
    data?: AuditReportResponse | any,
    options?: { tab?: string; sessionId?: string | null; reportPdfUrl?: string },
  ) => void;
  closeCanvas: () => void;
  setActiveArtifactData: (data: any) => void;
  setSidebarOpen: (open: boolean) => void;
  reset: (sessionId?: string | null) => void;
}

export const useCanvasStore = create<CanvasState>()(
  persist(
    (set, get) => ({
      isSidebarOpen: false,
      isOpen: false,
      width: undefined,
      activeArtifactId: null,
      activeArtifactData: null,
      content: null,
      activeTab: undefined,
      sessionId: null,
      reportPdfUrl: null,

      setArtifact: (id) =>
        set((state) => ({
          activeArtifactId: id,
          activeArtifactData: null,
          isSidebarOpen: id ? true : state.isSidebarOpen,
          isOpen: id ? true : state.isOpen,
        })),

      openArtifact: (_type, data) =>
        set(() => ({
          activeArtifactId: null,
          activeArtifactData: data,
          isSidebarOpen: true,
          isOpen: true,
        })),

      toggleSidebar: () =>
        set((state) => ({
          isSidebarOpen: !state.isSidebarOpen,
          isOpen: !state.isOpen,
        })),

      setActiveTab: (tab: string) =>
        set(() => ({
          activeTab: tab,
        })),

      openCanvas: (data, options) => {
        const resolvedSession = options?.sessionId ?? get().sessionId ?? null;
        const meta: any = data?.metadata || {};
        const payload: any = (data as any)?.payload || {};
        const resolvedReportUrl =
          options?.reportPdfUrl ||
          meta?.attachments?.full_report_pdf?.url ||
          meta?.attachments?.full_report_pdf?.presigned_url ||
          meta?.attachments?.report_pdf_url ||
          meta?.report_pdf_url ||
          meta?.report_url ||
          meta?.pdf_url ||
          payload?.attachments?.full_report_pdf?.url ||
          payload?.attachments?.full_report_pdf?.presigned_url ||
          payload?.attachments?.report_pdf_url ||
          payload?.report_pdf_url ||
          null;

        // Allow opening without structured audit content (e.g., Generic UI render)
        set((state) => ({
          isOpen: true,
          isSidebarOpen: true,
          content: data ?? state.content,
          activeArtifactId: null,
          activeArtifactData: data ?? state.activeArtifactData,
          activeTab: options?.tab ?? state.activeTab,
          sessionId: resolvedSession,
          reportPdfUrl: resolvedReportUrl ?? state.reportPdfUrl,
        }));
      },

      closeCanvas: () =>
        set((state) => ({
          ...state,
          isOpen: false,
          isSidebarOpen: false,
          content: null,
          activeArtifactId: null,
          activeArtifactData: null,
          activeTab: undefined,
          reportPdfUrl: null,
        })),

      setActiveArtifactData: (data: any) =>
        set(() => ({
          activeArtifactData: data,
          isSidebarOpen: true,
          isOpen: true,
        })),

      setSidebarOpen: (open: boolean) =>
        set((state) => ({
          isSidebarOpen: open,
          isOpen: open || state.isOpen,
        })),

      reset: (sessionId = null) =>
        set(() => ({
          isSidebarOpen: false,
          isOpen: false,
          activeArtifactId: null,
          activeArtifactData: null,
          content: null,
          activeTab: undefined,
          sessionId,
          reportPdfUrl: null,
        })),
    }),
    {
      name: "canvas-store",
      partialize: (state) => ({
        isSidebarOpen: state.isSidebarOpen,
        isOpen: state.isOpen,
        width: state.width,
        activeArtifactId: state.activeArtifactId,
        activeArtifactData: state.activeArtifactData,
        content: state.content,
        activeTab: state.activeTab,
        sessionId: state.sessionId,
        reportPdfUrl: state.reportPdfUrl,
      }),
    },
  ),
);
