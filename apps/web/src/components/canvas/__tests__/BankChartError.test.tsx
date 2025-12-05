/**
 * Tests for BankChartError Component
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { BankChartError } from "../BankChartError";

describe("BankChartError", () => {
  it("should render error title", () => {
    render(<BankChartError />);
    expect(screen.getByText("Error al cargar la gráfica")).toBeInTheDocument();
  });

  it("should render default error message", () => {
    render(<BankChartError />);
    expect(
      screen.getByText(/No se pudo cargar la gráfica/i),
    ).toBeInTheDocument();
  });

  it("should render custom error message", () => {
    const customMessage = "Error personalizado de prueba";
    render(<BankChartError message={customMessage} />);
    expect(screen.getByText(customMessage)).toBeInTheDocument();
  });

  it("should render retry button by default", () => {
    const mockRetry = jest.fn();
    render(<BankChartError onRetry={mockRetry} />);

    const retryButton = screen.getByRole("button", { name: /reintentar/i });
    expect(retryButton).toBeInTheDocument();
  });

  it("should call onRetry when retry button is clicked", () => {
    const mockRetry = jest.fn();
    render(<BankChartError onRetry={mockRetry} />);

    const retryButton = screen.getByRole("button", { name: /reintentar/i });
    fireEvent.click(retryButton);

    expect(mockRetry).toHaveBeenCalledTimes(1);
  });

  it("should not render retry button when showRetry is false", () => {
    const mockRetry = jest.fn();
    render(<BankChartError onRetry={mockRetry} showRetry={false} />);

    const retryButton = screen.queryByRole("button", { name: /reintentar/i });
    expect(retryButton).not.toBeInTheDocument();
  });

  it("should not render retry button when onRetry is not provided", () => {
    render(<BankChartError />);

    const retryButton = screen.queryByRole("button", { name: /reintentar/i });
    expect(retryButton).not.toBeInTheDocument();
  });

  it("should render warning icon", () => {
    const { container } = render(<BankChartError />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });

  it("should render help text", () => {
    render(<BankChartError />);
    expect(
      screen.getByText(/Si el problema persiste, contacta al administrador/i),
    ).toBeInTheDocument();
  });
});
