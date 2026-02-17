`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

export default function PageHeader({ icon, title, subtitle, children }) {
  return (
    <div className="mb-6 flex items-center justify-between">
      <div>
        <h1 className="text-3xl font-bold text-sre-text mb-2 flex items-center gap-2">
          <span className="material-icons text-sre-primary text-3xl">{icon}</span>
          {title}
        </h1>
        <p className="text-sre-text-muted">{subtitle}</p>
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  )
}