import PropTypes from 'prop-types'
import DashboardsTab from './DashboardsTab'
import DatasourcesTab from './DatasourcesTab'
import FoldersTab from './FoldersTab'
import { Spinner } from '../ui'

export default function GrafanaContent({ loading, activeTab, dashboards, datasources, folders, query, setQuery, onSearch, openDashboardEditor, onOpenGrafana, onDeleteDashboard, openDatasourceEditor, onDeleteDatasource, getDatasourceIcon, onCreateFolder, onDeleteFolder }) {
  if (loading) {
    return (
      <div className="py-12">
        <Spinner size="lg" />
      </div>
    )
  }

  if (activeTab === 'dashboards') {
    return (
      <DashboardsTab
        dashboards={dashboards}
        query={query}
        setQuery={setQuery}
        onSearch={onSearch}
        openDashboardEditor={openDashboardEditor}
        onOpenGrafana={onOpenGrafana}
        onDeleteDashboard={onDeleteDashboard}
      />
    )
  }

  if (activeTab === 'datasources') {
    return (
      <DatasourcesTab
        datasources={datasources}
        openDatasourceEditor={openDatasourceEditor}
        onDeleteDatasource={onDeleteDatasource}
        getDatasourceIcon={getDatasourceIcon}
      />
    )
  }

  return (
    <FoldersTab
      folders={folders}
      onCreateFolder={onCreateFolder}
      onDeleteFolder={onDeleteFolder}
    />
  )
}

GrafanaContent.propTypes = {
  loading: PropTypes.bool.isRequired,
  activeTab: PropTypes.string.isRequired,
  dashboards: PropTypes.arrayOf(PropTypes.object).isRequired,
  datasources: PropTypes.arrayOf(PropTypes.object).isRequired,
  folders: PropTypes.arrayOf(PropTypes.object).isRequired,
  query: PropTypes.string.isRequired,
  setQuery: PropTypes.func.isRequired,
  onSearch: PropTypes.func.isRequired,
  openDashboardEditor: PropTypes.func.isRequired,
  onOpenGrafana: PropTypes.func.isRequired,
  onDeleteDashboard: PropTypes.func.isRequired,
  openDatasourceEditor: PropTypes.func.isRequired,
  onDeleteDatasource: PropTypes.func.isRequired,
  getDatasourceIcon: PropTypes.func.isRequired,
  onCreateFolder: PropTypes.func.isRequired,
  onDeleteFolder: PropTypes.func.isRequired,
}
