`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import DashboardEditorModal from '../DashboardEditorModal'

describe('DashboardEditorModal — JSON sample loader', () => {
  it('loads the Mimir sample JSON and sets datasource + templating', () => {
    const setDashboardForm = vi.fn()
    const setJsonContent = vi.fn()

    render(
      <DashboardEditorModal
        isOpen
        onClose={() => {}}
        editingDashboard={null}
        dashboardForm={{ title: '', tags: '', folderId: 0, refresh: '30s', datasourceUid: '', useTemplating: false, visibility: 'private', sharedGroupIds: [] }}
        setDashboardForm={setDashboardForm}
        editorTab="json"
        setEditorTab={() => {}}
        jsonContent={''}
        setJsonContent={setJsonContent}
        jsonError={''}
        setJsonError={() => {}}
        fileUploaded={false}
        setFileUploaded={() => {}}
        folders={[]}
        datasources={[{ uid: 'mimir-prometheus', name: 'Mimir', type: 'prometheus' }]}
        groups={[]}
        onSave={() => {}}
      />
    )

    const btn = screen.getByTestId('load-mimir-sample')
    fireEvent.click(btn)

    expect(setJsonContent).toHaveBeenCalled()
    expect(setDashboardForm).toHaveBeenCalledWith(expect.objectContaining({ datasourceUid: 'mimir-prometheus', useTemplating: true }))
  })

  it('prompts when saving from form if JSON exists and supports merge/override', async () => {
    const setDashboardForm = vi.fn()
    const setJsonContent = vi.fn()
    const onSave = vi.fn()

    render(
      <DashboardEditorModal
        isOpen
        onClose={() => {}}
        editingDashboard={null}
        dashboardForm={{ title: 'Form Title', tags: 'a,b', folderId: 0, refresh: '30s', datasourceUid: '', useTemplating: false, visibility: 'private', sharedGroupIds: [] }}
        setDashboardForm={setDashboardForm}
        editorTab="form"
        setEditorTab={() => {}}
        jsonContent={'{"title":"Original JSON","panels":[{"id":1}] }'}
        setJsonContent={setJsonContent}
        jsonError={''}
        setJsonError={() => {}}
        fileUploaded={false}
        setFileUploaded={() => {}}
        folders={[]}
        datasources={[{ uid: 'mimir-prometheus', name: 'Mimir', type: 'prometheus' }]}
        groups={[]}
        onSave={onSave}
      />
    )

    const saveBtn = screen.getByText('Create Dashboard')
    fireEvent.click(saveBtn)

    // prompt should appear
    expect(screen.getByText('JSON content detected')).toBeInTheDocument()

    // merge option
    const mergeBtn = screen.getByTestId('json-conflict-merge')
    fireEvent.click(mergeBtn)
    // should have updated json content via setJsonContent
    expect(setJsonContent).toHaveBeenCalled()
    // modal should request parent save with merged JSON
    expect(onSave).toHaveBeenCalled()
    const mergedArg = onSave.mock.calls[0][0]
    const mergedObj = JSON.parse(mergedArg)
    expect(mergedObj.title).toBe('Form Title')
    expect(Array.isArray(mergedObj.panels)).toBe(true)
    expect(mergedObj.panels[0].id).toBe(1)

    // override option
    fireEvent.click(saveBtn)
    const overrideBtn = screen.getByTestId('json-conflict-override')
    fireEvent.click(overrideBtn)
    expect(setJsonContent).toHaveBeenCalled()
    // override should also request parent save with the new JSON
    expect(onSave.mock.calls.length).toBeGreaterThanOrEqual(2)
    const overrideArg = onSave.mock.calls[1][0]
    const overrideObj = JSON.parse(overrideArg)
    expect(overrideObj.title).toBe('Form Title')
    expect(Array.isArray(overrideObj.panels)).toBe(true)
    expect(overrideObj.panels.length).toBe(0)

    // cancel option hides the prompt
    fireEvent.click(saveBtn)
    const cancelBtn = screen.getByTestId('json-conflict-cancel')
    fireEvent.click(cancelBtn)
    expect(screen.queryByText('JSON content detected')).not.toBeInTheDocument()
  })
})
