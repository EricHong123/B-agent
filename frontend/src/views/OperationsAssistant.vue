<template>
  <div class="operations-assistant page-stack">
    <header class="page-heading">
      <div>
        <p class="page-kicker">
          {{ $t('Commerce assistants') }}
        </p>
        <h1>{{ $t('Operations assistant') }}</h1>
        <p>{{ $t('Explain performance, maintain listings, act on stock and order alerts, price and promote, and draft campaigns. Every write waits here for an operator to approve it.') }}</p>
      </div>
      <div class="heading-actions">
        <el-button
          :disabled="!auth"
          @click="refresh"
        >
          <el-icon><Refresh /></el-icon>
          {{ $t('Refresh') }}
        </el-button>
        <el-button
          :disabled="!auth"
          @click="resetSession"
        >
          {{ $t('New conversation') }}
        </el-button>
      </div>
    </header>

    <el-alert
      v-if="session && !session.model_configured"
      type="warning"
      :closable="false"
      :title="$t('No AI model is configured for the commerce assistants. The overview and approval queue still work.')"
    />

    <section
      v-if="overview"
      class="metric-row"
    >
      <el-card
        v-for="metric in metrics"
        :key="metric.label"
        shadow="never"
      >
        <span class="metric-label">{{ $t(metric.label) }}</span>
        <strong class="metric-value">{{ metric.value }}</strong>
        <span
          v-if="metric.change != null"
          :class="['metric-change', metric.change >= 0 ? 'up' : 'down']"
        >{{ metric.change >= 0 ? '+' : '' }}{{ metric.change }}%</span>
      </el-card>
    </section>

    <div class="layout">
      <el-card
        shadow="never"
        class="chat-card"
      >
        <AssistantChat
          ref="chat"
          :auth="auth"
          :can-approve="session?.can_approve"
          :placeholder="$t('Ask how the business is doing, or what to restock, reprice or promote')"
          :empty-text="$t('Try: give me today’s digest, or which listings need content fixes?')"
          @change="onChange"
          @change-action="act"
          @turn="refresh"
        />
      </el-card>

      <aside class="side">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>{{ $t('Waiting for approval') }}</span>
              <el-tag
                size="small"
                type="warning"
              >
                {{ pending.length }}
              </el-tag>
            </div>
          </template>
          <el-empty
            v-if="!pending.length"
            :description="$t('Nothing staged')"
            :image-size="48"
          />
          <ChangePreview
            v-for="change in pending"
            :key="change.change_id"
            class="queued"
            :change="change"
            :can-approve="session?.can_approve"
            @action="(action) => act(change.change_id, action)"
          />
        </el-card>

        <el-card
          v-if="overview"
          shadow="never"
        >
          <template #header>
            {{ $t('Needs attention') }}
          </template>
          <ul class="attention">
            <li
              v-for="alert in overview.needs_attention.inventory"
              :key="`${alert.kind}-${alert.listing_id}`"
            >
              <el-tag
                size="small"
                :type="alert.kind === 'low_stock' ? 'danger' : 'info'"
              >
                {{ $t(alert.kind) }}
              </el-tag>
              {{ alert.title }} · {{ $t('stock') }} {{ alert.stock }}
            </li>
            <li
              v-for="issue in overview.needs_attention.order_issues"
              :key="issue.issue_id"
            >
              <el-tag
                size="small"
                type="warning"
              >
                {{ $t(issue.kind) }}
              </el-tag>
              {{ issue.order_id }} · {{ issue.summary }}
            </li>
          </ul>
        </el-card>

        <el-card
          v-if="overview?.recent_changes.length"
          shadow="never"
        >
          <template #header>
            {{ $t('Recent decisions') }}
          </template>
          <ul class="attention">
            <li
              v-for="change in overview.recent_changes"
              :key="change.change_id"
            >
              <el-tag size="small">
                {{ $t(`change.${change.status}`) }}
              </el-tag>
              {{ change.summary }}
            </li>
          </ul>
        </el-card>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { commerceApi, type CommerceSessionAuth, type StagedChange } from '@/api/commerce'
import { formatMoney } from '@/api/fulfillment'
import { translate } from '@/i18n'
import AssistantChat from '@/components/Commerce/AssistantChat.vue'
import ChangePreview from '@/components/Commerce/ChangePreview.vue'

const session = ref<Awaited<ReturnType<typeof commerceApi.startOperationsSession>> | null>(null)
const overview = ref<Awaited<ReturnType<typeof commerceApi.overview>> | null>(null)
const pending = ref<StagedChange[]>([])
const chat = ref<InstanceType<typeof AssistantChat> | null>(null)

const auth = computed<CommerceSessionAuth | null>(() => (session.value ? { role: 'operations', sessionId: session.value.session_id } : null))

const metrics = computed(() => {
  const snapshot = overview.value?.snapshot
  if (!snapshot) return []
  return [
    { label: 'Booked value', value: formatMoney(snapshot.sales, snapshot.currency), change: snapshot.sales_change_pct },
    { label: 'Orders', value: String(snapshot.orders), change: snapshot.orders_change_pct },
    { label: 'Inquiries', value: String(snapshot.traffic ?? 0), change: snapshot.traffic_change_pct },
    { label: 'Inquiry-to-order rate', value: snapshot.conversion_rate != null ? `${snapshot.conversion_rate}%` : '—', change: snapshot.conversion_change_pct },
    { label: 'Pending approvals', value: String(snapshot.alerts?.pending_changes ?? 0), change: null },
  ]
})

async function refresh() {
  if (!auth.value) return
  const [view, changes] = await Promise.all([commerceApi.overview(auth.value), commerceApi.changes(auth.value)])
  overview.value = view
  pending.value = changes.pending
}

function onChange(change: StagedChange) {
  const index = pending.value.findIndex((item) => item.change_id === change.change_id)
  if (change.status === 'staged') {
    if (index >= 0) pending.value[index] = change
    else pending.value.push(change)
  } else if (index >= 0) {
    pending.value.splice(index, 1)
  }
}

async function act(changeId: string, action: 'apply' | 'discard') {
  if (!auth.value) return
  const result = await commerceApi.changeAction(auth.value, changeId, action)
  if (result.ok) {
    ElMessage.success(translate(action === 'apply' ? 'Change applied' : 'Change discarded'))
  } else {
    ElMessage.warning(result.reason || translate('The change could not go through'))
  }
  await refresh()
}

async function resetSession() {
  if (!auth.value || !session.value) return
  const fresh = await commerceApi.reset(auth.value)
  session.value = { ...session.value, session_id: fresh.session_id }
  chat.value?.reset()
}

onMounted(async () => {
  session.value = await commerceApi.startOperationsSession()
  await refresh()
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
    font-size: 22px;
    font-weight: 650;
    font-variant-numeric: tabular-nums;
  }

  .metric-change {
    font-size: 12px;

    &.up {
      color: var(--color-success);
    }

    &.down {
      color: var(--color-danger);
    }
  }
}

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  gap: 20px;
}

.side {
  display: grid;
  align-content: start;
  gap: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
}

.queued {
  padding: 10px 0;
  border-bottom: 1px solid var(--border-hairline);

  &:last-child {
    border-bottom: 0;
  }
}

.attention {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  font-size: 13px;
  list-style: none;
}

@media (max-width: 1080px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>
