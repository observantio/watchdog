import PropTypes from "prop-types";
import Section from "./Section";

function formatNumber(value, digits = 3) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return numeric.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function toDeploymentRows(deployments) {
  if (Array.isArray(deployments)) return deployments;
  if (Array.isArray(deployments?.items)) return deployments.items;
  if (Array.isArray(deployments?.events)) return deployments.events;
  return [];
}

function TableCard({ title, columns, rows, rowKey, renderRow, emptyText }) {
  return (
    <div className="border border-sre-border rounded-xl bg-sre-surface/20 overflow-hidden">
      <div className="px-3 py-2 border-b border-sre-border bg-sre-surface/40">
        <h4 className="text-sm font-semibold text-sre-text">{title}</h4>
      </div>
      {rows.length === 0 ? (
        <p className="p-4 text-xs text-sre-text-muted">{emptyText}</p>
      ) : (
        <div className="max-h-[280px] overflow-auto scrollbar-thin scrollbar-thumb-sre-border scrollbar-track-transparent">
          <table className="min-w-full text-left text-xs">
            <thead className="sticky top-0 bg-sre-surface/85 backdrop-blur-sm">
              <tr className="text-sre-text-muted uppercase tracking-wide">
                {columns.map((column) => (
                  <th key={column} className="px-3 py-2">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-sre-border/40">
              {rows.map((row, index) => (
                <tr
                  key={rowKey(row, index)}
                  className="hover:bg-sre-surface/35"
                >
                  {renderRow(row, index)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

TableCard.propTypes = {
  title: PropTypes.string.isRequired,
  columns: PropTypes.arrayOf(PropTypes.string).isRequired,
  rows: PropTypes.array.isRequired,
  rowKey: PropTypes.func.isRequired,
  renderRow: PropTypes.func.isRequired,
  emptyText: PropTypes.string.isRequired,
};

RcaCausalPanel.propTypes = {
  granger: PropTypes.object,
  bayesian: PropTypes.object,
  mlWeights: PropTypes.object,
  deployments: PropTypes.oneOfType([PropTypes.object, PropTypes.array]),
  compact: PropTypes.bool,
};

export default function RcaCausalPanel({
  granger,
  bayesian,
  mlWeights,
  deployments,
  compact = false,
}) {
  const grangerPairs = (
    granger?.causal_pairs ||
    granger?.warm_causal_pairs ||
    []
  )
    .slice()
    .sort(
      (left, right) => Number(right.strength || 0) - Number(left.strength || 0),
    );
  const posteriors = (bayesian?.posteriors || [])
    .slice()
    .sort(
      (left, right) =>
        Number(right.posterior || 0) - Number(left.posterior || 0),
    );
  const weightRows = Object.entries(mlWeights?.weights || {})
    .map(([signal, value]) => ({ signal, value: Number(value) }))
    .sort((left, right) => right.value - left.value);
  const deploymentItems = toDeploymentRows(deployments);

  const inner = (
    <>
      <h3 className="text-lg text-sre-text font-semibold mb-3">
        Causal and ML Insights
      </h3>
      <div
        className={
          compact
            ? "grid grid-cols-1 gap-3"
            : "grid grid-cols-1 xl:grid-cols-2 gap-3"
        }
      >
        <TableCard
          title={`Granger Causal Pairs (${grangerPairs.length})`}
          columns={["Cause", "Effect", "Strength"]}
          rows={grangerPairs}
          rowKey={(row, index) =>
            `${row.cause_metric || row.cause}-${row.effect_metric || row.effect}-${index}`
          }
          emptyText="No causal pairs returned in this range."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text">
                {row.cause_metric || row.cause || "-"}
              </td>
              <td className="px-3 py-2 text-sre-text">
                {row.effect_metric || row.effect || "-"}
              </td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">
                {formatNumber(row.strength, 4)}
              </td>
            </>
          )}
        />

        <TableCard
          title={`Bayesian Posterior Scores (${posteriors.length})`}
          columns={["Category", "Posterior", "Prior"]}
          rows={posteriors}
          rowKey={(row, index) => `${row.category}-${index}`}
          emptyText="No posterior probabilities returned."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text">{row.category || "-"}</td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">
                {formatNumber(row.posterior, 4)}
              </td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">
                {formatNumber(row.prior, 4)}
              </td>
            </>
          )}
        />

        <TableCard
          title={`Adaptive ML Weights (${weightRows.length})`}
          columns={["Signal", "Weight", "Distribution"]}
          rows={weightRows}
          rowKey={(row) => row.signal}
          emptyText="No ML weights available."
          renderRow={(row) => {
            const width = Math.max(6, Math.min(100, Math.abs(row.value) * 100));
            return (
              <>
                <td className="px-3 py-2 text-sre-text">{row.signal}</td>
                <td className="px-3 py-2 text-sre-text-muted font-mono">
                  {formatNumber(row.value, 4)}
                </td>
                <td className="px-3 py-2">
                  <div className="h-2 rounded-full bg-sre-border/40 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-sre-primary/80"
                      style={{ width: `${width}%` }}
                    />
                  </div>
                </td>
              </>
            );
          }}
        />

        <TableCard
          title={`Deployment Events (${deploymentItems.length})`}
          columns={["Service", "Version", "Timestamp"]}
          rows={deploymentItems}
          rowKey={(row, index) =>
            `${row.service || "service"}-${row.timestamp || "ts"}-${index}`
          }
          emptyText="No deployment events found for this scope."
          renderRow={(row) => (
            <>
              <td className="px-3 py-2 text-sre-text">{row.service || "-"}</td>
              <td className="px-3 py-2 text-sre-text-muted">
                {row.version || "-"}
              </td>
              <td className="px-3 py-2 text-sre-text-muted font-mono">
                {row.timestamp
                  ? new Date(Number(row.timestamp) * 1000).toLocaleString()
                  : "-"}
              </td>
            </>
          )}
        />
      </div>
    </>
  );

  if (compact) {
    return <div>{inner}</div>;
  }

  return <Section>{inner}</Section>;
}

RcaCausalPanel.propTypes = {
  granger: PropTypes.object,
  bayesian: PropTypes.object,
  mlWeights: PropTypes.object,
  deployments: PropTypes.oneOfType([PropTypes.array, PropTypes.object]),
  compact: PropTypes.bool,
};
