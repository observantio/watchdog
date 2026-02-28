`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

import { visualizer } from 'rollup-plugin-visualizer'

export default defineConfig(({ mode }) => {
  const plugins = [react()]
  if (process.env.ANALYZE) {
    plugins.push(visualizer({ filename: 'dist/report.html', gzipSize: true }))
  }

  return {
    plugins,
    server: {
      host: '0.0.0.0',
      port: 5173
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setupTests.js'],
    },
  }
})
