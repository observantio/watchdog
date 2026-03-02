`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`;

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // SRE Dark Theme (default)
        "sre-bg": "var(--sre-bg)",
        "sre-bg-alt": "var(--sre-bg-alt)",
        "sre-bg-card": "var(--sre-bg-card)",
        "sre-surface": "var(--sre-surface)",
        "sre-surface-light": "var(--sre-surface-light)",
        "sre-border": "var(--sre-border)",
        "sre-text": "var(--sre-text)",
        "sre-text-muted": "var(--sre-text-muted)",
        "sre-text-subtle": "var(--sre-text-subtle)",
        "sre-primary": "#3b82f6",
        "sre-primary-light": "#60a5fa",
        "sre-success": "#10b981",
        "sre-success-light": "#34d399",
        "sre-warning": "#f59e0b",
        "sre-warning-light": "#fbbf24",
        "sre-error": "#ef4444",
        "sre-error-light": "#f87171",
        "sre-accent": "#8b5cf6",
        "sre-accent-light": "#a78bfa",
        "sre-neon": "#39ff14",
      },
      fontFamily: {
        mono: [
          "Ubuntu Mono Sans",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Courier New",
          "monospace",
        ],
        sans: [
          "Ubuntu Mono",
          "Ubuntu",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      boxShadow: {
        "glow-sm": "0 0 10px rgba(59, 130, 246, 0.3)",
        glow: "0 0 20px rgba(59, 130, 246, 0.4)",
        "glow-lg": "0 0 30px rgba(59, 130, 246, 0.5)",
        neon: "0 0 10px rgba(57, 255, 20, 0.5)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "slide-up": "slideUp 0.3s ease-out",
        "fade-in": "fadeIn 0.4s ease-out",
      },
      keyframes: {
        slideUp: {
          "0%": { transform: "translateY(10px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
      },
    },
  },
  plugins: [require("tailwind-scrollbar")],
};
