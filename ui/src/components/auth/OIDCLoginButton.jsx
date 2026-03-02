import PropTypes from "prop-types";
import { Button } from "../ui";

export default function OIDCLoginButton({
  loading,
  onClick,
  providerLabel = "Single Sign-On",
}) {
  return (
    <Button
      type="button"
      variant="secondary"
      className="w-full"
      loading={loading}
      onClick={onClick}
    >
      {loading ? "Redirecting..." : `Continue with ${providerLabel}`}
    </Button>
  );
}

OIDCLoginButton.propTypes = {
  loading: PropTypes.bool,
  onClick: PropTypes.func.isRequired,
  providerLabel: PropTypes.string,
};
