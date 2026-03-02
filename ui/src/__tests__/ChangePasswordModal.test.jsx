import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ChangePasswordModal from "../components/ChangePasswordModal";
import { ToastProvider } from "../contexts/ToastContext";

// a simple noop for onClose
const noop = () => {};

describe("ChangePasswordModal", () => {
  it("displays forced password warning with 12 character requirement", () => {
    render(
      <ToastProvider>
        <ChangePasswordModal
          isOpen={true}
          onClose={noop}
          userId="user"
          isForced={true}
        />
      </ToastProvider>,
    );
    expect(
      screen.getByText(/You must change your password before continuing/),
    ).toBeInTheDocument();
    expect(screen.getByText(/at least 12 characters/)).toBeInTheDocument();
  });

  it("auto-shows the current password tooltip when modal is open", () => {
    render(
      <ToastProvider>
        <ChangePasswordModal isOpen={true} onClose={noop} userId="user" />
      </ToastProvider>,
    );
    expect(
      screen.getByText(
        "Enter your current password to verify your identity before changing it.",
      ),
    ).toBeInTheDocument();
  });
});
