`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { useState, useRef, useEffect, useId } from 'react'

export default function HelpTooltip({ text }) {
  const [show, setShow] = useState(false)
  const wrapperRef = useRef(null)
  const tooltipRef = useRef(null)
  const [tooltipStyle, setTooltipStyle] = useState({})
  const [arrowStyle, setArrowStyle] = useState({})
  const tooltipId = useId()

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      setShow((prev) => !prev)
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      setShow(false)
    }
  }

  useEffect(() => {
    if (!show) return

    const update = () => {
      const wr = wrapperRef.current
      const tp = tooltipRef.current
      if (!wr || !tp) return

      const margin = 12
      const viewportW = window.innerWidth
      const viewportH = window.innerHeight

      const maxWidth = Math.min(300, viewportW - margin * 2)
      tp.style.maxWidth = `${maxWidth}px`

      // measure after maxWidth applied
      const tpRect = tp.getBoundingClientRect()
      const tpWidth = tpRect.width
      const tpHeight = tpRect.height
      const wrRect = wr.getBoundingClientRect()

      // center tooltip on the wrapper, then clamp to viewport
      let left = Math.round(wrRect.left + wrRect.width / 2 - tpWidth / 2)
      if (left < margin) left = margin
      if (left + tpWidth + margin > viewportW) left = viewportW - tpWidth - margin

      // prefer placing tooltip above the element; if not enough space, place below
      let top = Math.round(wrRect.top - tpHeight - 8)
      let direction = 'top'
      if (top < margin) {
        top = Math.round(wrRect.bottom + 8)
        direction = 'bottom'
        if (top + tpHeight + margin > viewportH) {
          // clamp vertical position if still overflowing
          top = Math.max(margin, viewportH - tpHeight - margin)
        }
      }

      setTooltipStyle({ left: `${left}px`, top: `${top}px`, position: 'fixed' })

      // compute arrow position inside tooltip (in px from left of tooltip)
      const wrCenter = wrRect.left + wrRect.width / 2
      let arrowLeft = Math.round(wrCenter - left - 8) // 8 = approx half arrow width
      const maxArrowLeft = Math.max(8, tpWidth - 16)
      if (arrowLeft < 8) arrowLeft = 8
      if (arrowLeft > maxArrowLeft) arrowLeft = maxArrowLeft

      const arrowTop = direction === 'top' ? '100%' : '-8px'
      const arrowTransform = direction === 'top' ? 'none' : 'rotate(180deg)'
      setArrowStyle({ left: `${arrowLeft}px`, top: arrowTop, transform: arrowTransform })
    }

    // initial position and keep it updated on resize/scroll
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    const onKey = (e) => { if (e.key === 'Escape') setShow(false) }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
      window.removeEventListener('keydown', onKey)
    }
  }, [show])

  return (
    <div ref={wrapperRef} className="relative inline-block">
      <button
        type="button"
        aria-label="Help"
        aria-expanded={show}
        aria-describedby={show ? tooltipId : undefined}
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onFocus={() => setShow(true)}
        onBlur={() => setShow(false)}
        onKeyDown={handleKeyDown}
        className="ml-1 text-sre-text-muted cursor-help bg-transparent border-0 p-0"
      >
        <span className="material-icons text-sm">help_outline</span>
      </button>

      {show && (
        <div
          id={tooltipId}
          ref={tooltipRef}
          role="tooltip"
          style={tooltipStyle}
          className="px-4 py-3 bg-sre-bg-card text-sre-text text-sm rounded-lg shadow-lg border border-sre-border z-50 whitespace-normal"
        >
          {text}
          <div style={arrowStyle} className="absolute w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-sre-bg-card" />
        </div>
      )}
    </div>
  )
}