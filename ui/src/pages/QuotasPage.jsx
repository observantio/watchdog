import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import PageHeader from "../components/ui/PageHeader";
import { Card, Button, Spinner, Badge, Select } from "../components/ui";
import { getSystemQuotas } from "../api";
import { useToast } from "../contexts/ToastContext";
import { useAuth } from "../contexts/AuthContext";

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  const n = Number(value);
  return Number.isInteger(n) ? `${n}` : n.toFixed(2);
}

function sourceBadge(source) {
  if (source === "native") return "success";
  if (source === "prometheus") return "info";
  return "default";
}

function sourceLabel(source) {
  if (source === "native") return "native";
  if (source === "prometheus") return "prometheus";
  return "runtime";
}

function statusBadge(status) {
  if (status === "ok") return "success";
  if (status === "degraded") return "warning";
  return "error";
}

function quotaMessage(quota) {
  const status = quota?.status || "unavailable";
  if (status === "ok") return "";
  if (status === "degraded") {
    if (quota?.message) return String(quota.message);
    if (quota?.limit !== null && quota?.limit !== undefined) {
      return "Limit is available, but current usage is not provided by upstream.";
    }
    if (quota?.used !== null && quota?.used !== undefined) {
      return "Current usage is available, but upstream did not provide a limit.";
    }
    return "Partial quota data available. Some upstream fields are missing.";
  }
  return (
    String(quota?.message || "").trim() ||
    "Quota data is currently unavailable from upstream for this scope."
  );
}

function QuotaRow({ label, quota }) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-sm font-semibold text-sre-text">{label}</div>
          <div className="mt-1 text-xs text-sre-text-muted">
            Used {formatNumber(quota?.used)} / Limit {formatNumber(quota?.limit)}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={sourceBadge(quota?.source)}>
            {sourceLabel(quota?.source)}
          </Badge>
          <Badge variant={statusBadge(quota?.status)}>{quota?.status || "unavailable"}</Badge>
        </div>
      </div>
      <div className="mt-2 text-xs text-sre-text-muted">
        Remaining: {formatNumber(quota?.remaining)}
      </div>
      {!!quotaMessage(quota) && (
        <div className="mt-2 text-xs text-sre-text-muted">{quotaMessage(quota)}</div>
      )}
    </Card>
  );
}

export default function QuotasPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [quotas, setQuotas] = useState(null);
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const lastLoadedOrgRef = useRef("");

  const apiKeyOptions = useMemo(
    () =>
      (user?.api_keys || [])
        .filter((k) => (!k.is_shared || k.can_use) && !k.is_hidden)
        .map((k) => ({
          id: k.id,
          name: k.name,
          orgId: k.key,
          isEnabled: k.is_enabled,
        })),
    [user?.api_keys],
  );

  useEffect(() => {
    if (!selectedOrgId) {
      const enabled = apiKeyOptions.find((k) => k.isEnabled);
      setSelectedOrgId(enabled?.orgId || user?.org_id || "");
    }
  }, [apiKeyOptions, selectedOrgId, user?.org_id]);

  const loadQuotas = useCallback(async () => {
    if (!selectedOrgId) return;
    if (lastLoadedOrgRef.current === selectedOrgId) return;
    setLoading(true);
    try {
      const data = await getSystemQuotas(selectedOrgId);
      setQuotas(data || null);
      lastLoadedOrgRef.current = selectedOrgId;
    } catch (err) {
      setQuotas(null);
      toast.error(err?.body?.detail || err?.message || "Failed to load quotas");
    } finally {
      setLoading(false);
    }
  }, [selectedOrgId, toast]);

  useEffect(() => {
    loadQuotas();
  }, [loadQuotas]);

  const handleRefresh = useCallback(async () => {
    if (!selectedOrgId) return;
    lastLoadedOrgRef.current = "";
    await loadQuotas();
  }, [loadQuotas, selectedOrgId]);

  const apiKeys = useMemo(() => quotas?.api_keys || null, [quotas]);
  const apiKeyMax = Math.max(0, Number(apiKeys?.max || 0));
  const apiKeyUsed = Math.max(
    0,
    Math.min(apiKeyMax, Number(apiKeys?.current || 0)),
  );
  const apiKeySlots = useMemo(
    () =>
      Array.from({ length: apiKeyMax }, (_, idx) => ({
        index: idx,
        used: idx < apiKeyUsed,
      })),
    [apiKeyMax, apiKeyUsed],
  );

  return (
    <div className="animate-fade-in max-w-7xl mx-auto">
      <PageHeader
        icon="data_thresholding"
        title="Quotas"
        subtitle="Track runtime service quotas and API key capacity for your current tenant scope."
      />

      <div className="space-y-4">
        <Card className="p-4">
          <div className="grid grid-cols-1 gap-3">
            <div>
              <div className="mb-1 text-xs font-medium text-sre-text-muted uppercase tracking-wide">
                API Key Scope
              </div>
              <Select
                value={selectedOrgId}
                onChange={(e) => setSelectedOrgId(e.target.value)}
                className="w-full"
              >
                {apiKeyOptions.map((k) => (
                  <option key={k.id} value={k.orgId}>
                    {k.name} ({k.orgId})
                  </option>
                ))}
              </Select>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-sre-text">API Keys</div>
              <div className="mt-1 text-xs text-sre-text-muted">
                Current {formatNumber(apiKeys?.current)} / Max {formatNumber(apiKeys?.max)}
              </div>
            </div>
            <Badge variant={statusBadge(apiKeys?.status)}>{apiKeys?.status || "ok"}</Badge>
          </div>
          <div className="mt-3 grid grid-cols-5 gap-2 sm:grid-cols-10">
            {apiKeySlots.map((slot) => (
              <div
                key={slot.index}
                className={`flex h-9 items-center justify-center rounded-md border ${
                  slot.used
                    ? "border-sre-primary/70 bg-sre-primary/10 text-sre-primary"
                    : "border-sre-border bg-transparent text-sre-text-muted/60"
                }`}
                aria-label={slot.used ? "Used API key slot" : "Available API key slot"}
              >
                {slot.used ? (
                  <span className="material-icons text-base">key</span>
                ) : (
                  <span className="text-xs"> </span>
                )}
              </div>
            ))}
          </div>
          <div className="mt-2 text-xs text-sre-text-muted">
            Remaining: {formatNumber(apiKeys?.remaining)}
          </div>
        </Card>

        {loading ? (
          <Card className="p-8">
            <div className="flex items-center justify-center gap-3 text-sre-text-muted">
              <Spinner size="md" />
              Loading quotas...
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <QuotaRow label="Loki Tenant Quota" quota={quotas?.loki || {}} />
            <QuotaRow label="Tempo Tenant Quota" quota={quotas?.tempo || {}} />
          </div>
        )}

        <div className="flex justify-end">
          <Button size="sm" variant="secondary" onClick={handleRefresh} disabled={loading || !selectedOrgId}>
            Refresh
          </Button>
        </div>
      </div>
    </div>
  );
}
