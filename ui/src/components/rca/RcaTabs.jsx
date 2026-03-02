import PropTypes from "prop-types";

// A simple tab list component.  The parent is responsible for storing
// activeTab and handling onChange events.  "tabs" is an array of objects
// with { key, label, [icon] }.  If `sticky` is true we apply the same styles
// that RCAPage used previously (top sticky background) and any additional
// `className` is merged.
export default function RcaTabs({
  tabs,
  activeTab,
  onChange,
  sticky = false,
  className = "",
}) {
  const base = "flex flex-wrap gap-2 mb-4 py-2";
  const stickyCls = sticky ? "sticky top-0 z-20 bg-sre-bg-card" : "";

  return (
    <div className={`${base} ${stickyCls} ${className}`} role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={activeTab === tab.key}
          onClick={() => onChange(tab.key)}
          className={`px-2 py-2 rounded-none text-xs transition focus:outline-none focus:ring-2 focus:ring-sre-primary ${
            activeTab === tab.key
              ? "border-sre-primary bg-sre-primary/20 text-sre-primary"
              : "border-sre-border text-sre-text-muted hover:text-sre-text hover:bg-sre-surface/40"
          }`}
        >
          {tab.icon && (
            <span className="flex items-center mr-1">{tab.icon}</span>
          )}
          {tab.label}
        </button>
      ))}
    </div>
  );
}

RcaTabs.propTypes = {
  tabs: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      icon: PropTypes.node,
    }),
  ).isRequired,
  activeTab: PropTypes.string.isRequired,
  onChange: PropTypes.func.isRequired,
  sticky: PropTypes.bool,
  className: PropTypes.string,
};
