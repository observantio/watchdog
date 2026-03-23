import native from "./native.json";
import linux from "./linux.json";
import windows from "./windows.json";

const DASHBOARDS = [native, linux, windows];

const PROMQL_KEYWORDS = new Set([
  "and",
  "bool",
  "by",
  "group_left",
  "group_right",
  "ignoring",
  "offset",
  "on",
  "or",
  "unless",
  "without",
]);

const PROMQL_FUNCTIONS = new Set([
  "abs",
  "absent",
  "absent_over_time",
  "avg",
  "avg_over_time",
  "ceil",
  "changes",
  "clamp",
  "clamp_max",
  "clamp_min",
  "count",
  "count_over_time",
  "day_of_month",
  "day_of_week",
  "day_of_year",
  "delta",
  "deriv",
  "exp",
  "floor",
  "histogram_quantile",
  "holt_winters",
  "hour",
  "idelta",
  "increase",
  "irate",
  "label_join",
  "label_replace",
  "ln",
  "log10",
  "log2",
  "max",
  "max_over_time",
  "min",
  "min_over_time",
  "minute",
  "month",
  "predict_linear",
  "quantile",
  "quantile_over_time",
  "rate",
  "resets",
  "round",
  "scalar",
  "sort",
  "sort_desc",
  "sqrt",
  "stddev",
  "stddev_over_time",
  "stdvar",
  "stdvar_over_time",
  "sum",
  "sum_over_time",
  "time",
  "timestamp",
  "topk",
  "vector",
  "year",
]);

function walkDashboardTargets(node, expressions) {
  if (!node) return;
  if (Array.isArray(node)) {
    node.forEach((item) => walkDashboardTargets(item, expressions));
    return;
  }
  if (typeof node !== "object") return;

  if (typeof node.expr === "string") expressions.push(node.expr);
  if (typeof node.query === "string") expressions.push(node.query);
  if (typeof node.rawQuery === "string") expressions.push(node.rawQuery);

  if (Array.isArray(node.panels)) {
    node.panels.forEach((panel) => walkDashboardTargets(panel, expressions));
  }
  if (Array.isArray(node.targets)) {
    node.targets.forEach((target) => walkDashboardTargets(target, expressions));
  }
}

function nextNonWhitespace(text, startIndex) {
  for (let i = startIndex; i < text.length; i += 1) {
    if (!/\s/.test(text[i])) return text[i];
  }
  return "";
}

function prevNonWhitespace(text, startIndex) {
  for (let i = startIndex; i >= 0; i -= 1) {
    if (!/\s/.test(text[i])) return text[i];
  }
  return "";
}

function previousIdentifier(text, startIndex) {
  let end = startIndex;
  while (end >= 0 && /\s/.test(text[end])) end -= 1;
  let begin = end;
  while (begin >= 0 && /[a-zA-Z_]/.test(text[begin])) begin -= 1;
  return text.slice(begin + 1, end + 1);
}

function isLikelyMetricToken(expr, token, tokenIndex) {
  if (!token) return false;
  if (PROMQL_KEYWORDS.has(token) || PROMQL_FUNCTIONS.has(token)) return false;
  if (/^(true|false)$/i.test(token)) return false;

  const prev = prevNonWhitespace(expr, tokenIndex - 1);
  const next = nextNonWhitespace(expr, tokenIndex + token.length);
  const after = expr.slice(tokenIndex + token.length);

  if (/^\s*(=~|!~|!=|=)/.test(after)) return false;
  if (next === "(") return false;
  if (prev === ".") return false;
  if (prev === "(" && ["by", "without", "on", "ignoring"].includes(previousIdentifier(expr, tokenIndex - 2))) {
    return false;
  }

  return ["", "{", "[", ")", ",", "+", "-", "*", "/", "%", "^", ">", "<", "=", "!", "}", "]"].includes(next);
}

export function extractMetricNamesFromPromQl(expr) {
  if (!expr || typeof expr !== "string") return [];

  const re = /\b[a-zA-Z_:][a-zA-Z0-9_:]*\b/g;
  const found = new Set();
  let match = re.exec(expr);

  while (match) {
    const token = match[0];
    if (isLikelyMetricToken(expr, token, match.index)) {
      found.add(token);
    }
    match = re.exec(expr);
  }

  return Array.from(found);
}

export function collectDashboardMetricNames(dashboard) {
  const expressions = [];
  walkDashboardTargets(dashboard, expressions);

  const metrics = new Set();
  expressions.forEach((expr) => {
    extractMetricNamesFromPromQl(expr).forEach((metric) => metrics.add(metric));
  });

  return Array.from(metrics).sort((a, b) => a.localeCompare(b));
}

function toAnomalyFriendlyQuery(metric) {
  if (/_total$|_count$|_sum$|_bucket$/.test(metric)) {
    return `sum(rate(${metric}[5m]))`;
  }
  return metric;
}

export function mergeMetricQueries(existingQueries = [], additionalQueries = []) {
  const merged = [];
  const seen = new Set();

  [...existingQueries, ...additionalQueries].forEach((query) => {
    const normalized = String(query || "").trim();
    if (!normalized || seen.has(normalized)) return;
    seen.add(normalized);
    merged.push(normalized);
  });

  return merged;
}

export const ALL_DASHBOARD_METRICS = Array.from(
  DASHBOARDS.reduce((acc, dashboard) => {
    collectDashboardMetricNames(dashboard).forEach((metric) => acc.add(metric));
    return acc;
  }, new Set()),
).sort((a, b) => a.localeCompare(b));

export const RCA_DEFAULT_METRIC_QUERIES_FROM_DASHBOARDS = ALL_DASHBOARD_METRICS.map(
  (metric) => toAnomalyFriendlyQuery(metric),
);
