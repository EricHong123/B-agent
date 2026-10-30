// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/**
 * The apps this page hosts, each as its directory under examples/ and the class its frame
 * carries. next.config.ts resolves each app's own "@/..." imports inside that app;
 * postcss-scope.cjs confines each app's globals.css (Tailwind's output included) to its class.
 * components/UnifiedApp.tsx imports the same apps' pages, styles, typefaces, and messages.
 */

const path = require("node:path");

const EXAMPLES = path.resolve(__dirname, "..");

const HOSTED_APPS = [
  { dir: "retail/storefront-web", scope: "u-retail-store" },
  { dir: "retail/merchant-web", scope: "u-retail-portal" },
  { dir: "travel/storefront-web", scope: "u-travel-store" },
  { dir: "telecom/merchant-web", scope: "u-telecom-portal" },
  { dir: "entertainment/merchant-web", scope: "u-tickets-portal" },
].map((app) => ({ ...app, root: path.join(EXAMPLES, app.dir) }));

module.exports = { EXAMPLES, HOSTED_APPS };
