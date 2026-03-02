import PropTypes from "prop-types";
import { Card, Input, Button } from "../ui";

export default function RcaLookup({ value, onChange, onFind, onClear, error }) {
  return (
    <Card className="min-h-[180px]">
      <p className="text-sm text-sre-text font-semibold mb-2">
        Find by Report ID
      </p>
      <p className="text-xs text-sre-text-muted mb-3">
        Enter a report UUID to open a persisted report in your tenant.
      </p>
      <div className="space-y-3">
        <Input
          placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
          value={value}
          onChange={onChange}
        />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={onFind}>
            Find Report
          </Button>
          <Button size="sm" variant="secondary" onClick={onClear}>
            Clear
          </Button>
        </div>
        {error && <p className="text-xs text-sre-error">{error}</p>}
      </div>
    </Card>
  );
}

RcaLookup.propTypes = {
  value: PropTypes.string.isRequired,
  onChange: PropTypes.func.isRequired,
  onFind: PropTypes.func.isRequired,
  onClear: PropTypes.func.isRequired,
  error: PropTypes.string,
};
