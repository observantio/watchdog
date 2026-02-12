import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

createRoot(document.getElementById('root')).render(
  // StrictMode double-invokes lifecycle effects in development (React 18).
  // We disable it here to prevent duplicate API calls from mounting twice.
  <App />
)
