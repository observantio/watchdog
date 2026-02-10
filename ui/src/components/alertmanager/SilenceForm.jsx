import  { useState, useEffect } from 'react'
import PropTypes from 'prop-types'
import { Button, Input } from '../ui'
import { useAuth } from '../../contexts/AuthContext'

/**
 * SilenceForm component
 * @param {object} props - Component props
 */
export default function SilenceForm({ onSave, onCancel }) {
  const { user } = useAuth()
  const genId = () => Math.random().toString(36).slice(2, 9)
  const [matchers, setMatchers] = useState([{ id: genId(), name: 'alertname', value: '', isRegex: false, isEqual: true }])
  const [duration, setDuration] = useState('1')
  const [comment, setComment] = useState('')
  const [createdBy, setCreatedBy] = useState('')

  useEffect(() => {
    if (user?.username) setCreatedBy(user.username)
  }, [user])

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
      createdBy,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <label  htmlFor="matchers" className="text-sm font-semibold text-sre-text">Matchers</label>
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
        <Input
          label="Duration (hours)"
          type="number"
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
          min="1"
          required
        />
        <Input
          label="Comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Reason for silence"
          required
        />
      </div>

      <div>
        <Input
          label="Created By"
          value={createdBy}
          onChange={(e) => setCreatedBy(e.target.value)}
          placeholder="Your name"
          required
        />
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
