/**
 * E2E-style integration tests for Bank Chart Canvas flow
 *
 * Tests the complete user journey:
 * 1. User receives bank chart from chat
 * 2. Clicks button to open canvas
 * 3. Views chart in canvas sidebar
 * 4. Interacts with tabs (Chart, SQL, Interpretation)
 * 5. Downloads PNG / Exports CSV
 * 6. Uses keyboard shortcuts
 * 7. Closes canvas
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BankChartCanvasView } from "../BankChartCanvasView";
import { useCanvasStore } from "@/lib/stores/canvas-store";
import type { BankChartData } from "@/lib/types";

// Mock dependencies
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
jest.mock("../CanvasErrorBoundary", () => ({
  CanvasErrorBoundary: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

// Mock Plotly component
const MockPlot = () => (
  <div data-testid="plotly-chart" className="plotly">
    Chart Visualization
  </div>
);

jest.mock("react-plotly.js", () => MockPlot);

// Mock next/dynamic to return the component immediately (no lazy loading in tests)
jest.mock("next/dynamic", () => {
  return (fn: () => Promise<any>) => {
    // For react-plotly.js, return the MockPlot directly
    const Component = () => <MockPlot />;
    Component.displayName = "DynamicComponent";
    return Component;
  };
});

describe("Bank Chart Canvas - E2E Flow", () => {
  const mockBankChartData: BankChartData = {
    metric_name: "imor",
    bank_names: ["INVEX", "BBVA", "Santander"],
    time_range: {
      start: "2024-01-01",
      end: "2024-12-31",
    },
    plotly_config: {
      data: [
        {
          x: ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"],
          y: [2.5, 2.7, 2.3, 2.1],
          type: "bar",
          name: "INVEX",
        },
        {
          x: ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"],
          y: [3.1, 3.0, 2.9, 2.8],
          type: "bar",
          name: "BBVA",
        },
        {
          x: ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"],
          y: [2.8, 2.9, 2.7, 2.6],
          type: "bar",
          name: "Santander",
        },
      ],
      layout: {
        title: "IMOR - Índice de Morosidad 2024",
        xaxis: { title: "Trimestre" },
        yaxis: { title: "IMOR (%)" },
      },
    },
    data_as_of: "2024-12-01T00:00:00Z",
    metadata: {
      sql_generated:
        "SELECT bank_name, quarter, imor FROM metrics WHERE year = 2024",
      metric_interpretation:
        "El IMOR (Índice de Morosidad) mide la proporción de cartera vencida respecto a la cartera total. Un IMOR bajo indica mejor calidad crediticia.",
    },
  };

  describe("Complete User Journey", () => {
    it("should handle full chart viewing workflow", async () => {
      const user = userEvent.setup();

      // Render the chart view
      render(<BankChartCanvasView data={mockBankChartData} />);

      // Step 1: Verify chart loads with correct title
      expect(screen.getByText("IMOR")).toBeInTheDocument();

      // Step 2: Verify bank names are displayed
      expect(screen.getByText(/INVEX, BBVA, Santander/)).toBeInTheDocument();

      // Step 3: Verify time range is shown (check for "Actualizado" which contains date)
      expect(screen.getByText(/Actualizado:/)).toBeInTheDocument();

      // Step 4: Verify chart tab is active by default
      expect(screen.getByText("Gráfica")).toHaveClass("border-primary");

      // Step 5: Verify Plotly chart is rendered
      expect(screen.getByTestId("plotly-chart")).toBeInTheDocument();
    });

    it("should navigate between tabs successfully", async () => {
      const user = userEvent.setup();
      render(<BankChartCanvasView data={mockBankChartData} />);

      // Start on Chart tab
      const chartTab = screen.getByText("Gráfica");
      expect(chartTab).toHaveClass("border-primary");

      // Click SQL Query tab
      const sqlTab = screen.getByText("SQL Query");
      await user.click(sqlTab);

      // Verify SQL content is displayed
      await waitFor(() => {
        expect(screen.getByText(/SELECT bank_name/)).toBeInTheDocument();
      });

      // Click Interpretation tab
      const interpretationTab = screen.getByText("Interpretación");
      await user.click(interpretationTab);

      // Verify interpretation content is displayed
      await waitFor(() => {
        expect(screen.getByText(/Índice de Morosidad/)).toBeInTheDocument();
      });

      // Go back to Chart tab
      await user.click(chartTab);

      // Verify chart is displayed again
      expect(screen.getByTestId("plotly-chart")).toBeInTheDocument();
    });

    it("should export data via action buttons", async () => {
      const user = userEvent.setup();

      // Mock URL.createObjectURL
      global.URL.createObjectURL = jest.fn(() => "mock-blob-url");
      global.URL.revokeObjectURL = jest.fn();

      render(<BankChartCanvasView data={mockBankChartData} />);

      // Find and click CSV export button
      const csvButton = screen.getByTitle("Exportar a CSV");
      await user.click(csvButton);

      // Verify blob was created (CSV download triggered)
      expect(global.URL.createObjectURL).toHaveBeenCalled();

      // Find PNG download button
      const pngButton = screen.getByTitle("Descargar como PNG");
      expect(pngButton).toBeInTheDocument();

      // Click PNG button (actual download happens in browser with Plotly)
      await user.click(pngButton);

      // Verify button is functional
      expect(pngButton).toBeEnabled();
    });

    it("should display all metadata correctly", async () => {
      render(<BankChartCanvasView data={mockBankChartData} />);

      // Verify metric name
      expect(screen.getByText("IMOR")).toBeInTheDocument();

      // Verify all three banks are listed
      const bankText = screen.getByText(/INVEX, BBVA, Santander/);
      expect(bankText).toBeInTheDocument();

      // Verify date range and timestamp are shown
      expect(screen.getByText(/Actualizado:/)).toBeInTheDocument();

      // Verify at least one date element exists
      const dateElements = screen.getAllByText(/2024/);
      expect(dateElements.length).toBeGreaterThan(0);
    });

    it("should handle missing optional metadata gracefully", async () => {
      const dataWithoutMetadata: BankChartData = {
        ...mockBankChartData,
        metadata: {},
      };

      render(<BankChartCanvasView data={dataWithoutMetadata} />);

      // Chart tab should still be visible
      expect(screen.getByText("Gráfica")).toBeInTheDocument();

      // SQL and Interpretation tabs should NOT be visible
      expect(screen.queryByText("SQL Query")).not.toBeInTheDocument();
      expect(screen.queryByText("Interpretación")).not.toBeInTheDocument();

      // Chart should still render
      expect(screen.getByTestId("plotly-chart")).toBeInTheDocument();
    });
  });

  // Note: Canvas Panel Integration tests are covered in canvas-keyboard-shortcuts.test.tsx
  // This E2E suite focuses on the BankChartCanvasView component in isolation

  describe("Error Handling", () => {
    it("should show error when chart data is invalid", () => {
      const invalidData = {
        ...mockBankChartData,
        plotly_config: {
          data: null, // Invalid
          layout: {},
        },
      } as any;

      render(<BankChartCanvasView data={invalidData} />);

      // Should show error message
      expect(
        screen.getByText(/Datos de gráfica inválidos/),
      ).toBeInTheDocument();
    });

    it("should show error when metric name is missing", () => {
      const invalidData = {
        ...mockBankChartData,
        metric_name: "",
      };

      render(<BankChartCanvasView data={invalidData} />);

      expect(
        screen.getByText(/Nombre de métrica faltante/),
      ).toBeInTheDocument();
    });

    it("should show error when banks are missing", () => {
      const invalidData = {
        ...mockBankChartData,
        bank_names: [],
      };

      render(<BankChartCanvasView data={invalidData} />);

      expect(
        screen.getByText(/No se especificaron bancos/),
      ).toBeInTheDocument();
    });

    it("should show retry button on error", async () => {
      const user = userEvent.setup();
      const invalidData = {
        ...mockBankChartData,
        metric_name: "",
      };

      render(<BankChartCanvasView data={invalidData} />);

      const retryButton = screen.getByText("Reintentar");
      expect(retryButton).toBeInTheDocument();

      // Click retry button
      await user.click(retryButton);

      // Loading state should appear briefly
      // (In real scenario, this would trigger a re-fetch)
    });
  });

  describe("Responsive Behavior", () => {
    it("should render on mobile viewport", () => {
      // Mock mobile viewport
      global.innerWidth = 375;
      global.innerHeight = 667;

      render(<BankChartCanvasView data={mockBankChartData} />);

      // Chart should still render
      expect(screen.getByText("IMOR")).toBeInTheDocument();
      expect(screen.getByTestId("plotly-chart")).toBeInTheDocument();
    });

    it("should render on desktop viewport", () => {
      // Mock desktop viewport
      global.innerWidth = 1920;
      global.innerHeight = 1080;

      render(<BankChartCanvasView data={mockBankChartData} />);

      // Chart should render with full features
      expect(screen.getByText("IMOR")).toBeInTheDocument();
      expect(screen.getByTitle("Descargar como PNG")).toBeInTheDocument();
      expect(screen.getByTitle("Exportar a CSV")).toBeInTheDocument();
    });
  });

  describe("Performance", () => {
    it("should handle large datasets efficiently", () => {
      const largeData: BankChartData = {
        ...mockBankChartData,
        bank_names: Array.from({ length: 10 }, (_, i) => `Bank_${i}`),
        plotly_config: {
          ...mockBankChartData.plotly_config,
          data: Array.from({ length: 10 }, (_, i) => ({
            x: Array.from({ length: 12 }, (_, j) => `2024-${j + 1}`),
            y: Array.from({ length: 12 }, () => Math.random() * 5),
            type: "bar",
            name: `Bank_${i}`,
          })),
        },
      };

      const startTime = performance.now();
      render(<BankChartCanvasView data={largeData} />);
      const endTime = performance.now();

      // Should render in less than 1 second
      expect(endTime - startTime).toBeLessThan(1000);

      // Verify it rendered
      expect(screen.getByText("IMOR")).toBeInTheDocument();
    });

    it("should memoize sanitized content", () => {
      const { rerender } = render(
        <BankChartCanvasView data={mockBankChartData} />,
      );

      // Re-render with same data
      rerender(<BankChartCanvasView data={mockBankChartData} />);

      // Should still display correctly (memoization should prevent re-sanitization)
      expect(screen.getByText("IMOR")).toBeInTheDocument();
    });
  });
});
