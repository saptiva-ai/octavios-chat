import { create } from "zustand";

interface CanvasState {
  isSidebarOpen: boolean;
  activeArtifactId: string | null;
  setArtifact: (id: string | null) => void;
  toggleSidebar: () => void;
}

export const useCanvasStore = create<CanvasState>((set) => ({
  isSidebarOpen: false,
  activeArtifactId: null,
  setArtifact: (id) =>
    set((state) => ({
      activeArtifactId: id,
      isSidebarOpen: id ? true : state.isSidebarOpen,
    })),
  toggleSidebar: () =>
    set((state) => ({
      isSidebarOpen: !state.isSidebarOpen,
    })),
}));
