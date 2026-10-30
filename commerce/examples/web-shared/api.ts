// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { cookieLocale } from "./locale";
import type { AgentEvent, HandoffBrief, HandoffReason, MemoryFact, Order } from "./protocol";

const SESSION_HEADER = "X-Session-Id";

/**
 * The client both roles' web apps use; the storefront's cart, orders, and memory reads live here
 * too. The session token travels only in the session header. Reads return null on any failure
 * so callers keep their last good state.
 */
export class AgentApi {
  session: string | null = null;
  readonly base: string;

  /** `root` is the API's URL; `prefix` the role's route prefix ("/api", "/api/merchant"). */
  constructor(
    readonly root: string,
    prefix: string,
  ) {
    this.base = `${root}${prefix}`;
  }

  /** Files the API serves by path ("/products/AR-1002.webp"). */
  assetUrl(path: string | null | undefined): string | null {
    if (!path) return null;
    return path.startsWith("/") ? `${this.root}${path}` : path;
  }

  headers(json = false): Record<string, string> {
    const headers: Record<string, string> = {};
    if (this.session) headers[SESSION_HEADER] = this.session;
    if (json) headers["Content-Type"] = "application/json";
    return headers;
  }

  async get<T>(path: string, params?: Record<string, string>): Promise<T | null> {
    const query = params && Object.keys(params).length ? `?${new URLSearchParams(params)}` : "";
    return this.request<T>(`${path}${query}`, { headers: this.headers() });
  }

  async post<T>(path: string, body?: unknown): Promise<T | null> {
    return this.send<T>("POST", path, body);
  }

  async patch<T>(path: string, body: unknown): Promise<T | null> {
    return this.send<T>("PATCH", path, body);
  }

  async delete<T>(path: string, body?: unknown): Promise<T | null> {
    return this.send<T>("DELETE", path, body);
  }

  private async send<T>(method: string, path: string, body?: unknown): Promise<T | null> {
    return this.request<T>(path, {
      method,
      headers: this.headers(body !== undefined),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  private async request<T>(path: string, init: RequestInit): Promise<T | null> {
    try {
      const response = await fetch(`${this.base}${path}`, init);
      if (!response.ok) return null;
      return (await response.json()) as T;
    } catch {
      return null;
    }
  }

  /** A storefront passes its profile as `{ user_id }` and gets the shopper's name back; a merchant session names its operator. */
  async startSession(body?: Record<string, unknown>): Promise<{ sessionId: string; operator?: string; shopper?: { name: string; tier?: string } } | null> {
    const data = await this.post<{ session_id: string; operator?: string; name?: string | null; tier?: string | null }>("/session", body);
    if (!data?.session_id) return null;
    const shopper = data.name ? { name: data.name, tier: data.tier ?? undefined } : undefined;
    return { sessionId: data.session_id, operator: data.operator, shopper };
  }

  async fetchMemory(): Promise<MemoryFact[] | null> {
    const data = await this.get<{ facts?: MemoryFact[] }>("/memory");
    return data ? (data.facts ?? []) : null;
  }

  /** The corrected fact, or null when the store refused the value. */
  async editMemoryFact(key: string, value: string): Promise<MemoryFact | null> {
    const data = await this.patch<{ fact: MemoryFact }>("/memory", { key, value });
    return data?.fact ?? null;
  }

  async forgetMemoryFact(key: string): Promise<boolean> {
    return (await this.delete<{ ok: boolean }>("/memory", { key })) !== null;
  }

  /** The bag as the vertical's API shapes it (lines, count, subtotal, plus its own extras). */
  async fetchCart<T>(): Promise<T | null> {
    return this.get<T>("/cart");
  }

  /** The signed-in customer's orders, newest first. */
  async fetchOrders(): Promise<Order[] | null> {
    const data = await this.get<{ orders: Order[] }>("/orders");
    return data?.orders ?? null;
  }

  /** A vote on one reply; false when the API did not record it. */
  async sendFeedback(turnId: string, helpful: boolean): Promise<boolean> {
    return (await this.post<{ ok: boolean }>("/feedback", { turn_id: turnId, helpful })) !== null;
  }

  /** Opens a support ticket for a person to pick up; the ticket id and its brief, or null. */
  async requestHandoff(
    turnId: string | undefined,
    reason: HandoffReason,
  ): Promise<{ ticket: string; brief: HandoffBrief } | null> {
    const data = await this.post<{ ticket: string; brief: HandoffBrief }>("/handoff", { turn_id: turnId ?? null, reason });
    return data?.ticket ? { ticket: data.ticket, brief: data.brief } : null;
  }

  /** Throws when the request itself fails. */
  async *chatStream(message: string): AsyncGenerator<AgentEvent> {
    const response = await fetch(`${this.base}/chat`, {
      method: "POST",
      headers: this.headers(true),
      // The agent replies in the language the shopper picked.
      body: JSON.stringify({ message, locale: cookieLocale() }),
    });
    if (!response.ok || !response.body) throw new Error(`chat request failed: ${response.status}`);
    yield* readEventStream(response.body);
  }
}

async function* readEventStream(body: ReadableStream<Uint8Array>): AsyncGenerator<AgentEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventType: string | null = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline: number;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline).trimEnd();
      buffer = buffer.slice(newline + 1);
      if (line.startsWith("event: ")) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith("data: ") && eventType) {
        try {
          yield { type: eventType, data: JSON.parse(line.slice(6)) } as AgentEvent;
        } catch {
          // A malformed frame is dropped; the stream continues.
        }
      } else if (line === "") {
        eventType = null;
      }
    }
  }
}
