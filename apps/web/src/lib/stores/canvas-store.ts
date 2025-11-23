import { create } from "zustand";

interface CanvasState {
  isSidebarOpen: boolean;
  activeArtifactId: string | null;
  activeArtifactData: any | null;
  setArtifact: (id: string | null) => void;
  openArtifact: (type: string, data: any) => void;
  toggleSidebar: () => void;
  reset: () => void;
}

export const useCanvasStore = create<CanvasState>((set) => ({
  isSidebarOpen: false,
  activeArtifactId: null,
  activeArtifactData: null,
  setArtifact: (id) =>
    set((state) => ({
      activeArtifactId: id,
      activeArtifactData: null,
      isSidebarOpen: id ? true : state.isSidebarOpen,
    })),
  openArtifact: (_type, data) =>
    set(() => ({
      activeArtifactId: null,
      activeArtifactData: data,
      isSidebarOpen: true,
    })),
  toggleSidebar: () =>
    set((state) => ({
      isSidebarOpen: !state.isSidebarOpen,
    })),
  reset: () =>
    set(() => ({
      isSidebarOpen: false,
      activeArtifactId: null,
      activeArtifactData: null,
    })),
}));
