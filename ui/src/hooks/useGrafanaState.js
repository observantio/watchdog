`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useState, useEffect, useCallback } from 'react'
import {
  searchDashboards,getDatasources, getFolders, getGroups,
  toggleDashboardHidden, toggleDatasourceHidden,
  getDashboardFilterMeta, getDatasourceFilterMeta
} from '../api'
import { useToast } from '../contexts/ToastContext'
import { useAuth } from '../contexts/AuthContext'
import { GRAFANA_DATASOURCE_TYPES as DATASOURCE_TYPES } from '../utils/grafanaUtils'

export function useGrafanaState() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState('dashboards')
  const [dashboards, setDashboards] = useState([])
  const [datasources, setDatasources] = useState([])
  const [folders, setFolders] = useState([])
  const [groups, setGroups] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [dashboardMeta, setDashboardMeta] = useState({})
  const [datasourceMeta, setDatasourceMeta] = useState({})

  const [filters, setFilters] = useState({
    teamId: '',
    showHidden: false,
  })

  const toast = useToast()

  function handleApiError(e) {
    if (!e) return

    if (e && typeof e.status === 'number') {
      return
    }

    const msg = e.message || String(e || '')
    const lower = msg.toLowerCase()
    if (lower.includes('not found') && (lower.includes('access denied') || lower.includes('update failed'))) return
    toast.error(msg)
  }

  useEffect(() => {
    loadGroups()
  }, [])

  async function loadGroups() {
    try {
      const groupsData = await getGroups().catch(() => [])
      setGroups(groupsData)
    } catch (e) { /* silent */ void e }
  }

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      if (activeTab === 'dashboards') {
        const [dashboardsData, foldersData, datasourcesData, dashboardMetaData] = await Promise.all([
          searchDashboards({
            query: query || undefined,
            teamId: filters.teamId || undefined,
            showHidden: filters.showHidden,
          }).catch(() => []),
          getFolders().catch(() => []),
          getDatasources().catch(() => []),
          getDashboardFilterMeta().catch(() => ({})),
        ])
        setDashboards(dashboardsData)
        setFolders(foldersData)
        setDatasources(datasourcesData)
        setDashboardMeta(dashboardMetaData)
      } else if (activeTab === 'datasources') {
        const [datasourcesData, datasourceMetaData] = await Promise.all([
          getDatasources({
            teamId: filters.teamId || undefined,
            showHidden: filters.showHidden,
          }).catch(() => []),
          getDatasourceFilterMeta().catch(() => ({})),
        ])
        setDatasources(datasourcesData)
        setDatasourceMeta(datasourceMetaData)
      } else if (activeTab === 'folders') {
        const foldersData = await getFolders().catch(() => [])
        setFolders(foldersData)
      }
    } catch (e) {
      handleApiError(e)
    } finally {
      setLoading(false)
    }
  }, [activeTab, query, filters])

  useEffect(() => {
    loadData()
  }, [loadData])

  async function onSearch(e) {
    e.preventDefault()
    loadData()
  }

  function clearFilters() {
    setFilters({ teamId: '', showHidden: false })
    setQuery('')
  }

  async function handleToggleDashboardHidden(dashboard) {
    const nowHidden = !dashboard.is_hidden
    const confirm = window.confirm(nowHidden ? `Hide "${dashboard.title}"?` : `Unhide "${dashboard.title}"?`)
    if (!confirm) return

    try {
      await toggleDashboardHidden(dashboard.uid, nowHidden)
      toast.success(nowHidden ? 'Dashboard hidden' : 'Dashboard visible')
      loadData()
    } catch (e) { handleApiError(e) }
  }

  async function handleToggleDatasourceHidden(datasource) {
    const nowHidden = !datasource.is_hidden
    const confirm = window.confirm(nowHidden ? `Hide "${datasource.name}"?` : `Unhide "${datasource.name}"?`)
    if (!confirm) return

    try {
      await toggleDatasourceHidden(datasource.uid, nowHidden)
      toast.success(nowHidden ? 'Datasource hidden' : 'Datasource visible')
      loadData()
    } catch (e) { handleApiError(e) }
  }

  function getDatasourceIcon(type) {
    const found = DATASOURCE_TYPES.find(t => t.value === type)
    return found ? found.icon : '🔧'
  }

  const hasActiveFilters = filters.teamId || filters.showHidden

  return {
    activeTab,
    setActiveTab,
    dashboards,
    datasources,
    folders,
    groups,
    query,
    setQuery,
    loading,
    dashboardMeta,
    datasourceMeta,
    filters,
    setFilters,
    onSearch,
    clearFilters,
    handleToggleDashboardHidden,
    handleToggleDatasourceHidden,
    getDatasourceIcon,
    hasActiveFilters,
    loadData,
    toast,
    handleApiError,
    user,
  }
}