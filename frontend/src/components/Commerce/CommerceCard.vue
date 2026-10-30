<template>
  <div :class="['commerce-card', `card-${component}`]">
    <template v-if="component === 'products'">
      <h4 v-if="payload.title">
        {{ payload.title }}
      </h4>
      <div class="product-grid">
        <article
          v-for="entry in payload.items || []"
          :key="entry.product.product_id"
          class="product-tile"
        >
          <header>
            <strong>{{ entry.product.title }}</strong>
            <span class="sku">{{ entry.product.product_id }}</span>
          </header>
          <p class="price">
            {{ formatMoney(entry.product.price, entry.product.currency) }}
            <small v-if="entry.product.attributes?.moq">· MOQ {{ entry.product.attributes.moq }}</small>
          </p>
          <p
            v-if="entry.product.attributes?.lead_time"
            class="meta"
          >
            {{ $t('Lead time') }} {{ entry.product.attributes.lead_time }}
          </p>
          <p
            v-if="entry.reason"
            class="meta"
          >
            {{ entry.reason }}
          </p>
          <el-tag
            v-if="entry.product.attributes?.availability && entry.product.attributes.availability !== 'in stock'"
            size="small"
            :type="entry.product.in_stock ? 'info' : 'warning'"
          >
            {{ entry.product.in_stock ? $t('Made to order') : $t('out_of_stock') }}
          </el-tag>
          <el-button
            v-if="interactive && !hasOptions(entry.product)"
            size="small"
            type="primary"
            plain
            @click="emit('add', entry.product)"
          >
            {{ $t('Add to RFQ') }}
          </el-button>
          <span
            v-else-if="hasOptions(entry.product)"
            class="meta"
          >
            {{ $t('Ask for a variant') }}: {{ Object.keys(entry.product.options || {}).join(', ') }}
          </span>
        </article>
      </div>
    </template>

    <template v-else-if="component === 'comparison'">
      <h4 v-if="payload.title">
        {{ payload.title }}
      </h4>
      <el-table
        :data="payload.entries || []"
        size="small"
      >
        <el-table-column :label="$t('Product')">
          <template #default="{ row }">
            <strong>{{ row.product?.title }}</strong>
            <el-tag
              v-if="row.product_id === payload.recommended_product_id"
              size="small"
              type="success"
            >
              {{ $t('Recommended') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          :label="$t('Unit price')"
          width="120"
        >
          <template #default="{ row }">
            {{ formatMoney(row.product?.price, row.product?.currency) }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('Pros')">
          <template #default="{ row }">
            {{ (row.pros || []).join('; ') }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('Cons')">
          <template #default="{ row }">
            {{ (row.cons || []).join('; ') }}
          </template>
        </el-table-column>
      </el-table>
    </template>

    <template v-else-if="component === 'plan'">
      <h4>{{ payload.title }}</h4>
      <p v-if="payload.intro">
        {{ payload.intro }}
      </p>
      <ol>
        <li
          v-for="(step, index) in payload.steps || []"
          :key="index"
        >
          <strong>{{ step.label }}</strong>
          <span v-if="step.detail"> — {{ step.detail }}</span>
          <span
            v-if="step.products?.length"
            class="meta"
          > ({{ step.products.map((p: any) => p.product_id).join(', ') }})</span>
        </li>
      </ol>
    </template>

    <template v-else-if="component === 'guide'">
      <h4>{{ payload.title }}</h4>
      <section
        v-for="(section, index) in payload.sections || []"
        :key="index"
      >
        <h5>{{ section.heading }}</h5>
        <p>{{ section.body }}</p>
      </section>
      <p
        v-if="payload.evidence?.length"
        class="meta"
      >
        {{ $t('Sources') }}:
        <el-tag
          v-for="item in payload.evidence"
          :key="`${item.source_id}-${item.version}`"
          size="small"
        >
          {{ item.source_id }} v{{ item.version }}
        </el-tag>
      </p>
    </template>

    <template v-else-if="component === 'order_status'">
      <h4>{{ payload.order_id }}</h4>
      <p>{{ payload.summary }}</p>
      <p
        v-if="payload.next_step"
        class="meta"
      >
        {{ payload.next_step }}
      </p>
      <p
        v-if="payload.order"
        class="meta"
      >
        {{ $t(payload.order.status) }} · {{ formatMoney(payload.order.total, payload.order.currency) }}
        <template v-if="payload.order.estimated_delivery">
          · {{ payload.order.estimated_delivery }}
        </template>
      </p>
    </template>

    <template v-else-if="component === 'checkout'">
      <h4>{{ $t('RFQ basket') }}</h4>
      <ul class="lines">
        <li
          v-for="item in payload.cart?.items || []"
          :key="item.product_id"
        >
          {{ item.quantity }} × {{ item.title }} <span class="meta">({{ item.product_id }})</span>
          <span class="amount">{{ formatMoney(item.price * item.quantity, payload.cart.currency) }}</span>
        </li>
      </ul>
      <p class="meta">
        {{ $t('List-price estimate') }}: {{ formatMoney(payload.cart?.subtotal, payload.cart?.currency) }}
      </p>
      <el-button
        v-if="interactive"
        type="primary"
        size="small"
        @click="emit('submitRfq')"
      >
        {{ $t('Submit RFQ') }}
      </el-button>
    </template>

    <template v-else-if="component === 'disclosure'">
      <h4>{{ payload.title }}</h4>
      <el-descriptions
        :column="1"
        border
        size="small"
      >
        <el-descriptions-item
          v-for="row in payload.rows || []"
          :key="row.label"
          :label="row.label"
        >
          {{ row.value }} <span
            v-if="row.note"
            class="meta"
          >({{ row.note }})</span>
        </el-descriptions-item>
      </el-descriptions>
      <p
        v-for="note in payload.footnotes || []"
        :key="note"
        class="meta"
      >
        {{ note }}
      </p>
    </template>

    <template v-else-if="component === 'suggestions'">
      <div class="chips">
        <el-button
          v-for="chip in payload.suggestions || []"
          :key="chip"
          size="small"
          round
          @click="emit('send', chip)"
        >
          {{ chip }}
        </el-button>
      </div>
    </template>

    <template v-else-if="component === 'metrics'">
      <h4 v-if="payload.title">
        {{ payload.title }}
      </h4>
      <div class="metric-grid">
        <div
          v-for="metric in payload.metrics || []"
          :key="metric.metric"
          class="metric"
        >
          <span class="meta">{{ $t(metric.metric) }}</span>
          <strong>{{ metric.currency ? formatMoney(metric.value, metric.currency) : metric.value ?? '—' }}</strong>
          <span
            v-if="metric.change_pct != null"
            :class="metric.change_pct >= 0 ? 'up' : 'down'"
          >{{ metric.change_pct >= 0 ? '+' : '' }}{{ metric.change_pct }}%</span>
          <svg
            v-if="metric.series?.points?.length > 1"
            class="spark"
            viewBox="0 0 100 24"
            preserveAspectRatio="none"
          >
            <polyline
              :points="sparkline(metric.series.points)"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
            />
          </svg>
        </div>
      </div>
      <p
        v-if="payload.period"
        class="meta"
      >
        {{ payload.period }}
      </p>
    </template>

    <template v-else-if="component === 'digest'">
      <h4>{{ payload.title || $t('Daily digest') }}</h4>
      <ul class="digest">
        <li
          v-for="(item, index) in payload.items || []"
          :key="index"
        >
          <el-tag size="small">
            {{ $t(item.kind) }}
          </el-tag>
          <strong>{{ item.headline }}</strong>
          <p
            v-if="item.why_it_matters"
            class="meta"
          >
            {{ item.why_it_matters }}
          </p>
        </li>
      </ul>
    </template>

    <template v-else-if="component === 'change_preview'">
      <ChangePreview
        :change="payload.change"
        :headline="payload.headline"
        :can-approve="canApprove"
        @action="(action: 'apply' | 'discard') => emit('changeAction', payload.change.change_id, action)"
      />
    </template>

    <pre
      v-else
      class="raw"
    >{{ payload }}</pre>
  </div>
</template>

<script setup lang="ts">
import { formatMoney } from '@/api/fulfillment'
import ChangePreview from './ChangePreview.vue'

defineProps<{
  component: string
  payload: any
  interactive?: boolean
  canApprove?: boolean
}>()

const emit = defineEmits<{
  (event: 'add', product: any): void
  (event: 'send', text: string): void
  (event: 'submitRfq'): void
  (event: 'changeAction', changeId: string, action: 'apply' | 'discard'): void
}>()

function hasOptions(product: any) {
  return Object.keys(product?.options || {}).length > 0
}

function sparkline(points: { value: number }[]) {
  const values = points.map((point) => point.value)
  const min = Math.min(...values)
  const span = Math.max(...values) - min || 1
  return values
    .map((value, index) => `${(index / (values.length - 1)) * 100},${22 - ((value - min) / span) * 20}`)
    .join(' ')
}
</script>

<style lang="scss" scoped>
.commerce-card {
  margin: 8px 0;
  padding: 12px;
  border: 1px solid var(--border-hairline);
  border-radius: var(--radius-control);
  background: var(--surface-panel);

  h4 {
    margin: 0 0 8px;
    font-size: 14px;
  }

  h5 {
    margin: 8px 0 4px;
    font-size: 13px;
  }

  p {
    margin: 4px 0;
  }
}

.product-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}

.product-tile {
  display: grid;
  gap: 4px;
  padding: 10px;
  border: 1px solid var(--border-hairline);
  border-radius: var(--radius-control);

  header {
    display: grid;
    gap: 2px;
  }
}

.sku,
.meta {
  color: var(--text-secondary);
  font-size: 12px;
}

.price {
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.lines {
  margin: 0;
  padding-left: 16px;

  .amount {
    float: right;
    font-variant-numeric: tabular-nums;
  }
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.card-suggestions {
  padding: 0;
  border: 0;
  background: transparent;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}

.metric {
  display: grid;
  gap: 2px;

  strong {
    font-size: 18px;
    font-variant-numeric: tabular-nums;
  }

  .up {
    color: var(--color-success);
  }

  .down {
    color: var(--color-danger);
  }
}

.spark {
  width: 100%;
  height: 24px;
  color: var(--brand-accent);
}

.digest {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.raw {
  overflow: auto;
  max-height: 200px;
  font-size: 12px;
}
</style>
