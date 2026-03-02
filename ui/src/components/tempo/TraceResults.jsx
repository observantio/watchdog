import PropTypes from "prop-types";
import { Badge, Spinner } from "../ui";
import { formatDuration } from "../../utils/formatters";
import { getServiceName, hasSpanError } from "../../utils/helpers";

function TraceCard({
  trace,
  handleTraceClick,
  selectedIds,
  onToggleSelect,
  onShowOnMap,
}) {
  const t = trace;
  const rootSpan =
    t.spans?.find((s) => !s.parentSpanId && !s.parentSpanID) || t.spans?.[0];
  const duration = rootSpan?.duration || 0;
  const traceHasError = t.spans?.some(hasSpanError);
  // determine if this is a summary-only trace, which means we only have the root span
  const isSummary =
    Array.isArray(t.warnings) &&
    t.warnings.some((w) => w.toLowerCase().includes("summary"));
  // gather service names, ignore blanks and generic "unknown" labels
  const allServices =
    t.spans
      ?.map((s) => getServiceName(s))
      .filter((n) => n && n.toLowerCase() !== "unknown") || [];
  const serviceCount = new Set(allServices).size;
  const rootServiceName = rootSpan ? getServiceName(rootSpan) : "unknown";
  const traceId = t.traceID || t.traceId;
  const isSelected = selectedIds && selectedIds.has && selectedIds.has(traceId);

  return (
    <div className="p-5 bg-sre-surface/60 border border-sre-border rounded-xl group hover:shadow-lg transition-shadow flex flex-col justify-between min-h-[150px]">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-4 flex-1">
          <input
            type="checkbox"
            checked={!!isSelected}
            onChange={(e) =>
              onToggleSelect && onToggleSelect(traceId, e.target.checked)
            }
            className="mt-1"
            aria-label={`Select trace ${traceId}`}
          />
          <button
            onClick={() => handleTraceClick(traceId)}
            type="button"
            className="text-left flex-1"
          >
            <div>
              <div className="flex items-center gap-3 mb-2">
                <span
                  className={`material-icons ${traceHasError ? "text-red-500" : "text-green-500"} group-hover:scale-110 transition-transform`}
                >
                  {traceHasError ? "error" : "check_circle"}
                </span>
                <span className="font-mono text-sm text-sre-text font-semibold">
                  {traceId?.substring(0, 16)}...
                </span>
                <Badge variant={traceHasError ? "error" : "success"}>
                  {traceHasError ? "ERROR" : "OK"}
                </Badge>
                <Badge variant="info">
                  {t.spans?.length || 0}
                  {isSummary ? "+" : ""} spans
                </Badge>
                <Badge variant="default">
                  {serviceCount}
                  {isSummary ? "+" : ""} service{serviceCount !== 1 ? "s" : ""}
                </Badge>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm text-sre-text-muted leading-relaxed">
                <div>
                  <div className="text-xs">Service</div>
                  <div className="font-semibold text-sre-text truncate max-w-xs">
                    {rootServiceName}
                  </div>
                </div>
                {rootSpan?.operationName && (
                  <div>
                    <div className="text-xs">Operation</div>
                    <div className="font-semibold text-sre-text truncate max-w-xs">
                      {rootSpan.operationName}
                    </div>
                  </div>
                )}
                <div>
                  <div className="text-xs">Duration</div>
                  <div className="font-mono font-semibold text-sre-text">
                    {formatDuration(duration)}
                  </div>
                </div>
                <div>
                  <div className="text-xs">Started</div>
                  <div className="font-semibold text-sre-text">
                    {new Date(rootSpan?.startTime / 1000).toLocaleTimeString()}
                  </div>
                </div>
              </div>
            </div>
          </button>
        </div>
        <button
          type="button"
          title="Show dependency map"
          onClick={(e) => {
            e.stopPropagation();
            onToggleSelect && onToggleSelect(traceId, true);
            onShowOnMap && onShowOnMap(traceId);
          }}
          className="text-sre-text-muted group-hover:text-sre-primary transition-colors"
          aria-label={`Show dependency map for ${traceId}`}
        >
          <span className="material-icons">hub</span>
        </button>
      </div>
    </div>
  );
}

TraceCard.propTypes = {
  trace: PropTypes.object.isRequired,
  handleTraceClick: PropTypes.func.isRequired,
  selectedIds: PropTypes.object,
  onToggleSelect: PropTypes.func,
  onShowOnMap: PropTypes.func,
};

export default function TraceResults({
  traces,
  loading,
  handleTraceClick,
  selectedIds = new Set(),
  onToggleSelect = null,
  onShowOnMap = null,
}) {
  if (loading) {
    return (
      <div className="py-12 flex flex-col items-center">
        <Spinner size="lg" />
        <p className="text-sre-text-muted mt-4">Searching traces...</p>
      </div>
    );
  }

  if (!traces || traces.length === 0) {
    return (
      <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
        <span className="material-icons text-5xl text-sre-text-muted mb-4 block">
          timeline
        </span>
        <h3 className="text-xl font-semibold text-sre-text mb-2">
          No Traces Found
        </h3>
        <p className="text-sre-text-muted text-sm mb-6 max-w-md mx-auto">
          Try adjusting your search criteria, expanding the time range, or
          pasting a trace ID above.
        </p>
      </div>
    );
  }

  // Responsive grid for trace cards — two cards per row on medium+ screens for better spacing
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {traces.map((t) => (
        <TraceCard
          key={t.traceID || t.traceId || t.id}
          trace={t}
          handleTraceClick={handleTraceClick}
          selectedIds={selectedIds}
          onToggleSelect={onToggleSelect}
          onShowOnMap={onShowOnMap}
        />
      ))}
    </div>
  );
}

TraceResults.propTypes = {
  traces: PropTypes.arrayOf(PropTypes.object).isRequired,
  loading: PropTypes.bool,
  handleTraceClick: PropTypes.func.isRequired,
  selectedIds: PropTypes.object,
  onToggleSelect: PropTypes.func,
  onShowOnMap: PropTypes.func,
};
