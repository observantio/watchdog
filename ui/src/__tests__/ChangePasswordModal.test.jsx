import React from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ChangePasswordModal from '../components/ChangePasswordModal'

// a simple noop for onClose
const noop = () => {}

describe('ChangePasswordModal', () => {
  it('displays forced password warning with 12 character requirement', () => {
    render(<ChangePasswordModal isOpen={true} onClose={noop} userId="user" isForced={true} />)
    expect(screen.getByText(/You must change your password before continuing/)).toBeInTheDocument()
    expect(screen.getByText(/at least 12 characters/)).toBeInTheDocument()
  })

  it('auto-shows the current password tooltip when modal is open', () => {
    render(<ChangePasswordModal isOpen={true} onClose={noop} userId="user" />)
    expect(screen.getByText('Enter your current password to verify your identity before changing it.')).toBeInTheDocument()
  })
})
