import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { resolveBackendApiUrl } from './runtimeConfig'

const BASE = '/api/v1/commerce'
export const SESSION_HEADER = 'X-Commerce-Session'
export const BUYER_TOKEN_HEADER = 'X-Buyer-Token'

export type CommerceRole = 'buyer' | 'operations'
export type CommerceLocale = 'en' | 'zh'

export interface CommerceEvent {
  type:
    | 'text_delta'
    | 'tool_call'
    | 'tool_result'
    | 'ui'
    | 'ui_partial'
    | 'cart_update'
    | 'change_update'
    | 'progress'
    | 'turn_complete'
    | 'error'
  data: Record<string, any>
}

export interface CommerceProduct {
  product_id: string
  title: string
  brand?: string | null
  price: number
  currency: string
  image_url?: string | null
  category?: string | null
  attributes: Record<string, string>
  in_stock: boolean
  short_description?: string | null
  options?: Record<string, string[]>
  option_values?: Record<string, string>
  variant_of?: string | null
  variants?: CommerceProduct[]
}

export interface CartPayload {
  items: { product_id: string, title: string, price: number, quantity: number, option_values?: Record<string, string> }[]
  item_count: number
  subtotal: number
  currency: string
}

export interface StagedChange {
  change_id: string
  kind: 'listing_update' | 'price_update' | 'inventory_action' | 'promotion' | 'campaign'
  status: 'staged' | 'applied' | 'discarded' | 'expired'
  summary: string
  items: { target: string, field: string, before?: unknown, after?: unknown }[]
  created_at: string
  created_by: string
  applied_at?: string
  applied_by?: string
  guardrail_notes?: string[]
  currency?: string
  margin_impact?: number
  margin_before_pct?: number
  margin_after_pct?: number
}

export interface HandoffBrief {
  request: string | null
  tried: { tools: { name: string, status: string }[], held: { tool: string, reason: string }[], fallbacks: string[] }
  evidence_versions: { source_id: string, version: string, status: string }[]
  reason: string
}

export interface CommerceSessionAuth {
  role: CommerceRole
  sessionId: string
  buyerToken?: string
}

function headers(auth: CommerceSessionAuth): Record<string, string> {
  const result: Record<string, string> = { [SESSION_HEADER]: auth.sessionId }
  if (auth.buyerToken) result[BUYER_TOKEN_HEADER] = auth.buyerToken
  return result
}

function scope(role: CommerceRole) {
  return role === 'buyer' ? 'buyer' : 'operations'
}

export function parseCommerceFrames(buffer: string): { events: CommerceEvent[], rest: string } {
  const frames = buffer.split('\n\n')
  const rest = frames.pop() || ''
  const events: CommerceEvent[] = []
  for (const frame of frames) {
    let type = ''
    const data: string[] = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) type = line.slice(6).trim()
      if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (type && data.length) events.push({ type: type as CommerceEvent['type'], data: JSON.parse(data.join('\n')) })
  }
  return { events, rest }
}

export async function streamCommerceChat(
  auth: CommerceSessionAuth,
  body: { message: string, locale?: CommerceLocale, page?: Record<string, unknown> },
  onEvent: (event: CommerceEvent) => void,
  signal?: AbortSignal,
) {
  const authStore = useAuthStore()
  const requestHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
    ...headers(auth),
  }
  if (!auth.buyerToken && authStore.token) requestHeaders.Authorization = `Bearer ${authStore.token}`
  const response = await fetch(`${resolveBackendApiUrl()}${BASE}/${scope(auth.role)}/chat`, {
    method: 'POST',
    headers: requestHeaders,
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok || !response.body) {
    let detail = `Assistant request failed (${response.status})`
    try {
      detail = (await response.json()).detail || detail
    } catch {
      // keep the status text
    }
    throw new Error(detail)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const parsed = parseCommerceFrames(buffer)
    buffer = parsed.rest
    parsed.events.forEach(onEvent)
    if (done) break
  }
}

export const commerceApi = {
  async status() {
    return (await api.get(`${BASE}/status`)).data as {
      provider: string
      model: string
      merchant_model: string
      model_configured: boolean
      buyer_skills: string[]
      operations_skills: string[]
    }
  },
  async metrics(days = 30) {
    return (await api.get(`${BASE}/metrics`, { params: { days } })).data as {
      definitions_version: string
      roles: Record<string, Record<string, any>>
    }
  },
  async handoffs(includeResolved = false) {
    return (await api.get(`${BASE}/handoffs`, { params: { include_resolved: includeResolved } })).data as {
      ticket: string
      role: string
      created_at: string
      resolved_at?: string
      brief: HandoffBrief
    }[]
  },
  async resolveHandoff(ticket: string) {
    return (await api.post(`${BASE}/handoffs/${ticket}/resolve`)).data
  },
  async createInvite(customerId: number, days?: number) {
    return (await api.post(`${BASE}/buyer/invites`, { customer_id: customerId, days })).data as {
      id: string
      token: string
      portal_path: string
      expires_at: string
    }
  },
  async listInvites(customerId: number) {
    return (await api.get(`${BASE}/buyer/invites`, { params: { customer_id: customerId } })).data as {
      id: string
      expires_at: string
      revoked_at?: string
      last_used_at?: string
      created_at: string
    }[]
  },
  async revokeInvite(id: string) {
    return (await api.post(`${BASE}/buyer/invites/${id}/revoke`)).data
  },
  async startBuyerSession(options: { customerId?: number, buyerToken?: string }) {
    const config = options.buyerToken ? { headers: { [BUYER_TOKEN_HEADER]: options.buyerToken } } : {}
    return (await api.post(`${BASE}/buyer/session`, options.customerId ? { customer_id: options.customerId } : {}, config)).data as {
      session_id: string
      customer_id: number
      customer_name: string
      mode: 'portal' | 'assisted'
      model_configured: boolean
    }
  },
  async startOperationsSession() {
    return (await api.post(`${BASE}/operations/session`)).data as {
      session_id: string
      operator: string
      can_approve: boolean
      model_configured: boolean
    }
  },
  async products(auth: CommerceSessionAuth, query = '') {
    return (await api.get(`${BASE}/buyer/products`, { params: { query }, headers: headers(auth) })).data as { products: CommerceProduct[] }
  },
  async cart(auth: CommerceSessionAuth) {
    return (await api.get(`${BASE}/buyer/cart`, { headers: headers(auth) })).data as CartPayload
  },
  async addToCart(auth: CommerceSessionAuth, productId: string, quantity: number) {
    return (await api.post(`${BASE}/buyer/cart/add`, { product_id: productId, quantity }, { headers: headers(auth) })).data as CartPayload
  },
  async submitRfq(auth: CommerceSessionAuth, note?: string) {
    return (await api.post(`${BASE}/buyer/rfq`, { note }, { headers: headers(auth) })).data as {
      opportunity_id: string
      quotation_id: string
      quote_number: string
      below_moq: string[]
    }
  },
  async orders(auth: CommerceSessionAuth) {
    return (await api.get(`${BASE}/buyer/orders`, { headers: headers(auth) })).data as { orders: any[] }
  },
  async memory(auth: CommerceSessionAuth) {
    return (await api.get(`${BASE}/${scope(auth.role)}/memory`, { headers: headers(auth) })).data as {
      facts: { key: string, value: string, category: string }[]
    }
  },
  async forget(auth: CommerceSessionAuth, key: string) {
    return (await api.delete(`${BASE}/buyer/memory/${encodeURIComponent(key)}`, { headers: headers(auth) })).data
  },
  async feedback(auth: CommerceSessionAuth, turnId: string, helpful: boolean) {
    return (await api.post(`${BASE}/${scope(auth.role)}/feedback`, { turn_id: turnId, helpful }, { headers: headers(auth) })).data
  },
  async handoff(auth: CommerceSessionAuth, turnId: string | undefined, reason: 'user_requested' | 'after_negative_feedback' | 'after_error') {
    return (await api.post(`${BASE}/${scope(auth.role)}/handoff`, { turn_id: turnId, reason }, { headers: headers(auth) })).data as {
      ticket: string
      brief: HandoffBrief
    }
  },
  async reset(auth: CommerceSessionAuth) {
    return (await api.post(`${BASE}/${scope(auth.role)}/reset`, {}, { headers: headers(auth) })).data as { session_id: string }
  },
  async overview(auth: CommerceSessionAuth) {
    return (await api.get(`${BASE}/operations/overview`, { headers: headers(auth) })).data as {
      snapshot: Record<string, any>
      needs_attention: { inventory: any[], order_issues: any[], pending_changes: StagedChange[] }
      recent_changes: StagedChange[]
    }
  },
  async changes(auth: CommerceSessionAuth) {
    return (await api.get(`${BASE}/operations/changes`, { headers: headers(auth) })).data as {
      pending: StagedChange[]
      resolved: StagedChange[]
    }
  },
  async changeAction(auth: CommerceSessionAuth, changeId: string, action: 'apply' | 'discard') {
    return (await api.post(`${BASE}/operations/changes/${changeId}/${action}`, {}, { headers: headers(auth) })).data as {
      ok: boolean
      change: StagedChange | null
      reason?: string
    }
  },
  async catalogProducts() {
    return (await api.get(`${BASE}/catalog/products`)).data as any[]
  },
  async saveProduct(product: Record<string, unknown> & { id: string }) {
    return (await api.put(`${BASE}/catalog/products/${product.id}`, product)).data
  },
  async terms() {
    return (await api.get(`${BASE}/catalog/terms`)).data as any[]
  },
  async createTerm(term: Record<string, unknown>) {
    return (await api.post(`${BASE}/catalog/terms`, term)).data
  },
  async campaigns() {
    return (await api.get(`${BASE}/catalog/campaigns`)).data as any[]
  },
  async seedDemo() {
    return (await api.post(`${BASE}/catalog/seed-demo`)).data as Record<string, number>
  },
}
