import PropTypes from 'prop-types'
import { Card, Badge, Button } from '../ui'

export default function GroupCard({ group, usersCount, permsCount, onOpenPermissions, onEdit, onDelete }) {
  return (
    <Card className="p-0 relative overflow-visible bg-gradient-to-br from-sre-surface to-sre-surface/80 border-2 border-sre-border/50 hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm rounded-lg group">
      <div className="p-6">
        <div className="flex items-start gap-4 mb-4">
          <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-sre-primary/20 to-sre-primary/10 text-sre-primary flex items-center justify-center font-semibold border border-sre-border/50 flex-shrink-0">
            <span className="material-icons text-xl">groups</span>
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-xl font-bold text-sre-text truncate mb-1" title={group.name}>{group.name}</h3>
            <p className="text-sm text-sre-text-muted truncate" title={group.description || 'No description'}>
              {group.description || 'No description provided'}
            </p>
          </div>
        </div>

        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Badge variant="info" className="whitespace-nowrap text-xs px-3 py-1 font-medium">
              <span className="material-icons text-xs mr-1">security</span>
              {permsCount} permission{permsCount !== 1 ? 's' : ''}
            </Badge>
            <Badge variant="success" className="whitespace-nowrap text-xs px-3 py-1 font-medium">
              <span className="material-icons text-xs mr-1">person</span>
              {usersCount} member{usersCount !== 1 ? 's' : ''}
            </Badge>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 items-center pt-2 border-t border-sre-border/30">
          <Button size="sm" variant="ghost" className="flex items-center gap-2 hover:bg-sre-primary/10 hover:text-sre-primary transition-colors" onClick={() => onOpenPermissions(group)} aria-label={`Permissions for ${group.name}`}>
            <span className="material-icons text-sm">security</span>
            <span>Permissions</span>
          </Button>

          <Button size="sm" variant="ghost" className="flex items-center gap-2 hover:bg-sre-primary/10 hover:text-sre-primary transition-colors" onClick={() => onEdit(group)} aria-label={`Edit ${group.name}`}>
            <span className="material-icons text-sm">edit</span>
            <span>Edit</span>
          </Button>

          <Button size="sm" variant="ghost" className="flex items-center gap-2 hover:bg-red-500/10 hover:text-red-500 transition-colors" onClick={() => onDelete(group)} aria-label={`Delete ${group.name}`}>
            <span className="material-icons text-sm">delete</span>
            <span>Delete</span>
          </Button>
        </div>
      </div>
    </Card>
  )
}

GroupCard.propTypes = {
  group: PropTypes.object.isRequired,
  usersCount: PropTypes.number.isRequired,
  permsCount: PropTypes.number.isRequired,
  onOpenPermissions: PropTypes.func.isRequired,
  onEdit: PropTypes.func.isRequired,
  onDelete: PropTypes.func.isRequired,
}
