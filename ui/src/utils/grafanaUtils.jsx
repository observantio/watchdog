import { DATASOURCE_TYPES as DS_TYPES } from "./constants";

export const GRAFANA_DATASOURCE_TYPES = DS_TYPES.filter((datasourceType) =>
  ["prometheus", "loki", "tempo"].includes(datasourceType.value),
).map((datasourceType) => {
  const icons = {
    prometheus: (
      <svg
        className="w-6 h-6"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
      >
        <rect x="3" y="11" width="4" height="10" rx="1" />
        <rect x="9" y="7" width="4" height="14" rx="1" />
        <rect x="15" y="3" width="4" height="18" rx="1" />
      </svg>
    ),
    loki: (
      <svg
        className="w-6 h-6"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
      >
        <path
          d="M3 7h18M3 12h18M3 17h18"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
    tempo: (
      <svg
        className="w-6 h-6"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
      >
        <circle cx="11" cy="11" r="6" strokeWidth="2" />
        <path d="M21 21l-4.3-4.3" strokeWidth="2" strokeLinecap="round" />
      </svg>
    ),
  };

  return { ...datasourceType, icon: icons[datasourceType.value] || null };
});

// Replace datasource references inside a Grafana `dashboard` object with the
// selected datasource UID. This updates panel-level `datasource`, target
// `datasource`/`datasourceUid`, and templating datasource variables.
export function overrideDashboardDatasource(
  dashboard,
  datasourceUid,
  availableDatasources = [],
  injectTemplating = true,
) {
  if (!dashboard || !datasourceUid) return dashboard;

  const dsObj = availableDatasources.find(
    (d) => String(d.uid) === String(datasourceUid),
  );
  const dsName = dsObj ? dsObj.name : String(datasourceUid);

  // deep clone to avoid mutating caller's object
  const out = JSON.parse(JSON.stringify(dashboard));

  // only create/modify templating when caller explicitly requests it
  if (injectTemplating) {
    if (!out.templating || typeof out.templating !== "object") {
      out.templating = {
        list: [
          {
            name: "ds_default",
            label: "Datasource",
            type: "datasource",
            current: { text: dsName, value: datasourceUid },
          },
        ],
      };
    }
  }

  function replaceInValue(val) {
    if (!val || typeof val !== "object") return;
    if (Array.isArray(val)) {
      val.forEach((v) => replaceInValue(v));
      return;
    }
    for (const key of Object.keys(val)) {
      const v = val[key];
      if (key === "datasource" || key === "datasourceUid") {
        if (typeof v === "string") {
          val[key] = datasourceUid;
        } else if (v && typeof v === "object") {
          if ("uid" in v) {
            // replace object with uid string for simplicity
            val[key] = datasourceUid;
          } else if ("value" in v) {
            val[key].value = datasourceUid;
          } else {
            val[key] = datasourceUid;
          }
        }
        continue;
      }

      if (key === "targets" && Array.isArray(v)) {
        // Ensure each target explicitly references the selected datasource when
        // possible (e.g. Prometheus `expr` targets). Also set panel-level
        // `datasource` if the panel doesn't have one.
        v.forEach((t) => {
          if (t && typeof t === "object") {
            const hasExplicitDs = "datasource" in t || "datasourceUid" in t;

            if (hasExplicitDs) {
              // set both string and uid forms
              if ("datasource" in t) t.datasource = datasourceUid;
              if ("datasourceUid" in t) t.datasourceUid = datasourceUid;
              // also support object form that some Grafana panels use
              if (typeof t.datasource === "object" && t.datasource !== null)
                t.datasource.uid = datasourceUid;
            } else {
              // Heuristic: common query target fields that imply a Prometheus/metric
              // panel — set string/uid forms so Grafana can persist them.
              if (t.expr || t.query || t.rawQuery || t.metric) {
                t.datasource = datasourceUid;
                t.datasourceUid = datasourceUid;
              }
            }

            replaceInValue(t);
          }
        });

        // If the parent panel object has targets but no datasource, assign the
        // selected datasource so Grafana will use it as the panel-level default.
        if (!("datasource" in val) && !("datasourceUid" in val)) {
          val.datasource = datasourceUid;
          val.datasourceUid = datasourceUid;
        }

        // Also ensure panel-level datasource may exist as an object with uid
        if (val.datasource && typeof val.datasource === "string") {
          // keep string form but also add object form for compatibility
          val.datasourceUid = val.datasourceUid || val.datasource;
        } else if (val.datasource && typeof val.datasource === "object") {
          val.datasourceUid =
            val.datasource.uid || val.datasourceUid || val.datasource;
        }

        continue;
      }

      if (key === "templating" && v && typeof v === "object") {
        if (!injectTemplating) {
          // caller chose not to inject templating vars; recurse but don't modify
          replaceInValue(v.list);
          continue;
        }

        const list = v.list || [];
        // update existing datasource templating vars
        let found = false;
        list.forEach((item) => {
          if (item && item.type === "datasource") {
            item.current = item.current || {};
            item.current.value = datasourceUid;
            item.current.text = dsName;
            found = true;
          }
        });
        if (!found) {
          // insert a default datasource var at the front
          v.list = [
            {
              name: "ds_default",
              label: "Datasource",
              type: "datasource",
              current: { text: dsName, value: datasourceUid },
            },
            ...(v.list || []),
          ];
        }
        replaceInValue(v.list);
        continue;
      }

      // Recurse into nested objects/arrays
      if (v && typeof v === "object") replaceInValue(v);
    }
  }

  replaceInValue(out);
  return out;
}

// Resolve a templating value (uid or friendly name) to a datasource UID using
// the provided list of available datasources. Returns empty string on no match.
export function resolveToUid(candidate, availableDatasources = []) {
  if (!candidate && candidate !== 0) return "";
  const raw =
    typeof candidate === "object" && candidate !== null
      ? candidate.value || candidate.text || ""
      : String(candidate);
  if (!raw) return "";
  const byUid = availableDatasources.find((d) => String(d.uid) === String(raw));
  if (byUid) return byUid.uid;
  const byName = availableDatasources.find(
    (d) => String(d.name) === String(raw),
  );
  if (byName) return byName.uid;
  return "";
}

// Infer the dashboard-level datasource: prefer a templating var (`ds_default`)
// if present, otherwise fall back to the most common panel/target datasource.
// Returns { uid, useTemplating }.
export function inferDashboardDatasource(dashboard, availableDatasources = []) {
  if (!dashboard) return { uid: "", useTemplating: false };

  const templ = dashboard?.templating || dashboard?.dashboard?.templating;
  const raw =
    templ?.list?.find((v) => v?.type === "datasource")?.current?.value || "";
  const templUid = resolveToUid(raw, availableDatasources) || raw || "";
  if (templUid) return { uid: templUid, useTemplating: Boolean(raw) };

  const primary = findPrimaryDatasourceUid(dashboard);
  const resolvedPrimary =
    resolveToUid(primary, availableDatasources) || primary || "";
  return { uid: resolvedPrimary, useTemplating: false };
}

// Find the most common datasource uid used across panel/target entries.
export function findPrimaryDatasourceUid(dashboard) {
  if (!dashboard) return "";
  const panels = dashboard.panels || dashboard.dashboard?.panels || [];
  const counts = {};
  const add = (uid) => {
    if (!uid) return;
    const s = String(uid);
    counts[s] = (counts[s] || 0) + 1;
  };

  for (const p of panels) {
    if (!p) continue;
    if (p.datasourceUid) add(p.datasourceUid);
    if (p.datasource && typeof p.datasource === "string") add(p.datasource);
    if (p.datasource && typeof p.datasource === "object" && p.datasource.uid)
      add(p.datasource.uid);
    const targets = p.targets || [];
    for (const t of targets) {
      if (!t) continue;
      if (t.datasourceUid) add(t.datasourceUid);
      if (t.datasource && typeof t.datasource === "string") add(t.datasource);
      if (t.datasource && typeof t.datasource === "object" && t.datasource.uid)
        add(t.datasource.uid);
    }
  }

  let best = "";
  let bestCount = 0;
  for (const [k, v] of Object.entries(counts)) {
    if (v > bestCount) {
      best = k;
      bestCount = v;
    }
  }
  return best;
}
