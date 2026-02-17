`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { Alert } from '../ui'

export default function ErrorAlert({ error, onClose }) {
  if (!error) return null
  return (
    <Alert variant="error" className="mb-6" onClose={onClose}>
      <strong>Error:</strong> {error}
    </Alert>
  )
}