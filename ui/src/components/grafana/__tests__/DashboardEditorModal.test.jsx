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
})
