<template>
  <div class="commerce-admin page-stack">
    <header class="page-heading">
      <div>
        <p class="page-kicker">
          {{ $t('Commerce assistants') }}
        </p>
        <h1>{{ $t('Catalog and assistant quality') }}</h1>
        <p>{{ $t('The catalog and versioned trade terms both assistants answer from, the handoff queue, and resolution metrics.') }}</p>
      </div>
      <div class="heading-actions">
        <el-tag
          v-if="status"
          :type="status.model_configured ? 'success' : 'warning'"
        >
          {{ status.provider }} · {{ status.model }}
        </el-tag>
        <el-button
          v-if="isAdmin"
          @click="seed"
        >
          {{ $t('Load demo catalog') }}
        </el-button>
      </div>
    </header>

    <el-card shadow="never">
      <el-tabs v-model="tab">
        <el-tab-pane
          :label="$t('Catalog')"
          name="catalog"
        >
          <el-button
            v-if="isAdmin"
            type="primary"
            size="small"
            class="spaced"
            @click="editProduct()"
          >
            <el-icon><Plus /></el-icon>
            {{ $t('New product') }}
          </el-button>
          <el-table
            :data="products"
            size="small"
            row-key="listing_id"
          >
            <el-table-column
              prop="listing_id"
              label="SKU"
              width="140"
            />
            <el-table-column
              prop="title"
              :label="$t('Product')"
              min-width="220"
            />
            <el-table-column
              prop="category"
              :label="$t('Category')"
              width="120"
            />
            <el-table-column
              :label="$t('Unit price')"
              width="120"
            >
              <template #default="{ row }">
                {{ formatMoney(row.price, row.currency) }}
              </template>
            </el-table-column>
            <el-table-column
              prop="moq"
              label="MOQ"
              width="80"
            />
            <el-table-column
              prop="stock"
              :label="$t('stock')"
              width="90"
            />
            <el-table-column
              :label="$t('Status')"
              width="120"
            >
              <template #default="{ row }">
                <el-tag size="small">
                  {{ $t(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="$t('Content')"
              width="120"
            >
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="row.content_quality === 'good' ? 'success' : 'warning'"
                >
                  {{ $t(row.content_quality || 'unknown') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="isAdmin"
              width="90"
            >
              <template #default="{ row }">
                <el-button
                  text
                  size="small"
                  @click="editProduct(row)"
                >
                  {{ $t('Edit') }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane
          :label="$t('Trade terms')"
          name="terms"
        >
          <el-button
            v-if="isAdmin"
            type="primary"
            size="small"
            class="spaced"
            @click="termDialogOpen = true"
          >
            <el-icon><Plus /></el-icon>
            {{ $t('New version') }}
          </el-button>
          <el-table
            :data="terms"
            size="small"
          >
            <el-table-column
              prop="source_id"
              :label="$t('Source')"
              width="160"
            />
            <el-table-column
              prop="version"
              :label="$t('Version')"
              width="80"
            />
            <el-table-column
              prop="title"
              :label="$t('Title')"
              width="200"
            />
            <el-table-column
              :label="$t('In force')"
              width="100"
            >
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="row.in_force ? 'success' : 'info'"
                >
                  {{ $t(row.in_force ? 'Yes' : 'No') }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="content"
              :label="$t('Content')"
              min-width="300"
            />
          </el-table>
        </el-tab-pane>

        <el-tab-pane
          :label="$t('Campaigns')"
          name="campaigns"
        >
          <el-table
            :data="campaigns"
            size="small"
          >
            <el-table-column
              prop="name"
              :label="$t('Campaign')"
              min-width="200"
            />
            <el-table-column
              prop="channel"
              :label="$t('Channel')"
              width="110"
            />
            <el-table-column
              :label="$t('Status')"
              width="100"
            >
              <template #default="{ row }">
                {{ $t(row.status) }}
              </template>
            </el-table-column>
            <el-table-column
              :label="$t('Budget')"
              width="120"
            >
              <template #default="{ row }">
                {{ formatMoney(row.budget, row.currency) }}
              </template>
            </el-table-column>
            <el-table-column
              :label="$t('Revenue')"
              width="120"
            >
              <template #default="{ row }">
                {{ row.revenue != null ? formatMoney(row.revenue, row.currency) : '—' }}
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane
          :label="$t('Handoff queue')"
          name="handoffs"
        >
          <el-empty
            v-if="!handoffs.length"
            :description="$t('No open handoffs')"
            :image-size="56"
          />
          <article
            v-for="ticket in handoffs"
            :key="ticket.ticket"
            class="ticket"
          >
            <header>
              <strong>{{ ticket.ticket }}</strong>
              <el-tag size="small">
                {{ $t(ticket.role === 'buyer' ? 'Buyer assistant' : 'Operations assistant') }}
              </el-tag>
              <el-tag
                size="small"
                type="info"
              >
                {{ $t(ticket.brief.reason) }}
              </el-tag>
              <span class="meta">{{ new Date(ticket.created_at).toLocaleString() }}</span>
              <el-button
                size="small"
                @click="resolve(ticket.ticket)"
              >
                {{ $t('Mark resolved') }}
              </el-button>
            </header>
            <p v-if="ticket.brief.request">
              “{{ ticket.brief.request }}”
            </p>
            <p class="meta">
              {{ $t('Tried') }}: {{ ticket.brief.tried.tools.map((tool) => `${tool.name} (${tool.status})`).join(', ') || '—' }}
            </p>
            <p
              v-if="ticket.brief.tried.fallbacks.length"
              class="meta"
            >
              {{ $t('Fell back because') }}: {{ ticket.brief.tried.fallbacks.join(', ') }}
            </p>
          </article>
        </el-tab-pane>

        <el-tab-pane
          :label="$t('Assistant metrics')"
          name="metrics"
        >
          <div
            v-if="metrics"
            class="metrics-grid"
          >
            <el-card
              v-for="(values, role) in metrics.roles"
              :key="role"
              shadow="never"
            >
              <template #header>
                {{ $t(role === 'buyer' ? 'Buyer assistant' : 'Operations assistant') }}
              </template>
              <el-descriptions
                :column="1"
                size="small"
                border
              >
                <el-descriptions-item :label="$t('Effective sessions')">
                  {{ values.effective_sessions }}
                </el-descriptions-item>
                <el-descriptions-item
                  v-for="key in rateKeys"
                  :key="key"
                  :label="$t(key)"
                >
                  {{ percent(values[key]) }}
                </el-descriptions-item>
                <el-descriptions-item :label="$t('Latency p50 (ms)')">
                  {{ values.latency_p50_ms ?? '—' }}
                </el-descriptions-item>
              </el-descriptions>
            </el-card>
          </div>
          <p class="meta">
            {{ $t('Definitions follow commerce/docs/metrics.md, version {version}, over the last 30 days.', { version: metrics?.definitions_version || '' }) }}
          </p>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog
      v-model="productDialogOpen"
      :title="$t(productForm.isNew ? 'New product' : 'Edit product')"
      width="min(640px, 94vw)"
    >
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="SKU">
            <el-input
              v-model="productForm.id"
              :disabled="!productForm.isNew"
            />
          </el-form-item>
          <el-form-item :label="$t('Category')">
            <el-input v-model="productForm.category" />
          </el-form-item>
        </div>
        <el-form-item :label="$t('Product')">
          <el-input v-model="productForm.title" />
        </el-form-item>
        <el-form-item :label="$t('Short description')">
          <el-input v-model="productForm.short_description" />
        </el-form-item>
        <div class="form-grid">
          <el-form-item :label="$t('Unit price')">
            <el-input v-model="productForm.price" />
          </el-form-item>
          <el-form-item :label="$t('Unit cost')">
            <el-input v-model="productForm.unit_cost" />
          </el-form-item>
          <el-form-item label="MOQ">
            <el-input-number
              v-model="productForm.moq"
              :min="1"
            />
          </el-form-item>
          <el-form-item :label="$t('Lead time (days)')">
            <el-input-number
              v-model="productForm.lead_time_days"
              :min="1"
            />
          </el-form-item>
          <el-form-item :label="$t('stock')">
            <el-input-number
              v-model="productForm.stock"
              :min="0"
            />
          </el-form-item>
          <el-form-item :label="$t('Status')">
            <el-select v-model="productForm.status">
              <el-option
                v-for="option in ['active', 'paused', 'draft']"
                :key="option"
                :label="$t(option)"
                :value="option"
              />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item :label="$t('Attributes (one key=value per line)')">
          <el-input
            v-model="productForm.attributes"
            type="textarea"
            :rows="4"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="productDialogOpen = false">
          {{ $t('Cancel') }}
        </el-button>
        <el-button
          type="primary"
          @click="saveProduct"
        >
          {{ $t('Save') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="termDialogOpen"
      :title="$t('New terms version')"
      width="min(560px, 94vw)"
    >
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item :label="$t('Source')">
            <el-input
              v-model="termForm.source_id"
              placeholder="terms/payment"
            />
          </el-form-item>
          <el-form-item :label="$t('Version')">
            <el-input v-model="termForm.version" />
          </el-form-item>
        </div>
        <el-form-item :label="$t('Title')">
          <el-input v-model="termForm.title" />
        </el-form-item>
        <el-form-item :label="$t('Content')">
          <el-input
            v-model="termForm.content"
            type="textarea"
            :rows="4"
          />
        </el-form-item>
        <el-form-item :label="$t('Effective from')">
          <el-date-picker
            v-model="termForm.effective_at"
            type="datetime"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="termDialogOpen = false">
          {{ $t('Cancel') }}
        </el-button>
        <el-button
          type="primary"
          @click="saveTerm"
        >
          {{ $t('Save') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { commerceApi } from '@/api/commerce'
import { formatMoney } from '@/api/fulfillment'
import { useAuthStore } from '@/stores/auth'
import { translate } from '@/i18n'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin)
const tab = ref('catalog')
const status = ref<Awaited<ReturnType<typeof commerceApi.status>> | null>(null)
const products = ref<any[]>([])
const terms = ref<any[]>([])
const campaigns = ref<any[]>([])
const handoffs = ref<Awaited<ReturnType<typeof commerceApi.handoffs>>>([])
const metrics = ref<Awaited<ReturnType<typeof commerceApi.metrics>> | null>(null)
const rateKeys = ['resolution_rate', 'first_turn_resolution_rate', 'self_service_rate', 'handoff_rate', 'negative_feedback_rate', 'grounded_turn_rate', 'system_error_rate']

const productDialogOpen = ref(false)
const productForm = reactive({
  isNew: true,
  id: '',
  title: '',
  category: '',
  short_description: '',
  price: '',
  unit_cost: '',
  moq: 1,
  lead_time_days: 30,
  stock: 0,
  status: 'active',
  attributes: '',
})
const termDialogOpen = ref(false)
const termForm = reactive({ source_id: '', version: '', title: '', content: '', effective_at: new Date() })

function percent(value: { value: number | null } | undefined) {
  return value?.value == null ? '—' : `${(value.value * 100).toFixed(1)}%`
}

async function load() {
  const [statusData, productRows, termRows, campaignRows, handoffRows, metricData] = await Promise.all([
    commerceApi.status(),
    commerceApi.catalogProducts(),
    commerceApi.terms(),
    commerceApi.campaigns(),
    commerceApi.handoffs(),
    commerceApi.metrics(),
  ])
  status.value = statusData
  products.value = productRows
  terms.value = termRows
  campaigns.value = campaignRows
  handoffs.value = handoffRows
  metrics.value = metricData
}

async function seed() {
  const created = await commerceApi.seedDemo()
  ElMessage.success(translate('Demo catalog loaded: {products} products, {terms} terms', created))
  await load()
}

function editProduct(row?: any) {
  Object.assign(productForm, {
    isNew: !row,
    id: row?.listing_id || '',
    title: row?.title || '',
    category: row?.category || '',
    short_description: row?.short_description || '',
    price: row ? String(row.price) : '',
    unit_cost: row?.unit_cost != null ? String(row.unit_cost) : '',
    moq: row?.moq || 1,
    lead_time_days: row?.lead_time_days || 30,
    stock: row?.stock || 0,
    status: row?.status === 'out_of_stock' ? 'active' : row?.status || 'active',
    attributes: Object.entries(row?.attributes || {})
      .filter(([key]) => !['moq', 'lead_time'].includes(key))
      .map(([key, value]) => `${key}=${value}`)
      .join('\n'),
  })
  productDialogOpen.value = true
}

async function saveProduct() {
  const attributes = Object.fromEntries(
    productForm.attributes
      .split('\n')
      .map((line) => line.split('='))
      .filter((parts) => parts.length >= 2 && parts[0].trim())
      .map(([key, ...value]) => [key.trim(), value.join('=').trim()]),
  )
  await commerceApi.saveProduct({
    id: productForm.id.trim().toUpperCase(),
    title: productForm.title.trim(),
    category: productForm.category.trim() || null,
    short_description: productForm.short_description.trim() || null,
    price: productForm.price,
    unit_cost: productForm.unit_cost || null,
    moq: productForm.moq,
    lead_time_days: productForm.lead_time_days,
    stock: productForm.stock,
    status: productForm.status,
    attributes,
  })
  productDialogOpen.value = false
  ElMessage.success(translate('Saved'))
  await load()
}

async function saveTerm() {
  await commerceApi.createTerm({
    source_id: termForm.source_id.trim(),
    version: termForm.version.trim(),
    title: termForm.title.trim(),
    content: termForm.content.trim(),
    effective_at: termForm.effective_at.toISOString(),
  })
  termDialogOpen.value = false
  ElMessage.success(translate('Saved'))
  await load()
}

async function resolve(ticket: string) {
  await commerceApi.resolveHandoff(ticket)
  handoffs.value = await commerceApi.handoffs()
}

onMounted(load)
</script>

<style lang="scss" scoped>
.heading-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.spaced {
  margin-bottom: 12px;
}

.ticket {
  padding: 12px 0;
  border-bottom: 1px solid var(--border-hairline);

  header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }

  p {
    margin: 6px 0 0;
  }
}

.meta {
  color: var(--text-secondary);
  font-size: 12px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0 12px;
}
</style>
