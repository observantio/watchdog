`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useState, useEffect, useMemo } from 'react'
import {
  getAlerts, getSilences, getAlertRules, getNotificationChannels,
} from '../api'
import { normalizeRuleForUI } from '../utils/alertmanagerRuleUtils'

export const useAlertManagerData = () => {
  const [alerts, setAlerts] = useState([])
  const [silences, setSilences] = useState([])
  const [rules, setRules] = useState([])
  const [channels, setChannels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [alertsData, silencesData, rulesData, channelsData] = await Promise.all([
        getAlerts().catch(() => []),
        getSilences().catch(() => []),
        getAlertRules().catch(() => []),
        getNotificationChannels().catch(() => [])
      ])
      setAlerts(alertsData)
      setSilences((silencesData || []).filter(s => !(s?.status?.state && String(s.status.state).toLowerCase() === 'expired')))
      setRules(Array.isArray(rulesData) ? rulesData.map(normalizeRuleForUI) : [])
      setChannels(channelsData)
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const stats = useMemo(() => ({
    totalAlerts: alerts.length,
    critical: alerts.filter(a => a.labels?.severity === 'critical').length,
    warning: alerts.filter(a => a.labels?.severity === 'warning').length,
    activeSilences: silences.length,
    enabledRules: rules.filter(r => r.enabled).length,
    totalRules: rules.length,
    enabledChannels: channels.filter(c => c.enabled).length,
    totalChannels: channels.length,
  }), [alerts, silences, rules, channels])

  return {
    alerts,
    silences,
    rules,
    channels,
    loading,
    error,
    stats,
    reloadData: loadData,
    setError,
  }
}