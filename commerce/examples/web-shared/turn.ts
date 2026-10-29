// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import type { AgentApi } from "./api";
import type {
  AgentEvent,
  AssistantChatItem,
  AssistantSegment,
  ChatItem,
  MemoryFact,
  ReplySource,
  ToolCallData,
  TraceEntry,
  UIBlock,
  UISlotStatus,
} from "./protocol";
import { useT } from "./i18n";
import { describeToolCall } from "./tool-copy";

/** Pace between structural items when a burst arrives at once. */
const DRIP_MS = 180;
/** Pace once the final payload is waiting behind the queue. */
const FAST_DRIP_MS = 80;
/** Queue depth above which every second frame is dropped. */
const MAX_QUEUE = 8;
/** The arrays the server's partial signature counts, in its order. */
const STRUCTURAL_KEYS = ["items", "entries", "steps", "days", "sections", "metrics"] as const;
/** Consumed here; never reaches an app's component registry. */
const CHIPS_COMPONENT = "suggestions";
/** Grace for the memory extractor before the store is re-read. */
const MEMORY_REREAD_MS = 2500;

function structuralCount(block: UIBlock): number {
  const payload = block.payload as Record<string, unknown>;
  for (const key of STRUCTURAL_KEYS) {
    const value = payload[key];
    if (Array.isArray(value)) return value.length;
  }
  return 0;
}

function structuralPrefix(block: UIBlock, count: number): UIBlock {
  const payload = block.payload as Record<string, unknown>;
  for (const key of STRUCTURAL_KEYS) {
    const value = payload[key];
    if (Array.isArray(value)) {
      return { ...block, payload: { ...payload, [key]: value.slice(0, count) } };
    }
  }
  return block;
}

/** The current versions a `tool_result`'s `evidence` lists; withheld and superseded ones are not sources. */
function readSources(evidence: unknown): ReplySource[] {
  if (!Array.isArray(evidence)) return [];
  return evidence
    .filter((entry) => entry && typeof entry === "object" && entry.status === "current")
    .map((entry) => ({
      source_id: String(entry.source_id ?? ""),
      version: String(entry.version ?? ""),
      effective_at: String(entry.effective_at ?? ""),
    }))
    .filter((source) => source.source_id);
}

function mergeSources(known: ReplySource[] | undefined, added: ReplySource[]): ReplySource[] {
  const merged = [...(known ?? [])];
  for (const source of added) {
    if (!merged.some((m) => m.source_id === source.source_id && m.version === source.version)) {
      merged.push(source);
    }
  }
  return merged;
}

function eventBlock(event: AgentEvent): UIBlock {
  return { component: String(event.data.component ?? ""), payload: event.data.payload ?? {} };
}

/** Keyed by turn + component + ordinal, not tool_use id, so a retry keeps the card's DOM node. */
interface Slot {
  key: string;
  component: string;
  streamId?: string;
  status: UISlotStatus;
  rendered: number;
  queue: UIBlock[];
  timer: number | null;
  final: UIBlock | null;
}

export interface AgentTurnOptions {
  sessionId: string | null;
  unreachable: string;
  /** Runs before the transcript handles the event. */
  onEvent?: (event: AgentEvent, turn: number) => void;
  onTurnEnd?: (turn: number) => void;
  /** Skeleton to mount on `tool_call` for tools whose card arrives in one final event. */
  pendingComponent?: (tool: string) => string | null | undefined;
}

export interface AgentTurn {
  items: ChatItem[];
  setItems: Dispatch<SetStateAction<ChatItem[]>>;
  ready: boolean;
  /** A reply is streaming. */
  busy: boolean;
  send: (text: string) => Promise<void>;
  turnCount: number;
  /** Replies that have finished; a page re-reads what a reply may have changed when it moves. */
  completed: number;
  streaming: boolean;
  trace: TraceEntry[];
  memory: MemoryFact[];
  /** Keys changed since the page's first read of the store. */
  newMemoryKeys: ReadonlySet<string>;
  /** Re-reads the store after the shopper edits or forgets a fact; that key stops counting as new. */
  reloadMemory: (editedKey: string) => void;
  /** Records the user's vote on a finished reply. */
  rate: (turn: number, helpful: boolean) => void;
  /** Opens a ticket for a person from a reply; the reason follows from the reply's vote or error. */
  handoff: (turn: number) => Promise<void>;
}

export function useAgentTurn(api: AgentApi, options: AgentTurnOptions): AgentTurn {
  const { sessionId, unreachable, onEvent, onTurnEnd, pendingComponent } = options;
  // Read through a ref so a language switch does not rebuild the stream handlers.
  const t = useT();
  const tRef = useRef(t);
  tRef.current = t;
  const [items, setItems] = useState<ChatItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [turnState, setTurnState] = useState({ turnCount: 0, completed: 0, streaming: false });
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [memory, setMemory] = useState<MemoryFact[]>([]);
  const [newMemoryKeys, setNewMemoryKeys] = useState<ReadonlySet<string>>(() => new Set());
  const memoryBaseline = useRef<Map<string, string> | null>(null);
  const turnRef = useRef(0);
  const slotsRef = useRef<Map<string, Slot>>(new Map());
  const slotByStream = useRef<Map<string, string>>(new Map());
  const ordinals = useRef<Map<string, number>>(new Map());
  // Prose on both sides of a tool call shares a segment; the boundary gets a paragraph break.
  const afterToolRef = useRef(false);
  // The tool whose progress line is the current activity; its tool_result clears the line.
  const progressToolRef = useRef<string | null>(null);
  const callbacks = useRef({ onEvent, onTurnEnd, pendingComponent });
  callbacks.current = { onEvent, onTurnEnd, pendingComponent };

  const clearTimers = useCallback(() => {
    for (const slot of slotsRef.current.values()) {
      if (slot.timer != null) window.clearTimeout(slot.timer);
      slot.timer = null;
    }
  }, []);
  useEffect(() => clearTimers, [clearTimers]);

  const updateTurn = useCallback(
    (turn: number, update: (item: AssistantChatItem) => AssistantChatItem) => {
      setItems((previous) =>
        previous.map((item) =>
          item.kind === "assistant" && item.turn === turn ? update(item) : item,
        ),
      );
    },
    [],
  );

  const appendTrace = useCallback((entry: Omit<TraceEntry, "at">) => {
    setTrace((previous) => [...previous, { ...entry, at: performance.now() }]);
  }, []);

  const readMemory = useCallback((editedKey?: string) => {
    void api.fetchMemory().then((facts) => {
      if (facts === null) return;
      const baseline = (memoryBaseline.current ??= new Map(facts.map((f) => [f.key, f.value])));
      // A fact the shopper corrected or forgot on the page is not something the assistant learned.
      const edited = facts.find((f) => f.key === editedKey);
      if (editedKey) edited ? baseline.set(editedKey, edited.value) : baseline.delete(editedKey);
      setMemory(facts);
      const changed = facts.filter((f) => baseline.get(f.key) !== f.value).map((f) => f.key);
      setNewMemoryKeys(new Set(changed));
    });
  }, [api]);

  // The read before the first turn is the baseline for newMemoryKeys.
  useEffect(() => {
    if (sessionId) readMemory();
  }, [sessionId, readMemory]);

  const commit = useCallback(
    (turn: number, slot: Slot, block: UIBlock, status: UISlotStatus) => {
      slot.status = status;
      slot.rendered = structuralCount(block);
      updateTurn(turn, (item) => {
        const segments = [...item.segments];
        const index = segments.findIndex((s) => s.type === "ui" && s.slotKey === slot.key);
        const segment: AssistantSegment = { type: "ui", block, slotKey: slot.key, status };
        if (index >= 0) segments[index] = segment;
        else segments.push(segment);
        return { ...item, segments, activity: status === "pending" ? item.activity : undefined };
      });
    },
    [updateTurn],
  );

  const drain = useCallback(
    (turn: number, slot: Slot) => {
      slot.timer = null;
      const next = slot.queue.shift();
      if (next) {
        commit(turn, slot, next, "partial");
        if (slot.queue.length || slot.final) {
          const interval = slot.final ? FAST_DRIP_MS : DRIP_MS;
          slot.timer = window.setTimeout(() => drain(turn, slot), interval);
        }
      } else if (slot.final) {
        const block = slot.final;
        slot.final = null;
        commit(turn, slot, block, "final");
      }
    },
    [commit],
  );

  /** Cuts a partial into one-item steps so a burst lands item by item. */
  const schedule = useCallback(
    (turn: number, slot: Slot, block: UIBlock) => {
      const incoming = structuralCount(block);
      const queued = slot.queue[slot.queue.length - 1];
      const tail = queued ? structuralCount(queued) : slot.rendered;
      if (!slot.queue.length && slot.timer == null && incoming <= tail + 1) {
        commit(turn, slot, block, "partial");
        return;
      }
      if (slot.queue.length && incoming <= tail) {
        slot.queue[slot.queue.length - 1] = block;
        return;
      }
      for (let count = tail + 1; count < incoming; count++) {
        slot.queue.push(structuralPrefix(block, count));
      }
      slot.queue.push(block);
      if (slot.queue.length > MAX_QUEUE) {
        slot.queue = slot.queue.filter((_, i, all) => i % 2 === 1 || i === all.length - 1);
      }
      if (slot.timer != null) return;
      // The first frame shows at once; only growth is paced.
      if (slot.status === "pending") drain(turn, slot);
      else slot.timer = window.setTimeout(() => drain(turn, slot), DRIP_MS);
    },
    [commit, drain],
  );

  const flush = useCallback(
    (turn: number) => {
      for (const slot of slotsRef.current.values()) {
        if (slot.timer != null) window.clearTimeout(slot.timer);
        slot.timer = null;
        const last = slot.final ?? slot.queue[slot.queue.length - 1];
        const status: UISlotStatus = slot.final ? "final" : slot.status;
        slot.queue = [];
        slot.final = null;
        if (last) commit(turn, slot, last, status);
      }
    },
    [commit],
  );

  const openSlot = useCallback((turn: number, component: string, status: UISlotStatus, streamId?: string) => {
    const ordinal = ordinals.current.get(component) ?? 0;
    ordinals.current.set(component, ordinal + 1);
    const slot: Slot = {
      key: `${turn}-${component}-${ordinal}`,
      component,
      streamId,
      status,
      rendered: 0,
      queue: [],
      timer: null,
      final: null,
    };
    slotsRef.current.set(slot.key, slot);
    if (streamId) slotByStream.current.set(streamId, slot.key);
    return slot;
  }, []);

  const findSlot = useCallback((component: string, statuses?: UISlotStatus[]) => {
    let found: Slot | undefined;
    for (const slot of slotsRef.current.values()) {
      if (slot.component !== component) continue;
      if (!statuses || statuses.includes(slot.status)) found = slot;
    }
    return found;
  }, []);

  const handleEvent = useCallback(
    (turn: number, event: AgentEvent) => {
      callbacks.current.onEvent?.(event, turn);
      switch (event.type) {
        case "text_delta": {
          const delta = String(event.data.text ?? "");
          const afterTool = afterToolRef.current;
          afterToolRef.current = false;
          progressToolRef.current = null;
          updateTurn(turn, (item) => {
            const segments = [...item.segments];
            const last = segments[segments.length - 1];
            if (last?.type === "text") {
              const spaced = /\s$/.test(last.text) || /^\s/.test(delta);
              const gap = afterTool && last.text && !spaced ? "\n\n" : "";
              segments[segments.length - 1] = { type: "text", text: last.text + gap + delta };
            } else {
              segments.push({ type: "text", text: delta });
            }
            return { ...item, segments, activity: undefined };
          });
          return;
        }
        case "ui_partial": {
          const block = eventBlock(event);
          if (block.component === CHIPS_COMPONENT) return;
          const streamId = String(event.data.stream_id ?? "");
          const known = slotByStream.current.get(streamId);
          let slot = known ? slotsRef.current.get(known) : undefined;
          if (!slot) {
            // A new attempt adopts the component's skeleton or failed slot, else opens a new card.
            slot = findSlot(block.component, ["pending", "retrying"]);
            if (slot) {
              if (slot.timer != null) window.clearTimeout(slot.timer);
              slot.timer = null;
              slot.queue = [];
              slot.final = null;
              slot.rendered = 0;
              slot.status = "pending";
              slot.streamId = streamId;
            } else {
              slot = openSlot(turn, block.component, "pending", streamId);
            }
            slotByStream.current.set(streamId, slot.key);
          }
          schedule(turn, slot, block);
          return;
        }
        case "ui": {
          const block = eventBlock(event);
          if (block.component === CHIPS_COMPONENT) {
            const suggestions = (block.payload as { suggestions?: string[] }).suggestions ?? [];
            updateTurn(turn, (item) => ({ ...item, activity: undefined, suggestions }));
            return;
          }
          const streamId = event.data.stream_id ? String(event.data.stream_id) : undefined;
          const known = streamId ? slotByStream.current.get(streamId) : undefined;
          // Same adoption rule as ui_partial; a final without a stream id replaces the
          // component's card.
          const slot =
            (known ? slotsRef.current.get(known) : undefined) ??
            findSlot(block.component, streamId ? ["pending", "retrying"] : undefined) ??
            openSlot(turn, block.component, "final", streamId);
          if (streamId) {
            slot.streamId = streamId;
            slotByStream.current.set(streamId, slot.key);
          }
          if (slot.queue.length && slot.timer != null) {
            slot.final = block;
          } else {
            if (slot.timer != null) window.clearTimeout(slot.timer);
            slot.timer = null;
            slot.queue = [];
            slot.final = null;
            commit(turn, slot, block, "final");
          }
          return;
        }
        case "tool_call": {
          afterToolRef.current = true;
          progressToolRef.current = null;
          const data = event.data as Partial<ToolCallData>;
          const tool = String(data.tool ?? "tool");
          const input = data.input ?? {};
          // The model's own line for the call when it carries one, else the stock copy.
          const label = typeof data.label === "string" ? data.label.trim() : "";
          updateTurn(turn, (item) => ({
            ...item,
            tools: [...item.tools, tool],
            activity: label || describeToolCall(tool, input, tRef.current),
          }));
          const component = callbacks.current.pendingComponent?.(tool);
          if (component && !findSlot(component)) {
            const slot = openSlot(turn, component, "pending");
            commit(turn, slot, { component, payload: {} }, "pending");
          }
          const detail = JSON.stringify(input, null, 1);
          appendTrace({ kind: "tool_call", turn, label: tool, detail });
          return;
        }
        case "tool_result": {
          const resultTool = String(event.data.tool ?? "tool");
          if (progressToolRef.current === resultTool) {
            progressToolRef.current = null;
            updateTurn(turn, (item) => ({ ...item, activity: undefined }));
          }
          if (event.data.is_error) {
            // Streamed frames stay, dimmed, for the retry to adopt.
            const key = slotByStream.current.get(String(event.data.id ?? ""));
            const slot = key ? slotsRef.current.get(key) : undefined;
            if (slot?.status === "partial") {
              if (slot.timer != null) window.clearTimeout(slot.timer);
              slot.timer = null;
              const last = slot.queue[slot.queue.length - 1];
              slot.queue = [];
              slot.final = null;
              slot.status = "retrying";
              updateTurn(turn, (item) => ({
                ...item,
                segments: item.segments.map((s) =>
                  s.type === "ui" && s.slotKey === slot.key
                    ? { ...s, block: last ?? s.block, status: "retrying" }
                    : s,
                ),
              }));
            }
          }
          const current = readSources(event.data.evidence);
          if (current.length) {
            updateTurn(turn, (item) => ({ ...item, sources: mergeSources(item.sources, current) }));
          }
          appendTrace({
            kind: "tool_result",
            turn,
            label: resultTool,
            detail: String(event.data.summary ?? ""),
            isError: Boolean(event.data.is_error),
            status: event.data.status ? String(event.data.status) : undefined,
            reason: event.data.reason ? String(event.data.reason) : undefined,
            excerpt: typeof event.data.excerpt === "string" ? event.data.excerpt : undefined,
          });
          return;
        }
        case "progress": {
          const message = String(event.data.message ?? "").trim();
          if (!message) return;
          progressToolRef.current = event.data.tool ? String(event.data.tool) : null;
          updateTurn(turn, (item) => ({ ...item, activity: message }));
          return;
        }
        case "error": {
          const text = String(event.data.message ?? tRef.current("Something went wrong."));
          updateTurn(turn, (item) => ({
            ...item,
            segments: [...item.segments, { type: "error", text }],
          }));
          appendTrace({ kind: "error", turn, label: "error", detail: text, isError: true });
          return;
        }
        default:
          return;
      }
    },
    [appendTrace, commit, findSlot, openSlot, schedule, updateTurn],
  );

  const runTurn = useCallback(
    async (userText: string, events: AsyncIterable<AgentEvent>) => {
      const turn = ++turnRef.current;
      const startedAt = performance.now();
      clearTimers();
      slotsRef.current = new Map();
      slotByStream.current = new Map();
      ordinals.current = new Map();
      afterToolRef.current = false;
      progressToolRef.current = null;
      setTurnState((state) => ({ ...state, turnCount: turn, streaming: true }));
      setItems((previous) => [
        ...previous,
        { kind: "user", text: userText },
        { kind: "assistant", turn, segments: [], suggestions: [], pending: true, tools: [] },
      ]);
      try {
        for await (const event of events) {
          if (event.type === "turn_complete") {
            const usage = (event.data.usage ?? {}) as Record<string, number>;
            const n = (value?: number) => (value ?? 0).toLocaleString("en-US");
            appendTrace({
              kind: "turn_complete",
              turn,
              label: "turn complete",
              detail:
                tRef.current("in {input} · out {output} · cache read {cache}", {
                  input: n(usage.input_tokens),
                  output: n(usage.output_tokens),
                  cache: n(usage.cache_read_input_tokens),
                }),
              elapsedMs: performance.now() - startedAt,
            });
            const turnId = event.data.turn_id;
            if (typeof turnId === "string") updateTurn(turn, (item) => ({ ...item, turnId }));
            callbacks.current.onEvent?.(event, turn);
          } else {
            handleEvent(turn, event);
          }
        }
      } catch {
        updateTurn(turn, (item) =>
          item.segments.length
            ? item
            : { ...item, segments: [{ type: "error", text: unreachable }] },
        );
      } finally {
        // Partials freeze as they are; unadopted skeletons and failed slots go at turn end.
        flush(turn);
        updateTurn(turn, (item) => ({
          ...item,
          pending: false,
          activity: undefined,
          segments: item.segments
            .filter((s) => s.type !== "ui" || (s.status !== "pending" && s.status !== "retrying"))
            .map((s) =>
              s.type === "ui" && s.status === "partial" ? { ...s, status: "final" } : s,
            ),
        }));
        setTurnState((state) => ({ turnCount: turn, completed: state.completed + 1, streaming: false }));
        callbacks.current.onTurnEnd?.(turn);
      }
    },
    [appendTrace, clearTimers, flush, handleEvent, unreachable, updateTurn],
  );

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || busy || !sessionId) return;
      setBusy(true);
      await runTurn(message, api.chatStream(message));
      setBusy(false);
      window.setTimeout(() => readMemory(), MEMORY_REREAD_MS);
    },
    [api, busy, sessionId, runTurn, readMemory],
  );

  const itemOf = useCallback(
    (turn: number) =>
      items.find((item): item is AssistantChatItem => item.kind === "assistant" && item.turn === turn),
    [items],
  );

  const rate = useCallback(
    (turn: number, helpful: boolean) => {
      const item = itemOf(turn);
      if (!item?.turnId) return;
      updateTurn(turn, (current) => ({ ...current, rating: helpful ? "up" : "down" }));
      void api.sendFeedback(item.turnId, helpful);
    },
    [api, itemOf, updateTurn],
  );

  const handoff = useCallback(
    async (turn: number) => {
      const item = itemOf(turn);
      if (!item || item.ticket) return;
      const failed = item.segments.some((segment) => segment.type === "error");
      const reason = item.rating === "down" ? "after_negative_feedback" : failed ? "after_error" : "user_requested";
      const opened = await api.requestHandoff(item.turnId, reason);
      if (opened) updateTurn(turn, (current) => ({ ...current, ticket: opened.ticket, handoff: opened.brief }));
    },
    [api, itemOf, updateTurn],
  );

  return {
    items,
    setItems,
    rate,
    handoff,
    ready: sessionId != null,
    busy,
    send,
    ...turnState,
    trace,
    memory,
    newMemoryKeys,
    reloadMemory: readMemory,
  };
}
