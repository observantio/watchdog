import { useState } from 'react'
import PropTypes from 'prop-types'
import { Input, Checkbox } from '../ui'

export default function MemberList({ users, selectedMembers, toggleMember }) {
  const [searchQuery, setSearchQuery] = useState('')

  if (!users.length) {
    return <div className="text-sm text-sre-text-muted">No users available.</div>
  }

  const filteredUsers = users.filter((user) => {
    const query = searchQuery.toLowerCase()
    return (
      (user.full_name || user.username).toLowerCase().includes(query) ||
      user.email.toLowerCase().includes(query)
    )
  })

  const displayedUsers = filteredUsers.slice(0, 5)
  const hasMore = filteredUsers.length > 5

  const getUserLabel = (user) => {
    const name = user.full_name || user.username || user.id
    const email = user.email ? ` <${user.email}>` : ''
    return `${name}${email}`
  }

  return (
    <div className="space-y-3">
      <Input
        placeholder="Search users by name or email..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="text-sm"
      />

      <div className="max-h-64 overflow-y-auto space-y-2 pr-2">
        {displayedUsers.length === 0 ? (
          <div className="text-sm text-sre-text-muted">
            {searchQuery ? 'No users match your search.' : 'No users available.'}
          </div>
        ) : (
          <>
            {displayedUsers.map((user) => {
              const selected = selectedMembers.includes(user.id)
              return (
                <label
                  key={user.id}
                  className={`w-full text-left flex items-center gap-3 min-w-0 px-3 py-2 text-sm hover:bg-sre-surface transition-colors cursor-pointer ${selected ? 'text-sre-primary bg-sre-surface' : 'text-sre-text'}`}
                >
                  <Checkbox
                    checked={selected}
                    onChange={() => toggleMember(user.id)}
                  />
                  <span className="material-icons text-sm flex-shrink-0" aria-hidden>person</span>
                  <div className="truncate min-w-0">{getUserLabel(user)}</div>
                </label>
              )
            })}
            {hasMore && (
              <div className="text-xs text-sre-text-muted text-center py-2">
                Showing first 5 of {filteredUsers.length} users. Use search to find specific users.
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

MemberList.propTypes = {
  users: PropTypes.arrayOf(PropTypes.shape({
    id: PropTypes.string.isRequired,
    username: PropTypes.string,
    full_name: PropTypes.string,
    email: PropTypes.string.isRequired,
  })).isRequired,
  selectedMembers: PropTypes.arrayOf(PropTypes.string).isRequired,
  toggleMember: PropTypes.func.isRequired,
}
