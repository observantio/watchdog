import { Badge, Spinner } from "../../components/ui";
import { useEffect, useMemo, useState } from "react";
import PropTypes from "prop-types";
import { FixedSizeList as List } from "react-window";
import {
  formatNsToIso,
  formatRelativeTime,
  parseLogLine,
} from "../../utils/formatters";
import { getLogLevel } from "../../utils/helpers";

const MAX_STREAMS_RENDER = 30;


function hashString(value = "") {
  let hash = 5381;
  for (let i = 0; i < value.length; i += 1) {
    hash = ((hash << 5) + hash) ^ value.charCodeAt(i);
  }
  return Math.abs(hash).toString(36);
}

function normalizeStreamIdentity(stream) {
  if (!stream || typeof stream !== "object") return "";
  const sorted = Object.entries(stream)
    .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
    .map(([key, value]) => `${String(key)}=${String(value)}`);
  return sorted.join("|");
}

function buildLogItemKey(streamKey, value, index) {
  const ts = String(value?.[0] || "");
  const line =
    typeof value?.[1] === "string"
      ? value[1]
      : JSON.stringify(value?.[1] ?? "");
  return `${streamKey}-${ts}-${hashString(line.slice(0, 140))}-${index}`;
}

function normalizeStreamLabelValue(label, value) {
  if (typeof value !== "string") return value;
  if (!value.includes('="')) return value;

  const escapedLabel = String(label).replaceAll(
    /[.*+?^${}()|[\]\\]/g,
    String.raw`\\$&`,
  );
  const matcher = new RegExp(`${escapedLabel}="([^"]+)"`);
  const match = matcher.exec(value);
  if (match?.[1]) return match[1];

  const cutIndex = value.indexOf('",');
  if (cutIndex > 0) return value.slice(0, cutIndex);

  return value;
}

export default function LogResults({
  queryResult,
  loading,
  filterDisplayedLogs,
  searchText,
  viewMode,
  expandedLogs,
  toggleLogExpand,
  copyToClipboard,
  streamsPerPage,
}) {
  const [page, setPage] = useState(1);
  const normalizedSearch = String(searchText || "")
    .trim()
    .toLowerCase();
  const hasActiveFilter = normalizedSearch.length > 0;

  const filteredStreams = useMemo(() => {
    return (queryResult?.data?.result || [])
      .map((stream) => {
        if (hasActiveFilter) {
          const tokens = normalizedSearch.split(/\s+/).filter(Boolean);
          const values = (stream?.values || []).filter((v) => {
            const logText =
              typeof v[1] === "string" ? v[1] : JSON.stringify(v[1]);
            const labelsText = stream.stream
              ? Object.values(stream.stream).join(" ")
              : "";
            const hay = (logText + " " + labelsText).toLowerCase();
            return tokens.every((token) => hay.includes(token));
          });
          return { stream, values };
        }
        const values = filterDisplayedLogs
          ? filterDisplayedLogs(stream)
          : stream?.values || [];
        return { stream, values };
      })
      .filter((entry) => entry.values && entry.values.length > 0);
  }, [queryResult, hasActiveFilter, normalizedSearch, filterDisplayedLogs]);

  const perPage =
    typeof streamsPerPage === "number" && streamsPerPage > 0
      ? streamsPerPage
      : MAX_STREAMS_RENDER;
  const totalStreams = filteredStreams.length;
  const totalPages = Math.max(1, Math.ceil(totalStreams / perPage));

  useEffect(() => {
    setPage(1);
  }, [queryResult, normalizedSearch, perPage]);

  useEffect(() => {
    setPage((current) => Math.min(Math.max(current, 1), totalPages));
  }, [totalPages]);

  if (loading) {
    return (
      <div className="py-12 flex flex-col items-center ">
        <Spinner size="lg" />
        <p className="text-sre-text-muted mt-4">Querying logs...</p>
      </div>
    );
  }

  if (!queryResult?.data?.result || queryResult.data.result.length === 0) {
    return (
      <div className="text-center py-16 px-6 rounded-xl border-2 border-dashed border-sre-border bg-sre-bg-alt">
        <span className="material-icons text-5xl text-sre-text-muted mb-4 block">
          check_circle
        </span>
        <h3 className="text-xl font-semibold text-sre-text mb-2">
          No Logs Found
        </h3>
        <p className="text-sre-text-muted  text-sm mb-6 max-w-md mx-auto">
          Try adjusting your filters or expanding the time range. You must
          select the right key to look at as well
        </p>
      </div>
    );
  }

  if (hasActiveFilter && filteredStreams.length === 0) {
    return (
      <div className="text-center py-16">
        <p className="text-lg text-sre-text-muted mb-2">
          No logs match your filter
        </p>
        <p className="text-sm text-sre-text-subtle">
          Try a different search term
        </p>
      </div>
    );
  }
  const startIndex = Math.min(
    (page - 1) * perPage,
    Math.max(0, totalStreams - 1),
  );
  const endIndex = Math.min(startIndex + perPage, totalStreams);
  const visibleStreams = filteredStreams.slice(startIndex, endIndex);

  return (
    <div className="space-y-4 overflow-auto scrollbar-thin scrollbar-thumb-sre-border scrollbar-track-sre-bg-alt scrollbar-thumb-rounded max-h-[calc(100vh-18rem)] pr-2 md:pr-4">
      <div className="flex items-center justify-between rounded-lg border border-sre-border/60 bg-sre-bg-alt/60 px-3 py-2 text-xs text-sre-text-muted">
        <div className="font-medium">
          Showing {totalStreams === 0 ? 0 : startIndex + 1}–{endIndex} of{" "}
          {totalStreams} streams
        </div>
        {totalStreams > perPage && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              aria-label="Previous"
              className="px-2 py-1 rounded border border-sre-border bg-sre-surface hover:bg-sre-bg-alt disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-sre-text-subtle">
              Page {page} / {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              aria-label="Next"
              className="px-2 py-1 rounded border border-sre-border bg-sre-surface hover:bg-sre-bg-alt disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}
      </div>

      {visibleStreams.map(({ stream, values: filteredValues }, streamIdx) => {
        const rawStreamKey = normalizeStreamIdentity(stream.stream);
        const hashed = rawStreamKey
          ? `${hashString(rawStreamKey)}-${rawStreamKey.length}`
          : `fallback-${streamIdx}`;
        const streamKey = `stream-${hashed}-${startIndex + streamIdx}`;

        return (
          <div
            key={streamKey}
            className="border border-sre-border rounded-lg overflow-hidden bg-sre-surface/65"
          >
            <div className="bg-sre-bg-alt px-4 py-2 border-b border-sre-border">
              <div className="flex items-center justify-between">
                <div className="flex flex-wrap gap-2 pr-3">
                  {stream.stream &&
                    Object.entries(stream.stream).map(([k, v]) => (
                      <span
                        key={k}
                        className="inline-flex items-center gap-1 px-2 py-0.5 bg-sre-surface border border-sre-border/70 rounded text-xs font-mono"
                      >
                        <span className="text-sre-primary font-semibold">
                          {k}
                        </span>
                        <span className="text-sre-text-muted">=</span>
                        <span className="text-sre-text">
                          {normalizeStreamLabelValue(k, v)}
                        </span>
                      </span>
                    ))}
                </div>
                <Badge variant="default" className="text-[10px]">
                  {filteredValues.length} log
                  {filteredValues.length === 1 ? "" : "s"}
                </Badge>
              </div>
            </div>

            <div className="divide-y divide-sre-border">
              {(() => {
                const displayValues = filteredValues
                  .slice()
                  .slice(0, viewMode === "compact" ? 200 : 100)
                  .map((value, index) => ({
                    value,
                    key: buildLogItemKey(streamKey, value, index),
                  }));
                const rowHeight =
                  viewMode === "compact" ? 36 : viewMode === "raw" ? 100 : 120;

                const listHeight = displayValues.length * rowHeight;
                const Row = ({ index, style, data }) => {
                  const row = data[index];
                  const v = row.value;
                  const formatted = parseLogLine(v[1]);
                  const logKey = row.key;
                  const isExpanded = !!expandedLogs[logKey];
                  const badge = getLogLevel(v[1]);

                  let displayText;
                  if (isExpanded) {
                    displayText = formatted.data;
                  } else if (
                    typeof formatted.data === "string" &&
                    formatted.data.length > 300
                  ) {
                    displayText = formatted.data.substring(0, 300) + "...";
                  } else {
                    displayText = formatted.data;
                  }

                  if (viewMode === "compact") {
                    return (
                      <div
                        style={style}
                        className="px-4 py-2 hover:bg-sre-surface/70 transition-colors text-xs font-mono"
                      >
                        <span className="text-sre-text-muted mr-3 tabular-nums">
                          {formatNsToIso(v[0]).substring(11, 19)}
                        </span>
                        <span
                          className={`${badge.bgClass} px-2 py-0.5 rounded text-[10px] font-bold mr-2`}
                        >
                          {badge.text}
                        </span>
                        <span className={getLogLevel(v[1]).color}>
                          {String(v[1]).substring(0, 150)}
                          {String(v[1]).length > 150 ? "..." : ""}
                        </span>
                      </div>
                    );
                  }

                  if (viewMode === "raw") {
                    return (
                      <div
                        style={style}
                        className="px-4 py-2 hover:bg-sre-surface/70 transition-colors"
                      >
                        <pre className="text-xs font-mono text-sre-text whitespace-pre-wrap break-all">
                          {JSON.stringify(
                            { timestamp: v[0], log: v[1] },
                            null,
                            2,
                          )}
                        </pre>
                      </div>
                    );
                  }

                  return (
                    <div
                      style={style}
                      className="px-4 py-3 hover:bg-sre-surface/70 transition-colors"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-3">
                          <span
                            className={`${badge.bgClass} px-2 py-1 rounded text-[10px] font-bold border`}
                          >
                            {badge.text}
                          </span>
                          <div className="text-xs text-sre-text-muted">
                            <div className="font-semibold">
                              {formatNsToIso(v[0])}
                            </div>
                            <div className="text-[10px]">
                              {formatRelativeTime(v[0])}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => copyToClipboard(v[1])}
                            className="p-1 hover:bg-sre-bg-alt rounded text-sre-text-muted hover:text-sre-text"
                            title="Copy log"
                          >
                            <svg
                              className="w-4 h-4"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                              />
                            </svg>
                          </button>
                          {formatted.type === "json" && (
                            <button
                              type="button"
                              onClick={() => toggleLogExpand(logKey)}
                              className="p-1 hover:bg-sre-bg-alt rounded text-sre-text-muted hover:text-sre-text"
                            >
                              <svg
                                className={`w-4 h-4 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth={2}
                                  d="M19 9l-7 7-7-7"
                                />
                              </svg>
                            </button>
                          )}
                        </div>
                      </div>

                      {formatted.type === "json" ? (
                        <div className="mt-2 space-y-1">
                          {Object.entries(formatted.data)
                            .slice(0, isExpanded ? undefined : 5)
                            .map(([key, val]) => (
                              <div key={key} className="flex gap-3 text-sm">
                                <span className="text-sre-primary font-semibold min-w-[120px] font-mono">
                                  {key}:
                                </span>
                                <span
                                  className={`${getLogLevel(String(val)).color} flex-1 font-mono break-all`}
                                >
                                  {typeof val === "object"
                                    ? JSON.stringify(val)
                                    : String(val)}
                                </span>
                              </div>
                            ))}
                          {!isExpanded &&
                            Object.keys(formatted.data).length > 5 && (
                              <button
                                type="button"
                                onClick={() => toggleLogExpand(logKey)}
                                className="text-xs text-sre-primary hover:underline mt-2"
                              >
                                Show {Object.keys(formatted.data).length - 5}{" "}
                                more fields...
                              </button>
                            )}
                        </div>
                      ) : (
                        <div
                          className={`mt-2 text-sm font-mono ${getLogLevel(formatted.data).color} break-all`}
                        >
                          {displayText}
                          {!isExpanded && formatted.data.length > 300 && (
                            <button
                              type="button"
                              onClick={() => toggleLogExpand(logKey)}
                              className="text-xs text-sre-primary hover:underline ml-2"
                            >
                              Show more
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                };

                return (
                  <div>
                    <List
                      height={listHeight}
                      itemCount={displayValues.length}
                      itemSize={rowHeight}
                      itemData={displayValues}
                      itemKey={(index, data) => data[index].key}
                      width="100%"
                    >
                      {Row}
                    </List>
                  </div>
                );
              })()}
            </div>
          </div>
        );
      })}
    </div>
  );
}

LogResults.propTypes = {
  queryResult: PropTypes.object,
  loading: PropTypes.bool,
  filterDisplayedLogs: PropTypes.func,
  searchText: PropTypes.string,
  viewMode: PropTypes.string,
  expandedLogs: PropTypes.object,
  toggleLogExpand: PropTypes.func.isRequired,
  copyToClipboard: PropTypes.func.isRequired,
  streamsPerPage: PropTypes.number,
};
