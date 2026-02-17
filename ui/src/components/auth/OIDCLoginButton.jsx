`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import PropTypes from 'prop-types'
import { Button } from '../ui'

export default function OIDCLoginButton({ loading, onClick, providerLabel = 'Single Sign-On' }) {
  return (
    <Button
      type="button"
      variant="secondary"
      className="w-full"
      loading={loading}
      onClick={onClick}
    >
      {loading ? 'Redirecting...' : `Continue with ${providerLabel}`}
    </Button>
  )
}

OIDCLoginButton.propTypes = {
  loading: PropTypes.bool,
  onClick: PropTypes.func.isRequired,
  providerLabel: PropTypes.string,
}
