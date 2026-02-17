import PropTypes from 'prop-types'
import { Button } from '../../components/ui'
import HelpTooltip from '../HelpTooltip'
import { LOKI_TIME_RANGES, MAX_LOG_OPTIONS } from '../../utils/constants'

export default function LogQueryForm({
  queryMode,
  customLogQL,
  setCustomLogQL,
  labels,
  selectedLabel,
  setSelectedLabel,
  labelValuesCache,
  loadingValues,
  selectedValue,
  setSelectedValue,
  pattern,
  setPattern,
  rangeMinutes,
  setRangeMinutes,
  maxLogs,
  setMaxLogs,
  addFilter,
  selectedFilters,
  clearAllFilters,
  runQuery,
  onQueryModeChange,
  onLabelChange = undefined,
  loading = false,
  onRemoveFilter = undefined,
}) {
  return (
    <form onSubmit={runQuery} className="space-y-4">
      <div className="flex items-center gap-4 pb-3 border-b border-sre-border">
        <span className="text-sm text-sre-text-muted flex items-center">
          <span className="material-icons text-sm">build</span>
          <span className="ml-1">Mode:</span>
        </span>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="radio" value="builder" checked={queryMode === 'builder'} onChange={onQueryModeChange} className="text-sre-primary focus:ring-sre-primary" />
          <span className="text-sm text-sre-text">Filter Builder</span>
        </label>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="radio" value="custom" checked={queryMode === 'custom'} onChange={onQueryModeChange} className="text-sre-primary focus:ring-sre-primary" />
          <span className="text-sm text-sre-text">Custom LogQL</span>
        </label>
      </div>

      {queryMode === 'custom' ? (
        <div>
          <label className="block text-sm font-medium text-sre-text mb-2">
            <span>LogQL Query</span>
            <HelpTooltip text="Enter a complete LogQL query for advanced log filtering and aggregation. Examples: {app='myapp'} |= 'error', count_over_time({app='myapp'} [5m])" />
            <textarea value={customLogQL} onChange={(e)=>setCustomLogQL(e.target.value)} rows={4} className="mt-2 w-full px-3 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text font-mono text-sm focus:border-sre-primary focus:ring-1 focus:ring-sre-primary resize-none" />
          </label>
          <p className="text-xs text-sre-text-muted mt-1">Enter a LogQL query directly.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                <span>Label</span>
                <HelpTooltip text="Choose a label to filter logs. Labels are key-value pairs attached to log entries for categorization." />
                <select value={selectedLabel} onChange={(e)=>{setSelectedLabel(e.target.value); setSelectedValue(''); onLabelChange?.(e.target.value)}} className="mt-2 w-full px-3 pr-10 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text focus:border-sre-primary focus:ring-1 focus:ring-sre-primary">
                  <option value="">-- Select label --</option>
                  {labels?.map(l=> <option key={l} value={l}>{l}</option>)}
                </select>
              </label>
            </div>

            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                <span>Value</span>
                <HelpTooltip text="Select a specific value for the chosen label, or 'Any value' to match all values for that label." />
                <select value={selectedValue} onChange={(e)=>setSelectedValue(e.target.value)} disabled={!selectedLabel} className="mt-2 w-full px-3 pr-10 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text focus:border-sre-primary focus:ring-1 focus:ring-sre-primary">
                  <option value="">{loadingValues?.[selectedLabel] ? 'Loading...' : '-- Select value --'}</option>
                  {selectedLabel && !loadingValues?.[selectedLabel] && (
                    <option value="__any__">Any value</option>
                  )}
                  {(labelValuesCache?.[selectedLabel] ?? []).map(v=> <option key={v} value={v}>{v}</option>)}
                </select>
              </label>
            </div>

            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                <span>Text Filter</span>
                <HelpTooltip text="Filter logs containing specific text patterns. Use quotes for exact matches, e.g., 'timeout' or 'error 500'." />
                <input value={pattern} onChange={(e)=>setPattern(e.target.value)} placeholder='e.g., "timeout"' className="mt-2 w-full px-3 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text focus:border-sre-primary focus:ring-1 focus:ring-sre-primary" />
              </label>
            </div>

            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                <span>Time Range</span>
                <HelpTooltip text="Select how far back to search for logs. Larger ranges may take longer to query and return more results." />
                <select value={rangeMinutes} onChange={(e)=>setRangeMinutes(Number(e.target.value))} className="mt-2 w-full px-3 pr-10 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text focus:border-sre-primary focus:ring-1 focus:ring-sre-primary">
                  {LOKI_TIME_RANGES.map(tr => <option key={tr.value} value={tr.value}>{tr.label}</option>)}
                </select>
              </label>
            </div>

            <div>
              <label className="block text-sm font-medium text-sre-text mb-2">
                <span>Max Logs</span>
                <HelpTooltip text="Limit the number of log entries returned. Higher limits provide more data but may slow down queries." />
                <select value={maxLogs} onChange={(e)=>setMaxLogs(Number(e.target.value))} className="mt-2 w-full px-3 pr-10 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text focus:border-sre-primary focus:ring-1 focus:ring-sre-primary">
                  {MAX_LOG_OPTIONS.map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
            </div>
          </div>
        </>
      )}

      <div className="flex items-center gap-2">
        {queryMode === 'builder' && (
          <>
            <Button type="button" size="sm" onClick={addFilter} disabled={!selectedLabel || !selectedValue}>Add Filter</Button>
            {selectedFilters?.length > 0 && <Button type="button" size="sm" variant="ghost" onClick={clearAllFilters}>Clear All</Button>}
          </>
        )}
        <div className="flex-1" />
        <Button type="submit" size="sm" loading={!!loading}>Run Query</Button>
      </div>

      {selectedFilters?.length > 0 && (
        <div className="mt-2 flex gap-2 flex-wrap">
          {selectedFilters.map((f, i) => (
            <div key={`${f.label}-${f.value}-${i}`} className="inline-flex items-center gap-2 px-3 py-1.5 bg-sre-primary/10 border border-sre-primary/30 rounded-full">
              <span className="text-xs font-mono text-sre-primary font-semibold">{f.label}</span>
              <span className="text-xs font-mono text-sre-text">=</span>
              <span className="text-sm font-semibold text-sre-text">{f.value}</span>
              <button onClick={() => onRemoveFilter?.(i)} className="text-sre-text-muted hover:text-sre-text ml-1" type="button">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
    </form>
  )
}

LogQueryForm.propTypes = {
  queryMode: PropTypes.string.isRequired,
  customLogQL: PropTypes.string.isRequired,
  setCustomLogQL: PropTypes.func.isRequired,
  labels: PropTypes.arrayOf(PropTypes.string).isRequired,
  selectedLabel: PropTypes.string.isRequired,
  setSelectedLabel: PropTypes.func.isRequired,
  labelValuesCache: PropTypes.object.isRequired,
  loadingValues: PropTypes.object.isRequired,
  selectedValue: PropTypes.string.isRequired,
  setSelectedValue: PropTypes.func.isRequired,
  pattern: PropTypes.string.isRequired,
  setPattern: PropTypes.func.isRequired,
  rangeMinutes: PropTypes.number.isRequired,
  setRangeMinutes: PropTypes.func.isRequired,
  maxLogs: PropTypes.number.isRequired,
  setMaxLogs: PropTypes.func.isRequired,
  addFilter: PropTypes.func.isRequired,
  selectedFilters: PropTypes.arrayOf(PropTypes.shape({
    label: PropTypes.string.isRequired,
    value: PropTypes.string.isRequired,
  })).isRequired,
  clearAllFilters: PropTypes.func.isRequired,
  runQuery: PropTypes.func.isRequired,
  onQueryModeChange: PropTypes.func.isRequired,
  onLabelChange: PropTypes.func,
  loading: PropTypes.bool,
  onRemoveFilter: PropTypes.func,
}
