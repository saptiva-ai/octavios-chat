/**
 * Tests for Canvas Store - Bank Chart Integration
 *
 * Tests the state management for bank chart visualizations in the canvas.
 */

import { useCanvasStore } from "../canvas-store";
import type { BankChartData } from "@/lib/types";

const mockChartData: BankChartData = {
  type: "bank_chart",
  metric_name: "imor",
  bank_names: ["BBVA"],
  time_range: { start: "2024-01-01", end: "2024-12-31" },
  data_as_of: "2024-12-01T00:00:00Z",
  source: "CNBV",
  plotly_config: {
    data: [{ x: ["2024-01"], y: [2.5], type: "bar", name: "BBVA" }],
    layout: { title: "IMOR" },
  },
};

describe("Canvas Store - Bank Chart", () => {
  beforeEach(() => {
    // Reset store to initial state
    useCanvasStore.setState({
      isSidebarOpen: false,
      activeArtifactId: null,
      activeArtifactData: null,
      activeBankChart: null,
      activeMessageId: null,
      chartHistory: [],
    });
  });

  describe("openBankChart", () => {
    it("should open sidebar and set bank chart data", () => {
      const { openBankChart } = useCanvasStore.getState();

      openBankChart(mockChartData, "artifact_123", "msg_456", false);

      const state = useCanvasStore.getState();
      expect(state.isSidebarOpen).toBe(true);
      expect(state.activeBankChart).toEqual(mockChartData);
      expect(state.activeMessageId).toBe("msg_456");
    });

    it("should NOT set activeArtifactId when artifact is 'temp'", () => {
      const { openBankChart } = useCanvasStore.getState();

      openBankChart(mockChartData, "temp", "msg_789", false);

      const state = useCanvasStore.getState();
      expect(state.activeArtifactId).toBeNull();
      expect(state.activeBankChart).toEqual(mockChartData);
    });

    it("should set activeArtifactId when artifact is valid", () => {
      const { openBankChart } = useCanvasStore.getState();

      openBankChart(mockChartData, "artifact_real_123", "msg_abc", false);

      const state = useCanvasStore.getState();
      expect(state.activeArtifactId).toBe("artifact_real_123");
    });

    it("should clear activeArtifactData when opening bank chart", () => {
      // Set some audit data first
      useCanvasStore.setState({
        activeArtifactData: { type: "audit", data: "some audit" },
      });

      const { openBankChart } = useCanvasStore.getState();
      openBankChart(mockChartData, "artifact_123", "msg_456", false);

      const state = useCanvasStore.getState();
      expect(state.activeArtifactData).toBeNull();
    });

    it("should add chart to history", () => {
      const { openBankChart } = useCanvasStore.getState();

      openBankChart(mockChartData, "artifact_123", "msg_456", false);

      const state = useCanvasStore.getState();
      expect(state.chartHistory).toHaveLength(1);
      expect(state.chartHistory[0]).toEqual({
        artifactId: "artifact_123",
        messageId: "msg_456",
        isActive: true,
      });
    });

    it("should not duplicate charts in history", () => {
      const { openBankChart } = useCanvasStore.getState();

      // Open same chart twice
      openBankChart(mockChartData, "artifact_123", "msg_456", false);
      openBankChart(mockChartData, "artifact_123", "msg_456", false);

      const state = useCanvasStore.getState();
      expect(state.chartHistory).toHaveLength(1);
    });

    it("should mark correct chart as active in history", () => {
      const { openBankChart } = useCanvasStore.getState();

      // Open two different charts
      openBankChart(mockChartData, "artifact_1", "msg_1", false);
      openBankChart(mockChartData, "artifact_2", "msg_2", false);

      const state = useCanvasStore.getState();
      expect(state.chartHistory).toHaveLength(2);
      expect(state.chartHistory[0].isActive).toBe(false); // First chart
      expect(state.chartHistory[1].isActive).toBe(true); // Second chart
    });
  });

  describe("setActiveMessage", () => {
    it("should update activeMessageId", () => {
      const { setActiveMessage } = useCanvasStore.getState();

      setActiveMessage("msg_999");

      const state = useCanvasStore.getState();
      expect(state.activeMessageId).toBe("msg_999");
    });

    it("should mark matching chart as active in history", () => {
      const { openBankChart, setActiveMessage } = useCanvasStore.getState();

      // Add multiple charts
      openBankChart(mockChartData, "artifact_1", "msg_1", false);
      openBankChart(mockChartData, "artifact_2", "msg_2", false);

      // Set first message as active
      setActiveMessage("msg_1");

      const state = useCanvasStore.getState();
      expect(state.chartHistory[0].isActive).toBe(true);
      expect(state.chartHistory[1].isActive).toBe(false);
    });
  });

  describe("toggleSidebar", () => {
    it("should clear activeMessageId when closing sidebar", () => {
      const { openBankChart, toggleSidebar } = useCanvasStore.getState();

      // Open chart and sidebar
      openBankChart(mockChartData, "artifact_123", "msg_456", false);

      // Close sidebar
      toggleSidebar();

      const state = useCanvasStore.getState();
      expect(state.isSidebarOpen).toBe(false);
      expect(state.activeMessageId).toBeNull();
    });

    it("should mark all charts as inactive when closing sidebar", () => {
      const { openBankChart, toggleSidebar } = useCanvasStore.getState();

      // Add charts
      openBankChart(mockChartData, "artifact_1", "msg_1", false);
      openBankChart(mockChartData, "artifact_2", "msg_2", false);

      // Close sidebar
      toggleSidebar();

      const state = useCanvasStore.getState();
      expect(state.chartHistory.every((c) => !c.isActive)).toBe(true);
    });
  });

  describe("clearChartHistory", () => {
    it("should remove all charts from history", () => {
      const { openBankChart, clearChartHistory } = useCanvasStore.getState();

      // Add charts
      openBankChart(mockChartData, "artifact_1", "msg_1", false);
      openBankChart(mockChartData, "artifact_2", "msg_2", false);

      // Clear history
      clearChartHistory();

      const state = useCanvasStore.getState();
      expect(state.chartHistory).toHaveLength(0);
    });
  });
});
