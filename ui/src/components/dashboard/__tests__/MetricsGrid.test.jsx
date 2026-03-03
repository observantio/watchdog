import React from "react";
import { render } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import { MetricsGrid } from "../MetricsGrid";

describe("MetricsGrid", () => {
  it("ignores stale metricOrder indices that do not exist in metrics", () => {
    const metrics = [
      {
        id: "a",
        label: "A",
        value: "1",
        trend: "",
        status: "default",
        icon: null,
      },
      {
        id: "b",
        label: "B",
        value: "2",
        trend: "",
        status: "default",
        icon: null,
      },
    ];
    const metricOrder = [0, 1, 2]; 

    const { getByText } = render(
      <MetricsGrid
        metrics={metrics}
        metricOrder={metricOrder}
        onMetricOrderChange={vi.fn()}
      />,
    );

    expect(getByText("A")).toBeInTheDocument();
    expect(getByText("B")).toBeInTheDocument();
  });
});
