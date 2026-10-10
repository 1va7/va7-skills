---
name: va7-script
description: 将已明确的内容方向和素材整理成口播论证大纲，再按用户要求写全文、续写或整理用户口述。适用于 bullet points 大纲、已确认方向写稿、IP 视频改稿；只有粗选题且缺少立场或证据时，先用 va7-interview 补足真实缺口。
---

# 口播文案写作

为科技/创业/AI 领域创作者写口播视频文案。声音来自用户本人的 writing-style-profile（由 va7-voice-profile 生成），本 skill 提供论证结构、证据纪律和写作流程。

## 写稿前必读

1. 用户的文风档案：`<用户目录>/writing-style-profile.md`（路径在 config.json 的 voice_profile.path，config 由 va7-onboarding 产出）。第八节"模仿要点"是硬规则，写完按它自检。
2. 若用户目录下存在 `style-references/`（创作者本人的历史风格沉淀），写全文或整理口述时一并参考。

## 先确定当前产物

默认先交论证大纲；用户明确要求直接全文、续写或改稿时，交相应产物。不能把方向确认、已有 brief 或"跳过采访"自动解释为全文授权，也不能因文件缺失否认对话里已经给出的确认。

用当前用户原始请求运行辅助判断；不要把整段历史或 agent 改写的摘要当作本轮指令：

```bash
python3 ~/.claude/skills/va7-script/scripts/pre_draft_gate.py \
  --input "<用户本轮原始请求>" \
  --brief "<可选: content_brief.json>"
```

返回含 `decision`、`requested_artifact` 和 `may_write_full_draft`：

| decision | 下一步 |
|---|---|
| `ready_to_outline` | 只输出论证大纲，事实缺口标明待补 |
| `ready_to_draft` | 根据当前明确要求或同版本授权写全文 |
| `ready_to_revise` | 恢复被修改的原文，按指定范围整理、续写或改稿 |
| `needs_context` | 从对话、原文和已有文件恢复缺失状态；仍缺关键信息才定点提问 |
| `route_to_interview` | 粗选题确实缺立场、方向或证据，用 `va7-interview` 补缺口 |

脚本是保守的辅助判断；用户当前意图优先。材料不足时不编造一手经验。

### 继续任务时保存确认依据

持续多轮创作时，可在 `content_brief.json` 增加 `writing_state`（stage / outline_version / outline_confirmation / full_draft_authorization，含用户原话定位）。只在真实发生后更新状态；主张或大纲实质改变时递增版本，旧版确认不能自动批准新版。不为小改动额外建文件。

## 核心原则

1. **开头提出正文能兑现的问题。** 按本篇素材选择案例冲突、具体问题、反共识判断，或"背书→张力→价值"的 ABC 写法。数字和近期事件需要真实来源；不固定句数或字数。若开头承诺清单或答案，正文需要实际回答。详见 [references/hook-patterns.md](references/hook-patterns.md)。
2. **"为什么"从机制出发。** 从目的出发解释是废话（"助理收到指令就执行是正常的"）；要讲机制/原理层面的原因。
3. **保持真实的论证关系。** 分类时检查层级一致、含义不重叠；已确认的结构不能因新增细节擅自改层级。
4. **用容易理解的词作认知锚点。** 造词是给新概念一个传播抓手，不是为了制造反共识。测试：删掉造词论点还能讲通→好；论点崩塌→删。
5. **讲故事为论证服务。** 具体性（真实的人、时间、数字）、重温感（有真实动作和对白素材时）、意义（takeaway 与主题相关）三要素按素材自然取用；不为故事感编造时间、对话或客户经历。用于证明判断的案例直接复述事实同样有效。
6. **完整口播稿格式。** 连贯段落、可直接念出来；不用 bullet points 和 markdown 符号；短句不等于短段，每段通常 2-4 句，只有金句和强转折才单句成段。输出任何稿件必须附 `字数：X 字（脚本统计）`，用 `scripts/count_script_chars.py` 统计，禁止心算。
7. **深度体现为机制和判断能力。** 主要论点要让观众多会一个判断，用必要细节证明判断，删去重复总结和离题支线，不靠加框架、加分类或凑字数补深度。沿用用户已有的身份和结束语；课程或服务邀请需核对当次事实。
8. **递进只用于真实的递进关系。** 上一方案的局限确实引出下一方案时才写"X 解决了什么、仍缺什么、为什么需要 Y"；并列来源不虚构先后。
9. **Adversarial 研究（紧触发）。** 凡"市面上 X 都解决不了 Y""没有 Z 能做""要点名 2+ 个项目并贬低"类 claim，写正文前派 subagent 做最强 steelman 再转诚实评估。不做这步直接写，几乎肯定被懂行观众一句话打掉。完整协议见 [references/research-protocols.md](references/research-protocols.md) 第一部分。
10. **IP 立场 = 你的真实认知，不是 punch 最大化版本。** 写完每段问：这是我实际这么想的，还是为了视频好看？后者删掉重写。最严的失败模式：把别人（比如客户 CTO）的论点当成 IP 主张。
11. **Multi-party transcript reading。** 读多人对话转录稿走三轮：列各发言者 position（不合并）→ 标 agreed / contested → 明确 IP 本人的真实位置（可能是 contested 一方 less-punchy 的版本）。测试：能引用一句具体台词表明用户认同该 thesis 吗？不能就不要当 IP 立场。完整协议见 [references/research-protocols.md](references/research-protocols.md) 第二部分。

## 过程纪律

- **Rationale 是 upfront 约束，不是事后辩护。** 写 draft 前先列 ≤5 条 constraint（skill 规则 + 用户当前指令），写完只用一行确认每条状态。
- **每轮围绕当前产物推进。** 大纲阶段便于检查主张和证据；整稿阶段交自然段；局部修改只改指定部分。有多个可行方案给明确推荐，只提出真正影响下一步的待决问题。

## 写作流程

### -1. 确认 content brief

写稿前必须能引用：selected direction / thesis、用户真实立场、受众、viewer payoff、key tension、mechanism、至少一个 personal evidence、non-goals。先从对话和已恢复文件找；真正缺立场或关键证据才用 `va7-interview` 追问。大纲可标待补事实，不能把占位写成已发生的经历。

### 0. 写作前读经验底库（推荐）

有同类成品和历史修改记录时，查用户自己灵感库的成品表与版本追踪表（表 id 在 config.json），提取受众技术天花板、hook 模板、反复打回的 anti-pattern。读取方法见 [references/research-protocols.md](references/research-protocols.md) 第三部分。

### 1. 交付可审核的论证大纲

规格见 [references/speaking-outlines.md](references/speaking-outlines.md)。用具体判断和必要机制/案例支撑主线，不固定条数；同一轮请用户修改或确认，不要先写全文再倒提纲。

### 2. 按用户选择展开

大纲确认后可由用户口述、agent 代写或共同补关键段。用户明确要求直接写全文时尊重该选择；保留真实材料不足的边界。

### 3. 整理或改稿

给开头按要求续写；给整稿按授权修错字、重复、衔接和指定段落。保留原始口述与整理稿的来源，不把用户知识记成 agent 原创。

### 4. 验收当前产物

大纲检查主张能否被依据支持；完整稿再检查自然段、可念性和字数。事实与产品能力在录制前核对。

## 交付前硬检查

输出完整稿或口播替换段前：将最终口播正文存临时文件 → `python3 ~/.claude/skills/va7-script/scripts/count_script_chars.py --file <临时文件>` → 在稿件后写 `字数：<total_chars> 字（脚本统计）`。禁止"约 X 字"，禁止模型自数，没有脚本统计结果不交付。

## 参考

- [references/speaking-outlines.md](references/speaking-outlines.md) — 大纲规格
- [references/hook-patterns.md](references/hook-patterns.md) — 开头写法
- [references/writing-principles.md](references/writing-principles.md) — 通用写作原则
- [references/research-protocols.md](references/research-protocols.md) — 三项研究协议
