`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useEffect, useState } from 'react'
import { getActiveAgents } from '../api'

export function useAgentActivity() {
  const [agentActivity, setAgentActivity] = useState([])
  const [loadingAgents, setLoadingAgents] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        setLoadingAgents(true)
        const res = await getActiveAgents()
        setAgentActivity(Array.isArray(res) ? res : [])
      } catch (e) { void e
        setAgentActivity([])
      } finally {
        setLoadingAgents(false)
      }
    })()
  }, [])

  return {
    agentActivity,
    loadingAgents,
  }
}