`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import PropTypes from 'prop-types'
import { Card } from '../ui'

// simple wrapper used by panels to avoid repeating compact/card logic
export default function Section({ compact = false, className = '', children }) {
  if (compact) {
    return <div className={className}>{children}</div>
  }
  return (
    <Card className={`${className} border border-sre-border rounded-xl p-4`}> 
      {children}
    </Card>
  )
}

Section.propTypes = {
  compact: PropTypes.bool,
  className: PropTypes.string,
  children: PropTypes.node,
}
