// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

const config = {
  plugins: {
    "@tailwindcss/postcss": {},
    // Each hosted app's stylesheet stays inside its frame (postcss-scope.cjs).
    "./postcss-scope.cjs": {},
  },
};

export default config;
