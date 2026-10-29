// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** This app's typefaces, as CSS variables on the element that carries `fontVariables` (the
 * root element here; an app frame in examples/unified-web). */

import { Archivo, Fraunces } from "next/font/google";

// Display face: headlines, day numerals, prices, postcard city names.
const fraunces = Fraunces({
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz"],
  variable: "--font-display",
  display: "swap",
});

// Body face: copy, buttons, metadata lines.
const archivo = Archivo({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});

export const fontVariables = [fraunces.variable, archivo.variable].join(" ");
