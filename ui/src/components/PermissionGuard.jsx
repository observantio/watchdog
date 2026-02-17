`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import PropTypes from 'prop-types'
import { useAuth } from '../contexts/AuthContext'

export default function PermissionGuard({ any = [], all = [], children, fallback = null }) {
  const { hasPermission } = useAuth()

  if (all?.length > 0) {
    const ok = all.every(p => hasPermission(p))
    if (!ok) return fallback
    return children
  }

  if (any?.length > 0) {
    const ok = any.some(p => hasPermission(p))
    if (!ok) return fallback
    return children
  }

  return children
}

PermissionGuard.propTypes = {
  any: PropTypes.arrayOf(PropTypes.string),
  all: PropTypes.arrayOf(PropTypes.string),
  children: PropTypes.node,
  fallback: PropTypes.node
}
