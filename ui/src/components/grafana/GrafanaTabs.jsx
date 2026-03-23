import PropTypes from "prop-types";

export default function GrafanaTabs({ activeTab, onChange }) {
  const tabs = [
    {
      id: "dashboards",
      label: "Dashboards",
      icon: (
        <svg
          className="w-4 h-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
        >
          <path
            d="M3 13h8V3H3v10zm0 8h8v-6H3v6zM13 21h8V11h-8v10zM13 3v6h8V3h-8z"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      ),
    },
    {
      id: "datasources",
      label: "Datasources",
      icon: (
        <svg
          className="w-4 h-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
        >
          <path
            d="M6 3h12v4H6zM6 21h12v-4H6zM3 8h18v8H3z"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      ),
    },
    {
      id: "folders",
      label: "Folders",
      icon: (
        <svg
          className="w-4 h-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
        >
          <path
            d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      ),
    },
  ];

  return (
    <div className="grafana-main-tabs flex gap-2 mb-6 border-b border-sre-border justify-center items-center">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`pl-4 pr-4 py-2 font-medium text-sm transition-colors relative flex items-center gap-2 ${
            activeTab === tab.id
              ? "text-sre-primary border-b-2 border-sre-primary"
              : "text-sre-text-muted hover:text-sre-text"
          }`}
        >
          <span className="flex items-center">{tab.icon}</span>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

GrafanaTabs.propTypes = {
  activeTab: PropTypes.string.isRequired,
  onChange: PropTypes.func.isRequired,
};
