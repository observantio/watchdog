import PropTypes from "prop-types";
import DashboardsTab from "./DashboardsTab";
import DatasourcesTab from "./DatasourcesTab";
import FoldersTab from "./FoldersTab";
import { Spinner } from "../ui";

export default function GrafanaContent({
  loading,
  activeTab,
  dashboards,
  datasources,
  folders,
  groups,
  query,
  setQuery,
  filters,
  setFilters,
  onSearch,
  onClearFilters,
  hasActiveFilters,
  openDashboardEditor,
  onOpenGrafana,
  onDeleteDashboard,
  onToggleDashboardHidden,
  openDatasourceEditor,
  onDeleteDatasource,
  onToggleDatasourceHidden,
  getDatasourceIcon,
  onCreateFolder,
  onEditFolder,
  onDeleteFolder,
}) {
  if (loading) {
    return (
      <div className="py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  if (activeTab === "dashboards") {
    return (
      <DashboardsTab
        dashboards={dashboards}
        groups={groups}
        query={query}
        setQuery={setQuery}
        filters={filters}
        setFilters={setFilters}
        onSearch={onSearch}
        onClearFilters={onClearFilters}
        hasActiveFilters={hasActiveFilters}
        openDashboardEditor={openDashboardEditor}
        onOpenGrafana={onOpenGrafana}
        onDeleteDashboard={onDeleteDashboard}
        onToggleHidden={onToggleDashboardHidden}
      />
    );
  }

  if (activeTab === "datasources") {
    return (
      <DatasourcesTab
        datasources={datasources}
        groups={groups}
        filters={filters}
        setFilters={setFilters}
        onSearch={onSearch}
        onClearFilters={onClearFilters}
        hasActiveFilters={hasActiveFilters}
        openDatasourceEditor={openDatasourceEditor}
        onDeleteDatasource={onDeleteDatasource}
        onToggleHidden={onToggleDatasourceHidden}
        getDatasourceIcon={getDatasourceIcon}
      />
    );
  }

  return (
    <FoldersTab
      folders={folders}
      onCreateFolder={onCreateFolder}
      onEditFolder={onEditFolder}
      onDeleteFolder={onDeleteFolder}
    />
  );
}

GrafanaContent.propTypes = {
  loading: PropTypes.bool.isRequired,
  activeTab: PropTypes.string.isRequired,
  dashboards: PropTypes.arrayOf(PropTypes.object).isRequired,
  datasources: PropTypes.arrayOf(PropTypes.object).isRequired,
  folders: PropTypes.arrayOf(PropTypes.object).isRequired,
  groups: PropTypes.arrayOf(PropTypes.object),
  query: PropTypes.string,
  setQuery: PropTypes.func,
  filters: PropTypes.object,
  setFilters: PropTypes.func,
  onSearch: PropTypes.func,
  onClearFilters: PropTypes.func,
  hasActiveFilters: PropTypes.bool,
  openDashboardEditor: PropTypes.func.isRequired,
  onOpenGrafana: PropTypes.func.isRequired,
  onDeleteDashboard: PropTypes.func.isRequired,
  onToggleDashboardHidden: PropTypes.func,
  onEditDashboardLabels: PropTypes.func,
  openDatasourceEditor: PropTypes.func.isRequired,
  onDeleteDatasource: PropTypes.func.isRequired,
  onToggleDatasourceHidden: PropTypes.func,
  onEditDatasourceLabels: PropTypes.func,
  getDatasourceIcon: PropTypes.func.isRequired,
  onCreateFolder: PropTypes.func.isRequired,
  onEditFolder: PropTypes.func.isRequired,
  onDeleteFolder: PropTypes.func.isRequired,
};
