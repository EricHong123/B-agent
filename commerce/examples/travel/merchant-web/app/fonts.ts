// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** This app's typefaces, as CSS variables on the element that carries `fontVariables` (the
 * root element here; an app frame in examples/unified-web). */

import { Archivo, Fraunces } from "next/font/google";

// Display face: wordmark and view titles. Data and tables stay in the body face.
const fraunces = Fraunces({
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz"],
  variable: "--font-display",
  display: "swap",
});

const archivo = Archivo({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});

export const fontVariables = [fraunces.variable, archivo.variable].join(" ");
