import { useRef, useState } from "react";
import PropTypes from "prop-types";
import YAML from "yaml";
import { Card, Button, Input, Select } from "../ui";
import { TIME_RANGES } from "../../utils/constants";
import {
  mergeMetricQueries,
  RCA_DEFAULT_METRIC_QUERIES_FROM_DASHBOARDS,
} from "../grafana/dashboardTemplates/metricCatalog";

export default function RcaJobComposer({ onCreate, onDownloadTemplate, creating }) {
  const [timeRangeMinutes, setTimeRangeMinutes] = useState(60);
  const [step, setStep] = useState("15s");
  const [configFile, setConfigFile] = useState(null);
  const [downloadingTemplate, setDownloadingTemplate] = useState(false);
  const fileInputRef = useRef(null);

  async function handleSubmit(e) {
    e.preventDefault();
    const end = Math.floor(Date.now() / 1000);
    const start = end - Number(timeRangeMinutes) * 60;
    const payload = {
      start,
      end,
      step,
    };
    if (configFile) {
      payload.config_yaml = await configFile.text();
    }
    await onCreate(payload);
  }

  async function handleDownloadTemplate() {
    if (!onDownloadTemplate) return;
    setDownloadingTemplate(true);
    try {
      const response = await onDownloadTemplate();
      const defaults =
        response?.defaults && typeof response.defaults === "object"
          ? JSON.parse(JSON.stringify(response.defaults))
          : null;
      if (defaults) {
        const existingQueries = Array.isArray(
          defaults?.constants?.default_metric_queries,
        )
          ? defaults.constants.default_metric_queries
          : [];
        defaults.constants = defaults.constants || {};
        defaults.constants.default_metric_queries = mergeMetricQueries(
          existingQueries,
          RCA_DEFAULT_METRIC_QUERIES_FROM_DASHBOARDS,
        );
      }
      const templateYaml = defaults
        ? YAML.stringify(defaults)
        : String(response?.template_yaml || "");
      if (!templateYaml) return;
      const blob = new Blob([templateYaml], { type: "application/x-yaml" });
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = response?.file_name || "resolver-rca-defaults.yaml";
      anchor.click();
      window.URL.revokeObjectURL(url);
    } finally {
      setDownloadingTemplate(false);
    }
  }

  return (
    <Card>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Select
            label={<span className="text-sm font-medium">Time Window</span>}
            value={timeRangeMinutes}
            onChange={(e) => setTimeRangeMinutes(Number(e.target.value))}
            className="px-3 py-2 text-sm rounded-lg"
          >
            {TIME_RANGES.map((range) => (
              <option key={range.value} value={range.value}>
                {range.label}
              </option>
            ))}
          </Select>
          <Input
            label={<span className="text-sm font-medium">Resolution</span>}
            value={step}
            onChange={(e) => setStep(e.target.value)}
            className="px-3 py-2 text-sm rounded-lg"
          />
        </div>

        <section className="mt-5 space-y-3">
          <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
            <div>
              <h3 className="text-sm font-semibold text-sre-text">RCA YAML Overrides</h3>
              <p className="mt-1 text-xs leading-relaxed text-sre-text-muted">
                Upload a YAML file to override RCA thresholds, weights,
                built-in queries, and analyzer tuning for this job only. When
                no file is provided, Resolver uses the server defaults.
              </p>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="whitespace-nowrap"
              onClick={handleDownloadTemplate}
              loading={downloadingTemplate}
            >
              <span
                className="material-icons mr-1 text-base leading-none"
                aria-hidden="true"
              >
                download
              </span>
              Download Default YAML
            </Button>
          </div>
          <div className="space-y-2">
            <div className="text-sm font-medium text-sre-text">YAML File</div>
            <input
              id="rca-config-yaml-upload"
              ref={fileInputRef}
              type="file"
              accept=".yaml,.yml,text/yaml,application/x-yaml"
              onChange={(e) => setConfigFile(e.target.files?.[0] || null)}
              className="sr-only p-3"
            />
            <div className="rounded-xl border-2 border-dashed border-sre-border bg-sre-surface/30 p-6 text-center transition-colors duration-200 hover:border-sre-primary/70 hover:bg-sre-surface/50">
              <label
                htmlFor="rca-config-yaml-upload"
                className="flex cursor-pointer flex-col items-center justify-center gap-2"
              >
                <span
                  className="material-icons text-3xl text-sre-text-muted"
                  aria-hidden="true"
                >
                  upload_file
                </span>
                <span className="inline-flex items-center rounded-lg border border-sre-border bg-sre-surface px-3 py-1.5 text-sm font-medium text-sre-text">
                  Choose YAML File
                </span>
                <span className="inline-flex min-w-0 items-center gap-1 text-sm text-sre-text-muted">
                  <span
                    className="material-icons text-base leading-none"
                    aria-hidden="true"
                  >
                    {configFile ? "description" : "insert_drive_file"}
                  </span>
                  <span className="max-w-[28rem] truncate">
                    {configFile ? configFile.name : "No file chosen"}
                  </span>
                </span>
              </label>
              {configFile && (
                <div className="mt-3 flex justify-center">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="w-max"
                    onClick={() => {
                      setConfigFile(null);
                      if (fileInputRef.current) fileInputRef.current.value = "";
                    }}
                  >
                    <span
                      className="material-icons mr-1 text-base leading-none"
                      aria-hidden="true"
                    >
                      close
                    </span>
                    Clear
                  </Button>
                </div>
              )}
            </div>
            <p className="text-xs text-sre-text-muted">
              Optional. Upload a file generated from the default template and
              edit only the values you want to change.
            </p>
          </div>
        </section>

        <div className="flex justify-end">
          <Button
            type="submit"
            size="md"
            className="px-4 py-2 text-sm rounded-lg"
            loading={creating}
          >
            Generate Report
          </Button>
        </div>
      </form>
    </Card>
  );
}

RcaJobComposer.propTypes = {
  onCreate: PropTypes.func.isRequired,
  onDownloadTemplate: PropTypes.func,
  creating: PropTypes.bool,
};
