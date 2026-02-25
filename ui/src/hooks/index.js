`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useState, useEffect, useCallback, useRef } from 'react'

/**
 * Hook for API calls with loading and error states
 * @param {Function} apiFunc - API function to call
 * @param {any} initialData - Initial data value
 * @returns {{data, loading, error, execute, reset}} API state and controls
 */
export function useApi(apiFunc, initialData = null) {
  const [data, setData] = useState(initialData)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const execute = useCallback(async (...args) => {
    setLoading(true)
    setError(null)
    try {
      const result = await apiFunc(...args)
      setData(result)
      return result
    } catch (err) {
      setError(err.message || 'An error occurred')
      throw err
    } finally {
      setLoading(false)
    }
  }, [apiFunc])

  const reset = useCallback(() => {
    setData(initialData)
    setError(null)
    setLoading(false)
  }, [initialData])

  return { data, loading, error, execute, reset }
}

/**
 * Hook for debouncing values
 * @param {any} value - Value to debounce
 * @param {number} delay - Delay in milliseconds
 * @returns {any} Debounced value
 */
export function useDebounce(value, delay = 500) {
  const [debouncedValue, setDebouncedValue] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(timer)
    }
  }, [value, delay])

  return debouncedValue
}

/**
 * Hook for local storage with state sync
 * @param {string} key - Storage key
 * @param {any} initialValue - Initial value
 * @returns {[any, Function]} Value and setter
 */
export function useLocalStorage(key, initialValue) {
  const [storedValue, setStoredValue] = useState(() => {
    try {
      const item = globalThis.window.localStorage.getItem(key)
      return item ? JSON.parse(item) : initialValue
    } catch (error) {
      console.error(`Error reading localStorage key "${key}":`, error)
      return initialValue
    }
  })

  const setValue = useCallback((value) => {
    try {
      setStoredValue((previousValue) => {
        const valueToStore = typeof value === 'function' ? value(previousValue) : value
        globalThis.window.localStorage.setItem(key, JSON.stringify(valueToStore))
        return valueToStore
      })
    } catch (error) {
      console.error(`Error setting localStorage key "${key}":`, error)
    }
  }, [key])

  return [storedValue, setValue]
}

/**
 * Hook for pagination
 * @param {number} totalItems - Total number of items
 * @param {number} itemsPerPage - Items per page
 * @returns {object} Pagination state and controls
 */
export function usePagination(totalItems, itemsPerPage = 10) {
  const [currentPage, setCurrentPage] = useState(1)

  const totalPages = Math.ceil(totalItems / itemsPerPage)
  const startIndex = (currentPage - 1) * itemsPerPage
  const endIndex = Math.min(startIndex + itemsPerPage, totalItems)

  const goToPage = useCallback((page) => {
    const pageNumber = Math.max(1, Math.min(page, totalPages))
    setCurrentPage(pageNumber)
  }, [totalPages])

  const nextPage = useCallback(() => {
    goToPage(currentPage + 1)
  }, [currentPage, goToPage])

  const previousPage = useCallback(() => {
    goToPage(currentPage - 1)
  }, [currentPage, goToPage])

  const reset = useCallback(() => {
    setCurrentPage(1)
  }, [])

  return {
    currentPage,
    totalPages,
    startIndex,
    endIndex,
    goToPage,
    nextPage,
    previousPage,
    reset,
    hasNext: currentPage < totalPages,
    hasPrevious: currentPage > 1,
  }
}

/**
 * Hook for auto-refresh functionality
 * @param {Function} callback - Function to call on each interval
 * @param {number} interval - Interval in milliseconds
 * @param {boolean} enabled - Whether auto-refresh is enabled
 */
export function useAutoRefresh(callback, interval = 30000, enabled = false) {
  const savedCallback = useRef(callback)

  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  useEffect(() => {
    if (!enabled) return

    const tick = () => {
      if (typeof document !== 'undefined' && document.hidden) return
      savedCallback.current()
    }
    const id = setInterval(tick, interval)

    return () => clearInterval(id)
  }, [interval, enabled])
}

/**
 * Hook for click outside detection
 * @param {Function} handler - Handler function when clicked outside
 * @returns {React.RefObject} Ref to attach to element
 */
export function useClickOutside(handler) {
  const ref = useRef(null)

  useEffect(() => {
    const listener = (event) => {
      if (!ref.current || ref.current.contains(event.target)) {
        return
      }
      handler(event)
    }

    document.addEventListener('mousedown', listener)
    document.addEventListener('touchstart', listener)

    return () => {
      document.removeEventListener('mousedown', listener)
      document.removeEventListener('touchstart', listener)
    }
  }, [handler])

  return ref
}

/**
 * Hook for previous value
 * @param {any} value - Current value
 * @returns {any} Previous value
 */
export function usePrevious(value) {
  const ref = useRef()

  useEffect(() => {
    ref.current = value
  }, [value])

  return ref.current
}

/**
 * Hook for toggle state
 * @param {boolean} initialValue - Initial toggle value
 * @returns {[boolean, Function, Function, Function]} State and toggle functions
*/

export function useToggle(initialValue = false) {
  const [value, setValue] = useState(initialValue)

  const toggle = useCallback(() => {
    setValue(v => !v)
  }, [])

  const setTrue = useCallback(() => {
    setValue(true)
  }, [])

  const setFalse = useCallback(() => {
    setValue(false)
  }, [])

  return [value, toggle, setTrue, setFalse]
}

/**
 * Lock body scroll when `locked` is true and restore when false/unmount
 */
export function useBodyScrollLock(locked) {
  useEffect(() => {
    const prev = document.body.style.overflow
    if (locked) {
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.body.style.overflow = prev
    }
  }, [locked])
}

export { useDashboardData } from './useDashboardData'
export { useAgentActivity } from './useAgentActivity'
export { usePersistentOrder } from './usePersistentOrder'
export { useIncidentsData } from './useIncidentsData'
export { useAlertManagerData } from './useAlertManagerData'
