<template>
  <div class="fulfillment page-stack">
    <header class="page-heading">
      <div>
        <p class="page-kicker">
          {{ $t('Revenue operations') }}
        </p>
        <h1>{{ $t('Fulfillment') }}</h1>
        <p>{{ $t('Follow every inquiry from qualification and quotation through production, inspection, shipment and payment.') }}</p>
      </div>
      <div class="heading-actions">
        <el-button
          :loading="loading"
          @click="refresh"
        >
          <el-icon><Refresh /></el-icon>
          {{ $t('Refresh') }}
        </el-button>
        <el-button
          type="primary"
          @click="createDialogOpen = true"
        >
          <el-icon><Plus /></el-icon>
          {{ $t('New opportunity') }}
        </el-button>
      </div>
    </header>

    <section
      v-if="overview"
      class="metric-row"
    >
      <el-card
        v-for="metric in metrics"
        :key="metric.label"
        shadow="never"
        class="metric-card"
      >
        <span class="metric-label">{{ $t(metric.label) }}</span>
        <strong class="metric-value">{{ metric.value }}</strong>
      </el-card>
    </section>

    <el-card
      v-if="overview"
      shadow="never"
    >
      <template #header>
        {{ $t('Lead-to-delivery funnel') }}
      </template>
      <ol class="funnel">
        <li
          v-for="step in funnel"
          :key="step.label"
          class="funnel-step"
        >
          <span class="funnel-count">{{ step.count }}</span>
          <span class="funnel-label">{{ $t(step.label) }}</span>
        </li>
      </ol>
    </el-card>

    <div
      v-if="overview"
      class="attention-grid"
    >
      <el-card shadow="never">
        <template #header>
          {{ $t('Needs attention') }}
        </template>
        <el-empty
          v-if="!overview.alerts.length"
          :description="$t('Nothing is blocked or at risk')"
          :image-size="64"
        />
        <ul
          v-else
          class="alert-list"
        >
          <li
            v-for="(alert, index) in overview.alerts"
            :key="`${alert.kind}-${index}`"
            :class="['alert-item', alert.severity]"
          >
            <el-tag
              size="small"
              :type="severityType(alert.severity)"
            >
              {{ $t(alert.kind) }}
            </el-tag>
            <span class="alert-message">{{ alert.message }}</span>
            <el-button
              v-if="alert.order_id"
              text
              size="small"
              @click="openOrder(alert.order_id)"
            >
              {{ $t('Open order') }}
            </el-button>
            <el-button
              v-else-if="alert.opportunity_id"
              text
              size="small"
              @click="openOpportunity(alert.opportunity_id)"
            >
              {{ $t('Open') }}
            </el-button>
          </li>
        </ul>
      </el-card>

      <el-card shadow="never">
        <template #header>
          {{ $t('Buying inquiries without an opportunity') }}
        </template>
        <el-empty
          v-if="!overview.unconverted_inquiries.length"
          :description="$t('Every buying inquiry is in the pipeline')"
          :image-size="64"
        />
        <ul
          v-else
          class="alert-list"
        >
          <li
            v-for="inquiry in overview.unconverted_inquiries"
            :key="inquiry.conversation_id"
            class="alert-item"
          >
            <el-tag size="small">
              {{ $t(inquiry.intent) }}
            </el-tag>
            <span class="alert-message">{{ inquiry.customer_name }}</span>
            <el-button
              text
              size="small"
              @click="$router.push(`/conversations/${inquiry.conversation_id}`)"
            >
              {{ $t('View') }}
            </el-button>
            <el-button
              type="primary"
              text
              size="small"
              @click="convertInquiry(inquiry.conversation_id)"
            >
              {{ $t('Create opportunity') }}
            </el-button>
          </li>
        </ul>
      </el-card>
    </div>

    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <el-tab-pane
          :label="$t('Opportunities')"
          name="opportunities"
        >
          <el-table
            v-loading="loading"
            :data="opportunities"
            @row-click="(row: Opportunity) => openOpportunity(row.id)"
          >
            <el-table-column
              prop="title"
              :label="$t('Opportunity')"
              min-width="220"
            />
            <el-table-column
              prop="customer_name"
              :label="$t('Customer')"
              min-width="160"
            />
            <el-table-column
              :label="$t('Stage')"
              width="140"
            >
              <template #default="{ row }">
                <el-tag :type="stageType(row.stage)">
                  {{ $t(row.stage) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="$t('Value')"
              width="150"
            >
              <template #default="{ row }">
                {{ row.estimated_value ? formatMoney(row.estimated_value, row.currency) : '—' }}
              </template>
            </el-table-column>
            <el-table-column
              prop="quotation_count"
              :label="$t('Quotations')"
              width="110"
            />
          </el-table>
        </el-tab-pane>
        <el-tab-pane
          :label="$t('Orders')"
          name="orders"
        >
          <el-table
            v-loading="loading"
            :data="orders"
            @row-click="(row: OrderSummary) => openOrder(row.id)"
          >
            <el-table-column
              prop="order_number"
              :label="$t('Order')"
              min-width="170"
            />
            <el-table-column
              prop="customer_name"
              :label="$t('Customer')"
              min-width="160"
            />
            <el-table-column
              :label="$t('Status')"
              width="150"
            >
              <template #default="{ row }">
                <el-tag :type="orderType(row.status)">
                  {{ $t(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="$t('Production')"
              width="150"
            >
              <template #default="{ row }">
                <el-progress
                  :percentage="row.production_progress_percent"
                  :stroke-width="6"
                />
              </template>
            </el-table-column>
            <el-table-column
              :label="$t('Ship by')"
              width="140"
            >
              <template #default="{ row }">
                <span :class="{ 'at-risk': row.ship_date_at_risk }">{{ row.required_ship_date || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column
              :label="$t('Balance due')"
              width="150"
            >
              <template #default="{ row }">
                {{ formatMoney(row.balance_due, row.currency) }}
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog
      v-model="createDialogOpen"
      :title="$t('New opportunity')"
      width="min(560px, 92vw)"
    >
      <el-form
        label-position="top"
        @submit.prevent
      >
        <el-form-item :label="$t('Customer')">
          <el-select
            v-model="createForm.customer_id"
            filterable
            remote
            :remote-method="searchCustomers"
            :loading="customerSearchLoading"
            :placeholder="$t('Search customers')"
          >
            <el-option
              v-for="customer in customerOptions"
              :key="customer.id"
              :label="customer.company_name || customer.username || customer.email"
              :value="customer.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('Title')">
          <el-input v-model="createForm.title" />
        </el-form-item>
        <el-form-item :label="$t('Inquiry summary')">
          <el-input
            v-model="createForm.inquiry_summary"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
        <div class="form-grid">
          <el-form-item :label="$t('Product')">
            <el-input v-model="createForm.product" />
          </el-form-item>
          <el-form-item :label="$t('Quantity')">
            <el-input v-model="createForm.quantity" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="createDialogOpen = false">
          {{ $t('Cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="saving"
          :disabled="!createForm.customer_id || createForm.title.trim().length < 3"
          @click="createOpportunity"
        >
          {{ $t('Create') }}
        </el-button>
      </template>
    </el-dialog>

    <OpportunityDrawer
      v-model="drawerOpen"
      :opportunity-id="selectedOpportunityId"
      @changed="refresh"
      @order-created="openOrder"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { customerApi } from '@/api/customer'
import {
  fulfillmentApi,
  formatMoney,
  type Opportunity,
  type OrderSummary,
  type PipelineOverview,
} from '@/api/fulfillment'
import { translate } from '@/i18n'
import OpportunityDrawer from '@/components/Fulfillment/OpportunityDrawer.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const overview = ref<PipelineOverview | null>(null)
const opportunities = ref<Opportunity[]>([])
const orders = ref<OrderSummary[]>([])
const activeTab = ref('opportunities')
const drawerOpen = ref(false)
const selectedOpportunityId = ref<string | null>(null)
const createDialogOpen = ref(false)
const customerSearchLoading = ref(false)
const customerOptions = ref<{ id: number, username?: string, email?: string, company_name?: string }[]>([])
const createForm = reactive({
  customer_id: undefined as number | undefined,
  title: '',
  inquiry_summary: '',
  product: '',
  quantity: '',
})

const sumStages = (keys: string[]) => (overview.value?.opportunities || [])
  .filter((stage) => keys.includes(stage.key))
  .reduce((total, stage) => total + stage.count, 0)
const orderCount = (keys: string[]) => (overview.value?.orders || [])
  .filter((stage) => keys.includes(stage.key))
  .reduce((total, stage) => total + stage.count, 0)

const metrics = computed(() => {
  const data = overview.value
  if (!data) return []
  const leads = Object.values(data.leads).reduce((total, count) => total + count, 0)
  return [
    { label: 'Leads', value: String(leads) },
    { label: 'Open opportunities', value: String(sumStages(['inquiry', 'qualified', 'quoting', 'negotiation'])) },
    { label: 'Win rate', value: data.win_rate_percent ? `${data.win_rate_percent}%` : '—' },
    { label: 'Booked value', value: formatMoney(data.booked_value) },
    { label: 'Collected', value: formatMoney(data.collected_value) },
  ]
})

const funnel = computed(() => {
  const data = overview.value
  if (!data) return []
  const sentOutreach = data.outreach.sent || 0
  return [
    { label: 'Leads', count: Object.values(data.leads).reduce((total, count) => total + count, 0) },
    { label: 'Outreach sent', count: sentOutreach },
    { label: 'Inquiries', count: sumStages(['inquiry', 'qualified', 'quoting', 'negotiation', 'won', 'lost']) },
    { label: 'Quoted', count: sumStages(['quoting', 'negotiation', 'won']) },
    { label: 'Won', count: sumStages(['won']) },
    { label: 'In production', count: orderCount(['confirmed', 'in_production', 'quality_check']) },
    { label: 'Shipped', count: orderCount(['ready_to_ship', 'shipped']) },
    { label: 'Delivered', count: orderCount(['delivered', 'completed']) },
  ]
})

async function refresh() {
  loading.value = true
  try {
    const [pipeline, opportunityRows, orderRows] = await Promise.all([
      fulfillmentApi.pipeline(),
      fulfillmentApi.listOpportunities(),
      fulfillmentApi.listOrders(),
    ])
    overview.value = pipeline
    opportunities.value = opportunityRows
    orders.value = orderRows
  } finally {
    loading.value = false
  }
}

async function searchCustomers(query: string) {
  customerSearchLoading.value = true
  try {
    const data = await customerApi.list({ page: 1, page_size: 20, search: query || undefined })
    customerOptions.value = data.items as typeof customerOptions.value
  } finally {
    customerSearchLoading.value = false
  }
}

async function createOpportunity() {
  if (!createForm.customer_id) return
  saving.value = true
  try {
    const created = await fulfillmentApi.createOpportunity({
      customer_id: createForm.customer_id,
      title: createForm.title.trim(),
      inquiry_summary: createForm.inquiry_summary.trim() || undefined,
      requirements: {
        product: createForm.product.trim() || undefined,
        quantity: createForm.quantity.trim() || undefined,
      },
    })
    createDialogOpen.value = false
    Object.assign(createForm, { customer_id: undefined, title: '', inquiry_summary: '', product: '', quantity: '' })
    ElMessage.success(translate('Opportunity created'))
    await refresh()
    openOpportunity(created.id)
  } finally {
    saving.value = false
  }
}

async function convertInquiry(conversationId: string) {
  const created = await fulfillmentApi.createOpportunityFromConversation(conversationId)
  ElMessage.success(translate('Opportunity created'))
  await refresh()
  openOpportunity(created.id)
}

function openOpportunity(id: string) {
  selectedOpportunityId.value = id
  drawerOpen.value = true
}

function openOrder(id: string) {
  router.push(`/orders/${id}`)
}

function severityType(severity: string) {
  return ({ critical: 'danger', warning: 'warning', info: 'info' } as Record<string, 'danger' | 'warning' | 'info'>)[severity] || 'info'
}

function stageType(stage: string) {
  const types: Record<string, 'success' | 'danger' | 'warning' | 'primary' | 'info'> = {
    won: 'success',
    lost: 'danger',
    negotiation: 'warning',
    quoting: 'primary',
  }
  return types[stage] || 'info'
}

function orderType(status: string) {
  const types: Record<string, 'success' | 'danger' | 'warning' | 'primary' | 'info'> = {
    completed: 'success',
    delivered: 'success',
    shipped: 'primary',
    cancelled: 'danger',
    quality_check: 'warning',
  }
  return types[status] || 'info'
}

onMounted(async () => {
  await Promise.all([refresh(), searchCustomers('')])
  const opportunityId = route.query.opportunity
  if (typeof opportunityId === 'string') openOpportunity(opportunityId)
})
</script>

<style lang="scss" scoped>
.heading-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.metric-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}

.metric-card {
  .metric-label {
    display: block;
    color: var(--text-secondary);
    font-size: 13px;
  }

  .metric-value {
    display: block;
    margin-top: 6px;
    color: var(--text-primary);
    font-size: 24px;
    font-weight: 650;
    font-variant-numeric: tabular-nums;
  }
}

.funnel {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.funnel-step {
  display: grid;
  gap: 4px;
  padding: 12px;
  border: 1px solid var(--border-hairline);
  border-radius: var(--radius-control);
  background: var(--surface-muted);

  .funnel-count {
    color: var(--text-primary);
    font-size: 20px;
    font-weight: 650;
    font-variant-numeric: tabular-nums;
  }

  .funnel-label {
    color: var(--text-secondary);
    font-size: 12px;
  }
}

.attention-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 20px;
}

.alert-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.alert-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-left: 3px solid var(--border-color);
  border-radius: 6px;
  background: var(--surface-muted);

  &.critical {
    border-left-color: var(--color-danger);
  }

  &.warning {
    border-left-color: var(--color-warning);
  }

  .alert-message {
    flex: 1;
    min-width: 160px;
    color: var(--text-primary);
    font-size: 13px;
  }
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0 12px;
}

.at-risk {
  color: var(--color-danger);
  font-weight: 600;
}

:deep(.el-table__row) {
  cursor: pointer;
}
</style>
