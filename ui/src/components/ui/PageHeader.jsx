export default function PageHeader({ icon, title, subtitle, children }) {
  return (
    <div className="mb-6 flex items-center justify-between">
      <div>
        <h1 className="text-3xl font-bold text-sre-text mb-2 flex items-center gap-2">
          {icon ? (
            <span className="material-icons text-sre-text text-3xl">
              {icon}
            </span>
          ) : null}
          {title}
        </h1>
        <p className="text-sre-text-muted">{subtitle}</p>
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}
