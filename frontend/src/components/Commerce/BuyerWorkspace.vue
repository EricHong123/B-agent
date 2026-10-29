<template>
  <div class="buyer-workspace">
    <el-card
      shadow="never"
      class="chat-card"
    >
      <AssistantChat
        ref="chat"
        :auth="auth"
        :placeholder="$t('Ask about products, MOQ, lead times, trade terms or your orders')"
        :empty-text="$t('Tell the assistant what you are sourcing; it fills an RFQ basket for a quotation.')"
        interactive
        @cart="(value: CartPayload) => (cart = value)"
        @add="addFromCard"
        @submit-rfq="rfqDialogOpen = true"
        @turn="refreshSide"
      />
    </el-card>

    <aside class="side">
      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span>{{ $t('RFQ basket') }}</span>
            <el-tag size="small">
              {{ cart?.item_count || 0 }}
            </el-tag>
          </div>
        </template>
        <el-empty
          v-if="!cart?.items.length"
          :description="$t('Nothing in the basket yet')"
          :image-size="48"
        />
        <ul
          v-else
          class="lines"
        >
          <li
            v-for="item in cart.items"
            :key="item.product_id"
          >
            <span>{{ item.quantity }} × {{ item.title }}</span>
            <span class="meta">{{ item.product_id }}</span>
          </li>
        </ul>
        <p
          v-if="cart?.items.length"
          class="meta"
        >
          {{ $t('List-price estimate') }}: {{ formatMoney(cart.subtotal, cart.currency) }}
        </p>
        <el-button
          type="primary"
          :disabled="!cart?.items.length"
          @click="rfqDialogOpen = true"
        >
          {{ $t('Submit RFQ') }}
        </el-button>
      </el-card>

      <el-card shadow="never">
        <template #header>
          {{ $t('Orders') }}
        </template>
        <el-empty
          v-if="!orders.length"
          :description="$t('No orders yet')"
          :image-size="48"
        />
        <ul
          v-else
          class="lines"
        >
          <li
            v-for="order in orders"
            :key="order.order_id"
          >
            <span>{{ order.order_id }}</span>
            <el-tag size="small">
              {{ $t(order.status) }}
            </el-tag>
          </li>
        </ul>
      </el-card>

      <el-card shadow="never">
        <template #header>
          {{ $t('What the assistant remembers') }}
        </template>
        <el-empty
          v-if="!facts.length"
          :description="$t('Nothing remembered')"
          :image-size="48"
        />
        <ul
          v-else
          class="lines"
        >
          <li
            v-for="fact in facts"
            :key="fact.key"
          >
            <span>{{ fact.key }}: {{ fact.value }}</span>
            <el-button
              text
              size="small"
              @click="forget(fact.key)"
            >
              {{ $t('Forget') }}
            </el-button>
          </li>
        </ul>
      </el-card>
    </aside>

    <el-dialog
      v-model="rfqDialogOpen"
      :title="$t('Submit RFQ')"
      width="min(480px, 92vw)"
    >
      <p class="meta">
        {{ $t('The sales team prices the basket and replies with a formal quotation. Nothing is ordered or charged.') }}
      </p>
      <el-input
        v-model="rfqNote"
        type="textarea"
        :rows="3"
        :placeholder="$t('Notes for the sales team (logo, packaging, destination port)')"
      />
      <template #footer>
        <el-button @click="rfqDialogOpen = false">
          {{ $t('Cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="submitting"
          @click="submitRfq"
        >
          {{ $t('Submit RFQ') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { commerceApi, type CartPayload, type CommerceSessionAuth } from '@/api/commerce'
import { formatMoney } from '@/api/fulfillment'
import { translate } from '@/i18n'
import AssistantChat from './AssistantChat.vue'

const props = defineProps<{ auth: CommerceSessionAuth | null }>()
const emit = defineEmits<{ (event: 'rfq', result: { opportunity_id: string, quote_number: string }): void }>()

const chat = ref<InstanceType<typeof AssistantChat> | null>(null)
const cart = ref<CartPayload | null>(null)
const orders = ref<any[]>([])
const facts = ref<{ key: string, value: string }[]>([])
const rfqDialogOpen = ref(false)
const rfqNote = ref('')
const submitting = ref(false)

async function refreshSide() {
  if (!props.auth) return
  const [basket, orderList, memory] = await Promise.all([
    commerceApi.cart(props.auth),
    commerceApi.orders(props.auth),
    commerceApi.memory(props.auth),
  ])
  cart.value = basket
  orders.value = orderList.orders
  facts.value = memory.facts
}

async function addFromCard(product: any) {
  if (!props.auth) return
  const moq = Number.parseInt(String(product.attributes?.moq || '1'), 10) || 1
  cart.value = await commerceApi.addToCart(props.auth, product.product_id, moq)
  ElMessage.success(translate('Added to the RFQ basket'))
}

async function submitRfq() {
  if (!props.auth) return
  submitting.value = true
  try {
    const result = await commerceApi.submitRfq(props.auth, rfqNote.value.trim() || undefined)
    rfqDialogOpen.value = false
    rfqNote.value = ''
    const warning = result.below_moq.length ? ` ${translate('Below MOQ')}: ${result.below_moq.join(', ')}` : ''
    ElMessage.success(translate('RFQ {number} sent to the sales team', { number: result.quote_number }) + warning)
    emit('rfq', result)
    await refreshSide()
  } finally {
    submitting.value = false
  }
}

async function forget(key: string) {
  if (!props.auth) return
  await commerceApi.forget(props.auth, key)
  await refreshSide()
}

watch(() => props.auth?.sessionId, () => {
  chat.value?.reset()
  refreshSide()
})
onMounted(refreshSide)
</script>

<style lang="scss" scoped>
.buyer-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
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

.lines {
  display: grid;
  gap: 6px;
  margin: 0 0 8px;
  padding: 0;
  list-style: none;

  li {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 6px;
  }
}

.meta {
  color: var(--text-secondary);
  font-size: 12px;
}

@media (max-width: 960px) {
  .buyer-workspace {
    grid-template-columns: 1fr;
  }
}
</style>
