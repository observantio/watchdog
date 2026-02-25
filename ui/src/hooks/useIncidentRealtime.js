import { useEffect } from 'react'

export function useIncidentRealtime({ onUpdate, intervalMs = 5000 }) {
  useEffect(() => {
    let active = true
    let timeout
    async function poll() {
      try {
        const res = await fetch('/api/alertmanager/incidents')
        if (!res.ok) throw new Error('Failed to fetch incidents')
        const data = await res.json()
        if (active && typeof onUpdate === 'function') onUpdate(data)
      } catch (e) {
        // Optionally handle error
      } finally {
        if (active) timeout = setTimeout(poll, intervalMs)
      }
    }
    poll()
    return () => {
      active = false
      if (timeout) clearTimeout(timeout)
    }
  }, [onUpdate, intervalMs])
}
