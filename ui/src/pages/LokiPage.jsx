import { useState, useEffect, useCallback, useMemo } from "react";
import { useAutoRefresh } from "../hooks";
import PageHeader from "../components/ui/PageHeader";
import AutoRefreshControl from "../components/ui/AutoRefreshControl";
import { queryLogs, getLabels, getLabelValues, getLogVolume } from "../api";
import { Card, Button, Alert } from "../components/ui";
import { DEFAULT_QUERY_LIMITS, MAX_LOG_OPTIONS } from "../utils/constants";
import LogQueryForm from "../components/loki/LogQueryForm";
import LogResults from "../components/loki/LogResults";
import LogVolume from "../components/loki/LogVolume";
import LogQuickFilters from "../components/loki/LogQuickFilters";
import LogLabels from "../components/loki/LogLabels";
import { formatNsToIso } from "../utils/formatters";
import { LOKI_REFRESH_INTERVALS } from "../utils/constants";
import { useToast } from "../contexts/ToastContext";
import HelpTooltip from "../components/HelpTooltip";
import {
  normalizeLabelValues,
  computeTopTermsFromResult,
  getVolumeValues,
  buildFallbackVolume,
  buildSelectorFromFilters,
  escapeLogQLValue,
} from "../utils/lokiQueryUtils";

const LABEL_PREFETCH_LIMIT = 12;
const LABEL_PREFETCH_BATCH = 4;

export default function LokiPage() {
  const STORAGE_KEY = "lokiPageState";
  const loadSaved = () => {
    try {
      if (typeof localStorage === "undefined") return {};
      const s = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      return s && typeof s === "object" && !Array.isArray(s) ? s : {};
    } catch {
      return {};
    }
  };
  const saved = useMemo(() => loadSaved(), []);
  const savedSelectedFilters = useMemo(
    () => saved.selectedFilters || [],
    [saved.selectedFilters],
  );
  const savedSelectedLabel = saved.selectedLabel || "";

  const [labels, setLabels] = useState([]);
  const [labelValuesCache, setLabelValuesCache] = useState({});
  const [loadingValues, setLoadingValues] = useState({});
  const [selectedFilters, setSelectedFilters] = useState(savedSelectedFilters);
  const [selectedLabel, setSelectedLabel] = useState(savedSelectedLabel);
  const [selectedValue, setSelectedValue] = useState(saved.selectedValue || "");
  const [pattern, setPattern] = useState(saved.pattern || "");
  const [rangeMinutes, setRangeMinutes] = useState(saved.rangeMinutes || 60);
  const [searchLimit, setSearchLimit] = useState(
    saved.searchLimit || DEFAULT_QUERY_LIMITS.logs || 100,
  );
  const [pageSize, setPageSize] = useState(
    saved.pageSize || Math.min(...MAX_LOG_OPTIONS) || 20,
  );
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(30);
  const [viewMode, setViewMode] = useState(saved.viewMode || "table");
  const [expandedLogs, setExpandedLogs] = useState(saved.expandedLogs || {});
  const [searchText, setSearchText] = useState(saved.searchText || "");
  const [queryMode, setQueryMode] = useState(saved.queryMode || "builder");
  const [customLogQL, setCustomLogQL] = useState(saved.customLogQL || "");

  const [queryResult, setQueryResult] = useState(null);
  const [volume, setVolume] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [topTerms, setTopTerms] = useState([]);

  const logStats = useMemo(() => {
    const res = queryResult?.data?.result || [];
    if (!queryResult || res.length === 0) {
      return null;
    }

    const totalStreams = res.length;
    const totalLogs = res.reduce((acc, s) => acc + (s.values?.length || 0), 0);
    const avgLogs = totalStreams ? Math.round(totalLogs / totalStreams) : 0;
    const servicesSet = new Set(
      res
        .flatMap((s) => {
          if (s.stream) {
            return [
              s.stream.service_name,
              s.stream.service,
              ...(Object.values(s.stream) || []),
            ];
          }
          return [];
        })
        .filter((v) => typeof v === "string" && v),
    );
    const serviceList = Array.from(servicesSet);
    const serviceCount = serviceList.length;
    const termNames = topTerms ? topTerms.map((t) => t.term || String(t)) : [];
    const termCount = termNames.length;
    return {
      totalStreams,
      totalLogs,
      avgLogs,
      serviceCount,
      serviceList,
      termCount,
      termNames,
    };
  }, [queryResult, topTerms]);

  const toast = useToast();
  useAutoRefresh(() => executeQuery(), refreshInterval * 1000, autoRefresh);
  // Run once on mount to restore a saved query snapshot, without retriggering on later state updates.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    try {
      const toSave = {
        selectedFilters,
        rangeMinutes,
        searchLimit,
        pageSize,
        viewMode,
        expandedLogs,
        searchText,
        queryMode,
        ...(selectedLabel ? { selectedLabel } : {}),
        ...(selectedValue ? { selectedValue } : {}),
        ...(pattern ? { pattern } : {}),
        ...(customLogQL ? { customLogQL } : {}),
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave));
    } catch {
      // ignore
    }
  }, [
    selectedFilters,
    selectedLabel,
    selectedValue,
    pattern,
    rangeMinutes,
    searchLimit,
    pageSize,
    viewMode,
    expandedLogs,
    searchText,
    queryMode,
    customLogQL,
  ]);

  useEffect(() => {
    if (
      saved.selectedFilters?.length ||
      saved.pattern ||
      saved.customLogQL ||
      saved.selectedLabel ||
      saved.selectedValue
    ) {
      executeQuery();
    }
  }, []);

  const loadInitialData = useCallback(async () => {
    try {
      const lbls = await getLabels();
      const labelsArray = (lbls?.data || []).filter(
        (label) => typeof label === "string" && label.trim() !== "",
      );
      setLabels(labelsArray);

      if (labelsArray?.length > 0) {
        const prefetchLabels = labelsArray.slice(0, LABEL_PREFETCH_LIMIT);
        for (
          let idx = 0;
          idx < prefetchLabels.length;
          idx += LABEL_PREFETCH_BATCH
        ) {
          const batch = prefetchLabels.slice(idx, idx + LABEL_PREFETCH_BATCH);
          const settled = await Promise.allSettled(
            batch.map(async (label) => {
              const vals = await getLabelValues(label);
              return [label, normalizeLabelValues(label, vals?.data || [])];
            }),
          );
          setLabelValuesCache((prev) => {
            const next = { ...prev };
            settled.forEach((result) => {
              if (
                result.status === "fulfilled" &&
                Array.isArray(result.value)
              ) {
                const [label, values] = result.value;
                next[label] = values;
              }
            });
            return next;
          });
        }
      }
      if (
        savedSelectedLabel &&
        labelsArray &&
        !labelsArray.includes(savedSelectedLabel)
      ) {
        setSelectedLabel("");
        setSelectedValue("");
        try {
          const s = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
          let changed = false;
          if (
            s.selectedLabel === savedSelectedLabel ||
            Object.prototype.hasOwnProperty.call(s, "selectedLabel")
          ) {
            delete s.selectedLabel;
            changed = true;
          }
          if (Object.prototype.hasOwnProperty.call(s, "selectedValue")) {
            delete s.selectedValue;
            changed = true;
          }
          if (changed) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
          }
        } catch {
          // ignore malformed storage
        }
      }

      if (Array.isArray(savedSelectedFilters) && savedSelectedFilters.length) {
        const validFilters = savedSelectedFilters.filter((filter) =>
          labelsArray.includes(filter.label),
        );
        if (validFilters.length !== savedSelectedFilters.length) {
          setSelectedFilters(validFilters);
          try {
            const s = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
            s.selectedFilters = validFilters;
            localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
          } catch {
            // ignore malformed storage
          }
        }
      }
    } catch {
      setLabels([]);
    }
  }, [savedSelectedFilters, savedSelectedLabel]);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  async function loadLabelValues(label) {
    if (!label || labelValuesCache[label]) return;

    setLoadingValues((prev) => ({ ...prev, [label]: true }));
    try {
      const end = Date.now() * 1e6;
      const start = (Date.now() - rangeMinutes * 60 * 1000) * 1e6;
      const vals = await getLabelValues(label, {
        start: Math.round(start),
        end: Math.round(end),
      });
      const normalizedValues = normalizeLabelValues(label, vals?.data || []);
      setLabelValuesCache((prev) => ({ ...prev, [label]: normalizedValues }));
    } catch {
      // Silently handle - label will remain un-cached
    } finally {
      setLoadingValues((prev) => ({ ...prev, [label]: false }));
    }
  }

  function addFilter() {
    if (!selectedLabel || !selectedValue) return;
    setSelectedFilters((prev) => {
      const exists = prev.find(
        (p) => p.label === selectedLabel && p.value === selectedValue,
      );
      if (exists) return prev;
      return [...prev, { label: selectedLabel, value: selectedValue }];
    });
    setSelectedLabel("");
    setSelectedValue("");
  }

  function removeFilter(i) {
    setSelectedFilters((prev) => prev.filter((_, idx) => idx !== i));
  }

  function clearAllFilters() {
    setSelectedFilters([]);
    setPattern("");
  }

  function getEffectiveFilters(overrideFilters) {
    if (overrideFilters) return overrideFilters;
    if (selectedFilters.length) return selectedFilters;
    if (selectedLabel && selectedValue)
      return [{ label: selectedLabel, value: selectedValue }];
    return [];
  }

  function toggleLogExpand(logKey) {
    setExpandedLogs((prev) => ({ ...prev, [logKey]: !prev[logKey] }));
  }

  function downloadLogs() {
    if (!queryResult?.data?.result) return;
    const logs = [];
    queryResult.data.result.forEach((stream) => {
      stream.values.forEach((v) => {
        logs.push({
          timestamp: formatNsToIso(v[0]),
          stream: stream.stream,
          log: v[1],
        });
      });
    });
    const blob = new Blob([JSON.stringify(logs, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `loki-logs-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function filterDisplayedLogs(stream) {
    if (!stream?.values) return [];
    if (!searchText) return stream.values;
    const tokens = String(searchText)
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    return stream.values.filter((v) => {
      const logText = typeof v[1] === "string" ? v[1] : JSON.stringify(v[1]);
      const labelsText = stream.stream
        ? Object.values(stream.stream).join(" ")
        : "";
      const hay = (logText + " " + labelsText).toLowerCase();
      return tokens.every((t) => hay.includes(t));
    });
  }

  async function fetchAndSetVolume(
    volumeQuery,
    startNs,
    endNs,
    totalLogs,
    res,
  ) {
    try {
      const volRes = await getLogVolume(volumeQuery, {
        start: Math.round(startNs),
        end: Math.round(endNs),
        step: Math.max(60, Math.floor((rangeMinutes * 60) / 60)),
      });
      const vals = getVolumeValues(volRes);
      if (vals.some((v) => v > 0)) {
        setVolume(vals);
        return;
      }
    } catch {
      // Fall back to computed volume
    }
    setVolume(buildFallbackVolume(res, totalLogs));
  }

  async function executeQuery(overrideFilters, overridePattern) {
    setError(null);
    setLoading(true);

    const effectivePattern =
      overridePattern !== undefined ? overridePattern : pattern;
    const fallbackLabel = labels[0] || "service_name";

    try {
      const normalizedLimit = Math.max(1, Number(searchLimit) || 1);
      let q;
      let selectorForVolume;

      if (queryMode === "custom" && overrideFilters === undefined) {
        q = customLogQL.trim();
        if (!q) {
          setError("Please enter a LogQL query");
          setLoading(false);
          return;
        }
        selectorForVolume = q;
      } else {
        const filters = getEffectiveFilters(overrideFilters);
        const selector = buildSelectorFromFilters(filters, fallbackLabel);
        selectorForVolume = selector;
        q = selector;
        if (effectivePattern) {
          const escaped = escapeLogQLValue(effectivePattern);
          q += ` |= "${escaped}"`;
          selectorForVolume = `${selector} |= "${escaped}"`;
        }
      }

      const start = Date.now() - rangeMinutes * 60 * 1000;
      const startNs = start * 1e6;
      const endNs = Date.now() * 1e6;

      const res = await queryLogs({
        query: q,
        start: Math.round(startNs),
        end: Math.round(endNs),
        limit: normalizedLimit,
      });
      const safeResult = res || { data: { result: [] } };
      setQueryResult(safeResult);

      try {
        setTopTerms(computeTopTermsFromResult(safeResult, 12));
      } catch {
        setTopTerms([]);
      }

      const totalLogs =
        safeResult?.data?.result?.reduce(
          (acc, stream) => acc + (stream.values?.length || 0),
          0,
        ) || 0;
      await fetchAndSetVolume(
        selectorForVolume,
        startNs,
        endNs,
        totalLogs,
        safeResult,
      );
    } catch (e) {
      setError(e.message || "Failed to query logs");
    } finally {
      setLoading(false);
    }
  }

  function runQuery(e) {
    e?.preventDefault?.();
    executeQuery();
  }

  function handleSelectLabelValue(label, value) {
    const filters = [{ label, value }];
    setSelectedFilters(filters);
    setPattern("");
    setQueryMode("builder");
    executeQuery(filters, "");
  }

  function handleSelectPattern(term) {
    setSelectedFilters([]);
    setPattern(term);
    setQueryMode("builder");
    executeQuery([], term);
  }
  const copyToClipboard = async (text) => {
    const ok = await (
      await import("../utils/helpers")
    ).copyToClipboard(typeof text === "string" ? text : JSON.stringify(text));
    if (ok) toast.success("Copied to clipboard");
    else toast.error("Failed to copy to clipboard");
  };

  return (
    <div className="animate-fade-in">
      <PageHeader
        icon="view_stream"
        title="Logs"
        subtitle="Query and analyze logs using LogQL"
      >
        <AutoRefreshControl
          enabled={autoRefresh}
          onToggle={setAutoRefresh}
          interval={refreshInterval}
          onIntervalChange={setRefreshInterval}
          intervalOptions={LOKI_REFRESH_INTERVALS}
        />
      </PageHeader>

      {/* Stats bar similar to Tempo */}
      {logStats && logStats.totalStreams !== undefined && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
          {[
            {
              label: "Streams",
              value: logStats.totalStreams,
              color: "text-sre-text",
              detail: "",
            },
            {
              label: "Total Logs",
              value: logStats.totalLogs.toLocaleString(),
              color: "text-sre-text",
              detail: "",
            },
            {
              label: "Avg/stream",
              value: logStats.avgLogs.toLocaleString(),
              color: "text-sre-text",
              detail: "logs per stream",
            },
            {
              label: "Services",
              value: logStats.serviceCount,
              color: "text-sre-text",
              detail: (logStats.serviceList || []).join(", "),
            },
            {
              label: "Top Terms",
              value: logStats.termCount,
              color: "text-sre-text",
              detail: (logStats.termNames || []).join(", "),
            },
          ].map((stat) => (
            <Card
              key={stat.label}
              className="p-4 relative overflow-visible bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm"
            >
              <div className="text-sre-text-muted text-xs mb-1">
                {stat.label}
              </div>
              <div className={`text-2xl font-bold ${stat.color}`}>
                {stat.value}
              </div>
              {stat.detail && (
                <div className="text-xs text-sre-text-muted mt-1 truncate">
                  {stat.detail}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      {error && (
        <Alert variant="error" className="mb-6" onClose={() => setError(null)}>
          <strong>Error:</strong> {error}
        </Alert>
      )}

      <Card title="Search & Filter" className="mb-6">
        <LogQueryForm
          queryMode={queryMode}
          customLogQL={customLogQL}
          setCustomLogQL={setCustomLogQL}
          labels={labels}
          selectedLabel={selectedLabel}
          setSelectedLabel={setSelectedLabel}
          labelValuesCache={labelValuesCache}
          loadingValues={loadingValues}
          selectedValue={selectedValue}
          setSelectedValue={setSelectedValue}
          pattern={pattern}
          setPattern={setPattern}
          rangeMinutes={rangeMinutes}
          setRangeMinutes={setRangeMinutes}
          searchLimit={searchLimit}
          setSearchLimit={setSearchLimit}
          pageSize={pageSize}
          setPageSize={setPageSize}
          addFilter={addFilter}
          selectedFilters={selectedFilters}
          clearAllFilters={clearAllFilters}
          runQuery={runQuery}
          onQueryModeChange={(e) => setQueryMode(e.target.value)}
          onLabelChange={loadLabelValues}
          loading={loading}
          onRemoveFilter={removeFilter}
        />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-3">
          <Card
            title="Log Results"
            subtitle={
              queryResult?.data?.result?.length
                ? "Showing results"
                : "Run a query"
            }
          >
            <div className="mb-4 flex items-center justify-between pb-4 border-b border-sre-border">
              <div className="flex items-center gap-4">
                <div className="flex gap-1 bg-sre-bg-alt rounded-lg p-1">
                  {["table", "compact", "raw"].map((mode) => (
                    <button
                      key={mode}
                      onClick={() => setViewMode(mode)}
                      className={`px-3 py-1 rounded text-xs font-medium transition-colors ${viewMode === mode ? "bg-sre-primary text-white" : "text-sre-text-muted hover:text-sre-text"}`}
                    >
                      {mode.charAt(0).toUpperCase() + mode.slice(1)}
                    </button>
                  ))}
                </div>

                <input
                  type="text"
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  placeholder="Filter displayed logs..."
                  className="px-3 py-1 bg-sre-surface border border-sre-border rounded text-sm text-sre-text w-full md:w-72 max-w-md"
                />
                <HelpTooltip text="Filter the displayed log results by searching within the log content. Supports multiple keywords separated by spaces." />
              </div>

              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={downloadLogs}
                  disabled={!queryResult?.data?.result?.length}
                >
                  <span className="material-icons text-sm mr-1">download</span>{" "}
                  Export
                </Button>
              </div>
            </div>

            <LogResults
              key={`log-results-${viewMode}`}
              queryResult={queryResult}
              loading={loading}
              filterDisplayedLogs={filterDisplayedLogs}
              searchText={searchText}
              viewMode={viewMode}
              expandedLogs={expandedLogs}
              toggleLogExpand={toggleLogExpand}
              copyToClipboard={copyToClipboard}
              streamsPerPage={pageSize}
            />
          </Card>
        </div>

        <div className="space-y-6">
          <LogVolume volume={volume} />
          <LogQuickFilters
            labelValuesCache={labelValuesCache}
            topTerms={topTerms}
            onSelectLabelValue={handleSelectLabelValue}
            onSelectPattern={handleSelectPattern}
          />
          <LogLabels labels={labels} labelValuesCache={labelValuesCache} />
        </div>
      </div>
    </div>
  );
}
