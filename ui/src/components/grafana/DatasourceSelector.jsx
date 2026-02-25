import PropTypes from 'prop-types'
import { Select, Checkbox } from '../../components/ui'

export default function DatasourceSelector({
  datasourceUid,
  onDatasourceChange,
  useTemplating,
  onUseTemplatingChange,
  datasources,
  label = 'Default Datasource',
  helperText = "It uses the default datasource when selected.",
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-sre-text mb-2">{label}</label>
      <Select value={datasourceUid} onChange={(e) => onDatasourceChange(e.target.value)}>
        <option value="">-- None --</option>
        {datasources.map((ds) => (
          <option key={ds.uid} value={ds.uid}>{ds.name} ({ds.type})</option>
        ))}
      </Select>

      <div className="mt-2">
        <Checkbox
          label="Use templating variable (ds_default)"
          helperText={helperText}
          checked={!!useTemplating}
          onChange={(e) => onUseTemplatingChange(e.target.checked)}
        />
      </div>
    </div>
  )
}

DatasourceSelector.propTypes = {
  datasourceUid: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  onDatasourceChange: PropTypes.func.isRequired,
  useTemplating: PropTypes.bool,
  onUseTemplatingChange: PropTypes.func.isRequired,
  datasources: PropTypes.array,
  label: PropTypes.string,
  helperText: PropTypes.string,
}
