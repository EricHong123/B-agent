// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/**
 * Confines each hosted app's stylesheet to its frame. Runs after Tailwind, so the app's tokens,
 * its own classes, web-shared's rules, and the Tailwind output generated for it all move under
 * the app's class: `:root`, `html`, and `body` become the frame itself (`html:root`, which
 * outranks an app's `:root` in web-shared/theme.css, becomes the class twice), and every other
 * selector is prefixed with it. Keyframes and at-rules without selectors are left alone.
 */

const path = require("node:path");
const { HOSTED_APPS } = require("./hosted-apps.cjs");

function scoped(selector, scope) {
  if (selector === "html:root") return scope + scope;
  if (/^(:root|html|body|:host)$/.test(selector)) return scope;
  const lead = selector.match(/^(:root|html|body)(?=[\s.:#[>+~])/);
  if (lead) return scope + selector.slice(lead[0].length);
  return `${scope} ${selector}`;
}

module.exports = () => ({
  postcssPlugin: "acme-hosted-app-scope",
  OnceExit(root) {
    const file = root.source?.input?.file;
    const app = file && HOSTED_APPS.find((candidate) => file.startsWith(candidate.root + path.sep));
    if (!app) return;
    const scope = `.${app.scope}`;
    root.walkRules((rule) => {
      for (let parent = rule.parent; parent; parent = parent.parent) {
        if (parent.type === "atrule" && /keyframes$/i.test(parent.name)) return;
      }
      rule.selectors = rule.selectors.map((selector) => scoped(selector.trim(), scope));
    });
  },
});
module.exports.postcss = true;
