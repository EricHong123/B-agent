<template>
  <div class="buyer-assistant page-stack">
    <header class="page-heading">
      <div>
        <p class="page-kicker">
          {{ $t('Commerce assistants') }}
        </p>
        <h1>{{ $t('Buyer assistant') }}</h1>
        <p>{{ $t('Search the catalog, compare products, answer trade-term questions and build an RFQ for a customer, or send them their own portal link.') }}</p>
      </div>
      <div class="heading-actions">
        <el-select
          v-model="customerId"
          filterable
          remote
          :remote-method="searchCustomers"
          :placeholder="$t('Choose a customer')"
          style="width: 260px"
          @change="startSession"
        >
          <el-option
            v-for="customer in customers"
            :key="customer.id"
            :label="customer.company_name || customer.username || customer.email"
            :value="customer.id"
          />
        </el-select>
        <el-button
          :disabled="!customerId"
          @click="createInvite"
        >
          <el-icon><Link /></el-icon>
          {{ $t('Buyer portal link') }}
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
      :title="$t('No AI model is configured for the commerce assistants. Browsing and the RFQ basket still work.')"
    />

    <el-empty
      v-if="!auth"
      :description="$t('Choose a customer to start an assisted buyer session')"
    />
    <BuyerWorkspace
      v-else
      :auth="auth"
      @rfq="(result) => $router.push({ path: '/fulfillment', query: { opportunity: result.opportunity_id } })"
    />

    <el-dialog
      v-model="inviteDialogOpen"
      :title="$t('Buyer portal link')"
      width="min(560px, 92vw)"
    >
      <p class="meta">
        {{ $t('Send this link to the customer. It opens their own buyer assistant and expires on {date}.', { date: invite ? new Date(invite.expires_at).toLocaleDateString() : '' }) }}
      </p>
      <el-input
        :model-value="inviteUrl"
        readonly
      >
        <template #append>
          <el-button @click="copyInvite">
            {{ $t('Copy') }}
          </el-button>
        </template>
      </el-input>
      <p class="meta">
        {{ $t('The link is shown once. Revoke it below if it is shared by mistake.') }}
      </p>
      <el-table
        :data="invites"
        size="small"
      >
        <el-table-column :label="$t('Created')">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleDateString() }}
          </template>
        </el-table-column>
        <el-table-column :label="$t('Last used')">
          <template #default="{ row }">
            {{ row.last_used_at ? new Date(row.last_used_at).toLocaleString() : '—' }}
          </template>
        </el-table-column>
        <el-table-column width="110">
          <template #default="{ row }">
            <el-tag
              v-if="row.revoked_at"
              size="small"
              type="info"
            >
              {{ $t('Revoked') }}
            </el-tag>
            <el-button
              v-else
              text
              size="small"
              type="danger"
              @click="revokeInvite(row.id)"
            >
              {{ $t('Revoke') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import { commerceApi, type CommerceSessionAuth } from '@/api/commerce'
import { customerApi } from '@/api/customer'
import { translate } from '@/i18n'
import BuyerWorkspace from '@/components/Commerce/BuyerWorkspace.vue'

const route = useRoute()
const customers = ref<{ id: number, username?: string, email?: string, company_name?: string }[]>([])
const customerId = ref<number | undefined>()
const session = ref<Awaited<ReturnType<typeof commerceApi.startBuyerSession>> | null>(null)
const inviteDialogOpen = ref(false)
const invite = ref<Awaited<ReturnType<typeof commerceApi.createInvite>> | null>(null)
const invites = ref<Awaited<ReturnType<typeof commerceApi.listInvites>>>([])

const auth = computed<CommerceSessionAuth | null>(() => (session.value ? { role: 'buyer', sessionId: session.value.session_id } : null))
const inviteUrl = computed(() => (invite.value ? `${window.location.origin}${invite.value.portal_path}` : ''))

async function searchCustomers(query: string) {
  const data = await customerApi.list({ page: 1, page_size: 20, search: query || undefined })
  customers.value = data.items as typeof customers.value
}

async function startSession() {
  if (!customerId.value) return
  session.value = await commerceApi.startBuyerSession({ customerId: customerId.value })
}

async function resetSession() {
  if (!auth.value || !session.value) return
  const fresh = await commerceApi.reset(auth.value)
  session.value = { ...session.value, session_id: fresh.session_id }
}

async function createInvite() {
  if (!customerId.value) return
  invite.value = await commerceApi.createInvite(customerId.value)
  invites.value = await commerceApi.listInvites(customerId.value)
  inviteDialogOpen.value = true
}

async function revokeInvite(id: string) {
  if (!customerId.value) return
  await commerceApi.revokeInvite(id)
  invites.value = await commerceApi.listInvites(customerId.value)
}

async function copyInvite() {
  await navigator.clipboard.writeText(inviteUrl.value)
  ElMessage.success(translate('Copied'))
}

onMounted(async () => {
  await searchCustomers('')
  const fromQuery = Number(route.query.customer)
  if (Number.isInteger(fromQuery) && fromQuery > 0) {
    customerId.value = fromQuery
    await startSession()
  }
})
</script>

<style lang="scss" scoped>
.heading-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.meta {
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
