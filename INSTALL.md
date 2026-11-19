# 安装指南（写给帮你安装的 agent）

这套 skillset 是 VA7 的内容生产方案，跑在用户自己的机器和自己的 agent 里。你（agent）按下面的步骤装，装完直接运行 va7-onboarding 完成初始化，全程不需要用户再念咒语。定位和设计原则见 README。

## 前提

- 用户的 agent 运行环境（Claude Code 或 Codex，skills 目录分别为 `~/.claude/skills/` 和对应的 codex skills 目录）
- git 和 Python 3.10+
- lark-cli 已安装，并且配置好用户自己的飞书应用（bot + user 双身份）。因为整套流程建立在飞书妙记、Bitable 和文档之上，没有这一步跑不动。没配好也没关系——va7-onboarding 第一步会做诊断，明确告诉你缺什么、差哪几个权限点，照着补就行

## 取代码

三选一：

```bash
git clone https://github.com/1va7/va7-skills.git
```

大陆网络访问 GitHub 不稳定时：向 VA7 要 Gitee 镜像地址 clone，或直接解压他发的 zip 包（zip 更新时重新要一份覆盖即可，没有 OTA）。

## 安装

```bash
cd va7-skills
cp -r skills/va7-* ~/.claude/skills/   # Codex 用户拷到对应 skills 目录
```

装完立即运行 va7-onboarding，替用户走完初始化四步：飞书授权检查、创建他自己的灵感库 Bitable、妙记访问确认、文风校准。缺什么先诊断清楚再补（飞书应用、lark-cli、权限点），需要用户本人操作或确认的再去找他；文风校准需要用户确认哪几场会议/文章是他的语料。

### 装在 Antry bot 上

Antry 的技能目录是只读的，要由这个 bot 的管理员在 bot 的沙箱里上架；而且单个技能上架有约 93KB 的上限。用仓库自带的脚本，一条命令装完全部技能：

```bash
python3 scripts/antry_install.py --bot <你的 bot 名> --dry-run   # 先看每个技能的大小
python3 scripts/antry_install.py --bot <你的 bot 名>
```

脚本会去掉 tests/，超限的技能（va7-library、va7-monologue-video-editor）把最大的几个 Python 脚本 gzip 压缩，原位置留一个同名的小启动文件，调用方式和路径都不变。下一条消息起生效。

Antry 沙箱里不要用 `export`（不跨会话）：把 config 做成部署级的，建一个私有技能目录 `va7-config/`，放 `default.json`（格式见 `skills/va7-pipeline/config/default.example.json`，文风档案和 style_rules.json 放同目录、写相对路径）和一个说明用的 SKILL.md，同样 `antry skills push ./va7-config --bot <bot>`。脚本没有 VA7_USER_CONFIG 时会自动读它。

### 封面技能的大文件

字体和历史样本图不随技能分发。用封面技能前先跑一次（之后每次开工也跑，已就绪时秒过）：

```bash
python3 ~/.claude/skills/va7-cover-tools/scripts/cover_assets.py ensure
```

它会装 Pillow，从 Noto 官方仓库下载字体，从本仓库 Release `cover-assets-v1` 下载样本图，都按 sha256 校验，缓存在 `~/.cache/va7-cover-assets`。

## 初始化之后必须做的一件事

onboarding 会产出用户自己的 config.json，把它的路径导出：

```bash
export VA7_USER_CONFIG=<用户目录>/config.json
```

注意 export 只对当前会话生效。装完把这一行追加进用户的 shell 配置（~/.zshrc 或 ~/.bashrc），否则下次会话脚本会拒跑。也可以不用环境变量，改用上面「装在 Antry bot 上」里的 va7-config 部署级配置；查找顺序是 `VA7_USER_CONFIG` → `va7-config/default.json` → `va7-pipeline/config/default.json`。

## 更新

git clone 安装的：va7-pipeline 每天第一次调用时自动检查远程更新，有更新会列出来等用户确认，确认后 `git pull` 并重新执行上面的 cp 步骤。zip 安装的没有 OTA，要更新就找 VA7 重新拿包。
