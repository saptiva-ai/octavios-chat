/**
 * Tests for BankChartSkeleton Component
 */

import { render, screen } from "@testing-library/react";
import { BankChartSkeleton } from "../BankChartSkeleton";

describe("BankChartSkeleton", () => {
  it("should render without crashing", () => {
    const { container } = render(<BankChartSkeleton />);
    expect(container.firstChild).toBeInTheDocument();
  });

  it("should have animate-pulse class for animation", () => {
    const { container } = render(<BankChartSkeleton />);
    const animatedElement = container.querySelector(".animate-pulse");
    expect(animatedElement).toBeInTheDocument();
  });

  it("should render skeleton bars", () => {
    const { container } = render(<BankChartSkeleton />);
    const skeletonBars = container.querySelectorAll(".bg-primary\\/20");
    expect(skeletonBars.length).toBeGreaterThan(0);
  });

  it("should render metadata skeleton", () => {
    const { container } = render(<BankChartSkeleton />);
    const metadataSection = container.querySelector(".border-white\\/10");
    expect(metadataSection).toBeInTheDocument();
  });

  it("should render tabs skeleton", () => {
    const { container } = render(<BankChartSkeleton />);
    const tabSkeletons = container.querySelectorAll(".rounded-t");
    expect(tabSkeletons.length).toBeGreaterThanOrEqual(3);
  });
});
