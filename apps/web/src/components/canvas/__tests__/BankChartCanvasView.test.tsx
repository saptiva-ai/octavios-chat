/**
 * Tests for BankChartCanvasView Component
 *
 * Tests the full bank chart visualization in the canvas sidebar.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { BankChartCanvasView } from "../BankChartCanvasView";
import type { BankChartData } from "@/lib/types";

// Mock react-plotly.js to avoid rendering issues in tests
jest.mock("react-plotly.js", () => ({
  __esModule: true,
  default: ({ data, layout }: any) => (
    <div data-testid="plotly-chart">
      <div data-testid="plotly-data">{JSON.stringify(data)}</div>
      <div data-testid="plotly-layout">{JSON.stringify(layout)}</div>
    </div>
  ),
}));

const mockChartData: BankChartData = {
  type: "bank_chart",
  metric_name: "imor",
  bank_names: ["BBVA", "Santander", "HSBC"],
  time_range: {
    start: "2024-01-01",
    end: "2024-12-31",
  },
  data_as_of: "2024-12-01T10:30:00Z",
  source: "CNBV",
  plotly_config: {
    data: [
      {
        x: ["2024-01", "2024-02", "2024-03"],
        y: [2.5, 2.3, 2.1],
        type: "bar",
        name: "BBVA",
      },
    ],
    layout: {
      title: "IMOR - Índice de Morosidad",
      xaxis: { title: "Periodo" },
      yaxis: { title: "Porcentaje" },
    },
  },
  metadata: {
    sql_generated: "SELECT metric_value FROM banking_metrics WHERE metric_name = 'imor'",
    metric_interpretation: "El Índice de Morosidad (IMOR) representa el porcentaje de créditos vencidos.",
  },
};

describe("BankChartCanvasView", () => {
  it("should render metric name in header", () => {
    render(<BankChartCanvasView data={mockChartData} />);
    expect(screen.getByText("IMOR")).toBeInTheDocument();
  });

  it("should render bank names", () => {
    render(<BankChartCanvasView data={mockChartData} />);
    expect(screen.getByText(/BBVA, Santander, HSBC/)).toBeInTheDocument();
  });

  it("should render time range", () => {
    render(<BankChartCanvasView data={mockChartData} />);
    // Dates will be formatted based on locale
    expect(screen.getByText(/2024/)).toBeInTheDocument();
  });

  it("should render component without crashing", () => {
    const { container } = render(<BankChartCanvasView data={mockChartData} />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it("should render chart tab by default", () => {
    render(<BankChartCanvasView data={mockChartData} />);
    const plotlyChart = screen.getByTestId("plotly-chart");
    expect(plotlyChart).toBeInTheDocument();
  });

  it("should render SQL tab when clicked", () => {
    render(<BankChartCanvasView data={mockChartData} />);

    const sqlTab = screen.getByText(/SQL Query/i);
    fireEvent.click(sqlTab);

    expect(screen.getByText(/SELECT metric_value/)).toBeInTheDocument();
  });

  it("should render interpretation tab when clicked", () => {
    render(<BankChartCanvasView data={mockChartData} />);

    const interpretationTab = screen.getByText(/Interpretación/i);
    fireEvent.click(interpretationTab);

    expect(screen.getByText(/porcentaje de créditos vencidos/i)).toBeInTheDocument();
  });

  it("should switch between tabs correctly", () => {
    render(<BankChartCanvasView data={mockChartData} />);

    // Initially on chart tab
    expect(screen.getByTestId("plotly-chart")).toBeInTheDocument();

    // Switch to SQL tab
    const sqlTab = screen.getByText(/SQL Query/i);
    fireEvent.click(sqlTab);
    expect(screen.getByText(/SELECT metric_value/)).toBeInTheDocument();

    // Switch back to chart tab
    const chartTab = screen.getByText(/Gráfica/i);
    fireEvent.click(chartTab);
    expect(screen.getByTestId("plotly-chart")).toBeInTheDocument();
  });

  it("should render chart even if SQL query is missing", () => {
    const dataWithoutSQL = {
      ...mockChartData,
      metadata: {
        metric_interpretation: "Some interpretation",
      },
    };

    render(<BankChartCanvasView data={dataWithoutSQL} />);

    // Chart should still render
    const plotlyChart = screen.getByTestId("plotly-chart");
    expect(plotlyChart).toBeInTheDocument();
  });

  it("should render chart even if interpretation is missing", () => {
    const dataWithoutInterpretation = {
      ...mockChartData,
      metadata: {
        sql_generated: "SELECT * FROM table",
      },
    };

    render(<BankChartCanvasView data={dataWithoutInterpretation} />);

    // Chart should still render
    const plotlyChart = screen.getByTestId("plotly-chart");
    expect(plotlyChart).toBeInTheDocument();
  });

  it("should render Plotly chart with correct data", () => {
    render(<BankChartCanvasView data={mockChartData} />);

    const plotlyData = screen.getByTestId("plotly-data");
    const dataContent = plotlyData.textContent;

    expect(dataContent).toContain("2024-01");
    expect(dataContent).toContain("BBVA");
  });

  it("should render Plotly chart with correct layout", () => {
    render(<BankChartCanvasView data={mockChartData} />);

    const plotlyLayout = screen.getByTestId("plotly-layout");
    const layoutContent = plotlyLayout.textContent;

    expect(layoutContent).toContain("IMOR");
    expect(layoutContent).toContain("Periodo");
  });
});
