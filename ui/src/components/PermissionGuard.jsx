import PropTypes from "prop-types";
import { useAuth } from "../contexts/AuthContext";

export default function PermissionGuard({
  any = [],
  all = [],
  children,
  fallback = null,
}) {
  const { hasPermission } = useAuth();

  if (all?.length > 0) {
    const ok = all.every((p) => hasPermission(p));
    if (!ok) return fallback;
    return children;
  }

  if (any?.length > 0) {
    const ok = any.some((p) => hasPermission(p));
    if (!ok) return fallback;
    return children;
  }

  return children;
}

PermissionGuard.propTypes = {
  any: PropTypes.arrayOf(PropTypes.string),
  all: PropTypes.arrayOf(PropTypes.string),
  children: PropTypes.node,
  fallback: PropTypes.node,
};
