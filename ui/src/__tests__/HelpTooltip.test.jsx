import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import HelpTooltip from "../components/HelpTooltip";

describe("HelpTooltip", () => {
  it("shows tooltip automatically when autoShow is true", () => {
    render(<HelpTooltip text="auto text" autoShow />);
    expect(screen.getByRole("tooltip")).toHaveTextContent("auto text");
  });

  it("does not render tooltip by default when autoShow is false", () => {
    render(<HelpTooltip text="hidden text" />);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});
