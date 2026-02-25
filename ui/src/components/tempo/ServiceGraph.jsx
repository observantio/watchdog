`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import React from 'react'
import PropTypes from 'prop-types'
/**
 * ServiceGraph component
 * @param {object} props - Component props
 * @param {Array} props.traces - Array of trace objects
 */
export default function ServiceGraph(props) {
  const ServiceGraphAsync = React.lazy(() => import('./ServiceGraphAsync'))
  return (
    <React.Suspense fallback={<div className="p-6 text-center text-sre-text-muted">Loading service graph…</div>}>
      <ServiceGraphAsync {...props} />
    </React.Suspense>
  )
}

ServiceGraph.propTypes = {
  traces: PropTypes.arrayOf(PropTypes.object).isRequired,
}
