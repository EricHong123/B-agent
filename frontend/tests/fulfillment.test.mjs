import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import test from 'node:test'

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = (relativePath) => readFileSync(path.join(frontendDir, relativePath), 'utf8')

test('fulfillment workspace is routed and reachable from navigation', () => {
  const router = source('src/router/index.ts')
  const layout = source('src/layouts/MainLayout.vue')

  assert.match(router, /path: 'fulfillment'/)
  assert.match(router, /Fulfillment\.vue/)
  assert.match(router, /path: 'orders\/:id'/)
  assert.match(router, /OrderDetail\.vue/)
  assert.match(layout, /index="\/fulfillment"/)
})

test('fulfillment client covers the opportunity-to-delivery API surface', () => {
  const api = source('src/api/fulfillment.ts')

  for (const endpoint of [
    '/pipeline',
    '/events',
    '/opportunities',
    '/opportunities/from-conversation/',
    '/quotations',
    '/submit',
    '/review',
    '/send',
    '/accept',
    '/decline',
    '/orders',
    '/transition',
    '/production-tasks',
    '/inspections',
    '/shipments',
    '/payments',
  ]) {
    assert.ok(api.includes(endpoint), `missing ${endpoint}`)
  }
  assert.match(api, /\/api\/v1\/fulfillment/)
  assert.match(api, /idempotency_key/)
})

test('pipeline closes the loop from inquiries to delivery', () => {
  const view = source('src/views/Fulfillment.vue')
  const conversation = source('src/views/ConversationDetail.vue')

  assert.match(view, /fulfillmentApi\.pipeline/)
  assert.match(view, /unconverted_inquiries/)
  assert.match(view, /createOpportunityFromConversation/)
  assert.match(view, /alerts/)
  assert.match(conversation, /createOpportunityFromConversation/)
})

test('order detail renders server-side gate blockers instead of client-side status edits', () => {
  const view = source('src/views/OrderDetail.vue')

  assert.match(view, /next_transitions/)
  assert.match(view, /blockers/)
  assert.match(view, /:disabled="!next\.ready"/)
  assert.match(view, /fulfillmentApi\.transitionOrder/)
  assert.match(view, /newIdempotencyKey\('payment'\)/)
  assert.doesNotMatch(view, /transitionOrder\(orderId, '(shipped|delivered|completed)'/)
})

test('fulfillment workspace is bilingual', () => {
  const messages = source('src/i18n/index.ts')

  assert.match(messages, /Fulfillment: '履约中心'/)
  assert.match(messages, /'Lead-to-delivery funnel': '获客到交付漏斗'/)
  assert.match(messages, /in_production: '生产中'/)
  assert.match(messages, /'quote\.sent': '已发送'/)
  assert.match(messages, /'Move to \{stage\}': '推进到「\{stage\}」'/)
})
