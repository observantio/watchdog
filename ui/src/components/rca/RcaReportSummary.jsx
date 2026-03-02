import PropTypes from "prop-types";
import { MetricCard } from "../ui";
import Section from "./Section";

function severityStatus(severity) {
  if (severity === "critical" || severity === "high") return "error";
  if (severity === "medium") return "warning";
  return "success";
}

export default function RcaReportSummary({ report, compact = false }) {
  if (!report) return null;
  const quality = report.quality || null;
  const gatingProfile = quality?.gating_profile || "";
  const gatingProfileShort =
    gatingProfile.length > 18
      ? `${gatingProfile.slice(0, 15)}...`
      : gatingProfile;
  const suppressionTotal = quality?.suppression_counts
    ? Object.values(quality.suppression_counts).reduce(
        (acc, n) => acc + Number(n || 0),
        0,
      )
    : 0;
  const densityValues = quality?.anomaly_density
    ? Object.values(quality.anomaly_density).map((v) => Number(v || 0))
    : [];
  const maxDensity = densityValues.length ? Math.max(...densityValues) : null;

  const content = (
    <>
      <h3 className="text-lg text-sre-text font-semibold mb-2">
        Report Summary
      </h3>
      <p className="text-sm text-sre-text-muted mb-4">
        {report.summary || "No summary available"}
      </p>
      <div className="flex flex-wrap gap-3">
        <div className="flex-1 min-w-[150px]">
          <MetricCard
            label="Overall Severity"
            value={String(report.overall_severity || "unknown").toUpperCase()}
            status={severityStatus(report.overall_severity)}
          />
        </div>
        <div className="flex-1 min-w-[150px]">
          <MetricCard
            label="Metric Anomalies"
            value={report.metric_anomalies?.length || 0}
            status="info"
          />
        </div>
        <div className="flex-1 min-w-[150px]">
          <MetricCard
            label="Root Causes"
            value={report.root_causes?.length || 0}
            status="warning"
          />
        </div>
        <div className="flex-1 min-w-[150px]">
          <MetricCard
            label="Duration (s)"
            value={report.duration_seconds || 0}
            status="default"
          />
        </div>
        {quality && (
          <div className="flex-1 min-w-[150px]">
            <MetricCard
              label="Suppressed"
              value={suppressionTotal}
              status={suppressionTotal > 0 ? "warning" : "success"}
            />
          </div>
        )}
        {quality?.gating_profile && (
          <div className="flex-1 min-w-[180px]">
            <MetricCard
              label="Gating Profile"
              value={
                <span
                  className="block truncate text-base font-mono max-w-[10rem]"
                  title={gatingProfile}
                >
                  {gatingProfileShort}
                </span>
              }
              status="default"
            />
          </div>
        )}
        {maxDensity !== null && (
          <div className="flex-1 min-w-[160px]">
            <MetricCard
              label="Max Density/hr"
              value={maxDensity.toFixed(2)}
              status={maxDensity > 1 ? "warning" : "success"}
            />
          </div>
        )}
      </div>
    </>
  );

  if (compact) {
    return <div>{content}</div>;
  }

  // non-compact, wrap using Section to keep consistent style
  return <Section>{content}</Section>;
}

RcaReportSummary.propTypes = {
  report: PropTypes.object,
  compact: PropTypes.bool,
};
