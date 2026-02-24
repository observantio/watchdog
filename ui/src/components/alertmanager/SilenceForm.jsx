`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import  { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import { Button, Input, Select } from '../ui'
import HelpTooltip from '../HelpTooltip'
import { useAuth } from '../../contexts/AuthContext'
import { getGroups } from '../../api'

/**
 * SilenceForm component
 * @param {object} props - Component props
 */
export default function SilenceForm({ onSave, onCancel }) {
  const genId = () => Math.random().toString(36).slice(2, 9)
  const [matchers, setMatchers] = useState([{ id: genId(), name: '', value: '', isRegex: false, isEqual: true }])
  const [duration, setDuration] = useState('1')
  const [comment, setComment] = useState('')
  const [visibility, setVisibility] = useState('private')
  const [groups, setGroups] = useState([])
  const [selectedGroups, setSelectedGroups] = useState(new Set())

  useEffect(() => {
    loadGroups()
  }, [])

  const loadGroups = async () => {
    try {
      const groupsData = await getGroups()
      setGroups(groupsData)
    } catch {
      // Silently handle
    }
  }

  const toggleGroup = (groupId) => {
    const newGroups = new Set(selectedGroups)
    if (newGroups.has(groupId)) {
      newGroups.delete(groupId)
    } else {
      newGroups.add(groupId)
    }
    setSelectedGroups(newGroups)
  }

  const addMatcher = () => {
    setMatchers([...matchers, { id: genId(), name: '', value: '', isRegex: false, isEqual: true }])
  }

  const removeMatcher = (id) => {
    setMatchers(matchers.filter((m) => m.id !== id))
  }

  const updateMatcher = (id, field, value) => {
    setMatchers(matchers.map((m) => (m.id === id ? { ...m, [field]: value } : m)))
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const now = new Date()
    const endsAt = new Date(now.getTime() + Number(duration) * 60 * 60 * 1000)
    onSave({
      matchers,
      startsAt: now.toISOString(),
      endsAt: endsAt.toISOString(),
      comment,
      visibility,
      sharedGroupIds: visibility === 'group' ? Array.from(selectedGroups) : [],
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <label  htmlFor="matchers" className="text-sm font-semibold text-sre-text flex items-center gap-2">
          Matchers <HelpTooltip text="Define label matchers to specify which alerts should be silenced. Matchers work like filters." />
        </label>
        {matchers.map((matcher, index) => (
          <div key={matcher.id} className="flex gap-2 items-end">
            <Input
              label={index === 0 ? "Label" : ""}
              value={matcher.name}
              onChange={(e) => updateMatcher(matcher.id, 'name', e.target.value)}
              placeholder="label name"
              required
            />
            <Input
              label={index === 0 ? "Value" : ""}
              value={matcher.value}
              onChange={(e) => updateMatcher(matcher.id, 'value', e.target.value)}
              placeholder="label value"
              required
            />
            {matchers.length > 1 && (
              <Button type="button" variant="ghost" onClick={() => removeMatcher(matcher.id)}>
                <span className="material-icons text-sm">delete</span>
              </Button>
            )}
          </div>
        ))}
        <Button type="button" variant="ghost" onClick={addMatcher}>
          <span className="material-icons text-sm mr-2">add</span>{' '}
          Add Matcher
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-sre-text mb-2">
            Duration (hours) <HelpTooltip text="How long the silence should last in hours. Alerts matching the criteria will be suppressed for this duration." />
          </label>
          <Input
            type="number"
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            min="1"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-sre-text mb-2">
            Comment <HelpTooltip text="A description explaining why this silence was created." />
          </label>
          <Input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Reason for silence"
            required
          />
        </div>
      </div>

      <div className="border-t border-sre-border pt-4 space-y-3">
        <div>
          <label htmlFor="silence-visibility" className="block text-sm font-semibold text-sre-text mb-2 flex items-center gap-2">
            <span className="material-icons text-sm align-middle">visibility</span>
            Visibility <HelpTooltip text="Control who can view this silence. Private silences are only visible to you." />
          </label>
          <Select
            id="silence-visibility"
            value={visibility}
            onChange={(e) => {
              const newVisibility = e.target.value
              setVisibility(newVisibility)
              if (newVisibility !== 'group') {
                setSelectedGroups(new Set())
              }
            }}
          >
            <option value="private">Private - Only visible to me</option>
            <option value="group">Group - Share with specific groups</option>
            <option value="tenant">Public - Visible to all users in tenant</option>
          </Select>
          <p className="text-xs text-sre-text-muted mt-4">
            {visibility === 'private' && 'Only you can view and edit this silence'}
            {visibility === 'group' && 'Users in selected groups can view this silence'}
            {visibility === 'tenant' && 'All users in your organization can view this silence'}
          </p>
        </div>

        {visibility === 'group' && groups?.length > 0 && (
          <div>
            <label htmlFor="silence-groups" className="block text-sm font-medium text-sre-text mb-2">
              Share with Groups <HelpTooltip text="Select which user groups can view this silence." />
            </label>
            <div id="silence-groups" className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-48 overflow-y-auto p-2 border border-sre-border rounded bg-sre-surface">
              {groups.map((group) => (
                <label
                  key={group.id}
                  className="flex items-center gap-2 p-2 bg-sre-bg-alt rounded cursor-pointer hover:bg-sre-accent/10 transition-colors overflow-hidden"
                >
                  <input
                    type="checkbox"
                    checked={selectedGroups.has(group.id)}
                    onChange={() => toggleGroup(group.id)}
                    className="w-4 h-4"
                  />
                  <div className="flex-1 text-sm min-w-0">
                    {/* min-w-0 is needed on flex children to allow truncation */}
                    <div className="font-medium text-sre-text truncate w-full">{group.name}</div>
                    {group.description && (
                      <div className="text-xs text-sre-text-muted truncate w-full">{group.description}</div>
                    )}
                  </div>
                </label>
              ))}
            </div>
            <p className="text-xs text-sre-text-muted mt-2">
              {selectedGroups.size} group{selectedGroups.size === 1 ? '' : 's'} selected
            </p>
          </div>
        )}
      </div>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button type="submit">
          <span className="material-icons text-sm mr-2">volume_off</span>{' '}
          Create Silence
        </Button>
      </div>
    </form>
  )
}

SilenceForm.propTypes = {
  onSave: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
}
