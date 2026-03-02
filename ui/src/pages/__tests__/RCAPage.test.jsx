import React from "react";
import { fireEvent, render, waitFor } from "@testing-library/react";
import RCAPage from "../RCAPage";

const createJobMock = vi.fn(async () => ({
  job_id: "job-1",
  status: "queued",
}));
const refreshJobsMock = vi.fn();
const setSelectedJobIdMock = vi.fn();
const reloadReportMock = vi.fn();

const jobsState = {
  jobs: [],
  loadingJobs: false,
  creatingJob: false,
  deletingReport: false,
  selectedJobId: null,
  selectedJob: null,
};

const reportState = {
  loadingReport: false,
  reportError: null,
  reportErrorStatus: null,
  report: null,
  reportMeta: null,
  insights: {},
  hasReport: false,
};

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "u1" },
  }),
}));

vi.mock("../../hooks/useRcaJobs", () => ({
  useRcaJobs: () => ({
    ...jobsState,
    setSelectedJobId: setSelectedJobIdMock,
    createJob: createJobMock,
    deleteReportById: vi.fn(),
    removeJobByReportId: vi.fn(),
    refreshJobs: refreshJobsMock,
  }),
}));

vi.mock("../../hooks/useRcaReport", () => ({
  useRcaReport: () => ({
    ...reportState,
    reloadReport: reloadReportMock,
  }),
}));

describe("RCAPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    jobsState.jobs = [];
    jobsState.loadingJobs = false;
    jobsState.creatingJob = false;
    jobsState.deletingReport = false;
    jobsState.selectedJobId = null;
    jobsState.selectedJob = null;
    reportState.loadingReport = false;
    reportState.reportError = null;
    reportState.reportErrorStatus = null;
    reportState.report = null;
    reportState.reportMeta = null;
    reportState.insights = {};
    reportState.hasReport = false;
  });

  it("submits a create job request from composer", () => {
    const { getByText } = render(<RCAPage />);
    fireEvent.click(getByText("Generate Report"));
    expect(createJobMock).toHaveBeenCalledTimes(1);
    const payload = createJobMock.mock.calls[0][0];
    expect(payload).toHaveProperty("start");
    expect(payload).toHaveProperty("end");
    expect(payload).toHaveProperty("sensitivity");
  });

  it("shows quick-stat tiles when a report is available", () => {
    const fakeReport = {
      summary: "Test summary",
      overall_severity: "high",
      metric_anomalies: [1, 2],
      root_causes: [1],
      duration_seconds: 42,
    };
    reportState.report = fakeReport;
    reportState.reportMeta = fakeReport;
    reportState.hasReport = true;

    const { queryByText, getByText } = render(<RCAPage />);
    expect(queryByText("Test summary")).not.toBeInTheDocument();
    expect(getByText("Overall Severity")).toBeInTheDocument();
    expect(getByText("HIGH")).toBeInTheDocument();
    expect(getByText("Metric Anomalies")).toBeInTheDocument();
    expect(getByText("2")).toBeInTheDocument();
    expect(getByText("Root Causes")).toBeInTheDocument();
    expect(getByText("1")).toBeInTheDocument();
    expect(getByText("Duration (s)")).toBeInTheDocument();
    expect(getByText("42")).toBeInTheDocument();
  });
  it("clears a lookup id from storage when the report cannot be found", async () => {
    // start with a lookup value persisted
    localStorage.setItem("rcaPage.reportLookupId", JSON.stringify("bad-id"));
    reportState.reportError = "Report not found";
    reportState.reportErrorStatus = 404;

    render(<RCAPage />);
    // the component should react to the error by clearing both the stored
    // input and the internal id state so that subsequent mounts are quiet
    // the value should be reset to an empty string (stored as JSON) rather
    // than left as the invalid ID
    await waitFor(() => {
      expect(localStorage.getItem("rcaPage.reportLookupId")).toBe(
        JSON.stringify(""),
      );
    });
  });
  it("restores selected job id from localStorage when jobs include it", () => {
    localStorage.setItem("rcaPage.selectedJobId", "stored-job");
    jobsState.jobs = [{ job_id: "stored-job" }];

    render(<RCAPage />);
    expect(setSelectedJobIdMock).toHaveBeenCalledWith("stored-job");
  });

  it("removes stale selectedJobId from storage when jobs list changes", async () => {
    localStorage.setItem("rcaPage.selectedJobId", "gone-job");
    jobsState.jobs = [{ job_id: "other-job" }];

    render(<RCAPage />);
    await waitFor(() => {
      expect(localStorage.getItem("rcaPage.selectedJobId")).toBeNull();
    });
  });
});
