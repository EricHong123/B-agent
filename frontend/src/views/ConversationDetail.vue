<template>
  <div class="conversation-detail page-stack">
    <header class="page-heading">
      <div>
        <el-button
          text
          class="back-button"
          @click="$router.back()"
        >
          <el-icon><ArrowLeft /></el-icon>
          {{ $t('Conversations') }}
        </el-button>
        <h1>{{ $t('Conversation') }}</h1>
        <p class="conversation-id">
          {{ conversationId }}
        </p>
      </div>
    </header>

    <div class="conversation-content">
      <el-card
        class="messages-panel"
        shadow="never"
      >
        <div class="messages-list">
          <div
            v-for="message in messages"
            :key="message.id"
            :class="['message-item', message.role]"
          >
            <div class="message-bubble">
              <div class="message-role">
                {{ message.role }}
              </div>
              <div class="message-content">
                {{ message.content }}
              </div>
              <div class="message-time">
                {{ formatTime(message.sent_at) }}
              </div>
            </div>
          </div>
        </div>

        <div class="message-input">
          <el-input
            v-model="newMessage"
            type="textarea"
            :placeholder="$t('Type your message...')"
            @keyup.ctrl.enter="sendMessage"
          />
          <el-button
            type="primary"
            :loading="sending"
            @click="sendMessage"
          >
            {{ $t('Send') }} (Ctrl+Enter)
          </el-button>
        </div>
      </el-card>

      <el-card
        class="info-panel"
        shadow="never"
      >
        <template #header>
          {{ $t('Conversation Info') }}
        </template>
        <el-descriptions
          :column="1"
          border
        >
          <el-descriptions-item :label="$t('Platform')">
            {{ conversation?.platform }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('Status')">
            <el-tag>{{ $t(conversation?.status || '') }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="$t('Intent')">
            {{ conversation?.current_intent }}
          </el-descriptions-item>
          <el-descriptions-item :label="$t('AI Handled')">
            <el-tag :type="conversation?.ai_handled ? 'success' : 'info'">
              {{ $t(conversation?.ai_handled ? 'Yes' : 'No') }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <el-divider />

        <el-button
          type="primary"
          :loading="converting"
          @click="convertToOpportunity"
        >
          {{ $t('Create opportunity') }}
        </el-button>
        <el-button
          v-if="conversation?.ai_handled"
          type="warning"
          @click="takeover"
        >
          {{ $t('Takeover') }}
        </el-button>
        <el-button
          v-if="conversation?.manual_takeover"
          @click="release"
        >
          {{ $t('Release') }}
        </el-button>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '@/api'
import { fulfillmentApi } from '@/api/fulfillment'
import { translate } from '@/i18n'

const route = useRoute()
const router = useRouter()

const conversationId = route.params.id as string
const conversation = ref<any>(null)
const messages = ref<any[]>([])
const newMessage = ref('')
const sending = ref(false)
const converting = ref(false)

async function fetchConversation() {
  try {
    const response = await api.get(`/api/v1/conversations/${conversationId}`)
    conversation.value = response.data
    messages.value = response.data.messages
  } catch {
    ElMessage.error(translate('Failed to load conversation'))
  }
}

async function sendMessage() {
  if (!newMessage.value.trim()) return

  sending.value = true
  try {
    await api.post(`/api/v1/conversations/${conversationId}/messages`, {
      role: 'user',
      content: newMessage.value,
    })
    newMessage.value = ''
    await fetchConversation()
  } catch {
    ElMessage.error(translate('Failed to send message'))
  } finally {
    sending.value = false
  }
}

async function convertToOpportunity() {
  converting.value = true
  try {
    const opportunity = await fulfillmentApi.createOpportunityFromConversation(conversationId)
    await router.push({ path: '/fulfillment', query: { opportunity: opportunity.id } })
  } finally {
    converting.value = false
  }
}

async function takeover() {
  try {
    await api.post(`/api/v1/conversations/${conversationId}/takeover`)
    ElMessage.success(translate('Conversation taken over'))
    await fetchConversation()
  } catch {
    ElMessage.error(translate('Failed to take over'))
  }
}

async function release() {
  try {
    await api.post(`/api/v1/conversations/${conversationId}/release`)
    ElMessage.success(translate('Conversation released'))
    await fetchConversation()
  } catch {
    ElMessage.error(translate('Failed to release'))
  }
}

function formatTime(date: string) {
  return new Date(date).toLocaleTimeString()
}

onMounted(() => {
  fetchConversation()
})
</script>

<style lang="scss" scoped>
.conversation-detail {
  .back-button {
    margin: 0 0 8px -12px;
    color: var(--text-secondary);
  }

  .conversation-id {
    max-width: min(720px, 82vw);
    overflow: hidden;
    font-family: 'SFMono-Regular', Consolas, monospace;
    font-size: 12px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .conversation-content {
    display: grid;
    grid-template-columns: 1fr 300px;
    gap: 20px;
  }

  .messages-panel {
    display: flex;
    flex-direction: column;
    min-height: 560px;
    height: calc(100dvh - 220px);
  }

  .messages-list {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
  }

  .message-item {
    margin-bottom: 16px;

    &.user {
      .message-bubble {
        background: var(--apple-blue);
        color: white;
        margin-left: auto;
      }
    }

    &.assistant {
      .message-bubble {
        background: var(--surface-sunken);
      }
    }
  }

  .message-bubble {
    max-width: 70%;
    padding: 10px 13px;
    border-radius: 17px;

    .message-role {
      font-size: 12px;
      opacity: 0.8;
      margin-bottom: 4px;
    }

    .message-content {
      line-height: 1.5;
    }

    .message-time {
      font-size: 12px;
      opacity: 0.6;
      margin-top: 8px;
      text-align: right;
    }
  }

  .message-input {
    padding: 16px;
    border-top: 1px solid var(--border-hairline);

    .el-textarea {
      margin-bottom: 12px;
    }
  }

  .info-panel {
    height: fit-content;
  }
}

@media (max-width: 980px) {
  .conversation-detail .conversation-content {
    grid-template-columns: 1fr;
  }

  .conversation-detail .messages-panel {
    height: min(640px, calc(100dvh - 180px));
  }
}
</style>
