import { useState } from "react";
import PropTypes from "prop-types";
import { Card, Button, Input, Select } from "../ui";
import { TIME_RANGES } from "../../utils/constants";

export default function RcaJobComposer({ onCreate, onDownloadTemplate, creating }) {
  const [timeRangeMinutes, setTimeRangeMinutes] = useState(60);
  const [step, setStep] = useState("15s");
  const [configFile, setConfigFile] = useState(null);
  const [downloadingTemplate, setDownloadingTemplate] = useState(false);

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
      const templateYaml = String(response?.template_yaml || "");
      if (!templateYaml) return;
      const blob = new Blob([templateYaml], { type: "application/x-yaml" });
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = response?.file_name || "becertain-rca-defaults.yaml";
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

        <div className="rounded-lg border border-dashed border-sre-border bg-sre-surface/30 p-4 space-y-3">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-sm font-medium text-sre-text">
                RCA YAML Overrides
              </div>
              <p className="text-xs text-sre-text-muted mt-1">
                Upload a YAML file to override RCA thresholds, weights, built-in queries, and analyzer tuning for this job only.
                When no file is provided, BeCertain uses the server defaults.
              </p>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={handleDownloadTemplate}
              loading={downloadingTemplate}
            >
              Download Default YAML
            </Button>
          </div>
          <div>
            <Input
              label={<span className="text-sm font-medium">YAML File</span>}
              type="file"
              accept=".yaml,.yml,text/yaml,application/x-yaml"
              onChange={(e) => setConfigFile(e.target.files?.[0] || null)}
              className="px-3 py-2 text-sm rounded-lg"
            />
            <p className="text-xs text-sre-text-muted mt-1">
              {configFile ? `Selected: ${configFile.name}` : "Optional. Upload a file generated from the default template and edit only the values you want to change."}
            </p>
          </div>
        </div>

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
