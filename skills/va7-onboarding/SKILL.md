---
name: va7-onboarding
description: 新用户接入 VA7 内容创作方案的一次性初始化向导。当用户说"我要开始用这套内容方案"、"帮我初始化"、"新用户开通"、"接入流程"时使用。按顺序完成四步：检查 Lark CLI 授权状态、创建专属灵感库 Bitable、确认妙记可访问性、校准写作风格并生成 reference 档案。四步全部产出登记到用户配置文件。
version: 0.1.0
---

# va7-onboarding：新用户初始化向导

这套方案的核心思想：**让别人能用更好的文字表达出真实的自己**。所有初始化动作都为这一件事服务——拿到这个人真实的语言素材，校准出他自己的文风，之后的每一篇稿子都用他自己的声音写。

## 运行前提

- 本向导在飞书 bridge 环境下运行（`LARK_CHANNEL=1`）。
- 读取用户数据用 `--as user`，创建和写入用 `--as bot`。
- 用户身份授权只能在私聊（p2p）里发起；群里不能发授权链接。

## 四步流程

逐步执行，每步结束把结果登记进用户配置（见下文"用户配置"）。任何一步失败不要静默跳过，向用户说明缺什么、怎么补。

### 第 1 步：检查 Lark CLI 授权

```bash
lark-cli doctor --json
```

- 用户身份可用 → 记录状态为 `ok`，进入第 2 步。
- 用户身份缺失且当前是私聊 → 按两阶段流发起授权（`auth login --no-wait` 拿链接发给用户，然后 `auth login --device-code <code>` 前台阻塞等待）。
- 用户身份缺失且当前是群聊 → 告诉用户"授权要在私聊里做，请单独私信我"，停止后续步骤（后面三步都依赖用户身份读取）。

### 第 2 步：创建专属灵感库

用 provision 脚本为该用户创建一套全新的五表 Bitable：

```bash
python3 <skill_dir>/scripts/provision_base.py --name "<用户名>灵感库" --config <user_config.json>
```

脚本行为：

- 用 `--as bot` 从模板定义（`scripts/base_template.json`）创建 base 和五张表：原始素材库、选题库、内容生产排期、成品内容、写作复盘任务。
- 把 base_token 和五张表的 table_id 写回用户配置文件。
- 创建后按全局规则处理权限：请求人本人加 full_access；不开链接分享。

**不要**把任何人现成的生产库 token 给新用户——每个用户都用 provision 脚本建自己的库。

### 第 3 步：确认妙记可访问性

```bash
lark-cli minutes +search --as user --owner-ids me --page-size 5 --json
```

- 能列出记录 → 记录 `minutes: ok`，顺手记录最近一场妙记的 token 作为风格校准的候选语料。
- 列表为空 → 询问用户有没有会议录音/口述音频/历史文稿等其他语料来源；妙记不是必需品，风格校准可以用任何真实语料（见第 4 步）。

### 第 4 步：校准写作风格

调用 `va7-voice-profile` skill。语料来源按优先级：

1. 飞书妙记转写稿（用 `minutes +detail --transcript` 拉取，抽出发言人是本人的段落）
2. 历史写作稿 / 已发布内容（用户给链接或文本）
3. 飞书聊天记录（任何能拿到本人真实表达的地方）

拿不到任何语料时不要编造风格档案——明确告诉用户缺语料，让他提供任意一种。产出 `writing-style-profile.md` 存入用户目录，路径登记进用户配置。

## 用户配置

每个用户一个配置文件，存放在 `<workspace>/va7-users/<feishu_open_id>/config.json`：

```json
{
  "open_id": "ou_xxx",
  "display_name": "",
  "created_at": "",
  "lark_auth": "ok | pending | missing",
  "base": {
    "base_token": "",
    "tables": {
      "materials": "",
      "topics": "",
      "schedules": "",
      "finished": "",
      "writing_runs": ""
    },
    "url": ""
  },
  "minutes": "ok | empty | unavailable",
  "voice_profile": {
    "path": "",
    "calibrated_at": "",
    "corpus_sources": []
  },
  "onboarding_completed_at": ""
}
```

四步全绿后填 `onboarding_completed_at`。之后的创作流程（选题→访谈→大纲→成稿）从这份配置读 base_token 和风格档案路径，不再读任何硬编码值。

## 中断与续跑

每一步落盘后可续跑：重新执行时先读用户配置，跳过已完成的步骤，从第一个未完成步骤继续。

## 权限一次性拿全（va7-briefing 依赖）

初始化就要确认应用具备：扫用户全部妙记（minutes 读权限）、建群（im:chat）、建多维表格（bitable）、建文档。这些是每日早报和建库的地基，缺哪个 scope 当场补，不要等日运行时才暴露。早报功能开通时顺手建"XX 内容早报"群（bot + 用户本人），chat_id 登记进 config.json（briefing_chat 字段）。
