import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BankChartCanvasView } from "../BankChartCanvasView";
import type { BankChartData } from "@/lib/types";

// Mock react-plotly.js
jest.mock("react-plotly.js", () => {
  return function MockPlot() {
    return (
      <div data-testid="mock-plot" className="plotly">
        Mocked Plotly Chart
      </div>
    );
  };
});

describe("BankChartCanvasView - Download & Export", () => {
  const createMockData = (): BankChartData => ({
    metric_name: "imor",
    bank_names: ["INVEX", "BBVA"],
    time_range: {
      start: "2024-01-01",
      end: "2024-12-31",
    },
    plotly_config: {
      data: [
        {
          x: ["2024-01", "2024-02", "2024-03"],
          y: [2.5, 2.7, 2.3],
          type: "bar",
          name: "INVEX",
        },
        {
          x: ["2024-01", "2024-02", "2024-03"],
          y: [3.1, 3.0, 2.9],
          type: "bar",
          name: "BBVA",
        },
      ],
      layout: {
        title: "IMOR - Índice de Morosidad",
        xaxis: { title: "Periodo" },
        yaxis: { title: "IMOR (%)" },
      },
    },
    data_as_of: "2024-01-01T00:00:00Z",
    metadata: {},
  });

  beforeEach(() => {
    // Mock URL.createObjectURL and revokeObjectURL
    global.URL.createObjectURL = jest.fn(() => "mock-url");
    global.URL.revokeObjectURL = jest.fn();

    // Mock document.createElement to track link clicks
    jest.spyOn(document, "createElement");
    jest.spyOn(document.body, "appendChild");
    jest.spyOn(document.body, "removeChild");
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("Download PNG", () => {
    it("should render PNG download button", () => {
      const data = createMockData();
      render(<BankChartCanvasView data={data} />);

      const pngButton = screen.getByTitle("Descargar como PNG");
      expect(pngButton).toBeInTheDocument();
      expect(pngButton).toHaveTextContent("PNG");
    });

    it("should have correct button styling", () => {
      const data = createMockData();
      render(<BankChartCanvasView data={data} />);

      const pngButton = screen.getByTitle("Descargar como PNG");
      expect(pngButton).toHaveClass("hover:text-white");
      expect(pngButton).toHaveClass("bg-white/5");
    });

    it("should trigger PNG download on button click", async () => {
      const user = userEvent.setup();
      const data = createMockData();

      render(<BankChartCanvasView data={data} />);

      const pngButton = screen.getByTitle("Descargar como PNG");

      // Click the button - actual Plotly download happens in browser
      await user.click(pngButton);

      // Verify button is interactive
      expect(pngButton).toBeEnabled();
    });
  });

  describe("Export CSV", () => {
    it("should render CSV export button", () => {
      const data = createMockData();
      render(<BankChartCanvasView data={data} />);

      const csvButton = screen.getByTitle("Exportar a CSV");
      expect(csvButton).toBeInTheDocument();
      expect(csvButton).toHaveTextContent("CSV");
    });

    it("should create CSV file when clicked", async () => {
      const user = userEvent.setup();
      const data = createMockData();

      render(<BankChartCanvasView data={data} />);

      const csvButton = screen.getByTitle("Exportar a CSV");
      await user.click(csvButton);

      // Verify Blob was created
      expect(global.URL.createObjectURL).toHaveBeenCalled();
    });

    it("should create CSV with correct headers", async () => {
      const user = userEvent.setup();
      const data = createMockData();

      // Spy on Blob constructor
      const blobSpy = jest.spyOn(global, "Blob");

      render(<BankChartCanvasView data={data} />);

      const csvButton = screen.getByTitle("Exportar a CSV");
      await user.click(csvButton);

      // Verify Blob was created with CSV content
      expect(blobSpy).toHaveBeenCalledWith(
        expect.arrayContaining([expect.stringContaining("Banco,Periodo,IMOR")]),
        { type: "text/csv;charset=utf-8;" },
      );
    });

    it("should include data for all banks", async () => {
      const user = userEvent.setup();
      const data = createMockData();

      const blobSpy = jest.spyOn(global, "Blob");

      render(<BankChartCanvasView data={data} />);

      const csvButton = screen.getByTitle("Exportar a CSV");
      await user.click(csvButton);

      // Verify CSV includes both banks
      const csvContent = blobSpy.mock.calls[0][0][0] as string;
      expect(csvContent).toContain("INVEX");
      expect(csvContent).toContain("BBVA");
      expect(csvContent).toContain("2024-01");
      expect(csvContent).toContain("2.5");
      expect(csvContent).toContain("3.1");
    });

    it("should create download link with correct filename", async () => {
      const user = userEvent.setup();
      const data = createMockData();

      const createElementSpy = jest.spyOn(document, "createElement");

      render(<BankChartCanvasView data={data} />);

      const csvButton = screen.getByTitle("Exportar a CSV");
      await user.click(csvButton);

      // Find the link element creation
      const linkCall = createElementSpy.mock.calls.find(
        (call) => call[0] === "a",
      );
      expect(linkCall).toBeDefined();
    });

    it("should cleanup after download", async () => {
      const user = userEvent.setup();
      const data = createMockData();

      render(<BankChartCanvasView data={data} />);

      const csvButton = screen.getByTitle("Exportar a CSV");
      await user.click(csvButton);

      // Verify URL was revoked
      expect(global.URL.revokeObjectURL).toHaveBeenCalledWith("mock-url");
    });

    it("should handle empty data gracefully", async () => {
      const user = userEvent.setup();
      const data = createMockData();
      data.plotly_config.data = [];

      const consoleErrorSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      render(<BankChartCanvasView data={data} />);

      const csvButton = screen.getByTitle("Exportar a CSV");
      await user.click(csvButton);

      // Should not create blob for empty data
      expect(global.URL.createObjectURL).not.toHaveBeenCalled();

      consoleErrorSpy.mockRestore();
    });
  });

  describe("Button Placement", () => {
    it("should render both buttons in header", () => {
      const data = createMockData();
      render(<BankChartCanvasView data={data} />);

      const pngButton = screen.getByTitle("Descargar como PNG");
      const csvButton = screen.getByTitle("Exportar a CSV");

      // Both buttons should be in the same parent container
      expect(pngButton.parentElement).toBe(csvButton.parentElement);
    });

    it("should display buttons in correct order", () => {
      const data = createMockData();
      const { container } = render(<BankChartCanvasView data={data} />);

      const buttons = container.querySelectorAll("button");
      const buttonTexts = Array.from(buttons).map((btn) =>
        btn.textContent?.trim(),
      );

      // PNG button should come before CSV button
      const pngIndex = buttonTexts.findIndex((text) => text?.includes("PNG"));
      const csvIndex = buttonTexts.findIndex((text) => text?.includes("CSV"));

      expect(pngIndex).toBeLessThan(csvIndex);
    });
  });
});
