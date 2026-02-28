import React from 'react'
import { render, screen } from '@testing-library/react'
import { vi, describe, it, beforeEach, expect } from 'vitest'

// basic UI components are mocked to avoid importing tailwind/etc
gi.mock('../../ui', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: (props) => <input {...props} />,
  Select: ({ children, onChange, ...props }) => (
    <select {...props} onChange={(e) => onChange?.(e.target.value)}>{children}</select>
  ),
}))
vi.mock('../../HelpTooltip', () => ({ default: () => <span /> }))

// we will provide a fake AuthContext with configurable permission
gi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ hasPermission: vi.fn() }),
}))

import RuleEditor from '../RuleEditor'

// minimal props
const noop = () => {}
const defaultProps = { rule: null, apiKeys: [], onSave: noop, onCancel: noop }

describe('RuleEditor notification channel section', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('displays "No channels configured" message and manage link when user has read permission', () => {
    const { useAuth } = require('../../../contexts/AuthContext')
    useAuth.mockReturnValue({ hasPermission: () => true })

    render(<RuleEditor {...defaultProps} channels={[]} />)

    expect(screen.getByText(/No Channels Configured/i)).toBeInTheDocument()
    const link = screen.getByText('Manage Integrations').closest('a')
    expect(link).toHaveAttribute('href', '/integrations')
  })

  it('shows permission warning when user lacks read:channels', () => {
    const { useAuth } = require('../../../contexts/AuthContext')
    useAuth.mockReturnValue({ hasPermission: () => false })

    render(<RuleEditor {...defaultProps} channels={[]} />)

    expect(screen.getByText(/don't have permission/i)).toBeInTheDocument()
    expect(screen.queryByText('Manage Integrations')).not.toBeInTheDocument()
  })
})
