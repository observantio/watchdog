import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor, fireEvent } from "@testing-library/react";
import LokiPage from "../pages/LokiPage";

vi.mock("../hooks", () => ({
  useAutoRefresh: () => {},
}));

vi.mock("../contexts/ToastContext", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}));

vi.mock("../api", () => ({
  getLabels: vi.fn(),
  getLabelValues: vi.fn(),
  queryLogs: vi.fn(),
  getLogVolume: vi.fn(),
}));

vi.mock("../components/ui/PageHeader", () => ({
  default: ({ children }) => <div>{children}</div>,
}));
vi.mock("../components/ui/AutoRefreshControl", () => ({
  default: () => <div />,
}));
vi.mock("../components/ui", () => ({
  Card: ({ children }) => <div>{children}</div>,
  Button: ({ children }) => <button>{children}</button>,
  Alert: ({ children }) => <div>{children}</div>,
  Spinner: () => <div>Loading</div>,
  // tests reference Badge in LogResults, make sure mock exports it
  Badge: ({ children }) => <span>{children}</span>,
}));
// use real query form/results to exercise new controls
// mocks still exist for subordinate components we don't care about
// (LogVolume, LogQuickFilters, LogLabels)
//
// vi.mock('../components/loki/LogQueryForm', () => ({ default: () => <div /> }))
// vi.mock('../components/loki/LogResults', () => ({ default: () => <div /> }))
vi.mock("../components/loki/LogVolume", () => ({ default: () => <div /> }));
vi.mock("../components/loki/LogQuickFilters", () => ({
  default: () => <div />,
}));
vi.mock("../components/loki/LogLabels", () => ({ default: () => <div /> }));
vi.mock("../components/HelpTooltip", () => ({ default: () => <span /> }));

import * as api from "../api";

describe("LokiPage performance behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("prefetches label values with cap during initial load", async () => {
    const labels = Array.from({ length: 20 }, (_, i) => `label_${i}`);
    api.getLabels.mockResolvedValue({ data: labels });
    api.getLabelValues.mockImplementation(async (label) => ({
      data: [`${label}_value`],
    }));

    render(<LokiPage />);

    await waitFor(() => expect(api.getLabels).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.getLabelValues).toHaveBeenCalledTimes(12));
  });

  it("uses search limit and page size and paginates results", async () => {
    api.getLabels.mockResolvedValue({ data: [] });
    // generate 45 dummy streams each with one log value
    const fakeStreams = Array.from({ length: 45 }, (_, i) => ({
      stream: {},
      values: [[i, `log${i}`]],
    }));
    api.queryLogs.mockResolvedValue({ data: { result: fakeStreams } });

    const { getByText } = render(<LokiPage />);

    // change Search Limit to 50
    const limitLabel = getByText(/Search Limit/i);
    const limitSelect = limitLabel.parentElement.querySelector("select");
    fireEvent.change(limitSelect, { target: { value: "50" } });

    // change Page Size to 20
    const pageSizeLabel = getByText(/Page Size/i);
    // the select we want is immediately after the label, not just the first select in the parent
    const pageSizeSelect = pageSizeLabel.nextElementSibling;
    fireEvent.change(pageSizeSelect, { target: { value: "20" } });

    const runBtn = getByText(/Run Query/i);
    fireEvent.click(runBtn);

    await waitFor(() => expect(api.queryLogs).toHaveBeenCalled());
    const lastCall = api.queryLogs.mock.calls[0][0];
    expect(lastCall.limit).toBe(50);

    // pagination summary should reflect pageSize
    await waitFor(() =>
      expect(getByText(/Showing 1–20 of 45 streams/)).toBeInTheDocument(),
    );
  });

  it("displays statistic cards calculated from results", async () => {
    api.getLabels.mockResolvedValue({ data: [] });
    const fakeStreams = [
      {
        stream: { service_name: "svc1" },
        values: [
          [0, "a"],
          [1, "b"],
        ],
      },
      { stream: { service_name: "svc1" }, values: [[0, "c"]] },
      {
        stream: { service_name: "svc2" },
        values: [
          [0, "d"],
          [1, "e"],
          [2, "f"],
        ],
      },
    ];
    api.queryLogs.mockResolvedValue({ data: { result: fakeStreams } });

    const { getByText, container } = render(<LokiPage />);
    const runBtn = getByText(/Run Query/i);
    fireEvent.click(runBtn);

    await waitFor(() => expect(api.queryLogs).toHaveBeenCalled());
    // stats should appear with labels
    expect(getByText(/Streams/i)).toBeInTheDocument();
    expect(getByText(/Total Logs/i)).toBeInTheDocument();
    expect(getByText(/Avg\/stream/i)).toBeInTheDocument();
    expect(getByText(/Services/i)).toBeInTheDocument();
    expect(getByText(/Top Terms/i)).toBeInTheDocument();
    // verify service names appear in detail text
    expect(container.textContent).toContain("svc1");
    expect(container.textContent).toContain("svc2");
    // ensure top terms are rendered as strings not object placeholders
    expect(container.textContent).not.toContain("[object Object]");
    // confirm counts too
    const nums = container.querySelectorAll("div.text-2xl.font-bold");
    const values = Array.from(nums).map((n) => n.textContent.trim());
    // expect all metrics: streams,total,avg,services,terms
    expect(values).toEqual(expect.arrayContaining(["3", "6", "2", "2", "2"]));
  });

  it("hides statistic cards when there are no results", async () => {
    api.getLabels.mockResolvedValue({ data: [] });
    api.queryLogs.mockResolvedValue({ data: { result: [] } });

    const { queryByText, getByText } = render(<LokiPage />);
    const runBtn = getByText(/Run Query/i);
    fireEvent.click(runBtn);

    await waitFor(() => expect(api.queryLogs).toHaveBeenCalled());
    // stats labels should not be rendered at all
    expect(queryByText(/Streams/i)).toBeNull();
    expect(queryByText(/Total Logs/i)).toBeNull();
    expect(queryByText(/Avg\/stream/i)).toBeNull();
    expect(queryByText(/Services/i)).toBeNull();
    expect(queryByText(/Top Terms/i)).toBeNull();
  });

  it("restores filters from localStorage and triggers a query on mount", async () => {
    const saved = {
      selectedFilters: [{ label: "foo", value: "bar" }],
      searchLimit: 10,
    };
    localStorage.setItem("lokiPageState", JSON.stringify(saved));
    api.getLabels.mockResolvedValue({ data: [] });
    api.queryLogs.mockResolvedValue({ data: { result: [] } });

    render(<LokiPage />);

    await waitFor(() => expect(api.queryLogs).toHaveBeenCalled());
    const call = api.queryLogs.mock.calls[0][0];
    expect(call.limit).toBe(10);
  });
});
