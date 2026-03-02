import React from "react";
import PropTypes from "prop-types";
/**
 * ServiceGraph component
 * @param {object} props - Component props
 * @param {Array} props.traces - Array of trace objects
 */
export default function ServiceGraph(props) {
  const ServiceGraphAsync = React.lazy(() => import("./ServiceGraphAsync"));
  return (
    <React.Suspense
      fallback={
        <div className="p-6 text-center text-sre-text-muted">
          Loading service graph…
        </div>
      }
    >
      <ServiceGraphAsync {...props} />
    </React.Suspense>
  );
}

ServiceGraph.propTypes = {
  traces: PropTypes.arrayOf(PropTypes.object).isRequired,
};
