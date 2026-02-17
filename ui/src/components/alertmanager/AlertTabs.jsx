`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import PropTypes from 'prop-types'

export default function AlertTabs({ activeTab, onChange }) {
  const tabs = [
    { key: 'alerts', label: 'Alerts', icon: 'notification_important' },
    { key: 'rules', label: 'Rules', icon: 'rule' },
    { key: 'channels', label: 'Channels', icon: 'send' },
    { key: 'silences', label: 'Silences', icon: 'volume_off' },
  ]

  return (
    <div className="mb-6 flex gap-2 border-b border-sre-border">
      {tabs.map(tab => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={`px-4 py-2 flex items-center gap-2 border-b-2 transition-colors ${
            activeTab === tab.key ? 'border-sre-primary text-sre-primary' : 'border-transparent text-sre-text-muted hover:text-sre-text'
          }`}
        >
          <span className="material-icons text-sm">{tab.icon}</span>
          {tab.label}
        </button>
      ))}
    </div>
  )
}

AlertTabs.propTypes = {
  activeTab: PropTypes.string.isRequired,
  onChange: PropTypes.func.isRequired,
}
