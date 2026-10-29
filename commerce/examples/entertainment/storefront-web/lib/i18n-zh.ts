// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import type { Messages } from "web-shared";

/** Chinese for this app's strings, keyed by the English source text (web-shared/i18n.tsx). */
export const ZH: Messages = {
  // Shell: views, bag, composer
  Assistant: "助手",
  Tickets: "票夹",
  "ACME Assistant": "ACME 助手",
  "Your night": "我的夜场",
  "held seat": "个保留座位",
  "Ask about a ticket, a transfer, a refund…": "询问门票、转让或退款…",
  "Ask about a show, a tier, a fee…": "询问演出、票档或费用…",
  "Couldn't reach the entertainment API on port 8003. Start it with `uvicorn entertainment.api.main:app --app-dir examples --port 8003` and try again.":
    "无法连接 8003 端口的娱乐 API。请先用 `uvicorn entertainment.api.main:app --app-dir examples --port 8003` 启动，然后重试。",
  Working: "处理中",
  "ACME Assistant is working": "ACME 助手正在处理",

  // Home
  "Box office open · {name}": "票房营业中 · {name}",
  "The house lights are down.": "场灯已暗。",
  "The fees are not hidden.": "费用一目了然。",
  "Every price here is all-in. Ask what's on, or hold seats while you decide.":
    "这里的每个价格都是全包价。可以问问有什么演出，也可以先保留座位再慢慢决定。",
  "{tickets} in your wallet for {shows}.": "票夹里有 {tickets}，共 {shows}。",
  "{seats} held and counting down.": "已保留 {seats}，正在倒计时。",
  "You're #{position} on {lists}.": "你在 {lists} 中排第 {position} 位。",
  "a waitlist": "1 个候补队列",
  "{n} waitlists": "{n} 个候补队列",
  "Ask about any of it, or find the next night out.": "可以随时询问这些内容，或去找下一场演出。",
  "Two seated tickets for The Headliner on Friday": "周五 The Headliner 的两张坐席票",
  "The Synth-Pop Act says sold out. What are my options?": "The Synth-Pop Act 显示已售罄，我还有哪些选择？",
  "What's included in the Lower Bowl price?": "Lower Bowl 的票价里包含什么？",
  "What's on at ACME Amphitheater this summer?": "今年夏天 ACME Amphitheater 有哪些演出？",
  "Your tickets": "我的门票",
  "All tickets": "全部门票",
  Issued: "已出票",
  "On sale": "热卖中",
  "Sold out": "已售罄",
  "Open one to see what is left": "点开查看剩余票数",
  "What's still available for {name} on {date}?": "{name} 在 {date} 还有哪些票？",
  "What's still available for {name}?": "{name} 还有哪些票？",
  "from {price} {suffix}": "{price} 起 {suffix}",
  "all-in": "全包",
  "Nothing in the wallet yet. Held seats become tickets when you check out.":
    "票夹里还没有门票。保留的座位在结账后会变成门票。",

  // Plurals
  "{n} ticket": "{n} 张票",
  "{n} tickets": "{n} 张票",
  "{n} show": "{n} 场演出",
  "{n} shows": "{n} 场演出",
  "{n} seat": "{n} 个座位",
  "{n} seats": "{n} 个座位",
  "{n} transfer": "{n} 笔转让",
  "{n} transfers": "{n} 笔转让",
  "{n} returned ticket": "{n} 张退回的票",
  "{n} returned tickets": "{n} 张退回的票",

  // Tickets view and wallet
  "{tickets} across {shows}, {transfers} pending. Ask ACME Assistant about a transfer, resale, or refund.":
    "{tickets}，涉及 {shows}，{transfers}待完成。可以向 ACME 助手询问转让、转售或退款。",
  "{tickets} across {shows}. Ask ACME Assistant about a transfer, resale, or refund.":
    "{tickets}，涉及 {shows}。可以向 ACME 助手询问转让、转售或退款。",
  Waitlist: "候补",
  Event: "演出",
  "Ask about these tickets": "询问这些门票",
  "You're {position} in line": "你排在第 {position} 位",
  "Moves up on its own. When seats come back to you, a claim window opens at the top of the page.":
    "队列会自动前移。座位回到你手中时，页面顶部会打开领取窗口。",
  "What are my options for my {event} tickets: transfer, resale, or a refund?":
    "我的 {event} 门票有哪些选择：转让、转售还是退款？",
  "What are my options for my upcoming tickets: transfer, resale, or a refund?":
    "我即将到来的门票有哪些选择：转让、转售还是退款？",
  "Help me transfer my {event} tickets to a friend.": "帮我把 {event} 的门票转让给朋友。",
  "Help me transfer my upcoming tickets to a friend.": "帮我把即将到来的门票转让给朋友。",
  Ticket: "门票",
  Sec: "区",
  Row: "排",
  Seat: "座",
  "Transfer pending": "转让待完成",
  Transfer: "转让",
  Voided: "已作废",
  "the recipient": "接收人",
  "{voided} and reissued to {recipient}. The new code is on their phone; this one won't scan.":
    "{voided}，并已重新发给 {recipient}。新码在对方手机上，这个码无法再扫描。",
  "New code. The old one won't scan.": "新码已生成，旧码无法扫描。",
  "The entry code refreshes on its own, so a screenshot won't scan.":
    "入场码会自动刷新，截图无法扫描。",

  // Night panel and offers
  "Hold expires; the seats release to other buyers at 0:00": "保留到期后，座位会在 0:00 释放给其他买家",
  "Release now": "立即释放",
  Tonight: "今晚",
  "Return offer: your turn in line": "退票优先购：轮到你了",
  "at the original {price} all-in": "按原全包价 {price}",
  "Claim window closes": "领取窗口关闭于",
  "Claim seats": "领取座位",
  "{n} held": "已保留 {n}",
  "No seats held yet.": "还没有保留的座位。",
  "Ask ACME Assistant to hold seats for 8 minutes while you decide.": "让 ACME 助手为你保留座位 8 分钟，慢慢决定。",
  "Held total, all-in": "保留合计（全包）",
  "Nothing is charged until you check out.": "结账前不会扣款。",
  "Check out my held seats.": "为我保留的座位结账。",
  "Ask about these seats": "询问这些座位",
  "Tell me about the seats I'm holding: the view, what's included, and the all-in price.":
    "介绍一下我保留的座位：视野、包含的内容和全包价。",
  "Also held": "其他保留",
  "Your turn:": "轮到你了：",
  closes: "关闭于",

  // Cards: shared
  Recommended: "推荐",
  "Sold out · waitlist": "已售罄 · 可候补",
  "Selling fast": "热销中",
  "{remaining} left in {tier}": "{tier} 剩 {remaining} 张",
  "#{position} in line": "排第 {position} 位",
  "{ahead} ahead of you": "前面还有 {ahead} 人",
  "you're next": "下一个就是你",
  "updates automatically": "自动更新",
  "Value score, computed by the box office from live listing and inventory data":
    "价值评分，由票房根据实时挂牌和库存数据计算",
  Sources: "来源",

  // Cards: events, comparison, resale
  "What's on": "近期演出",
  "Tier comparison": "票档对比",
  "Best for: {text}": "适合：{text}",
  "Compared on: {dimensions}": "对比维度：{dimensions}",
  "{cheaper} saves {delta} per ticket · {pair} for a pair vs {pricier}":
    "{cheaper} 每张省 {delta} · 一对共省 {pair}（对比 {pricier}）",
  "per ticket": "每张",
  "Held for {minutes}:00": "已保留 {minutes}:00",
  "Hold pair ({n})": "保留一对（{n}）",
  "Hold 1": "保留 1 张",
  "Join the waitlist; you get a claim window if seats come back": "加入候补；座位回流时你会获得领取窗口",
  "This pair sells together: a {minutes}-minute hold on both, not charged":
    "这一对只能一起出售：两张一起保留 {minutes} 分钟，不扣款",
  "A {minutes}-minute hold, not charged; the seats release if the timer runs out":
    "保留 {minutes} 分钟，不扣款；计时结束后座位会被释放",
  "Couldn't": "未能完成",
  "Join waitlist": "加入候补",
  "Fan resale · capped listings, prices all-in": "粉丝转售 · 限价挂牌，价格为全包价",
  Section: "区域",
  Qty: "数量",
  Value: "价值",
  "All-in": "全包价",
  actions: "操作",
  "Value scores are computed by the box office: this {tier} ask is {basis}.":
    "价值评分由票房计算：这个 {tier} 的要价{basis}。",
  listing: "挂牌",
  "{pct} below": "低 {pct}",
  "level with": "持平",
  "{pct} above": "高 {pct}",
  "{direction} the box-office all-in price ({price}) for the same tier":
    "与同档位的票房全包价（{price}）相比，{direction}",
  "{direction} the box-office all-in price for the same tier": "与同档位的票房全包价相比，{direction}",

  // Cards: price and checkout
  "Price & terms": "价格与条款",
  "All-in price, no fees added later": "全包价，之后不再加收费用",
  "Order {id}": "订单 {id}",
  "Total, all-in": "合计（全包）",
  "Held for you, timer running, not charged": "已为你保留，计时中，未扣款",
  "Order summary: held, not charged": "订单摘要：已保留，未扣款",
  "Released, back on sale": "已释放，重新开售",
  "Held, not charged": "已保留，未扣款",
  "Hold ended": "保留已结束",
  "Hold expires": "保留将到期",
  "These seats went back on sale. Ask ACME Assistant to hold them again.": "这些座位已重新开售。可以让 ACME 助手再次为你保留。",
  "At 0:00 these seats release to other buyers.": "到 0:00 时，这些座位会释放给其他买家。",
  "Inside the total": "合计包含",
  "Face value": "票面价",
  "Seller price": "卖家定价",
  "Face / seller value": "票面价 / 卖家定价",
  "Service fee": "服务费",
  "Facility fee": "场馆费",
  "Order processing": "订单处理费",
  "Guaranteed valid for entry or your money back, and the all-in price you see is the full price you pay.":
    "保证可入场，否则退款；你看到的全包价就是你要支付的全部费用。",
  "Continue to checkout with {seller}": "前往 {seller} 结账",
  "Continue to checkout": "继续结账",
  "Nothing is charged here. Payment happens when you check out.": "这里不会扣款。付款在你结账时进行。",
  "Will-call pickup at the venue box office.": "在场馆票房现场取票。",
  "Mobile tickets are added to your wallet at purchase.": "购买后，电子票会加入你的票夹。",
  "Ask ACME Assistant to check out before the timer ends, or let the hold lapse and the seats go back on sale. Nothing is charged here.":
    "请在计时结束前让 ACME 助手为你结账，或让保留自然失效、座位重新开售。这里不会扣款。",

  // Cards: venue map
  "Stylized view from {section}, not a photo": "{section} 的示意视角，并非实景照片",
  "Fewer tickets": "减少票数",
  "More tickets": "增加票数",
  "{venue}: the room": "{venue}：场馆全貌",
  "live availability": "实时余票",
  "Stylized schematic of {venue}": "{venue} 的示意图",
  STAGE: "舞台",
  "Sold out, waitlist open": "已售罄，可候补",
  "{n} left": "剩 {n} 张",
  "Flat floor, closest to the stage": "平坦的场地，离舞台最近",
  "Raked seating wrapping the floor, clear elevated sightline": "阶梯式看台环绕场地，视线开阔且居高",
  "Highest vantage, full-stage panorama": "位置最高，可纵览整个舞台",
  "Elevated side vantage over the floor": "侧面高位，俯瞰场地",
  "Front-facing elevated view": "正对舞台的高位视角",
  "Stylized schematic, not a seat-accurate plan": "示意图，并非精确座位图",
  "General admission, no assigned seats": "站票入场，不指定座位",
  "Reserved seats, assigned together at purchase": "对号入座，购买时一并分配",
  "Held for {minutes}:00, not charged": "已保留 {minutes}:00，未扣款",
  "Couldn't hold. Try again": "保留失败，请重试",
  "Join waitlist for {n}": "为 {n} 张票加入候补",
  "Hold {n} for 8 min": "保留 {n} 张 8 分钟",
  "Stylized schematic. Counts are live inventory; prices are all-in per ticket.":
    "示意图。数量为实时库存；价格为每张全包价。",
};
