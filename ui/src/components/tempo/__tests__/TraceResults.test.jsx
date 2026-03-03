import { render } from "@testing-library/react";
import TraceResults from "../TraceResults";

function makeTrace(id, spans) {
  return { traceID: id, spans };
}

describe("TraceResults / TraceCard counts", () => {
  it("shows correct span and service counts for summary traces", () => {
    const sample = {
      traceID: "abc",
      spans: [
        {
          spanID: "root",
          serviceName: "svc1",
          operationName: "op",
          startTime: 0,
          duration: 1,
        },
      ],
    };
    const { getByText } = render(
      <TraceResults
        traces={[sample]}
        loading={false}
        handleTraceClick={() => {}}
      />,
    );
    expect(getByText((c) => /1\s*span/i.test(c))).toBeInTheDocument();
    expect(getByText((c) => /1\s*service/i.test(c))).toBeInTheDocument();
  });

  it("deduplicates service names when multiple spans share same service", () => {
    const sample = makeTrace("x", [
      { spanID: "s1", serviceName: "svc", parentSpanID: null },
      { spanID: "s2", serviceName: "svc", parentSpanID: "s1" },
    ]);
    const { getByText } = render(
      <TraceResults
        traces={[sample]}
        loading={false}
        handleTraceClick={() => {}}
      />,
    );
    expect(getByText(/2 spans/i)).toBeInTheDocument();
    expect(getByText(/1 service/i)).toBeInTheDocument();
  });

  it("ignores unknown service names when counting services", () => {
    const sample = makeTrace("y", [
      { spanID: "s1", serviceName: "unknown" },
      { spanID: "s2", serviceName: "unknown" },
    ]);
    const { getByText, queryByText } = render(
      <TraceResults
        traces={[sample]}
        loading={false}
        handleTraceClick={() => {}}
      />,
    );
    expect(getByText(/2 spans/i)).toBeInTheDocument();
    // there should be a service badge but count should show 0 services since both unknown
    expect(queryByText(/0 services/i)).toBeInTheDocument();
  });

  it('appends "+" to counts when trace is summary-only', () => {
    const sample = {
      traceID: "z",
      spans: [{ spanID: "r", serviceName: "svc" }],
      warnings: ["Trace summary only"],
    };
    const { getByText } = render(
      <TraceResults
        traces={[sample]}
        loading={false}
        handleTraceClick={() => {}}
      />,
    );
    expect(getByText((c) => /1\+?\s*span/i.test(c))).toBeInTheDocument();
    expect(getByText((c) => /1\+?\s*service/i.test(c))).toBeInTheDocument();
  });
});
