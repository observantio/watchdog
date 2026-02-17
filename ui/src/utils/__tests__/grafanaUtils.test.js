import { describe, it, expect } from 'vitest'
import { overrideDashboardDatasource, findPrimaryDatasourceUid, resolveToUid, inferDashboardDatasource } from '../grafanaUtils'

describe('overrideDashboardDatasource', () => {
  it('replaces panel.datasource and target.datasource with selected uid and updates templating', () => {
    const dashboard = {
      title: 'Test',
      templating: { list: [ { name: 'ds_default', type: 'datasource', current: { text: 'old', value: 'old-uid' } } ] },
      panels: [
        { id: 1, datasource: 'old-uid', targets: [ { expr: 'up', datasource: 'old-uid' } ] },
        { id: 2, datasource: { uid: 'old-uid', type: 'prometheus' }, targets: [ { expr: 'rate', datasourceUid: 'old-uid' } ] },
      ],
    }

    const datasources = [ { uid: 'new-uid', name: 'New DS', type: 'prometheus' } ]

    const out = overrideDashboardDatasource(dashboard, 'new-uid', datasources)

    // templating updated
    expect(out.templating).toBeDefined()
    expect(out.templating.list.find(i => i.type === 'datasource').current.value).toBe('new-uid')
    expect(out.templating.list.find(i => i.type === 'datasource').current.text).toBe('New DS')

    // panel-level datasource strings/objects replaced
    expect(out.panels[0].datasource).toBe('new-uid')
    expect(out.panels[0].targets[0].datasource).toBe('new-uid')
    expect(out.panels[1].datasource).toBe('new-uid')
    expect(out.panels[1].targets[0].datasourceUid).toBe('new-uid')
  })

  it('does not inject templating when injectTemplating is false but still updates panels/targets', () => {
    const dashboard = {
      title: 'No templating',
      panels: [ { id: 1, targets: [ { expr: 'up' } ] } ],
    }

    const out = overrideDashboardDatasource(dashboard, 'prom-uid', [{ uid: 'prom-uid', name: 'Prom' }], false)

    // templating should not be created/modified
    expect(out.templating).toBeUndefined()

    // panel-level datasource should still be applied
    expect(out.panels[0].datasource).toBe('prom-uid')
    expect(out.panels[0].targets[0].datasource).toBe('prom-uid')
  })

  it('adds a datasource templating variable when none exists (default behavior)', () => {
    const dashboard = { title: 'No templating', panels: [] }
    const out = overrideDashboardDatasource(dashboard, 'ds-1', [])
    expect(out.templating).toBeDefined()
    expect(Array.isArray(out.templating.list)).toBe(true)
    expect(out.templating.list[0].name).toBe('ds_default')
    expect(out.templating.list[0].current.value).toBe('ds-1')
  })

  it('adds panel.datasource and target.datasource for targets with expr when missing', () => {
    const dashboard = {
      title: 'Expr panels',
      panels: [
        { id: 1, title: 'CPU', targets: [ { expr: 'rate(cpu[5m])' } ] },
        { id: 2, title: 'Memory', targets: [ { expr: 'memory_usage' } ] },
      ],
    }
    const out = overrideDashboardDatasource(dashboard, 'prom-uid', [{ uid: 'prom-uid', name: 'Prom' }])

    expect(out.panels[0].datasource).toBe('prom-uid')
    expect(out.panels[0].datasourceUid).toBe('prom-uid')
    expect(out.panels[0].targets[0].datasource).toBe('prom-uid')
    expect(out.panels[0].targets[0].datasourceUid).toBe('prom-uid')
    expect(out.panels[1].datasource).toBe('prom-uid')
    expect(out.panels[1].datasourceUid).toBe('prom-uid')
    expect(out.panels[1].targets[0].datasource).toBe('prom-uid')
    expect(out.panels[1].targets[0].datasourceUid).toBe('prom-uid')
  })

  it('resolveToUid handles uid/name/object forms', () => {
    const datasources = [{ uid: 'prom-uid', name: 'Prom' }, { uid: 'loki-uid', name: 'Loki' }]
    expect(resolveToUid('prom-uid', datasources)).toBe('prom-uid')
    expect(resolveToUid('Prom', datasources)).toBe('prom-uid')
    expect(resolveToUid({ value: 'loki-uid' }, datasources)).toBe('loki-uid')
    expect(resolveToUid({ text: 'Loki' }, datasources)).toBe('loki-uid')
    expect(resolveToUid('missing', datasources)).toBe('')
  })

  it('inferDashboardDatasource prefers templating then falls back to panels', () => {
    const datasources = [{ uid: 'prom-uid', name: 'Prom' }]
    const dashWithTempl = { templating: { list: [ { type: 'datasource', current: { value: 'Prom' } } ] } }
    expect(inferDashboardDatasource(dashWithTempl, datasources)).toEqual({ uid: 'prom-uid', useTemplating: true })

    const dashWithPanels = { panels: [ { datasourceUid: 'x' }, { targets: [ { datasourceUid: 'x' } ] } ] }
    expect(inferDashboardDatasource(dashWithPanels, datasources)).toEqual({ uid: 'x', useTemplating: false })
  })

  it('findPrimaryDatasourceUid returns the most common datasource across panels/targets', () => {
    const dashboard = {
      panels: [
        { id: 1, datasourceUid: 'a', targets: [ { datasourceUid: 'a' } ] },
        { id: 2, datasource: 'b', targets: [ { datasource: 'b' }, { datasourceUid: 'a' } ] },
      ],
    }
    const uid = findPrimaryDatasourceUid(dashboard)
    expect(uid).toBe('a')
  })
})