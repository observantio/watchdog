module.exports = [
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        process: "readonly",
        vi: "readonly",
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },

    plugins: {
      react: require("eslint-plugin-react"),
      "jsx-a11y": require("eslint-plugin-jsx-a11y"),
    },

    settings: {
      react: { version: "detect" },
    },

    rules: {
      "react/prop-types": "off",
      "react/react-in-jsx-scope": "off",
      // react-hooks plugin currently incompatible with the installed ESLint version (v10)
      // keep rules enforced later after upgrading plugin/ESLint. Temporarily disabled here.
      // "react-hooks/rules-of-hooks": "error",
      // "react-hooks/exhaustive-deps": "warn",
      "jsx-a11y/no-noninteractive-element-interactions": "off",
      "jsx-a11y/label-has-associated-control": "off",
      "jsx-a11y/no-autofocus": "off",
    },
  },
];
