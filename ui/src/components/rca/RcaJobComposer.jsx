import { useMemo, useState } from 'react'
import PropTypes from 'prop-types'
import { Card, Button, Input, Select } from '../ui'
import { TIME_RANGES } from '../../utils/constants'

export default function RcaJobComposer({ onCreate, creating }) {
  const [timeRangeMinutes, setTimeRangeMinutes] = useState(60)
  const [servicesText, setServicesText] = useState('')
  const [logQuery, setLogQuery] = useState('')
  const [metricQueriesText, setMetricQueriesText] = useState('')
  const [sensitivity, setSensitivity] = useState(3)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [step, setStep] = useState('15s')
  const [apdexThresholdMs, setApdexThresholdMs] = useState(500)
  const [sloTarget, setSloTarget] = useState(0.999)
  const [correlationWindowSeconds, setCorrelationWindowSeconds] = useState(60)
  const [forecastHorizonSeconds, setForecastHorizonSeconds] = useState(1800)

  const parsedServices = useMemo(
    () => servicesText.split(',').map((v) => v.trim()).filter(Boolean),
    [servicesText]
  )
  const parsedMetricQueries = useMemo(
    () => metricQueriesText.split('\n').map((v) => v.trim()).filter(Boolean),
    [metricQueriesText]
  )

  function handleSubmit(e) {
    e.preventDefault()
    const end = Math.floor(Date.now() / 1000)
    const start = end - (Number(timeRangeMinutes) * 60)
    onCreate({
      start,
      end,
      step,
      services: parsedServices,
      log_query: logQuery.trim() || null,
      metric_queries: parsedMetricQueries.length > 0 ? parsedMetricQueries : null,
      sensitivity: Number(sensitivity),
      apdex_threshold_ms: Number(apdexThresholdMs),
      slo_target: Number(sloTarget),
      correlation_window_seconds: Number(correlationWindowSeconds),
      forecast_horizon_seconds: Number(forecastHorizonSeconds),
    })
  }

  return (
    <Card className="">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Select
            label={<span className="text-sm font-medium">Time Window</span>}
            value={timeRangeMinutes}
            onChange={(e) => setTimeRangeMinutes(Number(e.target.value))}
            className="px-3 py-2 text-sm rounded-lg"
          >
            {TIME_RANGES.map((range) => (
              <option key={range.value} value={range.value}>{range.label}</option>
            ))}
          </Select>
          <div>
            <Input
              label={<span className="text-sm font-medium">Services</span>}
              placeholder="api, checkout, payment"
              value={servicesText}
              onChange={(e) => setServicesText(e.target.value)}
              className="px-3 py-2 text-sm rounded-lg"
            />
            <p className="text-xs text-sre-text-muted mt-1">e.g. api, checkout, payment</p>
          </div>
          <div>
            <Input
              label={<span className="text-sm font-medium">Sensitivity</span>}
              type="number"
              min="1"
              max="6"
              step="0.1"
              value={sensitivity}
              onChange={(e) => setSensitivity(e.target.value)}
              className="px-3 py-2 text-sm rounded-lg"
            />
            <p className="text-xs text-sre-text-muted mt-1">1 (low) – 6 (high)</p>
          </div>
        </div>

        <div>
          <Input
            label="Log Query (optional)"
            placeholder='{service="api"} |= "error"'
            value={logQuery}
            onChange={(e) => setLogQuery(e.target.value)}
          />
          <p className="text-xs text-sre-text-muted mt-1">{`e.g. {service="api"} |= "error"`}</p>
        </div>

        <div>
          <label className="block text-sm text-sre-text mb-2">
            Metric Queries (optional, one per line)
          </label>
          <textarea
            value={metricQueriesText}
            onChange={(e) => setMetricQueriesText(e.target.value)}
            className="w-full min-h-24 px-3 py-2 bg-sre-surface border border-sre-border rounded-lg text-sre-text focus:outline-none focus:ring-2 focus:ring-sre-primary"
            placeholder="sum(rate(http_requests_total[5m])) by (service)"
          />
          <p className="text-xs text-sre-text-muted mt-1">
            Separate queries with newlines
          </p>
        </div>

        <button
          type="button"
          className="text-xs text-sre-primary hover:underline flex items-center gap-1"
          onClick={() => setShowAdvanced((v) => !v)}
        >
          {showAdvanced ? 'Hide advanced fields' : 'Show advanced fields'}
          <span className="material-icons text-xs">
            {showAdvanced ? 'expand_less' : 'expand_more'}
          </span>
        </button>

        {showAdvanced && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <Input label="Step" value={step} onChange={(e) => setStep(e.target.value)} />
            <Input label="Apdex Threshold (ms)" type="number" value={apdexThresholdMs} onChange={(e) => setApdexThresholdMs(e.target.value)} />
            <Input label="SLO Target" type="number" min="0" max="1" step="0.001" value={sloTarget} onChange={(e) => setSloTarget(e.target.value)} />
            <Input label="Correlation Window (s)" type="number" min="10" max="600" value={correlationWindowSeconds} onChange={(e) => setCorrelationWindowSeconds(e.target.value)} />
            <Input label="Forecast Horizon (s)" type="number" min="60" max="86400" value={forecastHorizonSeconds} onChange={(e) => setForecastHorizonSeconds(e.target.value)} />
          </div>
        )}

        <div className="flex justify-end">
          <Button type="submit" size="md" className="px-4 py-2 text-sm rounded-lg" loading={creating}>Generate Report</Button>
        </div>
      </form>
    </Card>
  )
}

RcaJobComposer.propTypes = {
  onCreate: PropTypes.func.isRequired,
  creating: PropTypes.bool,
}
