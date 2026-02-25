import PropTypes from 'prop-types'
import { Card, Badge } from '../../components/ui'

export default function LogLabels({ labels = [], labelValuesCache = {} }) {
  const list = labels || []

  return (
    <Card title="Available Labels" subtitle={`${list.length} labels`}>
      <div className="space-y-2 max-h-[30rem] overflow-y-auto pr-2 scrollbar-thin">
        {list.map(label => (
          <div key={label} className="flex items-center justify-between text-sm">
            <span className="font-mono text-sre-text">{label}</span>
            <Badge variant="default" size="sm">
              {labelValuesCache?.[label]?.length ?? '...'}
            </Badge>
          </div>
        ))}
      </div>
    </Card>
  )
}

LogLabels.propTypes = {
  labels: PropTypes.arrayOf(PropTypes.string),
  labelValuesCache: PropTypes.objectOf(PropTypes.arrayOf(PropTypes.string))
}
