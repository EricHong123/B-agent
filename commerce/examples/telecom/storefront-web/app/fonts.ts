// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** This app's typefaces, as CSS variables on the element that carries `fontVariables` (the
 * root element here; an app frame in examples/unified-web). */

import { Barlow, Spline_Sans_Mono } from "next/font/google";

// Barlow at both ends of its weight range: 100 for display, 700/800 for labels.
const barlow = Barlow({
  subsets: ["latin"],
  weight: ["100", "300", "400", "500", "600", "700", "800"],
  variable: "--font-body",
  display: "swap",
});

// Numerals, prices, allowances, and IDs render in mono with tabular figures.
const splineSansMono = Spline_Sans_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const fontVariables = [barlow.variable, splineSansMono.variable].join(" ");
