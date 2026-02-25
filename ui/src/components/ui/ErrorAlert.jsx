import { Alert } from '../ui'

export default function ErrorAlert({ error, onClose }) {
  if (!error) return null
  return (
    <Alert variant="error" className="mb-6" onClose={onClose}>
      <strong>Error:</strong> {error}
    </Alert>
  )
}