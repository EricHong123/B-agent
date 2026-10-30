// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import type { Messages } from "web-shared";

/** Chinese for this app's strings, keyed by the English source text (web-shared/i18n.tsx). */
export const ZH: Messages = {
  // Shell: views, bag, composer
  "ACME Assistant": "ACME 助手",
  Assistant: "助手",
  Account: "账户",
  Order: "订单",
  Orders: "订单",
  "{n} item": "{n} 件商品",
  "{n} items": "{n} 件商品",
  "{price}/mo": "{price}/月",
  "{price} today": "今日 {price}",
  "/mo": "/月",
  "Ask about your plan, an upgrade, a charge…": "问问你的套餐、升级或某笔费用…",
  "Ask about plans, phones, a fee…": "问问套餐、手机或某项费用…",

  // Home
  "Which plan fits how I use data?": "哪个套餐适合我的流量用量？",
  "Am I due for a phone upgrade?": "我可以升级手机了吗？",
  "Would bundling home internet save me money?": "合并办理家庭宽带能省钱吗？",
  "What's the early termination fee?": "提前解约的违约金是多少？",
  "You average {avg} GB on a {cap} GB plan.": "你平均每月用 {avg} GB，套餐为 {cap} GB。",
  "You average {avg} GB on a {cap} GB plan; top-ups came to {amount} over three months.":
    "你平均每月用 {avg} GB，套餐为 {cap} GB；近三个月加购流量共 {amount}。",
  "Ask which plan fits, and ACME Assistant compares them against your usage with the terms as written.":
    "问问哪个套餐合适，ACME 助手会按条款原文，结合你的用量为你比较。",
  "Your line is on track this cycle. Ask about plans, phones, or home fiber, and ACME Assistant quotes the terms as written.":
    "本周期你的号码用量正常。可以问问套餐、手机或家庭光纤，ACME 助手会按条款原文为你解答。",
  "{plan} · line active": "{plan} · 号码已开通",
  "No line yet": "还没有号码",
  "Let's read the <b>fine print</b> together, {name}.": "{name}，我们一起来看看<b>条款细则</b>。",
  "No ACME Mobile line on this account yet. Ask ACME Assistant to compare plans, phones, or home fiber.":
    "此账户下还没有 ACME Mobile 号码。可以让 ACME 助手帮你比较套餐、手机或家庭光纤。",

  // Plan panel
  "Your plan": "你的套餐",
  "Ask for a plan": "请助手推荐套餐",
  "Which plan would suit a new line?": "新办一个号码，哪个套餐合适？",
  "Ask if a plan fits": "问问套餐是否合适",
  Plan: "套餐",
  Data: "流量",
  Device: "设备",
  Upgrade: "升级",
  "avg {avg} GB of {cap} GB": "平均 {avg} GB / {cap} GB",
  "avg {avg} GB": "平均 {avg} GB",
  "month {month}/{total}": "第 {month}/{total} 个月",
  "Upgrade open": "可升级",
  "Upgrade later": "暂不可升级",

  // Account view
  "{name}'s line, as ACME Mobile has it. Ask which plan fits this usage, or what an upgrade would cost.":
    "{name} 的号码，以 ACME Mobile 记录为准。可以问问哪个套餐适合这样的用量，或升级需要多少钱。",
  "Couldn't load the account.": "无法加载账户。",
  "Plan and usage": "套餐与用量",
  "Plan price": "套餐价格",
  "Monthly bill": "每月账单",
  "Avg data": "平均流量",
  "Last {n} cycles": "最近 {n} 个周期",
  "Last {n} cycles · {cap} GB allowance": "最近 {n} 个周期 · 额度 {cap} GB",
  "{n} top-ups ≈ {amount} in 3 months": "3 个月内加购 {n} 次 ≈ {amount}",
  "{n} top-ups in 3 months": "3 个月内加购 {n} 次",
  "Device and contract": "设备与合约",
  "Ask about an upgrade": "问问升级事宜",
  "Am I due for a phone upgrade, and what would it cost?": "我可以升级手机了吗？需要多少钱？",
  Contract: "合约",
  "Month {month} of {total}": "第 {month} 个月，共 {total} 个月",
  "Installments left": "剩余分期",
  "Contract ends": "合约到期",
  "Trade-in about {amount} ({condition}). Quote good to {date}.": "折价回收约 {amount}（{condition}）。报价有效期至 {date}。",

  // Order panel
  "Nothing in the order yet.": "订单里还没有商品。",
  "Ask ACME Assistant about plans, phones, or home fiber.": "可以向 ACME 助手咨询套餐、手机或家庭光纤。",
  Monthly: "每月",
  "Due today": "今日应付",
  "Nothing is charged until you check out.": "结算前不会扣费。",
  "Your bill {before}/mo → {after}/mo": "你的账单 {before}/月 → {after}/月",
  "no change": "无变化",
  "{sign}{amount}/mo": "{sign}{amount}/月",
  "Check out my order.": "请帮我结算订单。",
  "Ask about this order": "咨询这笔订单",
  "Look over my order: is anything missing before I check out?": "帮我看看订单：结算前还缺什么吗？",
  "Remove the {name} from my order.": "把 {name} 从我的订单中移除。",
  "Change the {name} quantity to {quantity}.": "把 {name} 的数量改为 {quantity}。",

  // Cards: frame and shared
  "FIG {n}": "图 {n}",
  Sources: "来源",
  "Setup plan": "开通步骤",
  "Service facts": "服务说明",
  "Side by side": "并排对比",
  "Plan comparison": "套餐对比",
  "From the catalog": "目录精选",
  "Activation order for your confirmation": "待确认的开通订单",
  "Order {id}": "订单 {id}",
  ETA: "预计送达",
  Total: "合计",

  // Comparison table
  Recommended: "推荐",
  "Best for: ": "适合：",
  "Price difference: ": "价差：",
  "({low} vs {high})": "（{low} 对比 {high}）",
  "Compared on: {dimensions}": "对比维度：{dimensions}",

  // Activation ticket
  "Your bill": "你的账单",
  "{before}/mo → {after}/mo": "{before}/月 → {after}/月",
  "your current plan is replaced at activation; existing device installments continue unchanged":
    "开通时将替换你当前的套餐；已有的设备分期不受影响",
  "added to your current bill; existing device installments continue unchanged": "将计入你当前的账单；已有的设备分期不受影响",
  "Activation order": "开通订单",
  "NOT CHARGED": "未扣费",
  "eSIM ready": "eSIM 已就绪",
  "Activates in minutes after you check out.": "结算后几分钟内即可开通。",
  "Continue to checkout with {seller}": "前往 {seller} 结算",
  "Continue to checkout": "前往结算",
  "Nothing is charged here. Payment happens when you check out.": "此处不会扣费，付款在结算时进行。",

  // Product cards
  "Unlimited data": "不限流量",
  "{value}GB data": "{value}GB 流量",
  "{value}GB hotspot": "{value}GB 热点",
  "{value}h battery": "续航 {value} 小时",
  "{value}ms latency": "延迟 {value}ms",
  "No contract": "无合约",
  "Add the {title} ({id}) to my order.": "把 {title}（{id}）加入我的订单。",
  "Choose options for {title}": "选择 {title} 的配置",
  "Add {title} to order": "将 {title} 加入订单",
  "Device agreement: {name}": "设备协议：{name}",
  "month {month} of {total}": "第 {month} 个月，共 {total} 个月",
  "✓ early upgrade open": "✓ 已可提前升级",
  "early upgrade {date}": "提前升级日 {date}",
  "you are here": "当前位置",
  "{n} payment left": "剩余 {n} 期",
  "{n} payments left": "剩余 {n} 期",
  "outright unlocks {date}": "{date} 买断解锁",
  "Trade-in appraisal": "折价回收估价",
  "{device} · Tier {tier}": "{device} · {tier} 档",
  "Quote valid through {date}": "报价有效期至 {date}",
  "Out of stock": "缺货",
  from: "起价",
  "Scroll to previous products": "向前滚动查看商品",
  "Scroll to more products": "向后滚动查看更多商品",

  // Plan matrix
  "your plan today": "你当前的套餐",
  "same price as today": "与当前价格相同",
  "{sign}{amount}/mo vs today": "比当前 {sign}{amount}/月",
  "Data used in each of the last 3 billing cycles": "最近 3 个账单周期各自的流量用量",
  "Your last 3 cycles": "你最近 3 个周期",
  "---- {gb} GB allowance ({name})": "---- 额度 {gb} GB（{name}）",
  "---- {gb} GB allowance": "---- 额度 {gb} GB",
  "Avg {avg} GB/mo": "平均 {avg} GB/月",
  "Building the plan comparison": "正在生成套餐对比",
  dimension: "对比项",
  "✓ fits your {avg} GB avg": "✓ 满足你平均 {avg} GB 的用量",
  "⚠ under your {avg} GB avg": "⚠ 低于你平均 {avg} GB 的用量",
  "matches a saved preference": "符合已保存的偏好",
  Unlimited: "不限量",
  "Scroll to previous plans": "向前滚动查看套餐",
  "Scroll to more plans": "向后滚动查看更多套餐",

  // Showcase
  "ACME Mobile component showcase (fixture data)": "ACME Mobile 组件展示（示例数据）",
};
