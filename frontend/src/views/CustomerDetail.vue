<template>
  <div class="customer-detail page-stack">
    <header class="page-heading">
      <div>
        <el-button
          text
          class="back-button"
          @click="$router.back()"
        >
          <el-icon><ArrowLeft /></el-icon>
          {{ $t('Customers') }}
        </el-button>
        <h1>{{ customer?.username || $t('Customer Detail') }}</h1>
        <p>{{ $t('Identity, contact details and current engagement classification.') }}</p>
      </div>
      <el-button
        v-if="customer"
        type="primary"
        plain
        @click="$router.push({ path: '/buyer-assistant', query: { customer: customer.id } })"
      >
        <el-icon><ShoppingCart /></el-icon>
        {{ $t('Open buyer assistant') }}
      </el-button>
    </header>

    <el-descriptions
      v-if="customer"
      class="detail-surface"
      :column="3"
      border
    >
      <el-descriptions-item :label="$t('Email')">
        <div class="email-verification">
          <span>{{ customer.email || $t('No email') }}</span>
          <el-tag
            v-if="verificationStatus"
            :type="verificationTagType"
            effect="light"
            round
          >
            {{ $t(verificationStatus) }}
          </el-tag>
          <el-button
            v-if="customer.email"
            size="small"
            :loading="verifying"
            @click="verifyEmail"
          >
            {{ $t('Verify email') }}
          </el-button>
        </div>
      </el-descriptions-item>
      <el-descriptions-item :label="$t('WhatsApp')">
        {{ customer.whatsapp }}
      </el-descriptions-item>
      <el-descriptions-item :label="$t('Platform')">
        {{ customer.platform }}
      </el-descriptions-item>
      <el-descriptions-item :label="$t('Country')">
        {{ customer.country }}
      </el-descriptions-item>
      <el-descriptions-item :label="$t('Category')">
        {{ customer.category }}
      </el-descriptions-item>
      <el-descriptions-item :label="$t('Followers')">
        {{ customer.follower_count }}
      </el-descriptions-item>
      <el-descriptions-item :label="$t('Status')">
        <el-tag :type="getStatusType(customer.status)">
          {{ $t(customer.status) }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item :label="$t('Intent Level')">
        <el-tag
          v-if="customer.intent_level"
          :type="getIntentType(customer.intent_level)"
        >
          {{ $t(customer.intent_level) }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item :label="$t('Tags')">
        <el-tag
          v-for="tag in customer.tags"
          :key="tag"
          style="margin-right: 4px"
        >
          {{ tag }}
        </el-tag>
      </el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { customerApi } from '@/api/customer'
import { translate } from '@/i18n'

const route = useRoute()
const customer = ref<any>(null)
const verifying = ref(false)
const verificationStatus = ref('')

const verificationTagType = computed(() => {
  if (verificationStatus.value === 'valid') return 'success'
  if (['invalid', 'disposable', 'legal_restricted'].includes(verificationStatus.value)) {
    return 'danger'
  }
  return 'warning'
})

async function fetchCustomer() {
  try {
    customer.value = await customerApi.get(Number(route.params.id))
    verificationStatus.value = customer.value.custom_fields?.email_verification_status || ''
  } catch {
    // Handle error
  }
}

async function verifyEmail() {
  verifying.value = true
  try {
    const result = await customerApi.verifyEmail(Number(route.params.id))
    verificationStatus.value = result.status
    ElMessage.success(translate('Email verification completed.'))
  } catch (error: any) {
    if (error?.response?.status === 451) {
      verificationStatus.value = 'legal_restricted'
      ElMessage.error(translate('This contact is legally restricted and outreach is blocked.'))
    }
  } finally {
    verifying.value = false
  }
}

function getStatusType(status: string) {
  const types: Record<string, any> = {
    new: 'info',
    contacted: 'primary',
    engaged: 'warning',
    converted: 'success',
    lost: 'danger',
  }
  return types[status] || 'info'
}

function getIntentType(level: string) {
  const types: Record<string, any> = {
    low: 'info',
    medium: 'primary',
    high: 'warning',
    very_high: 'success',
  }
  return types[level] || 'info'
}

onMounted(() => {
  fetchCustomer()
})
</script>

<style lang="scss" scoped>
.back-button {
  margin: 0 0 8px -12px;
  color: var(--text-secondary);
}

.detail-surface {
  overflow: hidden;
  border: 1px solid var(--border-hairline);
  border-radius: var(--radius-card);
  background: var(--surface-elevated);
  box-shadow: var(--shadow-card);
}

.email-verification {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

@media (max-width: 760px) {
  .detail-surface :deep(.el-descriptions__body),
  .detail-surface :deep(.el-descriptions__table),
  .detail-surface :deep(.el-descriptions__table tbody),
  .detail-surface :deep(.el-descriptions__table tr) {
    display: block;
    width: 100%;
  }

  .detail-surface :deep(.el-descriptions__cell) {
    display: flex;
    width: 100%;
  }

  .detail-surface :deep(.el-descriptions__label) {
    min-width: 112px;
  }
}
</style>
