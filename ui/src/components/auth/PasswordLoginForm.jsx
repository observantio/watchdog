import PropTypes from 'prop-types'
import { Button, Input } from '../ui'

export default function PasswordLoginForm({
  username,
  password,
  onUsernameChange,
  onPasswordChange,
  onSubmit,
  loading,
  disabled,
}) {
  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <label htmlFor="username" className="block text-sm font-medium text-sre-text mb-1">
          Username
        </label>
        <Input
          id="username"
          type="text"
          value={username}
          onChange={(e) => onUsernameChange(e.target.value.toLowerCase())}
          placeholder="Enter your username"
          required
          autoFocus
          autoComplete="username"
          disabled={disabled}
        />
      </div>

      <div>
        <label htmlFor="password" className="block text-sm font-medium text-sre-text mb-1">
          Password
        </label>
        <Input
          id="password"
          type="password"
          value={password}
          onChange={(e) => onPasswordChange(e.target.value)}
          placeholder="Enter your password"
          required
          autoComplete="current-password"
          disabled={disabled}
        />
      </div>

      <Button
        type="submit"
        variant="primary"
        className="w-full"
        loading={loading}
        disabled={disabled}
      >
        {loading ? 'Signing in...' : 'Sign In'}
      </Button>
    </form>
  )
}

PasswordLoginForm.propTypes = {
  username: PropTypes.string.isRequired,
  password: PropTypes.string.isRequired,
  onUsernameChange: PropTypes.func.isRequired,
  onPasswordChange: PropTypes.func.isRequired,
  onSubmit: PropTypes.func.isRequired,
  loading: PropTypes.bool,
  disabled: PropTypes.bool,
}
