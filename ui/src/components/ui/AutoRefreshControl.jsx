import HelpTooltip from "../HelpTooltip";
import { REFRESH_INTERVALS } from "../../utils/constants";

export default function AutoRefreshControl({
  enabled,
  onToggle,
  interval,
  onIntervalChange,
  label = "Auto-refresh",
  tooltip = "Automatically refresh the query results at the selected interval. Useful for monitoring live data.",
  intervalOptions = REFRESH_INTERVALS,
}) {
  return (
    <div className="flex items-center gap-3">
      <label className="flex items-center gap-2 text-sm text-sre-text">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          className="rounded border-sre-border bg-sre-surface"
        />
        <span>{label}</span>
        <HelpTooltip text={tooltip} />
      </label>

      {enabled && (
        <div className="flex items-center gap-2">
          <select
            value={interval}
            onChange={(e) => onIntervalChange(Number(e.target.value))}
            className="px-2 pr-10 py-1 bg-sre-surface border border-sre-border rounded text-sm"
          >
            {intervalOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <HelpTooltip text="How often to automatically refresh. Shorter intervals provide more real-time data but increase server load." />
        </div>
      )}
    </div>
  );
}
