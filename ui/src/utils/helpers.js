`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`;
/**
 * Get log level information from log line
 * @param {string|object} line - Log line to analyze
 * @returns {{text: string, color: string, bgClass: string}} Log level info
 */

export function getLogLevel(line) {
  const lowerLine = (
    typeof line === "string" ? line : JSON.stringify(line)
  ).toLowerCase();

  if (lowerLine.includes("error") || lowerLine.includes("fatal")) {
    return {
      text: "ERROR",
      color: "text-red-400",
      bgClass: "bg-red-500/20 text-red-400 border-red-500/30",
    };
  }
  if (lowerLine.includes("warn")) {
    return {
      text: "WARN",
      color: "text-yellow-400",
      bgClass: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    };
  }
  if (lowerLine.includes("info")) {
    return {
      text: "INFO",
      color: "text-blue-400",
      bgClass: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    };
  }
  if (lowerLine.includes("debug")) {
    return {
      text: "DEBUG",
      color: "text-gray-400",
      bgClass: "bg-gray-500/20 text-gray-400 border-gray-500/30",
    };
  }

  return {
    text: "LOG",
    color: "text-sre-text",
    bgClass: "bg-sre-surface text-sre-text-muted border-sre-border",
  };
}

/**
 * Extract service name from span
 * @param {object} span - Span object
 * @returns {string} Service name
 */
export function getServiceName(span) {
  if (!span) return "unknown";
  if (span.serviceName) return span.serviceName;
  if (span.process?.serviceName) return span.process.serviceName;

  const tagKey = ["service.name", "service", "service_name"];
  const tagVal = getSpanAttribute(span, tagKey);
  if (tagVal != null) return String(tagVal);

  return "unknown";
}

/**
 * Get span attribute value
 * @param {object} span - Span object
 * @param {string} keys - Attribute key to look for
 * @returns {any} Attribute value or null
 */
function getFromAttributes(attrs, keys) {
  if (!attrs || typeof attrs !== "object") return null;
  for (const key of keys) {
    const val = attrs[key];
    if (val != null) return val;
  }
  return null;
}

function getFromTags(tags, keys) {
  if (Array.isArray(tags)) {
    for (const key of keys) {
      const tag = tags.find((t) => t?.key === key);
      if (tag?.value != null) return tag.value;
    }
    return null;
  }
  if (typeof tags === "object" && tags) {
    for (const key of keys) {
      const val = tags[key];
      if (val != null) return val;
    }
  }
  return null;
}

export function getSpanAttribute(span, keys) {
  if (!span || !keys) return null;
  const keyList = Array.isArray(keys) ? keys : [keys];

  const attrVal = getFromAttributes(span.attributes, keyList);
  if (attrVal != null) return attrVal;

  return getFromTags(span.tags, keyList);
}

/**
 * Calculate percentile of an array
 * @param {number[]} arr - Array of numbers
 * @param {number} p - Percentile (0-1)
 * @returns {number} Percentile value
 */
export function percentile(arr, p) {
  if (!arr.length) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  const idx = Math.min(
    sorted.length - 1,
    Math.max(0, Math.floor(sorted.length * p)),
  );
  return sorted[idx];
}

/**
 * Check if a trace span has an error status
 * @param {object} span - Span object
 * @returns {boolean} True if the span has an error
 */
export function hasSpanError(span) {
  return Boolean(
    span?.status?.code === "ERROR" ||
    (Array.isArray(span?.tags)
      ? span.tags.some((t) => t.key === "error" && t.value === true)
      : span?.tags?.error === true),
  );
}

/**
 * Deterministic color for a service name (hash-based)
 * @param {string} name - Service name
 * @param {boolean} hasError - Whether the span errored
 * @returns {string} Tailwind background class
 */
export function getSpanColorClass(name, hasError = false) {
  if (hasError) return "bg-red-500";
  const SERVICE_COLORS = [
    "bg-blue-500",
    "bg-green-500",
    "bg-purple-500",
    "bg-amber-500",
    "bg-cyan-500",
    "bg-pink-500",
    "bg-indigo-500",
    "bg-teal-500",
    "bg-orange-500",
    "bg-lime-500",
  ];
  let hash = 0;
  for (let i = 0; i < (name || "").length; i++) {
    hash = Math.trunc((hash << 5) - hash + name.codePointAt(i));
  }
  return SERVICE_COLORS[Math.abs(hash) % SERVICE_COLORS.length];
}

/**
 * Copy text to clipboard
 * @param {string} text - Text to copy
 * @returns {Promise<void>}
 */
export async function copyToClipboard(text) {
  try {
    if (typeof navigator !== "undefined" && navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to legacy copy path below.
  }

  try {
    const textarea = document.createElement("textarea");
    textarea.value = String(text ?? "");
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    const ok = document.execCommand("copy");
    textarea.remove();
    return Boolean(ok);
  } catch {
    return false;
  }
}

/**
 * Download data as JSON file
 * @param {any} data - Data to download
 * @param {string} filename - File name
 */
export function downloadJSON(data, filename = "data.json") {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  if (typeof URL?.createObjectURL !== "function") return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  if (typeof URL?.revokeObjectURL === "function") {
    URL.revokeObjectURL(url);
  }
}

/**
 * Download arbitrary text/binary as a file
 * @param {string|Blob} content
 * @param {string} filename
 * @param {string} type
 */
export function downloadFile(
  content,
  filename = "file.txt",
  type = "text/plain",
) {
  const blob =
    content instanceof Blob ? content : new Blob([content], { type });
  if (typeof URL?.createObjectURL !== "function") return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  if (typeof URL?.revokeObjectURL === "function") {
    URL.revokeObjectURL(url);
  }
}

/**
 * Debounce function
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in ms
 * @returns {Function} Debounced function
 */
export function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * Deep clone an object
 * @param {any} obj - Object to clone
 * @returns {any} Cloned object
 */
export function deepClone(obj) {
  try {
    return structuredClone(obj);
  } catch {
    return obj;
  }
}

/**
 * Check if value is empty
 * @param {any} value - Value to check
 * @returns {boolean} True if empty
 */
export function isEmpty(value) {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value).length === 0;
  return false;
}

/**
 * Generate unique ID
 * @returns {string} Unique ID
 */
export function generateId() {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
}
