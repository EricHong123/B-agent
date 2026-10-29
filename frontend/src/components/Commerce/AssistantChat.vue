<template>
  <div class="assistant-chat">
    <div
      ref="scroller"
      class="transcript"
    >
      <el-empty
        v-if="!items.length"
        :description="emptyText"
        :image-size="64"
      />
      <div
        v-for="(item, index) in items"
        :key="index"
        :class="['bubble', item.kind]"
      >
        <template v-if="item.kind === 'user'">
          <p>{{ item.text }}</p>
        </template>
        <template v-else>
          <span class="ai-label">{{ $t('AI assistant') }}<template v-if="item.model"> · {{ item.model }}</template></span>
          <div
            v-for="(segment, segmentIndex) in item.segments"
            :key="segmentIndex"
            class="segment"
          >
            <p
              v-if="segment.type === 'text'"
              class="text"
            >
              {{ segment.text }}
            </p>
            <el-alert
              v-else-if="segment.type === 'error'"
              type="error"
              :closable="false"
              :title="segment.text"
            />
            <CommerceCard
              v-else
              :component="segment.component"
              :payload="segment.payload"
              :interactive="interactive"
              :can-approve="canApprove"
              @add="(product: any) => emit('add', product)"
              @send="send"
              @submit-rfq="emit('submitRfq')"
              @change-action="(id: string, action: 'apply' | 'discard') => emit('changeAction', id, action)"
            />
          </div>
          <p
            v-if="item.pending"
            class="activity"
          >
            <el-icon class="is-loading">
              <Loading />
            </el-icon>
            {{ item.activity || $t('Working…') }}
          </p>
          <div
            v-if="!item.pending && item.turnId"
            class="reply-actions"
          >
            <el-button
              text
              size="small"
              :type="item.rating === 'up' ? 'primary' : undefined"
              @click="vote(item, true)"
            >
              👍
            </el-button>
            <el-button
              text
              size="small"
              :type="item.rating === 'down' ? 'danger' : undefined"
              @click="vote(item, false)"
            >
              👎
            </el-button>
            <el-button
              v-if="!item.ticket"
              text
              size="small"
              @click="handoff(item)"
            >
              {{ $t('Talk to a person') }}
            </el-button>
            <el-tag
              v-else
              size="small"
              type="success"
            >
              {{ $t('Ticket {ticket} opened', { ticket: item.ticket }) }}
            </el-tag>
          </div>
        </template>
      </div>
    </div>
    <form
      class="composer"
      @submit.prevent="send(draft)"
    >
      <el-input
        v-model="draft"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 5 }"
        :placeholder="placeholder"
        :disabled="!auth || busy"
        @keydown.enter.exact.prevent="send(draft)"
      />
      <el-button
        type="primary"
        native-type="submit"
        :loading="busy"
        :disabled="!auth || !draft.trim()"
      >
        {{ $t('Send') }}
      </el-button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  commerceApi,
  streamCommerceChat,
  type CartPayload,
  type CommerceEvent,
  type CommerceSessionAuth,
  type StagedChange,
} from '@/api/commerce'
import { locale, translate } from '@/i18n'
import CommerceCard from './CommerceCard.vue'

type Segment =
  | { type: 'text', text: string }
  | { type: 'error', text: string }
  | { type: 'ui', component: string, payload: any }

interface AssistantItem {
  kind: 'assistant'
  segments: Segment[]
  pending: boolean
  activity?: string
  turnId?: string
  rating?: 'up' | 'down'
  ticket?: string
  model?: string
  failed?: boolean
}

type Item = { kind: 'user', text: string } | AssistantItem

const props = defineProps<{
  auth: CommerceSessionAuth | null
  placeholder: string
  emptyText: string
  interactive?: boolean
  canApprove?: boolean
  model?: string
}>()

const emit = defineEmits<{
  (event: 'cart', cart: CartPayload): void
  (event: 'change', change: StagedChange): void
  (event: 'add', product: any): void
  (event: 'submitRfq'): void
  (event: 'changeAction', changeId: string, action: 'apply' | 'discard'): void
  (event: 'turn'): void
}>()

const items = ref<Item[]>([])
const draft = ref('')
const busy = ref(false)
const scroller = ref<HTMLElement | null>(null)

function scrollDown() {
  nextTick(() => {
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
  })
}

function apply(reply: AssistantItem, event: CommerceEvent) {
  const data = event.data
  if (event.type === 'text_delta') {
    const last = reply.segments[reply.segments.length - 1]
    if (last?.type === 'text') last.text += data.text
    else reply.segments.push({ type: 'text', text: data.text })
    reply.activity = undefined
  } else if (event.type === 'tool_call') {
    reply.activity = data.label || translate('Checking {tool}…', { tool: String(data.tool || '').replace(/_/g, ' ') })
  } else if (event.type === 'progress') {
    reply.activity = data.message
  } else if (event.type === 'ui') {
    reply.segments.push({ type: 'ui', component: data.component, payload: data.payload })
    reply.activity = undefined
  } else if (event.type === 'cart_update') {
    emit('cart', data.cart)
  } else if (event.type === 'change_update') {
    emit('change', data.change)
  } else if (event.type === 'turn_complete') {
    reply.turnId = data.turn_id
  } else if (event.type === 'error') {
    reply.segments.push({ type: 'error', text: data.message })
    reply.failed = true
  }
}

async function send(text: string) {
  const message = text.trim()
  if (!message || !props.auth || busy.value) return
  draft.value = ''
  items.value.push({ kind: 'user', text: message })
  const reply: AssistantItem = { kind: 'assistant', segments: [], pending: true, model: props.model }
  items.value.push(reply)
  const live = items.value[items.value.length - 1] as AssistantItem
  busy.value = true
  scrollDown()
  try {
    await streamCommerceChat(
      props.auth,
      { message, locale: locale.value === 'zh-CN' ? 'zh' : 'en' },
      (event) => {
        apply(live, event)
        scrollDown()
      },
    )
  } catch (error) {
    live.segments.push({ type: 'error', text: error instanceof Error ? error.message : String(error) })
    live.failed = true
  } finally {
    live.pending = false
    busy.value = false
    emit('turn')
    scrollDown()
  }
}

async function vote(item: AssistantItem, helpful: boolean) {
  if (!props.auth || !item.turnId) return
  await commerceApi.feedback(props.auth, item.turnId, helpful)
  item.rating = helpful ? 'up' : 'down'
}

async function handoff(item: AssistantItem) {
  if (!props.auth) return
  const reason = item.failed ? 'after_error' : item.rating === 'down' ? 'after_negative_feedback' : 'user_requested'
  const result = await commerceApi.handoff(props.auth, item.turnId, reason)
  item.ticket = result.ticket
  ElMessage.success(translate('Ticket {ticket} opened', { ticket: result.ticket }))
}

function reset() {
  items.value = []
}

defineExpose({ send, reset })
</script>

<style lang="scss" scoped>
.assistant-chat {
  display: grid;
  grid-template-rows: 1fr auto;
  min-height: 520px;
  max-height: calc(100dvh - 220px);
  gap: 12px;
}

.transcript {
  display: grid;
  align-content: start;
  gap: 12px;
  overflow-y: auto;
  padding: 4px;
}

.bubble {
  max-width: 92%;

  &.user {
    justify-self: end;
    padding: 8px 12px;
    border-radius: 14px;
    background: var(--surface-selected);

    p {
      margin: 0;
      white-space: pre-wrap;
    }
  }

  &.assistant {
    justify-self: start;
    width: 100%;
  }
}

.ai-label {
  color: var(--text-tertiary);
  font-size: 11px;
}

.text {
  margin: 4px 0;
  line-height: 1.6;
  white-space: pre-wrap;
}

.activity {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 13px;
}

.reply-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
}

.composer {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
</style>
