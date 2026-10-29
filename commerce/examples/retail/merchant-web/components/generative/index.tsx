// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** One entry per merchant presentation tool. */

import { type ChangeActionHandler, type GenerativeBlockProps, UnknownBlock } from "web-shared";
import type { ChangePreviewPayload, DigestPayload, MetricsPayload, StagedChange } from "@/lib/types";
import ChangePreviewCard from "./ChangePreviewCard";
import DigestCard from "./DigestCard";
import MetricsCard from "./MetricsCard";

export default function GenerativeBlock({
  block,
  status,
  onChangeAction,
  onPrefill,
}: GenerativeBlockProps & {
  onChangeAction?: ChangeActionHandler<StagedChange>;
  onPrefill?: (text: string) => void;
}) {
  switch (block.component) {
    case "metrics":
      return <MetricsCard payload={block.payload as MetricsPayload} />;
    case "digest":
      return <DigestCard payload={block.payload as DigestPayload} onPrefill={onPrefill} />;
    case "change_preview":
      return <ChangePreviewCard payload={block.payload as ChangePreviewPayload} onAct={onChangeAction} />;
    default:
      return status === "final" ? <UnknownBlock component={block.component} /> : null;
  }
}
