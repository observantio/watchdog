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