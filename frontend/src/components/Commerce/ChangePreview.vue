<template>
  <div class="change-preview">
    <header>
      <strong>{{ headline || change.summary }}</strong>
      <el-tag
        size="small"
        :type="statusType(change.status)"
      >
        {{ $t(`change.${change.status}`) }}
      </el-tag>
    </header>
    <el-table
      :data="change.items"
      size="small"
    >
      <el-table-column
        prop="target"
        :label="$t('Listing')"
        width="150"
      />
      <el-table-column
        prop="field"
        :label="$t('Field')"
        width="130"
      />
      <el-table-column :label="$t('Change')">
        <template #default="{ row }">
          <span class="before">{{ shown(row.before) }}</span> → <strong>{{ shown(row.after) }}</strong>
        </template>
      </el-table-column>
    </el-table>
    <p
      v-if="change.margin_before_pct != null && change.margin_after_pct != null"
      class="meta"
    >
      {{ $t('Margin') }} {{ change.margin_before_pct }}% → {{ change.margin_after_pct }}%
    </p>
    <p
      v-if="change.margin_impact != null"
      class="meta"
    >
      {{ $t('Estimated weekly margin impact') }}: {{ formatMoney(change.margin_impact, change.currency || 'USD') }}
    </p>
    <p
      v-for="note in change.guardrail_notes || []"
      :key="note"
      class="meta"
    >
      {{ note }}
    </p>
    <p
      v-if="change.status === 'staged'"
      class="meta"
    >
      {{ $t('Approving writes these values to the live catalog; it is refused if they changed since staging.') }}
    </p>
    <div
      v-if="change.status === 'staged'"
      class="actions"
    >
      <el-button
        type="primary"
        size="small"
        :disabled="!canApprove"
        :title="canApprove ? '' : $t('Only operators or admins approve staged changes')"
        @click="emit('action', 'apply')"
      >
        {{ $t('Approve and apply') }}
      </el-button>
      <el-button
        size="small"
        @click="emit('action', 'discard')"
      >
        {{ $t('Discard') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { StagedChange } from '@/api/commerce'
import { formatMoney } from '@/api/fulfillment'

defineProps<{ change: StagedChange, headline?: string | null, canApprove?: boolean }>()
const emit = defineEmits<{ (event: 'action', action: 'apply' | 'discard'): void }>()

function shown(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  return String(value).length > 80 ? `${String(value).slice(0, 77)}…` : String(value)
}

function statusType(status: string) {
  return ({ staged: 'warning', applied: 'success', discarded: 'info', expired: 'danger' } as Record<string, 'warning' | 'success' | 'info' | 'danger'>)[status] || 'info'
}
</script>

<style lang="scss" scoped>
.change-preview {
  display: grid;
  gap: 6px;

  header,
  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
  }
}

.before {
  color: var(--text-tertiary);
  text-decoration: line-through;
}

.meta {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}
</style>
