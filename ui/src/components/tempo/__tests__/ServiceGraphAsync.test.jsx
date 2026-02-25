// JSDOM doesn't provide ResizeObserver which reactflow expects
if (typeof global.ResizeObserver === 'undefined') {
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

import React from 'react'
import { render } from '@testing-library/react'
import ServiceGraphAsync from '../ServiceGraphAsync.jsx'

// minimal props to render without errors
const dummyTraces = [{
  spans: [
    { service: 'a', startTime: 0, duration: 100 },
    { service: 'b', startTime: 10, duration: 50, parentSpanId: null },
  ],
}]

describe('ServiceGraphAsync styling', () => {
  it('includes minimap styles and dark mode overrides', () => {
    const { container } = render(<ServiceGraphAsync traces={dummyTraces} />)
    const styleTag = container.querySelector('style')
    expect(styleTag).toBeTruthy()
    const text = styleTag.textContent
    expect(text).toMatch(/\.react-flow__minimap/)
    expect(text).toMatch(/\.dark \.react-flow__minimap/)
    expect(text).toMatch(/background:\s*#ffffff/)
  })
})
