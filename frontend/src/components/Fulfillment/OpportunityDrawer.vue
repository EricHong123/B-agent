<template>
  <el-drawer
    :model-value="modelValue"
    :title="opportunity?.title || $t('Opportunity')"
    size="min(760px, 100vw)"
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
  >
    <div
      v-if="opportunity"
      v-loading="loading"
      class="drawer-stack"
    >
      <section class="summary-row">
        <el-tag :type="opportunity.stage === 'won' ? 'success' : opportunity.stage === 'lost' ? 'danger' : 'primary'">
          {{ $t(opportunity.stage) }}
        </el-tag>
        <span>{{ opportunity.customer_name }}</span>
        <span v-if="opportunity.estimated_value">{{ formatMoney(opportunity.estimated_value, opportunity.currency) }}</span>
        <el-button
          v-if="opportunity.conversation_id"
          text
          size="small"
          @click="$router.push(`/conversations/${opportunity.conversation_id}`)"
        >
          {{ $t('View conversation') }}
        </el-button>
        <el-button
          v-if="opportunity.order_id"
          type="primary"
          size="small"
          @click="emit('orderCreated', opportunity.order_id)"
        >
          {{ $t('Open order') }}
        </el-button>
      </section>

      <p
        v-if="opportunity.inquiry_summary"
        class="inquiry"
      >
        {{ opportunity.inquiry_summary }}
      </p>
      <el-alert
        v-if="opportunity.lost_reason"
        type="error"
        :closable="false"
        :title="`${$t('Lost')}: ${opportunity.lost_reason}`"
      />

      <el-card shadow="never">
        <template #header>
          {{ $t('Requirements') }}
        </template>
        <div class="form-grid">
          <el-input
            v-model="requirements.product"
            :placeholder="$t('Product')"
            :disabled="closed"
          />
          <el-input
            v-model="requirements.quantity"
            :placeholder="$t('Quantity')"
            :disabled="closed"
          />
          <el-input
            v-model="requirements.unit"
            :placeholder="$t('Unit')"
            :disabled="closed"
          />
          <el-input
            v-model="requirements.target_price"
            :placeholder="$t('Target price')"
            :disabled="closed"
          />
          <el-input
            v-model="requirements.destination_country"
            :placeholder="$t('Destination')"
            :disabled="closed"
          />
        </div>
        <div
          v-if="!closed"
          class="action-row"
        >
          <el-button
            size="small"
            :loading="saving"
            @click="saveRequirements"
          >
            {{ $t('Save requirements') }}
          </el-button>
          <el-button
            v-for="stage in opportunity.allowed_stages"
            :key="stage"
            size="small"
            :type="stage === 'lost' ? 'danger' : 'primary'"
            plain
            @click="moveStage(stage)"
          >
            {{ $t(stage === 'lost' ? 'Mark lost' : 'Move to {stage}', { stage: $t(stage) }) }}
          </el-button>
        </div>
        <div
          v-else-if="opportunity.stage === 'lost'"
          class="action-row"
        >
          <el-button
            size="small"
            @click="moveStage('qualified')"
          >
            {{ $t('Reopen') }}
          </el-button>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span>{{ $t('Quotations') }}</span>
            <el-button
              v-if="canQuote"
              type="primary"
              size="small"
              @click="openQuoteDialog"
            >
              <el-icon><Plus /></el-icon>
              {{ $t('New revision') }}
            </el-button>
          </div>
        </template>
        <el-empty
          v-if="!quotations.length"
          :description="$t(canQuote ? 'No quotations yet' : 'Qualify the inquiry to start quoting')"
          :image-size="56"
        />
        <article
          v-for="quote in quotations"
          :key="quote.id"
          class="quote"
        >
          <header class="quote-header">
            <strong>{{ quote.quote_number }}</strong>
            <el-tag
              size="small"
              :type="quoteType(quote.status)"
            >
              {{ $t(`quote.${quote.status}`) }}
            </el-tag>
            <el-tag
              v-if="quote.expired"
              size="small"
              type="danger"
            >
              {{ $t('expired') }}
            </el-tag>
            <el-tag
              v-if="quote.requires_escalated_approval && ['draft', 'approval_pending'].includes(quote.status)"
              size="small"
              type="warning"
            >
              {{ $t('Needs admin approval') }}
            </el-tag>
            <span class="quote-total">{{ formatMoney(quote.total, quote.currency) }}</span>
          </header>
          <p class="quote-meta">
            {{ quote.incoterm }} · {{ quote.payment_terms }} · {{ $t('Lead time') }} {{ quote.lead_time_days }}d ·
            {{ $t('Valid until') }} {{ quote.valid_until }}
            <template v-if="quote.margin_percent">
              · {{ $t('Margin') }} {{ quote.margin_percent }}%
            </template>
          </p>
          <el-table
            :data="quote.line_items"
            size="small"
          >
            <el-table-column
              prop="product"
              :label="$t('Product')"
              min-width="160"
            />
            <el-table-column
              :label="$t('Quantity')"
              width="120"
            >
              <template #default="{ row }">
                {{ row.quantity }} {{ row.unit }}
              </template>
            </el-table-column>
            <el-table-column
              prop="unit_price"
              :label="$t('Unit price')"
              width="110"
            />
            <el-table-column
              prop="amount"
              :label="$t('Amount')"
              width="120"
            />
          </el-table>
          <div class="action-row">
            <el-button
              v-if="quote.status === 'draft'"
              size="small"
              type="primary"
              @click="act(() => fulfillmentApi.submitQuotation(quote.id))"
            >
              {{ $t('Submit for approval') }}
            </el-button>
            <template v-if="quote.status === 'approval_pending'">
              <el-button
                size="small"
                type="success"
                @click="review(quote, 'approve')"
              >
                {{ $t('Approve') }}
              </el-button>
              <el-button
                size="small"
                type="danger"
                plain
                @click="review(quote, 'reject')"
              >
                {{ $t('Reject') }}
              </el-button>
            </template>
            <el-button
              v-if="quote.status === 'approved'"
              size="small"
              type="primary"
              @click="act(() => fulfillmentApi.sendQuotation(quote.id, 'email'))"
            >
              {{ $t('Mark as sent') }}
            </el-button>
            <template v-if="quote.status === 'sent'">
              <el-button
                size="small"
                type="success"
                @click="openAcceptDialog(quote)"
              >
                {{ $t('Customer accepted') }}
              </el-button>
              <el-button
                size="small"
                plain
                @click="decline(quote)"
              >
                {{ $t('Customer declined') }}
              </el-button>
            </template>
          </div>
        </article>
      </el-card>

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
            <span v-if="event.to_status && !event.event_type.startsWith('quotation.')"> → {{ $t(event.to_status) }}</span>
          </el-timeline-item>
        </el-timeline>
      </el-card>
    </div>

    <el-dialog
      v-model="quoteDialogOpen"
      :title="$t('New quotation revision')"
      width="min(820px, 96vw)"
      append-to-body
    >
      <div class="form-grid">
        <el-form-item :label="$t('Currency')">
          <el-input
            v-model="quoteForm.currency"
            maxlength="3"
          />
        </el-form-item>
        <el-form-item :label="$t('Incoterm')">
          <el-select v-model="quoteForm.incoterm">
            <el-option
              v-for="term in incoterms"
              :key="term"
              :label="term"
              :value="term"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('Deposit %')">
          <el-input-number
            v-model="quoteForm.deposit_percent"
            :min="0"
            :max="100"
          />
        </el-form-item>
        <el-form-item :label="$t('Lead time (days)')">
          <el-input-number
            v-model="quoteForm.lead_time_days"
            :min="1"
            :max="365"
          />
        </el-form-item>
        <el-form-item :label="$t('Valid for (days)')">
          <el-input-number
            v-model="quoteForm.valid_days"
            :min="1"
            :max="180"
          />
        </el-form-item>
      </div>
      <el-form-item :label="$t('Payment terms')">
        <el-input v-model="quoteForm.payment_terms" />
      </el-form-item>
      <div
        v-for="(line, index) in quoteForm.line_items"
        :key="index"
        class="line-grid"
      >
        <el-input
          v-model="line.product"
          :placeholder="$t('Product')"
        />
        <el-input
          v-model="line.quantity"
          :placeholder="$t('Quantity')"
        />
        <el-input
          v-model="line.unit"
          :placeholder="$t('Unit')"
        />
        <el-input
          v-model="line.unit_price"
          :placeholder="$t('Unit price')"
        />
        <el-input
          v-model="line.unit_cost"
          :placeholder="$t('Unit cost')"
        />
        <el-button
          text
          :disabled="quoteForm.line_items.length === 1"
          @click="quoteForm.line_items.splice(index, 1)"
        >
          <el-icon><Delete /></el-icon>
        </el-button>
      </div>
      <el-button
        text
        @click="quoteForm.line_items.push(emptyLine())"
      >
        <el-icon><Plus /></el-icon>
        {{ $t('Add line') }}
      </el-button>
      <div class="form-grid">
        <el-form-item :label="$t('Freight')">
          <el-input v-model="quoteForm.freight_amount" />
        </el-form-item>
        <el-form-item :label="$t('Discount')">
          <el-input v-model="quoteForm.discount_amount" />
        </el-form-item>
      </div>
      <p class="quote-preview">
        {{ $t('Estimated total') }}: <strong>{{ formatMoney(previewTotal, quoteForm.currency || 'USD') }}</strong>
      </p>
      <template #footer>
        <el-button @click="quoteDialogOpen = false">
          {{ $t('Cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="createQuotation"
        >
          {{ $t('Create draft') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="acceptDialogOpen"
      :title="$t('Convert to order')"
      width="min(520px, 92vw)"
      append-to-body
    >
      <el-form label-position="top">
        <el-form-item :label="$t('Fulfillment mode')">
          <el-radio-group v-model="acceptForm.fulfillment_mode">
            <el-radio-button value="in_house">
              {{ $t('in_house') }}
            </el-radio-button>
            <el-radio-button value="outsourced">
              {{ $t('outsourced') }}
            </el-radio-button>
            <el-radio-button value="mixed">
              {{ $t('mixed') }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="$t('Customer PO number')">
          <el-input v-model="acceptForm.customer_po_number" />
        </el-form-item>
        <el-form-item :label="$t('Required ship date')">
          <el-date-picker
            v-model="acceptForm.required_ship_date"
            type="date"
            value-format="YYYY-MM-DD"
          />
        </el-form-item>
        <el-form-item :label="$t('Shipping address')">
          <el-input
            v-model="acceptForm.shipping_address"
            type="textarea"
            :rows="2"
          />
        </el-form-item>
        <el-form-item>
          <el-switch
            v-model="acceptForm.balance_before_shipment"
            :active-text="$t('Balance due before shipment')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="acceptDialogOpen = false">
          {{ $t('Cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          @click="acceptQuotation"
        >
          {{ $t('Create order') }}
        </el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  fulfillmentApi,
  formatMoney,
  type FulfillmentEvent,
  type FulfillmentMode,
  type Opportunity,
  type OpportunityRequirements,
  type OpportunityStage,
  type Quotation,
  type QuotationLineItem,
} from '@/api/fulfillment'
import { translate } from '@/i18n'
import { promptText } from '@/composables/usePromptText'

const props = defineProps<{ modelValue: boolean, opportunityId: string | null }>()
const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'changed'): void
  (event: 'orderCreated', orderId: string): void
}>()

const incoterms = ['EXW', 'FCA', 'FOB', 'CFR', 'CIF', 'CPT', 'CIP', 'DAP', 'DPU', 'DDP']
const loading = ref(false)
const saving = ref(false)
const opportunity = ref<Opportunity | null>(null)
const quotations = ref<Quotation[]>([])
const events = ref<FulfillmentEvent[]>([])
const requirements = reactive<OpportunityRequirements>({})
const quoteDialogOpen = ref(false)
const acceptDialogOpen = ref(false)
const acceptingQuote = ref<Quotation | null>(null)

const emptyLine = (): QuotationLineItem => ({ product: '', quantity: '', unit: 'pcs', unit_price: '', unit_cost: '' })
const quoteForm = reactive({
  currency: 'USD',
  incoterm: 'FOB',
  payment_terms: '30% T/T deposit, 70% before shipment',
  deposit_percent: 30,
  lead_time_days: 30,
  valid_days: 15,
  line_items: [emptyLine()],
  freight_amount: '0',
  discount_amount: '0',
})
const acceptForm = reactive({
  fulfillment_mode: 'in_house' as FulfillmentMode,
  customer_po_number: '',
  required_ship_date: '',
  shipping_address: '',
  balance_before_shipment: true,
})

const closed = computed(() => ['won', 'lost'].includes(opportunity.value?.stage || ''))
const canQuote = computed(() => ['qualified', 'quoting', 'negotiation'].includes(opportunity.value?.stage || ''))
const previewTotal = computed(() => {
  const subtotal = quoteForm.line_items.reduce(
    (total, line) => total + Number(line.quantity || 0) * Number(line.unit_price || 0),
    0
  )
  return subtotal + Number(quoteForm.freight_amount || 0) - Number(quoteForm.discount_amount || 0)
})

async function load() {
  if (!props.opportunityId) return
  loading.value = true
  try {
    const [row, quotes, timeline] = await Promise.all([
      fulfillmentApi.getOpportunity(props.opportunityId),
      fulfillmentApi.listQuotations(props.opportunityId),
      fulfillmentApi.events({ opportunity_id: props.opportunityId }),
    ])
    opportunity.value = row
    quotations.value = [...quotes].reverse()
    events.value = timeline
    Object.keys(requirements).forEach((key) => delete requirements[key as keyof OpportunityRequirements])
    Object.assign(requirements, row.requirements)
  } finally {
    loading.value = false
  }
}

async function act(action: () => Promise<unknown>) {
  saving.value = true
  try {
    await action()
    await load()
    emit('changed')
  } finally {
    saving.value = false
  }
}

function cleanRequirements(): OpportunityRequirements {
  return Object.fromEntries(
    Object.entries(requirements).filter(([, value]) => value !== '' && value !== undefined && value !== null)
  ) as OpportunityRequirements
}

async function saveRequirements() {
  if (!opportunity.value) return
  const id = opportunity.value.id
  await act(() => fulfillmentApi.updateOpportunity(id, { requirements: cleanRequirements() }))
  ElMessage.success(translate('Saved'))
}

async function moveStage(stage: OpportunityStage) {
  if (!opportunity.value) return
  const id = opportunity.value.id
  let reason: string | undefined
  if (stage === 'lost') {
    const value = await promptText('Why was this opportunity lost?', 'Mark lost')
    if (value === null) return
    reason = value
  }
  await act(async () => {
    if (stage === 'qualified' && opportunity.value?.stage === 'inquiry') {
      await fulfillmentApi.updateOpportunity(id, { requirements: cleanRequirements() })
    }
    await fulfillmentApi.transitionOpportunity(id, stage, reason)
  })
}

function openQuoteDialog() {
  const latest = quotations.value[0]
  Object.assign(quoteForm, {
    currency: latest?.currency || opportunity.value?.currency || 'USD',
    incoterm: latest?.incoterm || requirements.incoterm || 'FOB',
    payment_terms: latest?.payment_terms || quoteForm.payment_terms,
    deposit_percent: latest?.deposit_percent ?? 30,
    lead_time_days: latest?.lead_time_days ?? 30,
    line_items: latest
      ? latest.line_items.map((line) => ({ ...line, unit_cost: '' }))
      : [{ ...emptyLine(), product: requirements.product || '', quantity: requirements.quantity || '', unit: requirements.unit || 'pcs' }],
  })
  quoteDialogOpen.value = true
}

async function createQuotation() {
  if (!opportunity.value) return
  const id = opportunity.value.id
  const lineItems = quoteForm.line_items.map((line) => ({
    product: line.product.trim(),
    quantity: line.quantity,
    unit: line.unit || 'pcs',
    unit_price: line.unit_price,
    ...(line.unit_cost ? { unit_cost: line.unit_cost } : {}),
  }))
  await act(() => fulfillmentApi.createQuotation(id, {
    ...quoteForm,
    currency: quoteForm.currency.toUpperCase(),
    line_items: lineItems,
  }))
  quoteDialogOpen.value = false
}

async function review(quote: Quotation, decision: 'approve' | 'reject') {
  const note = await promptText('Review note', decision === 'approve' ? 'Approve' : 'Reject')
  if (note === null) return
  await act(() => fulfillmentApi.reviewQuotation(quote.id, decision, note))
}

async function decline(quote: Quotation) {
  const reason = await promptText('Why did the customer decline?', 'Customer declined')
  if (reason === null) return
  await act(() => fulfillmentApi.declineQuotation(quote.id, reason))
}

function openAcceptDialog(quote: Quotation) {
  acceptingQuote.value = quote
  acceptDialogOpen.value = true
}

async function acceptQuotation() {
  if (!acceptingQuote.value) return
  saving.value = true
  try {
    const order = await fulfillmentApi.acceptQuotation(acceptingQuote.value.id, {
      fulfillment_mode: acceptForm.fulfillment_mode,
      customer_po_number: acceptForm.customer_po_number.trim() || undefined,
      required_ship_date: acceptForm.required_ship_date || undefined,
      shipping_address: acceptForm.shipping_address.trim() || undefined,
      balance_before_shipment: acceptForm.balance_before_shipment,
    })
    acceptDialogOpen.value = false
    ElMessage.success(translate('Order {number} created', { number: order.order_number }))
    emit('changed')
    emit('orderCreated', order.id)
  } finally {
    saving.value = false
  }
}

function quoteType(status: string) {
  const types: Record<string, 'success' | 'danger' | 'warning' | 'primary' | 'info'> = {
    accepted: 'success',
    approved: 'success',
    rejected: 'danger',
    declined: 'danger',
    approval_pending: 'warning',
    sent: 'primary',
  }
  return types[status] || 'info'
}

watch(
  () => [props.modelValue, props.opportunityId] as const,
  ([open]) => {
    if (open) load()
  },
  { immediate: true }
)
</script>

<style lang="scss" scoped>
.drawer-stack {
  display: grid;
  gap: 16px;
}

.summary-row,
.action-row,
.quote-header,
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
  margin-top: 12px;
}

.inquiry {
  margin: 0;
  padding: 12px;
  border-radius: var(--radius-control);
  background: var(--surface-muted);
  color: var(--text-secondary);
  white-space: pre-wrap;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px 12px;
}

.line-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 0.8fr 1fr 1fr auto;
  gap: 8px;
  margin-bottom: 8px;
}

.quote {
  padding: 12px 0;
  border-bottom: 1px solid var(--border-hairline);

  &:last-child {
    border-bottom: 0;
  }
}

.quote-total {
  margin-left: auto;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.quote-meta,
.quote-preview {
  margin: 6px 0 10px;
  color: var(--text-secondary);
  font-size: 13px;
}

@media (max-width: 640px) {
  .line-grid {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
