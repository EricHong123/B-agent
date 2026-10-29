// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** The web apps' icon set: 24px line icons drawn here, so no icon package is needed. */

import type { SVGProps } from "react";

const STROKE = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

const PATHS = {
  home: <path d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1z" />,
  tag: (
    <>
      <path d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7l8.3 8.3-8.7 8.7z" />
      <circle cx="8" cy="8" r="1.4" />
    </>
  ),
  inbox: (
    <>
      <path d="M4 13.5 6.5 5h11L20 13.5V19H4z" />
      <path d="M4 13.5h5l1 2h4l1-2h5" />
    </>
  ),
  box: (
    <>
      <path d="M3.5 7.5 12 3.5l8.5 4v9L12 20.5l-8.5-4z" />
      <path d="M3.5 7.5 12 11.5l8.5-4M12 11.5v9" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6" />
      <path d="m16 16 4 4" />
    </>
  ),
  message: <path d="M4.5 5.5h15v10h-8l-4.5 3.5v-3.5h-2.5z" />,
  return: (
    <>
      <path d="M9 6.5 4.5 11 9 15.5" />
      <path d="M4.5 11H15a4.5 4.5 0 0 1 0 9h-3" />
    </>
  ),
  truck: (
    <>
      <path d="M3 6.5h11v9H3zM14 10h4l3 3v2.5h-7" />
      <circle cx="7" cy="17.5" r="1.8" />
      <circle cx="17" cy="17.5" r="1.8" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  low: (
    <>
      <path d="M4.5 19.5h15" />
      <rect x="6.5" y="13" width="3.5" height="6.5" rx=".6" />
      <path d="M14 8.5v7m0 0-2.5-2.5M14 15.5l2.5-2.5" />
    </>
  ),
  chart: <path d="M4 19.5h16M6.5 16V11M11 16V6.5M15.5 16v-7" />,
  alert: (
    <>
      <path d="M12 4.5 20.5 19h-17z" />
      <path d="M12 10v4M12 16.5v.5" />
    </>
  ),
  calendar: (
    <>
      <rect x="4" y="5.5" width="16" height="14" rx="1.5" />
      <path d="M4 10h16M8.5 3.5v4M15.5 3.5v4" />
    </>
  ),
  ticket: (
    <>
      <path d="M3.5 8.5a2 2 0 0 0 0 4v3h17v-3a2 2 0 0 0 0-4v-3h-17z" />
      <path d="M14 5.5v10" strokeDasharray="1.5 2" />
    </>
  ),
  bed: (
    <>
      <path d="M3.5 18v-7h17v7M3.5 15h17M3.5 11V6.5" />
      <rect x="6.5" y="8" width="5" height="3" rx="1" />
    </>
  ),
  signal: <path d="M5 19.5v-3M9.5 19.5v-6.5M14 19.5V9M18.5 19.5v-15" />,
  edit: (
    <>
      <path d="M4.5 19.5h4l10-10-4-4-10 10z" />
      <path d="m12.5 7.5 4 4" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 19.5c1-3.5 3.8-5 7-5s6 1.5 7 5" />
    </>
  ),
  check: <path d="m5 12.5 4.5 4.5L19 7.5" strokeWidth={2} />,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  "thumb-up": <path d="M7.5 11v9h-3v-9zM7.5 11l3.8-6.7a1.9 1.9 0 0 1 3.5 1.2L14 10h5a2 2 0 0 1 2 2.4l-1.3 6A2 2 0 0 1 17.7 20H7.5" />,
  "thumb-down": (
    <path
      d="M7.5 11v9h-3v-9zM7.5 11l3.8-6.7a1.9 1.9 0 0 1 3.5 1.2L14 10h5a2 2 0 0 1 2 2.4l-1.3 6A2 2 0 0 1 17.7 20H7.5"
      transform="rotate(180 12.75 12)"
    />
  ),
  headset: (
    <>
      <path d="M4.5 14v-2a7.5 7.5 0 0 1 15 0v2" />
      <path d="M4.5 14h3v5h-2a1 1 0 0 1-1-1zM19.5 14h-3v5h2a1 1 0 0 0 1-1z" />
    </>
  ),
  expand: <path d="M14 4.5h5.5V10M10 19.5H4.5V14M19.5 4.5 13.5 10.5M4.5 19.5l6-6" />,
  collapse: <path d="M19.5 10H14V4.5M4.5 14H10v5.5M14 10l5.5-5.5M10 14l-5.5 5.5" />,
  "arrow-up": <path d="M12 19V5M6 11l6-6 6 6" strokeWidth={2} />,
  "arrow-right": <path d="M5 12h14M13 6l6 6-6 6" />,
  "chevron-right": <path d="m9 6 6 6-6 6" />,
  plane: <path d="M20.5 12.5 13 10V5.5a1.5 1.5 0 0 0-3 0V10l-7.5 2.5v2l7.5-1.2v4.2l-2.5 1.7V21l4-1 4 1v-1.8L13 17.5v-4.2l7.5 1.2z" />,
  pin: (
    <>
      <path d="M12 20.5s6.5-5.6 6.5-10.5a6.5 6.5 0 0 0-13 0c0 4.9 6.5 10.5 6.5 10.5z" />
      <circle cx="12" cy="10" r="2.2" />
    </>
  ),
  bag: (
    <>
      <path d="M5 8.5h14l-1 11.5H6z" />
      <path d="M9 8.5V7a3 3 0 0 1 6 0v1.5" />
    </>
  ),
  photo: (
    <>
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <circle cx="9" cy="10" r="1.6" />
      <path d="m5 17 4.5-4 3.5 3 2.5-2 4 3.5" />
    </>
  ),
  settings: (
    <>
      <path d="M4.5 7h9M17.5 7h2M4.5 17h2M10.5 17h9" />
      <circle cx="15.5" cy="7" r="2" />
      <circle cx="8.5" cy="17" r="2" />
    </>
  ),
} as const;

export type IconName = keyof typeof PATHS | "spark";

/** `spark` is the assistant's mark and the only filled glyph. */
export function Icon({
  name,
  size = 18,
  className = "",
  ...rest
}: { name: IconName; size?: number } & Omit<SVGProps<SVGSVGElement>, "name">) {
  if (name === "spark") {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden className={`shrink-0 ${className}`} {...rest}>
        <path d="M12 2.5c.4 4.6 2.4 7.4 7.5 8-5.1.6-7.1 3.4-7.5 8-.4-4.6-2.4-7.4-7.5-8 5.1-.6 7.1-3.4 7.5-8z" />
        <path d="M19 15c.2 2 .9 3 3 3.2-2.1.3-2.8 1.3-3 3.3-.2-2-.9-3-3-3.3 2.1-.2 2.8-1.2 3-3.2z" opacity=".7" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden className={`shrink-0 ${className}`} {...STROKE} {...rest}>
      {PATHS[name]}
    </svg>
  );
}
