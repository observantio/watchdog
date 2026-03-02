import { describe, expect, it } from "vitest";
import {
  buildFallbackVolume,
  buildSelectorFromFilters,
  computeTopTermsFromResult,
  getVolumeValues,
  normalizeLabelValue,
  normalizeLabelValues,
} from "../lokiQueryUtils";

describe("lokiQueryUtils", () => {
  it("normalizes label values from selectors and raw text", () => {
    expect(normalizeLabelValue("service", 'service="api"')).toBe("api");
    expect(normalizeLabelValue("service", 'api",level="error"')).toBe("api");
  });

  it("deduplicates and sorts label values", () => {
    const values = normalizeLabelValues("service", [
      'service="api"',
      'service="web"',
      'service="api"',
    ]);
    expect(values).toEqual(["api", "web"]);
  });

  it("computes top terms with fallback and extracts volumes", () => {
    const result = {
      data: {
        result: [
          { values: [["1", '{"message":"error timeout"}']] },
          { stream: { service: "api" }, values: [] },
        ],
      },
    };
    const terms = computeTopTermsFromResult(result, 5);
    expect(terms.length).toBeGreaterThan(0);

    const volume = getVolumeValues({
      data: {
        result: [
          {
            values: [
              ["1", "3"],
              ["2", "4"],
            ],
          },
        ],
      },
    });
    expect(volume).toEqual([3, 4]);
  });

  it("builds selectors and fallback volume buckets", () => {
    expect(buildSelectorFromFilters([], "service")).toBe('{service=~".+"}');
    expect(buildSelectorFromFilters([{ label: "service", value: "api" }])).toBe(
      '{service="api"}',
    );

    const fallback = buildFallbackVolume(
      { data: { result: [{ values: [["1000000000", "1"]] }] } },
      0,
    );
    expect(Array.isArray(fallback)).toBe(true);
    expect(fallback.length).toBeGreaterThan(0);
  });
});
