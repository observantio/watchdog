`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import React from 'react'
import PropTypes from 'prop-types'
import { Alert, Button } from './ui'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true }
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo)
    this.setState({ hasError: true, error, errorInfo })
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null })
    if (this.props.onReset) {
      this.props.onReset()
    }
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="min-h-screen flex items-center justify-center p-4 bg-sre-bg">
          <div className="max-w-2xl w-full">
            <Alert variant="error" className="mb-4">
              <div className="flex items-start gap-3">
                <span className="material-icons text-2xl">error_outline</span>
                <div className="flex-1">
                  <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
                  <p className="text-sm mb-4">
                    An unexpected error occurred in the application. Please try refreshing the page.
                  </p>
                  
                  {this.state.error && (
                    <details className="mt-4">
                      <summary className="cursor-pointer text-sm font-semibold mb-2">
                        Error Details
                      </summary>
                      <pre className="text-xs bg-sre-bg-alt p-4 rounded border border-sre-border overflow-auto max-h-64">
                        {this.state.error.toString()}
                        {this.state.errorInfo && `\n\n${this.state.errorInfo.componentStack}`}
                      </pre>
                    </details>
                  )}

                  <div className="flex gap-2 mt-4">
                    <Button onClick={this.handleReset}>
                      <span className="material-icons text-sm mr-2">refresh</span>
                      <span>Try Again</span>
                    </Button>
                    <Button variant="ghost" onClick={() => globalThis.location.reload()}>
                      Reload Page
                    </Button>
                  </div>
                </div>
              </div>
            </Alert>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

ErrorBoundary.propTypes = {
  children: PropTypes.node.isRequired,
  fallback: PropTypes.node,
  onReset: PropTypes.func
}
