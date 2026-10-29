import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import test from 'node:test'

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = (relativePath) => readFileSync(path.join(frontendDir, relativePath), 'utf8')

test('commerce assistants are routed and in the navigation, with a public buyer portal', () => {
  const router = source('src/router/index.ts')
  const layout = source('src/layouts/MainLayout.vue')

  for (const route of ['buyer-assistant', 'operations-assistant', 'commerce']) {
    assert.match(router, new RegExp(`path: '${route}'`))
    assert.match(layout, new RegExp(`index="/${route}"`))
  }
  const portal = router.slice(router.indexOf("path: '/portal'"), router.indexOf("path: '/',"))
  assert.match(portal, /BuyerPortal\.vue/)
  assert.doesNotMatch(portal, /requiresAuth/)
})

test('the commerce client streams chat and scopes every session request', () => {
  const api = source('src/api/commerce.ts')

  assert.match(api, /X-Commerce-Session/)
  assert.match(api, /X-Buyer-Token/)
  assert.match(api, /text\/event-stream/)
  assert.match(api, /\/api\/v1\/commerce/)
  for (const endpoint of ['/buyer/rfq', '/buyer/cart/add', '/operations/changes/', '/handoff', '/feedback', '/catalog/terms', '/metrics']) {
    assert.ok(api.includes(endpoint), `missing ${endpoint}`)
  }
  assert.doesNotMatch(api, /localStorage\.(setItem|getItem)\([^)]*token/i)
})

test('staged changes apply only from the console approval control', () => {
  const preview = source('src/components/Commerce/ChangePreview.vue')
  const operations = source('src/views/OperationsAssistant.vue')
  const card = source('src/components/Commerce/CommerceCard.vue')

  assert.match(preview, /:disabled="!canApprove"/)
  assert.match(operations, /commerceApi\.changeAction/)
  assert.match(card, /change_preview/)
  assert.doesNotMatch(source('src/components/Commerce/AssistantChat.vue'), /changeAction\(/)
})

test('replies carry an AI label, votes and a handoff to a person', () => {
  const chat = source('src/components/Commerce/AssistantChat.vue')

  assert.match(chat, /\$t\('AI assistant'\)/)
  assert.match(chat, /commerceApi\.feedback/)
  assert.match(chat, /commerceApi\.handoff/)
  assert.match(chat, /after_negative_feedback/)
})

test('the buyer basket is a request for quotation, not a checkout', () => {
  const workspace = source('src/components/Commerce/BuyerWorkspace.vue')
  const messages = source('src/i18n/index.ts')

  assert.match(workspace, /commerceApi\.submitRfq/)
  assert.doesNotMatch(workspace, /payment|card number/i)
  assert.match(messages, /'RFQ basket': '询价单'/)
  assert.match(messages, /'Buyer assistant': '采购商助手'/)
  assert.match(messages, /'Operations assistant': '运营助手'/)
})
