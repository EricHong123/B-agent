// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { createRequire } from "node:module";
import path from "node:path";

const { HOSTED_APPS } = createRequire(import.meta.url)("./hosted-apps.cjs");

/**
 * Each hosted app writes "@/lib/api" for its own lib/api.ts: resolve "@/" inside the app the
 * importing file belongs to, so the apps' sources are used as they are.
 */
class HostedAppAlias {
  apply(resolver) {
    const target = resolver.ensureHook("resolve");
    resolver.getHook("described-resolve").tapAsync("HostedAppAlias", (request, context, callback) => {
      const spec = request.request;
      const from = typeof request.path === "string" ? request.path : "";
      const app =
        spec?.startsWith("@/") &&
        HOSTED_APPS.find((candidate) => from === candidate.root || from.startsWith(candidate.root + path.sep));
      if (!spec || !app) return callback();
      resolver.doResolve(
        target,
        { ...request, request: path.join(app.root, spec.slice(2)) },
        `@/ in ${app.dir}`,
        context,
        callback,
      );
    });
  }
}

/** @type {import("next").NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["web-shared"],
  // No AGENTS.md or CLAUDE.md written into this directory on start; the repo's CLAUDE.md applies.
  agentRules: false,
  // The hosted apps live beside this one under examples/.
  experimental: { externalDir: true },
  // A hosted app's "@/" paths mean its own directory, which one tsconfig cannot express; each
  // app type-checks in its own directory, and this app's build skips the check.
  typescript: { ignoreBuildErrors: true },
  // The retail storefront's product photos are its own public files; the retail API serves the
  // same directory, so the photos come from there.
  async rewrites() {
    const retailApi = process.env.NEXT_PUBLIC_RETAIL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [{ source: "/products/:path*", destination: `${retailApi}/products/:path*` }];
  },
  webpack(config) {
    config.resolve.plugins = [...(config.resolve.plugins ?? []), new HostedAppAlias()];
    return config;
  },
};

export default nextConfig;
