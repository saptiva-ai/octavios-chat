import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CanvasPanel } from "../canvas-panel";
import { useCanvasStore } from "@/lib/stores/canvas-store";

// Mock all dependencies
jest.mock("@/lib/stores/canvas-store");
jest.mock("@/lib/api-client");
jest.mock("../markdown-renderer", () => ({
  MarkdownRenderer: () => <div>Mocked Markdown</div>,
}));
jest.mock("../mermaid-graph", () => ({
  MermaidGraph: () => <div>Mocked Mermaid</div>,
}));
jest.mock("../views/AuditDetailView", () => ({
  AuditDetailView: () => <div>Mocked Audit</div>,
}));
jest.mock("../BankChartCanvasView", () => ({
  BankChartCanvasView: () => <div>Mocked Bank Chart</div>,
}));
jest.mock("../CanvasErrorBoundary", () => ({
  CanvasErrorBoundary: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

describe("CanvasPanel - Keyboard Shortcuts", () => {
  const mockToggleSidebar = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    (useCanvasStore as unknown as jest.Mock).mockImplementation((selector) =>
      selector({
        activeArtifactId: null,
        isSidebarOpen: false,
        toggleSidebar: mockToggleSidebar,
        activeArtifactData: null,
        activeBankChart: null,
      }),
    );
  });

  it("should toggle canvas with Cmd+K on Mac", async () => {
    const user = userEvent.setup();
    render(<CanvasPanel />);

    // Simulate Cmd+K (metaKey)
    await user.keyboard("{Meta>}k{/Meta}");

    expect(mockToggleSidebar).toHaveBeenCalledTimes(1);
  });

  it("should toggle canvas with Ctrl+K on Windows/Linux", async () => {
    const user = userEvent.setup();
    render(<CanvasPanel />);

    // Simulate Ctrl+K (ctrlKey)
    await user.keyboard("{Control>}k{/Control}");

    expect(mockToggleSidebar).toHaveBeenCalledTimes(1);
  });

  it("should close canvas with Escape when sidebar is open", async () => {
    (useCanvasStore as unknown as jest.Mock).mockImplementation((selector) =>
      selector({
        activeArtifactId: null,
        isSidebarOpen: true, // Canvas is open
        toggleSidebar: mockToggleSidebar,
        activeArtifactData: null,
        activeBankChart: null,
      }),
    );

    const user = userEvent.setup();
    render(<CanvasPanel />);

    await user.keyboard("{Escape}");

    expect(mockToggleSidebar).toHaveBeenCalledTimes(1);
  });

  it("should NOT close canvas with Escape when sidebar is closed", async () => {
    (useCanvasStore as unknown as jest.Mock).mockImplementation((selector) =>
      selector({
        activeArtifactId: null,
        isSidebarOpen: false, // Canvas is closed
        toggleSidebar: mockToggleSidebar,
        activeArtifactData: null,
        activeBankChart: null,
      }),
    );

    const user = userEvent.setup();
    render(<CanvasPanel />);

    await user.keyboard("{Escape}");

    // Should not toggle when already closed
    expect(mockToggleSidebar).not.toHaveBeenCalled();
  });

  it("should prevent default behavior for keyboard shortcuts", async () => {
    const user = userEvent.setup();
    render(<CanvasPanel />);

    const preventDefaultSpy = jest.fn();

    // Create a custom keyboard event
    const event = new KeyboardEvent("keydown", {
      key: "k",
      metaKey: true,
      bubbles: true,
      cancelable: true,
    });

    Object.defineProperty(event, "preventDefault", {
      value: preventDefaultSpy,
    });

    window.dispatchEvent(event);

    expect(preventDefaultSpy).toHaveBeenCalled();
  });

  it("should cleanup event listener on unmount", () => {
    const removeEventListenerSpy = jest.spyOn(window, "removeEventListener");

    const { unmount } = render(<CanvasPanel />);

    unmount();

    expect(removeEventListenerSpy).toHaveBeenCalledWith(
      "keydown",
      expect.any(Function),
    );

    removeEventListenerSpy.mockRestore();
  });

  it("should handle multiple rapid keyboard shortcuts", async () => {
    const user = userEvent.setup();
    render(<CanvasPanel />);

    // Rapidly press Cmd+K multiple times
    await user.keyboard("{Meta>}k{/Meta}");
    await user.keyboard("{Meta>}k{/Meta}");
    await user.keyboard("{Meta>}k{/Meta}");

    expect(mockToggleSidebar).toHaveBeenCalledTimes(3);
  });

  it("should not interfere with other key combinations", async () => {
    const user = userEvent.setup();
    render(<CanvasPanel />);

    // Press Cmd+S (should not trigger canvas toggle)
    await user.keyboard("{Meta>}s{/Meta}");

    // Press just K without modifier (should not trigger)
    await user.keyboard("k");

    expect(mockToggleSidebar).not.toHaveBeenCalled();
  });
});
