import React from 'react'
import { render } from '@testing-library/react'
import LogVolume from '../../loki/LogVolume.jsx'

describe('volume components truncation', () => {
  it('renders numbers with truncate class in LogVolume', () => {
    const vol = []
    const { container } = render(<LogVolume volume={[1, 2, 3]} />)
    const totals = container.querySelectorAll('.truncate')
    expect(totals.length).toBeGreaterThan(0)
  })
})
