import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  deepClone,
  getLogLevel,
  getServiceName,
  getSpanAttribute,
  hasSpanError,
  isEmpty,
  percentile,
  copyToClipboard,
} from '../helpers'

describe('helpers', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('extracts log levels and service names', () => {
    expect(getLogLevel('fatal error').text).toBe('ERROR')
    expect(getLogLevel('warn: issue').text).toBe('WARN')
    expect(getServiceName({ process: { serviceName: 'api' } })).toBe('api')
    expect(getServiceName(null)).toBe('unknown')
  })

  it('reads span attributes from attributes and tags', () => {
    expect(getSpanAttribute({ attributes: { 'service.name': 'svc' } }, 'service.name')).toBe('svc')
    expect(getSpanAttribute({ tags: [{ key: 'k', value: 'v' }] }, 'k')).toBe('v')
    expect(getSpanAttribute(null, 'k')).toBeNull()
  })

  it('computes percentile and error checks', () => {
    expect(percentile([1, 2, 3, 4], 0.5)).toBe(3)
    expect(hasSpanError({ status: { code: 'ERROR' } })).toBe(true)
    expect(hasSpanError({ tags: { error: true } })).toBe(true)
  })

  it('handles clone and empty checks', () => {
    const value = { a: 1 }
    expect(deepClone(value)).toEqual(value)
    expect(isEmpty('  ')).toBe(true)
    expect(isEmpty([])).toBe(true)
    expect(isEmpty({})).toBe(true)
    expect(isEmpty('x')).toBe(false)
  })

  it('copies to clipboard safely', async () => {
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
    await expect(copyToClipboard('abc')).resolves.toBe(true)
  })

  it('downloads a file without throwing', () => {
    if (typeof URL.createObjectURL !== 'function') {
      vi.stubGlobal('URL', { createObjectURL: vi.fn().mockReturnValue('blob://x') })
    } else {
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob://x')
    }
    const append = vi.spyOn(document.body, 'appendChild')
    expect(() => downloadFile('hello', 'file.txt', 'text/plain')).not.toThrow()
    append.mockRestore()
  })
})
