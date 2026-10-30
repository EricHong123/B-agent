// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import type { Messages } from "web-shared";

/** Chinese for this app's strings, keyed by the English source text (web-shared/i18n.tsx). */
export const ZH: Messages = {
  // Frame: views, cart label, composer
  Assistant: "助手",
  Orders: "订单",
  Guest: "访客",
  Cart: "购物车",
  item: "件商品",
  "{count} delayed": "{count} 个延误",
  "Ask about an order, a return, a delivery…": "问问订单、退货或配送情况…",
  "Ask about a product, a project, an order…": "问问商品、项目或订单…",
  "Searching the catalog…": "正在搜索商品目录…",
  "Couldn't reach the retail API on port 8000. Start it with `uvicorn retail.api.main:app --app-dir examples --port 8000` and try again.":
    "无法连接 8000 端口上的零售 API。请先用 `uvicorn retail.api.main:app --app-dir examples --port 8000` 启动，然后重试。",

  // Orders view
  "{count} order running late. Ask why, or ask about a return on anything delivered.": "{count} 个订单延误。可以问问原因，或询问已送达商品的退货。",
  "{count} orders running late. Ask why, or ask about a return on anything delivered.": "{count} 个订单延误。可以问问原因，或询问已送达商品的退货。",
  "{count} order on the way. Ask about any of them, or about a return on anything delivered.": "{count} 个订单在途中。可以询问任意订单，或已送达商品的退货。",
  "{count} orders on the way. Ask about any of them, or about a return on anything delivered.": "{count} 个订单在途中。可以询问任意订单，或已送达商品的退货。",

  // Home
  "{greeting}, {name}": "{greeting}，{name}",
  "Good morning": "早上好",
  "Good afternoon": "下午好",
  "Good evening": "晚上好",
  Hello: "你好",
  "Ask about a product, a project, an order, or a return.": "问问商品、项目、订单或退货。",
  "Nothing on the way right now. Ask about a product, a project, or a return.": "目前没有在途订单。可以问问商品、项目或退货。",
  "{count} order on the way": "{count} 个订单在途中",
  "{count} orders on the way": "{count} 个订单在途中",
  "{head}; the next arrives {date}.": "{head}；下一单预计 {date} 送达。",
  "{head}.": "{head}。",
  "One is running late.": "其中一个延误了。",
  "{count} are running late.": "其中 {count} 个延误了。",
  "A tent for a first family camping trip, under $250": "第一次全家露营要用的帐篷，250 美元以内",
  "Set up a home office in a small spare room for about $800": "在小客房里布置一间家庭办公室，预算约 800 美元",
  "Drip or espresso for busy weekday mornings?": "工作日早晨赶时间，滴滤咖啡机还是意式咖啡机？",
  "Remember: small apartment, no outdoor storage, and a golden retriever": "请记住：住小公寓，没有户外储物空间，养了一只金毛",
  "Popular right now": "当前热门",
  "Bestsellers and new arrivals; open one to ask about it": "畅销商品和新品；点开任意一件即可询问",
  "Tell me about the {title}.": "介绍一下{title}。",

  // Cart
  "Free shipping on this order ✓": "本单免运费 ✓",
  "{amount} away from free shipping": "再买 {amount} 即可免运费",
  "Anything more ships free": "再买任何商品都免运费",
  "Standard shipping is free on orders over {amount}.": "订单满 {amount} 可享标准配送免运费。",
  "{count} item": "{count} 件商品",
  "{count} items": "{count} 件商品",
  "Nothing in the cart yet.": "购物车还是空的。",
  "Ask ACME Assistant for anything in the store.": "想要店里的任何东西，都可以问 ACME 助手。",
  Subtotal: "小计",
  "Subtotal · {count} item": "小计 · {count} 件商品",
  "Subtotal · {count} items": "小计 · {count} 件商品",
  "Check out my cart.": "帮我结算购物车。",
  "Ask about this cart": "咨询这份购物车",
  "Look over my cart: anything missing or worth swapping?": "帮我看看购物车：有没有漏掉的，或者值得换的？",
  "{price} each": "每件 {price}",
  "Remove the {name} from my cart.": "把{name}从购物车中移除。",
  "Change the {name} quantity to {quantity}.": "把{name}的数量改为 {quantity}。",

  // Product tiles and rows
  "From {price}": "{price} 起",
  "Only {count} left": "仅剩 {count} 件",
  "Out of stock": "缺货",
  "Add the {title} ({id}) to my cart.": "把{title}（{id}）加入我的购物车。",
  "Choose options for {title}": "选择{title}的规格",
  "Add {title} to cart": "将{title}加入购物车",
  "30-day returns": "30 天退货",

  // Product carousel and detail
  "Sitting near the low end of its own range · last {days} days": "处于自身价格区间的低位 · 近 {days} 天",
  "Sitting near the high end of its own range · last {days} days": "处于自身价格区间的高位 · 近 {days} 天",
  "Sitting in the typical band of its own range · last {days} days": "处于自身价格区间的常见水平 · 近 {days} 天",
  "From {count} customer reviews": "来自 {count} 条顾客评价",
  "{name}: {pct}% positive across {mentions} mentions": "{name}：在 {mentions} 次提及中好评率 {pct}%",
  "{mentions} mentions": "{mentions} 次提及",
  Options: "可选规格",
  "Add the {title} in {option} ({id}) to my cart.": "把{option}款的{title}（{id}）加入我的购物车。",
  "Collapse details": "收起详情",
  "Loading details…": "正在加载详情…",
  "Scroll to previous products": "向前滚动查看商品",
  "Scroll to more products": "向后滚动查看更多商品",

  // Comparison
  Recommended: "推荐",
  "Best for: {text}": "适合：{text}",
  "Price difference: {amount} {range}": "价格差：{amount} {range}",
  "({low} vs {high})": "（{low} 对比 {high}）",
  "Compared on: {dimensions}": "对比维度：{dimensions}",

  // Guide
  "Sources: {sources}": "来源：{sources}",

  // Plan
  "Planned picks {amount}": "计划选购 {amount}",
  "Planned picks {amount} (cheapest option per step)": "计划选购 {amount}（每步取最便宜的选项）",
  "{count} step with no items to show": "{count} 个步骤暂无可展示的商品",
  "{count} steps with no items to show": "{count} 个步骤暂无可展示的商品",
  "No items to show for this step.": "这一步暂无可展示的商品。",

  // Order status
  Ordered: "已下单",
  Packed: "已打包",
  Shipped: "已发货",
  Delivered: "已送达",
  delayed: "延误",
  "The original delivery estimate was missed": "已超过原定送达时间",
  "Order {id}": "订单 {id}",
  processing: "处理中",
  shipped: "已发货",
  "out for delivery": "派送中",
  delivered: "已送达",
  cancelled: "已取消",
  "return initiated": "已申请退货",
  refunded: "已退款",
  Total: "合计",
  "Estimated delivery: {date}": "预计送达：{date}",
  "Track package": "查看物流",

  // Checkout
  "Ready to check out": "可以结算了",
  "Not charged": "未扣款",
  Shipping: "运费",
  "standard · {eta}": "标准配送 · {eta}",
  "3–5 business days": "3–5 个工作日",
  Free: "免费",
  "Calculated at checkout": "结算时计算",
  "Add {amount} more to unlock free shipping": "再添加 {amount} 即可免运费",
  Tax: "税费",
  "Estimated total": "预计合计",
  "Before tax; the final total appears at checkout.": "未含税；最终合计将在结算时显示。",
  "Before shipping and tax; the final total appears at checkout.": "未含运费和税费；最终合计将在结算时显示。",
  "Most items can be returned within 30 days of delivery for a refund to your original payment method.": "大多数商品可在送达后 30 天内退货，款项退回原支付方式。",
  "Continue to checkout with {seller}": "前往 {seller} 结算",
  "Continue to checkout": "继续结算",
  "Nothing is charged here. Payment happens when you check out.": "此处不会扣款，付款在结算时进行。",

  // Showcase
  "ACME component showcase (fixture data)": "ACME 组件展示（示例数据）",
};
