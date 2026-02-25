import PropTypes from 'prop-types'

export default function RuleEditorTabs({ activeTab, onChange }) {
  const tabs = [
    { key: 'basic', label: 'Basic', icon: 'settings' },
    { key: 'condition', label: 'Condition', icon: 'functions' },
    { key: 'details', label: 'Details', icon: 'description' },
    { key: 'advanced', label: 'Advanced', icon: 'tune' },
  ]

  return (
    <div className="mb-6 flex gap-2 border-b border-sre-border justify-start">
      {tabs.map(tab => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={`pl-0 pr-4 py-2 flex items-center gap-2 border-b-2 transition-colors ${
            activeTab === tab.key
              ? 'border-sre-primary text-sre-primary'
              : 'border-transparent text-sre-text-muted hover:text-sre-text'
          }`}
        >
          <span className="material-icons text-sm">{tab.icon}</span>
          {tab.label}
        </button>
      ))}
    </div>
  )
}

RuleEditorTabs.propTypes = {
  activeTab: PropTypes.string.isRequired,
  onChange: PropTypes.func.isRequired,
}