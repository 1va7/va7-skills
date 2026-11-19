# va7-skills

市面上做内容的 agent 都从"什么火"出发：整理爆款维度，追热点，替你判断该说什么。这套东西反着来。它只服务一种人——创始人、合伙人、高管，脑子里本来就有一堆选题和洞见，缺的只是把它们变成内容的时间和笔力。

源头不同，后面的设计都从这里推出来。因为内容来自你本人，所以第一步永远是文风校准，不是写稿；因为观点是你自己的，所以宁可访谈追问，也不替你编一个立场；因为稿子挂在你的名字上，所以旁听来的观点只转述，编造是红线。

一句话：AI 出笔力和工序，你出观点和判断。

## 生产线

素材 → 选题 → 大纲 → 口播全文 → 终稿 → 排期发布 → 复盘

| 阶段 | skill | 干什么 |
|---|---|---|
| 开通 | va7-onboarding | 四步初始化：授权检查、建你自己的灵感库 Bitable、妙记确认、文风校准 |
| 地基 | va7-voice-profile | 从你的妙记、文章、聊天语料里量出 writing-style-profile，之后所有稿子按这个声音写 |
| 入口 | va7-pipeline | 总路由。你说"我有个想法""这是场会议""帮我找选题"，它在背后判断该走哪条路 |
| 选题 | va7-interview | 立场、受众、证据没聊清楚之前不开写 |
| 写稿 | va7-script | 口播论证大纲、全文写作、口述整理 |
| 入库 | va7-library | 素材抓取、转写、校验、写进灵感库 |
| 发布 | va7-publish | 文字标题、正文（≤200 字）、Hashtag、章节（标题 + 换章句，有 SRT 时补时间）写回灵感库 |

## 几条规矩

先校准再写稿。没有文风档案不开写，因为档案不是几行形容词，是从你自己的语料里量出来的：句长、因果连接词、固定收尾、禁用词，每条带证据，写完还要过量化自检。

粗选题不等于写稿授权。缺立场和证据就先访谈补齐，所以你不会收到一篇看起来很顺、但不是你的稿子。

编辑判断留给人。素材到选题的拆解是判断题，不自动一比一转换，不值得转的会写明理由，因为工具不该替你决定说什么。

用户数据私有。你的语料、档案、灵感库只存在你自己的目录和你自己的 Bitable 里，永远不进这个仓库。

## 新用户接入

1. 跑 va7-onboarding，四步走完，产出你的用户目录和 config.json。
2. 二选一：`export VA7_USER_CONFIG=<用户目录>/config.json`；或者做成部署级全局配置，在 skills 目录旁放一个私有的 `va7-config/default.json`（格式见 `va7-pipeline/config/default.example.json`，文风档案和 style_rules.json 可放同目录，路径写相对路径），这样所有会话、所有沙箱读到同一份。
3. 之后所有请求都从 va7-pipeline 进。

配置查找顺序：`VA7_USER_CONFIG` → `va7-config/default.json` → `va7-pipeline/config/default.json`。`python3 skills/va7-pipeline/scripts/va7config.py` 打印实际读到的 base、表和文风档案路径。都没有时，只读脚本跳过灵感库检索，写入脚本直接报错。

## 闸门（v0.6）

写稿和发布不再靠 agent 记得规则，改成脚本放行：每个环节先预检（没读完 skill、缺输入就停），过程中的人确认只认人的原话和消息 id，交付前机器项全过、人逐项审过才发校验码。共用库 `va7-pipeline/scripts/gatelib.py`；写稿闸门 `script_gate.py` 和文风机检 `style_check.py` 也放在 `va7-pipeline/scripts/`，发布闸门是 `va7-publish/scripts/publish_gate.py`。文风机检规则 style_rules.json 属于个人文风，不在仓库里，由 config 的 `voice_profile.style_rules` 指过去。

## OTA

`scripts/ota_check.sh` 每天第一次调用时检查远程有没有更新，有更新会列出改了什么，你确认才拉取，绝不静默覆盖。

## TODO

- va7-script 内置的风格参考目前是 VA7 本人沉淀，新用户先当脚手架用，攒够自己的成品稿后重校准替换。
- 视频剪辑（va7-monologue-video-editor）和封面（va7-video-cover-maker）还没多用户化，暂不进包。
