import { api } from '@/api'

export type OpportunityStage = 'inquiry' | 'qualified' | 'quoting' | 'negotiation' | 'won' | 'lost'
export type QuotationStatus =
  | 'draft'
  | 'approval_pending'
  | 'approved'
  | 'rejected'
  | 'sent'
  | 'accepted'
  | 'declined'
  | 'superseded'
export type OrderStatus =
  | 'confirmed'
  | 'in_production'
  | 'quality_check'
  | 'ready_to_ship'
  | 'shipped'
  | 'delivered'
  | 'completed'
  | 'cancelled'
export type FulfillmentMode = 'in_house' | 'outsourced' | 'mixed'

export interface OpportunityRequirements {
  product?: string
  quantity?: string
  unit?: string
  target_price?: string
  destination_country?: string
  incoterm?: string
  required_by?: string
  certifications?: string[]
  notes?: string
}

export interface Opportunity {
  id: string
  customer_id: number
  customer_name: string
  conversation_id?: string
  title: string
  source: string
  stage: OpportunityStage
  allowed_stages: OpportunityStage[]
  inquiry_summary?: string
  requirements: OpportunityRequirements
  estimated_value?: string
  currency: string
  expected_close_date?: string
  lost_reason?: string
  won_at?: string
  order_id?: string
  quotation_count: number
  created_at: string
  updated_at: string
}

export interface QuotationLineItem {
  product: string
  description?: string
  hs_code?: string
  quantity: string
  unit: string
  unit_price: string
  unit_cost?: string
  amount?: string
}

export interface Quotation {
  id: string
  opportunity_id: string
  quote_number: string
  revision: number
  status: QuotationStatus
  currency: string
  incoterm: string
  payment_terms: string
  deposit_percent: number
  lead_time_days: number
  valid_until: string
  expired: boolean
  line_items: QuotationLineItem[]
  subtotal: string
  freight_amount: string
  discount_amount: string
  total: string
  margin_percent?: string
  requires_escalated_approval: boolean
  notes?: string
  review_reason?: string
  reviewed_at?: string
  sent_at?: string
  accepted_at?: string
  created_at: string
}

export interface QuotationCreate {
  currency: string
  incoterm: string
  payment_terms: string
  deposit_percent: number
  lead_time_days: number
  valid_days: number
  line_items: QuotationLineItem[]
  freight_amount: string
  discount_amount: string
  notes?: string
}

export interface TransitionReadiness {
  status: OrderStatus
  ready: boolean
  blockers: string[]
}

export interface ProductionTask {
  id: string
  kind: 'work_order' | 'purchase_order'
  reference_number: string
  description: string
  supplier_name?: string
  production_line?: string
  quantity: string
  unit: string
  status: 'planned' | 'in_progress' | 'completed' | 'cancelled'
  progress_percent: number
  planned_start?: string
  planned_finish?: string
  overdue: boolean
  notes?: string
}

export interface Inspection {
  id: string
  stage: 'pre_production' | 'inline' | 'pre_shipment'
  result: 'passed' | 'failed' | 'conditional'
  inspector: string
  sample_size?: number
  defects: { description: string, severity: string, count: number }[]
  report_url?: string
  notes?: string
  inspected_at: string
}

export interface Shipment {
  id: string
  shipment_number: string
  status: 'booked' | 'departed' | 'arrived' | 'delivered'
  transport_mode: string
  carrier: string
  tracking_number?: string
  bill_of_lading?: string
  container_number?: string
  port_of_loading?: string
  port_of_discharge?: string
  etd?: string
  eta?: string
  departed_at?: string
  delivered_at?: string
}

export interface Payment {
  id: string
  kind: 'deposit' | 'balance' | 'other'
  amount: string
  currency: string
  method: string
  reference?: string
  received_at: string
}

export interface OrderSummary {
  id: string
  order_number: string
  customer_id: number
  customer_name: string
  opportunity_id: string
  quotation_id: string
  status: OrderStatus
  fulfillment_mode: FulfillmentMode
  currency: string
  total: string
  amount_paid: string
  balance_due: string
  required_ship_date?: string
  ship_date_at_risk: boolean
  production_progress_percent: number
  created_at: string
  updated_at: string
}

export interface OrderDetail extends OrderSummary {
  customer_po_number?: string
  incoterm: string
  payment_terms: string
  line_items: QuotationLineItem[]
  deposit_required: string
  balance_before_shipment: boolean
  shipping_address?: string
  cancel_reason?: string
  version: number
  next_transitions: TransitionReadiness[]
  production_tasks: ProductionTask[]
  inspections: Inspection[]
  shipments: Shipment[]
  payments: Payment[]
}

export interface FulfillmentEvent {
  id: string
  order_id?: string
  event_type: string
  from_status?: string
  to_status?: string
  payload: Record<string, unknown>
  created_at: string
}

export interface PipelineStage {
  key: string
  count: number
  value: string
}

export interface PipelineAlert {
  kind: string
  severity: 'info' | 'warning' | 'critical'
  message: string
  opportunity_id?: string
  order_id?: string
}

export interface UnconvertedInquiry {
  conversation_id: string
  customer_id: number
  customer_name: string
  intent: string
  last_message_at?: string
}

export interface PipelineOverview {
  leads: Record<string, number>
  outreach: Record<string, number>
  opportunities: PipelineStage[]
  quotations: Record<string, number>
  orders: PipelineStage[]
  win_rate_percent?: string
  booked_value: string
  collected_value: string
  unconverted_inquiries: UnconvertedInquiry[]
  alerts: PipelineAlert[]
}

const BASE = '/api/v1/fulfillment'

export const fulfillmentApi = {
  async pipeline() {
    return (await api.get<PipelineOverview>(`${BASE}/pipeline`)).data
  },
  async events(params: { opportunity_id?: string, order_id?: string }) {
    return (await api.get<FulfillmentEvent[]>(`${BASE}/events`, { params })).data
  },
  async listOpportunities(params?: { stage?: string, customer_id?: number }) {
    return (await api.get<Opportunity[]>(`${BASE}/opportunities`, { params })).data
  },
  async getOpportunity(id: string) {
    return (await api.get<Opportunity>(`${BASE}/opportunities/${id}`)).data
  },
  async createOpportunity(payload: {
    customer_id: number
    title: string
    inquiry_summary?: string
    requirements?: OpportunityRequirements
    currency?: string
  }) {
    return (await api.post<Opportunity>(`${BASE}/opportunities`, payload)).data
  },
  async createOpportunityFromConversation(
    conversationId: string,
    payload: { title?: string, requirements?: OpportunityRequirements } = {}
  ) {
    return (
      await api.post<Opportunity>(`${BASE}/opportunities/from-conversation/${conversationId}`, payload)
    ).data
  },
  async updateOpportunity(id: string, payload: { requirements?: OpportunityRequirements, inquiry_summary?: string }) {
    return (await api.patch<Opportunity>(`${BASE}/opportunities/${id}`, payload)).data
  },
  async transitionOpportunity(id: string, stage: OpportunityStage, reason?: string) {
    return (await api.post<Opportunity>(`${BASE}/opportunities/${id}/transition`, { stage, reason })).data
  },
  async listQuotations(opportunityId: string) {
    return (await api.get<Quotation[]>(`${BASE}/opportunities/${opportunityId}/quotations`)).data
  },
  async createQuotation(opportunityId: string, payload: QuotationCreate) {
    return (await api.post<Quotation>(`${BASE}/opportunities/${opportunityId}/quotations`, payload)).data
  },
  async submitQuotation(id: string) {
    return (await api.post<Quotation>(`${BASE}/quotations/${id}/submit`)).data
  },
  async reviewQuotation(id: string, decision: 'approve' | 'reject', reason: string) {
    return (await api.post<Quotation>(`${BASE}/quotations/${id}/review`, { decision, reason })).data
  },
  async sendQuotation(id: string, channel: 'email' | 'whatsapp' | 'other') {
    return (await api.post<Quotation>(`${BASE}/quotations/${id}/send`, { channel })).data
  },
  async declineQuotation(id: string, reason: string) {
    return (await api.post<Quotation>(`${BASE}/quotations/${id}/decline`, { reason })).data
  },
  async acceptQuotation(
    id: string,
    payload: {
      fulfillment_mode: FulfillmentMode
      customer_po_number?: string
      required_ship_date?: string
      shipping_address?: string
      balance_before_shipment: boolean
    }
  ) {
    return (await api.post<OrderDetail>(`${BASE}/quotations/${id}/accept`, payload)).data
  },
  async listOrders(params?: { status?: string, customer_id?: number }) {
    return (await api.get<OrderSummary[]>(`${BASE}/orders`, { params })).data
  },
  async getOrder(id: string) {
    return (await api.get<OrderDetail>(`${BASE}/orders/${id}`)).data
  },
  async transitionOrder(id: string, status: OrderStatus, reason?: string) {
    return (await api.post<OrderDetail>(`${BASE}/orders/${id}/transition`, { status, reason })).data
  },
  async addProductionTask(id: string, payload: Record<string, unknown>) {
    return (await api.post<OrderDetail>(`${BASE}/orders/${id}/production-tasks`, payload)).data
  },
  async updateProductionTask(id: string, taskId: string, payload: Record<string, unknown>) {
    return (await api.patch<OrderDetail>(`${BASE}/orders/${id}/production-tasks/${taskId}`, payload)).data
  },
  async recordInspection(id: string, payload: Record<string, unknown>) {
    return (await api.post<OrderDetail>(`${BASE}/orders/${id}/inspections`, payload)).data
  },
  async createShipment(id: string, payload: Record<string, unknown>) {
    return (await api.post<OrderDetail>(`${BASE}/orders/${id}/shipments`, payload)).data
  },
  async updateShipment(id: string, shipmentId: string, payload: Record<string, unknown>) {
    return (await api.patch<OrderDetail>(`${BASE}/orders/${id}/shipments/${shipmentId}`, payload)).data
  },
  async recordPayment(
    id: string,
    payload: {
      idempotency_key: string
      kind: Payment['kind']
      amount: string
      currency: string
      method: string
      reference?: string
    }
  ) {
    return (await api.post<OrderDetail>(`${BASE}/orders/${id}/payments`, payload)).data
  },
}

export function formatMoney(value: string | number | undefined | null, currency = 'USD') {
  const amount = Number(value ?? 0)
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 2 }).format(amount)
  } catch {
    return `${currency} ${amount.toFixed(2)}`
  }
}

export function newIdempotencyKey(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`
}
