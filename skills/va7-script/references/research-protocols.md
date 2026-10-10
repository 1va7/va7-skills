# 研究协议（三合一）

写作前的研究纪律：adversarial 研究、多人转录稿读法、经验底库读取。三条协议合并于此，触发条件见 SKILL.md。

---

# 第一部分：Adversarial 研究协议

# Adversarial 研究协议

> **Why this matters**: "市面上 X 都不行" 类 claim 是 IP 视频翻车率最高的句式. 不做 steelman 就发, 几乎肯定被懂行观众一句话打掉。

---

## 触发条件 (任一即触发, 紧触发)

- "市面上的 X 都解决不了 Y"
- "现在没有 Z 类工具能做"
- "整个 W 赛道都错了"
- "目前唯一能做 V 的是..."
- 凡是要点名 2+ 个 specific 项目并贬低/否定它们的——也触发

凡触发, 在写正文之前 (不是写完之后), 派 subagent。

---

## Subagent 提示词模板

直接复制下面这段, 替换 `[XXX]` 部分:

```
需要一次强力对抗式研究, stress-test 一个即将公开宣称的论点, 避免被懂行的观众一句话打掉. 论点会出现在面向中文 AI 工程师群体的小红书 IP 视频里, 作者是日烧 X 亿 token 的重度 AI coding 用户.

**待 stress-test 的论点**: [插入完整论点, 包括所有限定词]

**具体使用场景定义清楚**: [插入具体场景——agent A 的具体动作, 目标 agent B 的具体期望, 中间需要保留的所有 state]

**任务**:

(1) **列出所有可被合理认为是该范畴的项目**, 按热度/对比合理性排序:
- OSS framework: [类别]
- 商业产品: [类别]
- MCP / 协议层方案: [类别]
- 学术: [类别]
每个项目 1-2 句话定位 (它是什么、解决什么、不解决什么)

(2) **对前 6-10 个最强对手做 steelman**:
- 扮演该项目的核心贡献者或最坚定支持者
- 调研其官方 docs、GitHub README、最新 release notes、blog/twitter announcement、demo videos、issues 里的相关讨论
- 找出**具体的 API/机制/扩展路径**, 论证"通过 X 步骤其实能完成 [目标]"
- 必须技术鲁棒, 不能 handwave: 必须列出具体 API call sequence、字段映射、是否能 preserve 关键 schema

(3) **对每个 steelman 给出诚实评估**: 防住了原论点 / 部分防住 / 没防住. 给具体技术理由.

(4) **Sanity check**:
- 有没有项目已经在做相邻问题?
- 有没有 spec / 协议层方案?
- 社区/Reddit/HN/Twitter/小红书 有没有相关讨论?

(5) **最终结论 + 措辞建议**:
- 论点是否 holds?
- 哪些项目可以被精准点名 (点名要有 documented 依据, 不是凭名气)?
- 措辞应该是什么? "市面上" 是否需要换成更准确的范畴词?
- **最危险的对抗反驳是什么** (一个懂行观众最可能的"actually X 已经做了"反驳), 预先想好怎么应对

(6) **给出 3 版可上视频措辞** (保守 → punchy), 按抗反驳能力排序. 每版附"如果观众反驳 X, 怎么挡住".

**报告格式**:
- 字数 1500-2500 字
- 重点在 (5) (6), 前面是支撑
- 每个被点名的项目必须有官方 docs/GitHub 链接支撑
- 不要写成百科——所有内容服务于 "这个论点能不能上视频" 这一个判断
- 用中文回报

可以并行 WebFetch 多个项目的 docs. 如果需要操作浏览器看 dynamic 内容 (Twitter discussion, demo video) 可以用 web-access skill.
```

---

## 用结果做什么

### Case A: 论点 holds

→ 用 subagent 给的精准措辞**替换原版**。
→ 把"最危险反驳"准备好的应对作为视频里的"内行护甲句"。
→ 把"哪些项目可以精准点名"的 list 替换原版那些凭名气敲的项目名。

### Case B: 论点 partial holds

→ 缩小范围。改成"对于 X 子场景, 现有方案不行"——不是"全行业不行"。
→ 在视频里**主动承认**最强对手的存在, 用一句话切清"它做的是 Y, 我做的是 Z"。

### Case C: 论点 not holds

→ **推翻整个 thesis**。承认这一步是诚信的体现。
→ 重新想 thesis——可能你撞到的不是"市面上没人做"的问题, 是"你的视角看错了"。

---

## Anti-pattern

❌ subagent 跑完, 把 finding 当 trivia 略过, 还用原版措辞——这是最严重的失败, 等于白做。

❌ subagent 找出强对手, 自己心里 hand-wave 觉得没事——你的"觉得没事"扛不住懂行观众。

❌ "懂行观众应该懂我意思" — 不会的, 他们会留 angry 评论, 然后视频在算法里被 demote。

❌ subagent 给了 3 版措辞, 你挑最 punchy 那版用 — 应该挑**抗反驳能力最强**那版 (subagent 报告里有排序)。

---

## 经典案例 (这次会话的实证)

待 stress-test 论点: "市面上所有 agent memory 方案都解决不了 CC↔Codex session 状态接力"

Subagent finding (摘要):
- 论点严格成立, 但需精修措辞
- 最危险对手是 cli-continues (1.2k stars), 不是 Mem0/Letta——它专门做跨 CLI 接力
- cli-continues 做的是 summary handoff (压成 markdown 注入), 不是 runtime state migration
- 推荐措辞: 主动承认 cli-continues 的存在, 切清"它是历史简报, 不是运行时态搬家"

Without subagent, 视频会被一条评论 "不是有 cli-continues 吗" 打塌。
With subagent, 提前 disarm 了这个反驳, 立场更稳。

完整案例参见会话记录 `9fbf6d7c-d1c2-42d0-9887-9fd7196acae4`.

---

# 第二部分：多人对话 / 转录稿读法协议

# 多人对话 / 转录稿读法协议

> **Why this matters**: 把一方论点 (你不买的那些) 当成"双方达成的视角", 然后用最 punchy 的那条作为 IP 立场——这是 IP 翻车的原因之一. "为了搞反共识而搞非共识" 的根源就在 reading 错。

---

## 三轮读法 (强制)

### 第一轮: 列出每个发言者的 position

不要合并, 不要总结. 每个发言者**单独**列。

如果有名字 (凯瑞 / VA7 / CTO) 就用名字; 如果只有 "说话人 1/2", 先标记, 后面 disambiguate。

输出格式:

```
### Speaker A (= [实际身份])
核心论点 1: [一句话]
核心论点 2: [一句话]
用过的关键例子: [list]
关键造词: [list]

### Speaker B (= [实际身份])
核心论点 1: [一句话]
...
```

### 第二轮: 标识 agreed vs contested

- **agreed**: 双方/多方都明确同意的命题 (有具体台词支撑)
- **contested**: 一方主张, 另一方反对 / 不被说服 / 仅 entertain
- **open**: 未达成结论的开放问题

⚠️ **警告**: 大量"看起来 agreed"的命题实际是 contested. 一方没明确反对, 但也没买账——这种要标 contested。

### 第三轮: 锁定用户 (IP 本人) 的真实位置

用户的位置可能是 contested 一边的 less-punchy 版本. 比如:
- CTO: 主张 "X 颠覆 Y"
- VA7: 倾向 "X 和 Y 解的是不同问题"
- → IP 立场 = VA7 的, **不是** CTO 的, **不是**两者综合

**测试**: 你能引用一句具体台词, 表明用户对这个 thesis 表达了认同吗?
- 能 → IP 立场可以包含它
- 不能 → 不要把它当 IP 立场, 即使它更 punchy

---

## Anti-pattern

### ❌ "把多个发言者的 distinct 论点合并成'双方达成的视角'"

这是这次会话最严的 reading 失败。即使你的"IP 立场不偏移"原则没违反, 单独这一条 reading 错也能让你翻车。

### ❌ "用户没明确反对 = 用户支持"

不一定。用户可能在 entertain 这个论点但没买账。关键看用户**主动表达赞同**的台词, 不看用户**没表达反对**的沉默。

### ❌ "用户提了一个例子 = 用户支持那个例子背后的整个 framework"

用户可能只是觉得这个例子有趣 / 好笑 / 形象, 不是为这个 framework 背书。

### ❌ "用户提了反驳但语气温和 = 反驳不算反驳"

中文表达常常用"嗯"、"我想想"、"OK"等模糊词。这些经常是不买账的信号, 不是同意的信号。看完整句, 不只是结尾词。

### ❌ "把转录稿当 monologue 读"

转录稿是 dialogue. 必须先 disambiguate speakers, 再读 content. 跳过 disambiguation 直接合并双方观点 = 必翻车。

---

## 实操检查清单

写稿之前, 如果稿子的核心 thesis 来源于多人对话/转录稿:

1. [ ] 我列了每个发言者的 position 吗 (单独, 不合并)?
2. [ ] 我标了 agreed / contested 吗?
3. [ ] 我能引用具体台词证明用户支持这个 thesis 吗?
4. [ ] 我的 thesis 是不是比用户的实际位置更 punchy?
5. [ ] 如果是 (4), 我有没有偷偷在 push 别人 (CTO/同事/某发言者) 的论点?

任何一条 No → 重读, 重新锁定 IP 立场。

---

## 经典案例 (这次会话的实证)

转录稿: VA7 ↔ CTO (凯瑞) 的讨论, 主题: agent 状态管理 vs 记忆管理。

### 错误读法 (我的失败)

把 CTO 的论点链 (控制论 / 减肥例子 / 状态 ⊃ 记忆 / 主观能动性 / 执行者→编排者) 当成"双方达成的视角", 然后做出 IP 立场 = "执行者→编排者 是 agent 进化下一步"。

### 正确读法 (用户打回后)

**Speaker 1 (CTO)**:
- 主张: 状态管理 > 记忆管理
- 论据: 控制论 / 减肥例子 / 主观能动性 / 编排者
- 关键造词: "执行者→编排者", "状态驱动 vs 任务驱动"

**Speaker 2 (VA7)**:
- 主张: 记忆管理只要颗粒度够细就够好
- 用法: defend 主流玩家 (Mem0/Letta 等)
- 关键例子: "身临其境" 用来理解状态

**Agreed**: (无, 两人没达成结论)
**Contested**: "状态 > 记忆", "主观能动性 only with state", "执行者→编排者"
**用户真实位置 (VA7)**: "想搞清楚 state 和 memory 各有什么场景, 不是判断谁优"

→ IP 立场应该是: **"两件事不是同一类问题, 各管各场景"**, 不是 "执行者→编排者 颠覆论"。

完整案例参见会话记录 `9fbf6d7c-d1c2-42d0-9887-9fd7196acae4`.

---

# 第三部分：经验底库读取协议

# 经验底库读取协议

> **Why this matters**: 不读经验底库直接动笔, 起步分 ≤ 60. 读了起步是 80+. 这是 SKILL.md 中 Step 0 的具体执行指引。

---

## 要读什么

| 表 | base_token | table_id | 用途 |
|---|---|---|---|
| 成品表 | `<base_token，见 config.json>` | `<finished 表 id>` | 已发同类稿子, 提取 anatomy / 受众 tech 天花板 / Hook 模板 |
| 版本追踪表 | `<base_token，见 config.json>` | `<版本追踪表 id>` | 历史 critique 记录, 提取 anti-pattern |

---

## 怎么读

### 推荐方式: lark-cli

```bash
# 列出表字段 (确认 schema 没漂移)
lark-cli api GET "/open-apis/bitable/v1/apps/<base_token，见 config.json>/tables/<finished 表 id>/fields"

# 列出表记录
lark-cli api GET "/open-apis/bitable/v1/apps/<base_token，见 config.json>/tables/<finished 表 id>/records?page_size=100"
```

### Fallback: 直接 API 调用 (lark-cli 默认 bot 没权限时)

```python
import urllib.request, json

# Main Agent (read-only) credentials
# 详见 ~/.claude/projects/-Users-va7/memory/reference_feishu_credentials.md
APP_ID = "cli_a9f59de34db89bef"
APP_SECRET = "4osIcfx6UeKGgyPLfwVv6gmcOGGaD51b"
BASE_TOKEN = "<base_token，见 config.json>"


def get_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["tenant_access_token"]


def list_records(table_id, page_size=100):
    token = get_token()
    url = (f"https://open.feishu.cn/open-apis/bitable/v1/apps/"
           f"{BASE_TOKEN}/tables/{table_id}/records?page_size={page_size}")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req).read())


# 用法
chengpin = list_records("<finished 表 id>")  # 成品表
versions = list_records("<版本追踪表 id>")  # 版本追踪表
```

---

## 从成品表里提取什么

| 提取项 | 提取方法 |
|---|---|
| **受众技术天花板** | 找正文里出现过的最技术的术语 → 这是上限。新稿超过的术语必须类比 / 砍掉 |
| **Hook 模板** | 列出每条 Hook, 找共同结构 (近期事件 + 数字 + 反差) |
| **正文 anatomy** | 数段落数 / 每段长度 / bullet 编号方式 / 过渡句模式 |
| **类比层级** | 列出所有用过的类比, 看其来源域 (生活 / 职场 / 技术) |
| **数据表达模式** | "X token / Y 美金 / Z 个客户" — 数字 + 单位 + 上下文 |
| **落款模板** | 抄一份 standard ending |
| **传播表现** | 看 点赞/收藏/评论/分享 字段——哪类主题/结构传播好 |

---

## 从版本追踪表里提取什么

| 提取项 | 提取方法 |
|---|---|
| **Anti-pattern** | 看"主要变更"和"关键修改意见"字段, 找重复出现的 critique theme |
| **红线** | 看 VA7 直接斥责的话 (如"乱讲" / "废话" / "越改越差了") — 不可踩 |
| **重写偏好** | 看 VA7 自己重写的版本和原版的 diff — 找 VA7 偏好的措辞模式 |
| **特定 record id** | 引用红线时, record_id 是来源凭证 — 让规则可追溯 |

---

## 输出格式 (写给自己看)

读完之后, 在 working memory 里维持一份:

```
## 当前 baseline 摘要 (本次写作前读取于 [timestamp])

### 受众 tech 天花板
- 接受: [list]
- 临界 (需要类比消化): [list]
- 禁区: [list]

### Hook 模板
- 时间锚: [list of patterns]
- 数字模式: [list]
- 反差/决断模式: [list]

### 正文 anatomy
- 段落数: X
- bullet 模式: [list]
- 过渡句库: [list]

### 类比层级
- 已用过的类比来源: [生活/职场/CS/...]
- 最高层 (用过的最抽象): [example]
- 最低层 (用过的最具体): [example]

### 红线 (本次必避)
1. [from version table, with record_id]
2. ...

### 高传播主题特征
- [从成品表 点赞/收藏 排序提取]
```

---

## 何时不读

- 任务是非常微小的修改 (改一两个词)
- 已在过去 30 分钟读过且 Bitable 无新版本
- 用户明确说 "skip baseline 这次直接写"

---

## Anti-pattern

❌ "我已经读过 SKILL.md 里的 va7-style.md 了, 不需要再读 Bitable" — static reference 是历史快照, Bitable 是 live 数据。

❌ "成品表只有 6 条, 我扫一眼就行" — 必须 systematic 提取 (受众 tech 天花板 / Hook 模板 / anatomy / 类比层级 / 数据表达模式 / 落款模板 / 传播表现 — 7 项), 不是浏览。

❌ "版本追踪表是历史 noise, 看成品表就够了" — 反了。critique 历史比成功 pattern 更高信息密度。VA7 的红线全在 critique 里, 不在成品里。
