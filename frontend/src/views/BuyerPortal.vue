<template>
  <div class="buyer-portal">
    <header class="portal-header">
      <div>
        <h1>{{ session ? session.customer_name : $t('Buyer portal') }}</h1>
        <p>{{ $t('Source products, check trade terms and request a quotation. Replies are written by an AI assistant; a person from our sales team prices every quotation.') }}</p>
      </div>
      <el-button
        text
        @click="toggleLocale"
      >
        {{ locale === 'zh-CN' ? 'English' : '中文' }}
      </el-button>
    </header>
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      :title="error"
    />
    <BuyerWorkspace
      v-else-if="auth"
      :auth="auth"
    />
    <el-skeleton
      v-else
      :rows="6"
      animated
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { commerceApi, type CommerceSessionAuth } from '@/api/commerce'
import { locale, toggleLocale, translate } from '@/i18n'
import BuyerWorkspace from '@/components/Commerce/BuyerWorkspace.vue'

const route = useRoute()
const token = typeof route.query.token === 'string' ? route.query.token : ''
const session = ref<Awaited<ReturnType<typeof commerceApi.startBuyerSession>> | null>(null)
const error = ref('')

const auth = computed<CommerceSessionAuth | null>(() =>
  session.value ? { role: 'buyer', sessionId: session.value.session_id, buyerToken: token } : null,
)

onMounted(async () => {
  if (!token) {
    error.value = translate('This page needs the portal link your sales contact sent you.')
    return
  }
  try {
    session.value = await commerceApi.startBuyerSession({ buyerToken: token })
  } catch {
    error.value = translate('This buyer portal link is not valid. Ask your sales contact for a new one.')
  }
})
</script>

<style lang="scss" scoped>
.buyer-portal {
  display: grid;
  gap: 20px;
  max-width: 1280px;
  min-height: 100dvh;
  margin: 0 auto;
  padding: 24px 16px;
  background: var(--surface-canvas);
}

.portal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;

  h1 {
    margin: 0;
    font-size: clamp(22px, 3vw, 30px);
  }

  p {
    max-width: 720px;
    margin: 6px 0 0;
    color: var(--text-secondary);
  }
}
</style>
