# 安装指南（写给帮你安装的 agent）

这套 skillset 是 VA7 的内容生产方案，跑在用户自己的机器和自己的 agent 里。你（agent）按下面的步骤装，装完由 va7-onboarding 完成初始化。定位和设计原则见 README。

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

装完让用户对你说一句"我要开始用这套内容方案，帮我初始化"，这句会触发 va7-onboarding，走完授权检查、建他自己的灵感库、妙记确认、文风校准四步。

## 初始化之后必须做的一件事

onboarding 会产出用户自己的 config.json，把它的路径导出：

```bash
export VA7_USER_CONFIG=<用户目录>/config.json
```

注意 export 只对当前会话生效。装完把这一行追加进用户的 shell 配置（~/.zshrc 或 ~/.bashrc），否则下次会话脚本会拒跑。

## 更新

git clone 安装的：va7-pipeline 每天第一次调用时自动检查远程更新，有更新会列出来等用户确认，确认后 `git pull` 并重新执行上面的 cp 步骤。zip 安装的没有 OTA，要更新就找 VA7 重新拿包。
