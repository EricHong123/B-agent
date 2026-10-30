<template>
  <div class="order-detail page-stack">
    <header class="page-heading">
      <div>
        <el-button
          text
          class="back-button"
          @click="$router.push('/fulfillment')"
        >
          <el-icon><ArrowLeft /></el-icon>
          {{ $t('Fulfillment') }}
        </el-button>
        <h1>{{ order?.order_number || $t('Order') }}</h1>
        <p v-if="order">
          {{ order.customer_name }} · {{ $t(order.fulfillment_mode) }} · {{ order.incoterm }}
          <template v-if="order.customer_po_number">
            · {{ $t('Customer PO') }} {{ order.customer_po_number }}
          </template>
        </p>
      </div>
      <div
        v-if="order"
        class="heading-actions"
      >
        <el-button
          @click="$router.push({ path: '/fulfillment', query: { opportunity: order.opportunity_id } })"
        >
          {{ $t('Opportunity') }}
        </el-button>
        <el-button
          v-if="cancellable"
          type="danger"
          plain
          @click="cancelOrder"
        >
          {{ $t('Cancel order') }}
        </el-button>
      </div>
    </header>

    <template v-if="order">
      <el-card shadow="never">
        <el-steps
          :active="activeStep"
          :process-status="order.status === 'cancelled' ? 'error' : 'process'"
          finish-status="success"
          align-center
        >
          <el-step
            v-for="step in lifecycle"
            :key="step"
            :title="$t(step)"
          />
        </el-steps>
        <el-alert
          v-if="order.status === 'cancelled'"
          type="error"
          :closable="false"
          :title="`${$t('cancelled')}: ${order.cancel_reason || ''}`"
          class="spaced"
        />
        <div
          v-for="next in order.next_transitions"
          :key="next.status"
          class="gate"
        >
          <el-button
            type="primary"
            :disabled="!next.ready"
            :loading="saving"
            @click="advance(next.status)"
          >
            {{ $t('Move to {stage}', { stage: $t(next.status) }) }}
          </el-button>
          <ul
            v-if="next.blockers.length"
            class="blockers"
          >
            <li
              v-for="blocker in next.blockers"
              :key="blocker"
            >
              {{ blocker }}
            </li>
          </ul>
        </div>
      </el-card>

      <section class="metric-row">
        <el-card shadow="never">
          <span class="metric-label">{{ $t('Order total') }}</span>
          <strong class="metric-value">{{ formatMoney(order.total, order.currency) }}</strong>
        </el-card>
        <el-card shadow="never">
          <span class="metric-label">{{ $t('Deposit required') }}</span>
          <strong class="metric-value">{{ formatMoney(order.deposit_required, order.currency) }}</strong>
        </el-card>
        <el-card shadow="never">
          <span class="metric-label">{{ $t('Received') }}</span>
          <strong class="metric-value">{{ formatMoney(order.amount_paid, order.currency) }}</strong>
        </el-card>
        <el-card shadow="never">
          <span class="metric-label">{{ $t('Balance due') }}</span>
          <strong class="metric-value">{{ formatMoney(order.balance_due, order.currency) }}</strong>
        </el-card>
        <el-card shadow="never">
          <span class="metric-label">{{ $t('Ship by') }}</span>
          <strong :class="['metric-value', { 'at-risk': order.ship_date_at_risk }]">
            {{ order.required_ship_date || '—' }}
          </strong>
        </el-card>
      </section>

      <div class="panel-grid">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>{{ $t('Production') }}</span>
              <el-button
                v-if="taskEditable"
                size="small"
                type="primary"
                @click="taskDialogOpen = true"
              >
                <el-icon><Plus /></el-icon>
                {{ $t(defaultTaskKind === 'purchase_order' ? 'New purchase order' : 'New work order') }}
              </el-button>
            </div>
          </template>
          <el-empty
            v-if="!order.production_tasks.length"
            :description="$t('Plan production before releasing the order')"
            :image-size="56"
          />
          <article
            v-for="task in order.production_tasks"
            :key="task.id"
            class="row-item"
          >
            <div class="row-title">
              <strong>{{ task.reference_number }}</strong>
              <el-tag size="small">
                {{ $t(task.kind) }}
              </el-tag>
              <el-tag
                size="small"
                :type="task.status === 'completed' ? 'success' : task.status === 'cancelled' ? 'danger' : 'info'"
              >
                {{ $t(task.status) }}
              </el-tag>
              <el-tag
                v-if="task.overdue"
                size="small"
                type="danger"
              >
                {{ $t('overdue') }}
              </el-tag>
            </div>
            <p class="row-meta">
              {{ task.description }} · {{ task.quantity }} {{ task.unit }}
              <template v-if="task.supplier_name">
                · {{ task.supplier_name }}
              </template>
              <template v-if="task.production_line">
                · {{ task.production_line }}
              </template>
              <template v-if="task.planned_finish">
                · {{ $t('Due') }} {{ task.planned_finish }}
              </template>
            </p>
            <el-progress :percentage="task.progress_percent" />
            <div
              v-if="!closed"
              class="action-row"
            >
              <el-button
                v-if="task.status === 'planned'"
                size="small"
                @click="updateTask(task.id, { status: 'in_progress' })"
              >
                {{ $t('Start') }}
              </el-button>
              <template v-if="task.status === 'in_progress'">
                <el-button
                  size="small"
                  @click="updateProgress(task.id, task.progress_percent)"
                >
                  {{ $t('Update progress') }}
                </el-button>
                <el-button
                  size="small"
                  type="success"
                  @click="updateTask(task.id, { status: 'completed' })"
                >
                  {{ $t('Complete') }}
                </el-button>
              </template>
            </div>
          </article>
        </el-card>

        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>{{ $t('Quality control') }}</span>
              <el-button
                v-if="inspectionAllowed"
                size="small"
                type="primary"
                @click="inspectionDialogOpen = true"
              >
                <el-icon><Plus /></el-icon>
                {{ $t('Record inspection') }}
              </el-button>
            </div>
          </template>
          <el-empty
            v-if="!order.inspections.length"
            :description="$t('A passed pre-shipment inspection is required to ship')"
            :image-size="56"
          />
          <article
            v-for="inspection in order.inspections"
            :key="inspection.id"
            class="row-item"
          >
            <div class="row-title">
              <strong>{{ $t(inspection.stage) }}</strong>
              <el-tag
                size="small"
                :type="inspection.result === 'passed' ? 'success' : inspection.result === 'failed' ? 'danger' : 'warning'"
              >
                {{ $t(inspection.result) }}
              </el-tag>
            </div>
            <p class="row-meta">
              {{ inspection.inspector }} · {{ new Date(inspection.inspected_at).toLocaleString() }}
              <template v-if="inspection.defects.length">
                · {{ inspection.defects.length }} {{ $t('defect types') }}
              </template>
            </p>
          </article>
        </el-card>

        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>{{ $t('Shipments') }}</span>
              <el-button
                v-if="shipmentAllowed"
                size="small"
                type="primary"
                @click="shipmentDialogOpen = true"
              >
                <el-icon><Plus /></el-icon>
                {{ $t('Book shipment') }}
              </el-button>
            </div>
          </template>
          <el-empty
            v-if="!order.shipments.length"
            :description="$t('Book a shipment once goods reach quality check')"
            :image-size="56"
          />
          <article
            v-for="shipment in order.shipments"
            :key="shipment.id"
            class="row-item"
          >
            <div class="row-title">
              <strong>{{ shipment.shipment_number }}</strong>
              <el-tag size="small">
                {{ $t(shipment.status) }}
              </el-tag>
            </div>
            <p class="row-meta">
              {{ $t(shipment.transport_mode) }} · {{ shipment.carrier }}
              <template v-if="shipment.tracking_number || shipment.bill_of_lading">
                · {{ shipment.tracking_number || shipment.bill_of_lading }}
              </template>
              <template v-if="shipment.port_of_loading || shipment.port_of_discharge">
                · {{ shipment.port_of_loading || '?' }} → {{ shipment.port_of_discharge || '?' }}
              </template>
              <template v-if="shipment.eta">
                · ETA {{ shipment.eta }}
              </template>
            </p>
            <div
              v-if="order.status !== 'cancelled'"
              class="action-row"
            >
              <el-button
                v-if="shipment.status === 'booked'"
                size="small"
                @click="departShipment(shipment.id, shipment.tracking_number || shipment.bill_of_lading)"
              >
                {{ $t('Mark departed') }}
              </el-button>
              <el-button
                v-if="shipment.status === 'departed'"
                size="small"
                @click="updateShipment(shipment.id, { status: 'arrived' })"
              >
                {{ $t('Mark arrived') }}
              </el-button>
              <el-button
                v-if="['departed', 'arrived'].includes(shipment.status)"
                size="small"
                type="success"
                @click="updateShipment(shipment.id, { status: 'delivered' })"
              >
                {{ $t('Mark delivered') }}
              </el-button>
            </div>
          </article>
        </el-card>

        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>{{ $t('Payments') }}</span>
              <el-button
                v-if="order.status !== 'cancelled' && Number(order.balance_due) > 0"
                size="small"
                type="primary"
                @click="openPaymentDialog"
              >
                <el-icon><Plus /></el-icon>
                {{ $t('Record payment') }}
              </el-button>
            </div>
          </template>
          <el-empty
            v-if="!order.payments.length"
            :description="$t('No payments received yet')"
            :image-size="56"
          />
          <article
            v-for="payment in order.payments"
            :key="payment.id"
            class="row-item"
          >
            <div class="row-title">
              <strong>{{ formatMoney(payment.amount, payment.currency) }}</strong>
              <el-tag size="small">
                {{ $t(payment.kind) }}
              </el-tag>
            </div>
            <p class="row-meta">
              {{ payment.method.toUpperCase() }} · {{ new Date(payment.received_at).toLocaleDateString() }}
              <template v-if="payment.reference">
                · {{ payment.reference }}
              </template>
            </p>
          </article>
        </el-card>
      </div>

      <el-card shadow="never">
        <template #header>
          {{ $t('Timeline') }}
        </template>
        <el-timeline>
          <el-timeline-item
            v-for="event in events"
            :key="event.id"
            :timestamp="new Date(event.created_at).toLocaleString()"
          >
            {{ $t(event.event_type) }}
            <span v-if="event.from_status && event.to_status && event.from_status !== event.to_status">
              {{ $t(event.from_status) }} → {{ $t(event.to_status) }}
            </span>
            <span v-else-if="event.to_status"> → {{ $t(event.to_status) }}</span>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </template>

    <el-dialog
      v-model="taskDialogOpen"
      :title="$t('Plan production')"
      width="min(520px, 92vw)"
    >
      <el-form label-position="top">
        <el-form-item
          v-if="order?.fulfillment_mode === 'mixed'"
          :label="$t('Type')"
        >
          <el-radio-group v-model="taskForm.kind">
            <el-radio-button value="work_order">
              {{ $t('work_order') }}
            </el-radio-button>
            <el-radio-button value="purchase_order">
              {{ $t('purchase_order') }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="$t('Description')">
          <el-input v-model="taskForm.description" />
        </el-form-item>
        <div class="form-grid">
          <el-form-item :label="$t('Quantity')">
            <el-input v-model="taskForm.quantity" />
          </el-form-item>
          <el-form-item :label="$t('Unit')">
            <el-input v-model="taskForm.unit" />
          </el-form-item>
        </div>
        <el-form-item
          v-if="taskForm.kind === 'purchase_order'"
          :label="$t('Supplier')"
        >
          <el-input v-model="taskForm.supplier_name" />
        </el-form-item>
        <el-form-item
          v-else
          :label="$t('Production line')"
        >
          <el-input v-model="taskForm.production_line" />
        </el-form-item>
        <div class="form-grid">
          <el-form-item :label="$t('Planned start')">
            <el-date-picker
              v-model="taskForm.planned_start"
              type="date"
              value-format="YYYY-MM-DD"
            />
          </el-form-item>
          <el-form-item :label="$t('Planned finish')">
            <el-date-picker
              v-model="taskForm.planned_finish"
              type="date"
              value-format="YYYY-MM-DD"
            />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="taskDialogOpen = false">
          {{ $t('Cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="addTask"
        >
          {{ $t('Create') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="inspectionDialogOpen"
      :title="$t('Record inspection')"
      width="min(520px, 92vw)"
    >
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item :label="$t('Stage')">
            <el-select v-model="inspectionForm.stage">
              <el-option
                v-for="stage in ['pre_production', 'inline', 'pre_shipment']"
                :key="stage"
                :label="$t(stage)"
                :value="stage"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('Result')">
            <el-select v-model="inspectionForm.result">
              <el-option
                v-for="result in ['passed', 'conditional', 'failed']"
                :key="result"
                :label="$t(result)"
                :value="result"
              />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item :label="$t('Inspector')">
          <el-input v-model="inspectionForm.inspector" />
        </el-form-item>
        <el-form-item :label="$t('Notes')">
          <el-input
            v-model="inspectionForm.notes"
            type="textarea"
            :rows="2"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="inspectionDialogOpen = false">
          {{ $t('Cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="recordInspection"
        >
          {{ $t('Save') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="shipmentDialogOpen"
      :title="$t('Book shipment')"
      width="min(560px, 92vw)"
    >
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item :label="$t('Transport mode')">
            <el-select v-model="shipmentForm.transport_mode">
              <el-option
                v-for="mode in ['sea', 'air', 'rail', 'road', 'express']"
                :key="mode"
                :label="$t(mode)"
                :value="mode"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('Carrier')">
            <el-input v-model="shipmentForm.carrier" />
          </el-form-item>
          <el-form-item :label="$t('Tracking / B/L number')">
            <el-input v-model="shipmentForm.tracking_number" />
          </el-form-item>
          <el-form-item :label="$t('Container')">
            <el-input v-model="shipmentForm.container_number" />
          </el-form-item>
          <el-form-item :label="$t('Port of loading')">
            <el-input v-model="shipmentForm.port_of_loading" />
          </el-form-item>
          <el-form-item :label="$t('Port of discharge')">
            <el-input v-model="shipmentForm.port_of_discharge" />
          </el-form-item>
          <el-form-item label="ETD">
            <el-date-picker
              v-model="shipmentForm.etd"
              type="date"
              value-format="YYYY-MM-DD"
            />
          </el-form-item>
          <el-form-item label="ETA">
            <el-date-picker
              v-model="shipmentForm.eta"
              type="date"
              value-format="YYYY-MM-DD"
            />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="shipmentDialogOpen = false">
          {{ $t('Cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="createShipment"
        >
          {{ $t('Create') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="paymentDialogOpen"
      :title="$t('Record payment')"
      width="min(480px, 92vw)"
    >
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item :label="$t('Type')">
            <el-select v-model="paymentForm.kind">
              <el-option
                v-for="kind in ['deposit', 'balance', 'other']"
                :key="kind"
                :label="$t(kind)"
                :value="kind"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('Method')">
            <el-select v-model="paymentForm.method">
              <el-option
                v-for="method in ['tt', 'lc', 'paypal', 'card', 'cash', 'other']"
                :key="method"
                :label="method.toUpperCase()"
                :value="method"
              />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item :label="`${$t('Amount')} (${order?.currency || ''})`">
          <el-input v-model="paymentForm.amount" />
        </el-form-item>
        <el-form-item :label="$t('Bank reference')">
          <el-input v-model="paymentForm.reference" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="paymentDialogOpen = false">
          {{ $t('Cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="recordPayment"
        >
          {{ $t('Save') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  fulfillmentApi,
  formatMoney,
  newIdempotencyKey,
  type FulfillmentEvent,
  type OrderDetail,
  type OrderStatus,
  type Payment,
} from '@/api/fulfillment'
import { promptText } from '@/composables/usePromptText'

const route = useRoute()
const orderId = route.params.id as string

const lifecycle: OrderStatus[] = ['confirmed', 'in_production', 'quality_check', 'ready_to_ship', 'shipped', 'delivered', 'completed']
const order = ref<OrderDetail | null>(null)
const events = ref<FulfillmentEvent[]>([])
const saving = ref(false)
const taskDialogOpen = ref(false)
const inspectionDialogOpen = ref(false)
const shipmentDialogOpen = ref(false)
const paymentDialogOpen = ref(false)
const paymentKey = ref('')

const taskForm = reactive({
  kind: 'work_order' as 'work_order' | 'purchase_order',
  description: '',
  quantity: '',
  unit: 'pcs',
  supplier_name: '',
  production_line: '',
  planned_start: '',
  planned_finish: '',
})
const inspectionForm = reactive({ stage: 'pre_shipment', result: 'passed', inspector: '', notes: '' })
const shipmentForm = reactive({
  transport_mode: 'sea',
  carrier: '',
  tracking_number: '',
  container_number: '',
  port_of_loading: '',
  port_of_discharge: '',
  etd: '',
  eta: '',
})
const paymentForm = reactive({ kind: 'deposit' as Payment['kind'], method: 'tt', amount: '', reference: '' })

const closed = computed(() => ['completed', 'cancelled'].includes(order.value?.status || ''))
const activeStep = computed(() => {
  if (!order.value) return 0
  if (order.value.status === 'completed') return lifecycle.length
  const index = lifecycle.indexOf(order.value.status)
  return index < 0 ? 0 : index
})
const cancellable = computed(() => ['confirmed', 'in_production', 'quality_check', 'ready_to_ship'].includes(order.value?.status || ''))
const taskEditable = computed(() => ['confirmed', 'in_production', 'quality_check'].includes(order.value?.status || ''))
const inspectionAllowed = computed(() => !['completed', 'cancelled', 'shipped', 'delivered'].includes(order.value?.status || ''))
const shipmentAllowed = computed(() => ['quality_check', 'ready_to_ship', 'shipped'].includes(order.value?.status || ''))
const defaultTaskKind = computed(() => order.value?.fulfillment_mode === 'outsourced' ? 'purchase_order' : 'work_order')

async function load() {
  const [detail, timeline] = await Promise.all([
    fulfillmentApi.getOrder(orderId),
    fulfillmentApi.events({ order_id: orderId }),
  ])
  order.value = detail
  events.value = [...timeline].reverse()
  taskForm.kind = defaultTaskKind.value
}

async function run(action: () => Promise<OrderDetail>) {
  saving.value = true
  try {
    order.value = await action()
    events.value = [...(await fulfillmentApi.events({ order_id: orderId }))].reverse()
    return true
  } catch {
    return false
  } finally {
    saving.value = false
  }
}

async function advance(status: OrderStatus) {
  await run(() => fulfillmentApi.transitionOrder(orderId, status))
}

async function cancelOrder() {
  const reason = await promptText('Why is this order cancelled?', 'Cancel order')
  if (reason === null) return
  await run(() => fulfillmentApi.transitionOrder(orderId, 'cancelled', reason))
}

const optional = (value: string) => value.trim() || undefined

async function addTask() {
  const ok = await run(() => fulfillmentApi.addProductionTask(orderId, {
    kind: taskForm.kind,
    description: taskForm.description.trim(),
    quantity: taskForm.quantity,
    unit: taskForm.unit || 'pcs',
    supplier_name: taskForm.kind === 'purchase_order' ? optional(taskForm.supplier_name) : undefined,
    production_line: taskForm.kind === 'work_order' ? optional(taskForm.production_line) : undefined,
    planned_start: taskForm.planned_start || undefined,
    planned_finish: taskForm.planned_finish || undefined,
  }))
  if (ok) {
    taskDialogOpen.value = false
    Object.assign(taskForm, { description: '', quantity: '', supplier_name: '', production_line: '', planned_start: '', planned_finish: '' })
  }
}

async function updateTask(taskId: string, payload: Record<string, unknown>) {
  await run(() => fulfillmentApi.updateProductionTask(orderId, taskId, payload))
}

async function updateProgress(taskId: string, current: number) {
  const value = await promptText('Progress (%)', 'Update progress', {
    inputValue: String(current),
    validator: (input: string) => /^\d{1,3}$/.test(input.trim()) && Number(input) <= 100,
  })
  if (value === null) return
  await updateTask(taskId, { progress_percent: Number(value) })
}

async function recordInspection() {
  const ok = await run(() => fulfillmentApi.recordInspection(orderId, {
    stage: inspectionForm.stage,
    result: inspectionForm.result,
    inspector: inspectionForm.inspector.trim(),
    notes: optional(inspectionForm.notes),
  }))
  if (ok) inspectionDialogOpen.value = false
}

async function createShipment() {
  const ok = await run(() => fulfillmentApi.createShipment(orderId, {
    transport_mode: shipmentForm.transport_mode,
    carrier: shipmentForm.carrier.trim(),
    tracking_number: optional(shipmentForm.tracking_number),
    container_number: optional(shipmentForm.container_number),
    port_of_loading: optional(shipmentForm.port_of_loading),
    port_of_discharge: optional(shipmentForm.port_of_discharge),
    etd: shipmentForm.etd || undefined,
    eta: shipmentForm.eta || undefined,
  }))
  if (ok) shipmentDialogOpen.value = false
}

async function updateShipment(shipmentId: string, payload: Record<string, unknown>) {
  await run(() => fulfillmentApi.updateShipment(orderId, shipmentId, payload))
}

async function departShipment(shipmentId: string, existingReference?: string) {
  if (existingReference) {
    await updateShipment(shipmentId, { status: 'departed' })
    return
  }
  const reference = await promptText('Bill of lading or tracking number', 'Mark departed')
  if (reference === null) return
  await updateShipment(shipmentId, { status: 'departed', bill_of_lading: reference })
}

function openPaymentDialog() {
  if (!order.value) return
  const paid = Number(order.value.amount_paid)
  const depositDue = Math.max(Number(order.value.deposit_required) - paid, 0)
  paymentForm.kind = depositDue > 0 ? 'deposit' : 'balance'
  paymentForm.amount = (depositDue > 0 ? depositDue : Number(order.value.balance_due)).toFixed(2)
  paymentForm.reference = ''
  paymentKey.value = newIdempotencyKey('payment')
  paymentDialogOpen.value = true
}

async function recordPayment() {
  if (!order.value) return
  const currency = order.value.currency
  const ok = await run(() => fulfillmentApi.recordPayment(orderId, {
    idempotency_key: paymentKey.value,
    kind: paymentForm.kind,
    amount: paymentForm.amount,
    currency,
    method: paymentForm.method,
    reference: optional(paymentForm.reference),
  }))
  if (ok) paymentDialogOpen.value = false
}

onMounted(load)
</script>

<style lang="scss" scoped>
.back-button {
  margin: 0 0 8px -12px;
  color: var(--text-secondary);
}

.heading-actions,
.action-row,
.row-title,
.card-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.card-header {
  justify-content: space-between;
}

.action-row {
  margin-top: 8px;
}

.spaced {
  margin-top: 16px;
}

.gate {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 12px;
  margin-top: 20px;
}

.blockers {
  margin: 0;
  padding-left: 18px;
  color: var(--color-warning);
  font-size: 13px;
  line-height: 1.7;
}

.metric-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;

  .metric-label {
    display: block;
    color: var(--text-secondary);
    font-size: 13px;
  }

  .metric-value {
    display: block;
    margin-top: 6px;
    color: var(--text-primary);
    font-size: 20px;
    font-weight: 650;
    font-variant-numeric: tabular-nums;
  }
}

.panel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 20px;
}

.row-item {
  padding: 10px 0;
  border-bottom: 1px solid var(--border-hairline);

  &:last-child {
    border-bottom: 0;
  }
}

.row-meta {
  margin: 4px 0 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0 12px;
}

.at-risk {
  color: var(--color-danger) !important;
}
</style>
