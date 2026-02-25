import React from 'react'
import { describe, it, expect } from 'vitest'
import { render, fireEvent, screen, waitFor } from '@testing-library/react'
import { axe, toHaveNoViolations } from 'jest-axe'
import { Modal } from '../ui'
import HelpTooltip from '../HelpTooltip'

expect.extend(toHaveNoViolations)

describe('Modal accessibility and focus behavior', () => {
  it('traps focus within modal and restores focus on close', async () => {
    const trigger = document.createElement('button')
    trigger.textContent = 'open'
    document.body.appendChild(trigger)
    trigger.focus()

    const onClose = vi.fn()
    const { rerender } = render(
      <Modal isOpen onClose={onClose} title="Test Modal">
        <button type="button">First</button>
        <button type="button">Last</button>
      </Modal>
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Close modal' })).toHaveFocus()
    })

    const closeButton = screen.getByRole('button', { name: 'Close modal' })
    const last = screen.getByRole('button', { name: 'Last' })

    closeButton.focus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(last).toHaveFocus()

    rerender(
      <Modal isOpen={false} onClose={onClose} title="Test Modal">
        <button type="button">First</button>
        <button type="button">Last</button>
      </Modal>
    )

    await waitFor(() => {
      expect(trigger).toHaveFocus()
    })

    trigger.remove()
  })

  it('has no obvious a11y violations', async () => {
    const { container } = render(
      <Modal isOpen onClose={() => {}} title="A11y Modal">
        <button type="button">Action</button>
      </Modal>
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('HelpTooltip accessibility', () => {
  it('sets aria-describedby when visible and supports keyboard toggle', async () => {
    render(<HelpTooltip text="Helpful content" />)

    const button = screen.getByRole('button', { name: 'Help' })
    fireEvent.focus(button)

    const tooltip = await screen.findByRole('tooltip')
    expect(button).toHaveAttribute('aria-describedby', tooltip.getAttribute('id'))

    fireEvent.keyDown(button, { key: 'Escape' })
    await waitFor(() => {
      expect(screen.queryByRole('tooltip')).toBeNull()
    })

    fireEvent.keyDown(button, { key: 'Enter' })
    expect(await screen.findByRole('tooltip')).toBeInTheDocument()
  })

  it('has no obvious a11y violations', async () => {
    const { container } = render(<HelpTooltip text="Tooltip text" />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
