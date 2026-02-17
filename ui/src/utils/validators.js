`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

/**
 * Validate email address
 * @param {string} email - Email to validate
 * @returns {boolean} True if valid
 */
export function isValidEmail(email) {
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  return re.test(String(email).toLowerCase())
}

/**
 * Validate URL
 * @param {string} url - URL to validate
 * @returns {boolean} True if valid
 */
export function isValidURL(url) {
  try {
    new URL(url)
    return true
  } catch {
    return false
  }
}

/**
 * Validate LogQL query
 * @param {string} query - LogQL query to validate
 * @returns {{valid: boolean, error?: string}} Validation result
 */
export function validateLogQL(query) {
  if (!query || query.trim() === '') {
    return { valid: false, error: 'Query cannot be empty' }
  }
  
  // Basic validation - query should start with { for label selectors
  if (!query.includes('{') || !query.includes('}')) {
    return { valid: false, error: 'Query must include label selectors in {}' }
  }
  
  return { valid: true }
}

/**
 * Validate PromQL query
 * @param {string} query - PromQL query to validate
 * @returns {{valid: boolean, error?: string}} Validation result
 */
export function validatePromQL(query) {
  if (!query || query.trim() === '') {
    return { valid: false, error: 'Query cannot be empty' }
  }
  
  // Basic validation
  const invalidChars = /[<>]/g
  if (invalidChars.test(query)) {
    return { valid: false, error: 'Query contains invalid characters' }
  }
  
  return { valid: true }
}

/**
 * Validate duration string (e.g., "5m", "1h", "30s")
 * @param {string} duration - Duration string
 * @returns {boolean} True if valid
 */
export function isValidDuration(duration) {
  const re = /^\d+[smhd]$/
  return re.test(duration)
}

/**
 * Validate required field
 * @param {any} value - Value to validate
 * @returns {{valid: boolean, error?: string}} Validation result
 */
export function validateRequired(value) {
  if (value === null || value === undefined || value === '') {
    return { valid: false, error: 'This field is required' }
  }
  return { valid: true }
}

/**
 * Validate minimum length
 * @param {string} value - Value to validate
 * @param {number} minLength - Minimum length
 * @returns {{valid: boolean, error?: string}} Validation result
 */
export function validateMinLength(value, minLength) {
  if (!value || value.length < minLength) {
    return { valid: false, error: `Must be at least ${minLength} characters` }
  }
  return { valid: true }
}

/**
 * Validate maximum length
 * @param {string} value - Value to validate
 * @param {number} maxLength - Maximum length
 * @returns {{valid: boolean, error?: string}} Validation result
 */
export function validateMaxLength(value, maxLength) {
  if (value && value.length > maxLength) {
    return { valid: false, error: `Must be at most ${maxLength} characters` }
  }
  return { valid: true }
}

/**
 * Validate number range
 * @param {number} value - Value to validate
 * @param {number} min - Minimum value
 * @param {number} max - Maximum value
 * @returns {{valid: boolean, error?: string}} Validation result
 */
export function validateRange(value, min, max) {
  const num = Number(value)
  if (Number.isNaN(num)) {
    return { valid: false, error: 'Must be a number' }
  }
  if (num < min || num > max) {
    return { valid: false, error: `Must be between ${min} and ${max}` }
  }
  return { valid: true }
}
