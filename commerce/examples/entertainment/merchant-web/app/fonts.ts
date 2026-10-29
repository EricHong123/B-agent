// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** This app's typefaces, as CSS variables on the element that carries `fontVariables` (the
 * root element here; an app frame in examples/unified-web). */

import { Archivo, Big_Shoulders, IBM_Plex_Mono } from "next/font/google";

const bigShoulders = Big_Shoulders({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800", "900"],
  variable: "--font-display",
  display: "swap",
  // next/font has no fallback metrics for this face yet.
  adjustFontFallback: false,
  fallback: ["Arial Narrow", "sans-serif"],
});

const archivo = Archivo({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-body",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-mono",
  display: "swap",
});

export const fontVariables = [bigShoulders.variable, archivo.variable, plexMono.variable].join(" ");
