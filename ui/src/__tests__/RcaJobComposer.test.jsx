import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RcaJobComposer from "../components/rca/RcaJobComposer";


describe("RcaJobComposer", () => {
  it("submits only window, resolution, and uploaded YAML", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    const onDownloadTemplate = vi.fn().mockResolvedValue({
      template_yaml: "version: 1\n",
      file_name: "becertain-rca-defaults.yaml",
    });
    const file = new File(["version: 1\nsettings:\n  mad_threshold: 8.0\n"], "rca.yaml", {
      type: "application/x-yaml",
    });
    file.text = vi.fn(async () => "version: 1\nsettings:\n  mad_threshold: 8.0\n");

    render(
      <RcaJobComposer
        onCreate={onCreate}
        onDownloadTemplate={onDownloadTemplate}
        creating={false}
      />,
    );

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "15" },
    });
    fireEvent.change(screen.getByDisplayValue("15s"), {
      target: { value: "30s" },
    });
    fireEvent.change(document.querySelector('input[type="file"]'), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate Report" }));

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    const payload = onCreate.mock.calls[0][0];

    expect(payload.step).toBe("30s");
    expect(payload.config_yaml).toContain("mad_threshold: 8.0");
    expect(payload).not.toHaveProperty("services");
    expect(payload).not.toHaveProperty("log_query");
    expect(payload).not.toHaveProperty("metric_queries");
    expect(payload.start).toBeLessThan(payload.end);
  });

  it("downloads the default YAML template", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    const onDownloadTemplate = vi.fn().mockResolvedValue({
      template_yaml: "version: 1\nrequest:\n  step: 15s\n",
      file_name: "becertain-rca-defaults.yaml",
    });
    const originalCreateElement = document.createElement.bind(document);
    const createObjectURL = vi.fn(() => "blob:template");
    const revokeObjectURL = vi.fn();
    const click = vi.fn();
    const createElement = vi
      .spyOn(document, "createElement")
      .mockImplementation((tagName) => {
        if (tagName === "a") {
          return {
            click,
            href: "",
            download: "",
          };
        }
        return originalCreateElement(tagName);
      });

    vi.stubGlobal("URL", {
      createObjectURL,
      revokeObjectURL,
    });

    render(
      <RcaJobComposer
        onCreate={onCreate}
        onDownloadTemplate={onDownloadTemplate}
        creating={false}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Download Default YAML" }));

    await waitFor(() => expect(onDownloadTemplate).toHaveBeenCalledTimes(1));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:template");

    createElement.mockRestore();
  });
});