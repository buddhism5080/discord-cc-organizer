[English](./README.md) | 简体中文

# discord-cc-organizer

`discord-cc-organizer` 是一个面向高 thread 密度工作流的 Discord 管理工具集，使用 Python 编写。

它最初围绕 Claude Code + cc-connect 工作流构建，后被抽取为独立仓库。

## 功能

- 查看当前 Discord thread / channel 上下文
- 重命名、归档、关闭 thread
- 创建 category、text channel、forum channel
- 为活跃 Discord threads 生成 organize 规划
- 应用 organize 规划，创建结构并迁移 threads
- 将正在进行的对话 continuation 到新的 Discord thread，同时保留 session 映射
- 监视 cc-connect session store，并为新的 Discord session 自动命名
- 当 Discord thread 被删除时，自动清理相关本地 cc-connect / Claude 垃圾
- 在 organize 执行后清理旧 channel 和空 category

## 仓库结构

```text
bin/
  discordctl.py
  discord-watch.py
  discord-migrate.py
docs/
  CONFIGURATION.md
  CONTINUATION_MIGRATE.md
  INSTALLATION.md
  WATCHER.md
state/
.env.example
AGENTS.md
LICENSE
README.md
README.zh-CN.md
SKILL.md
```

## 脚本说明

### `bin/discordctl.py`
主 CLI，负责 Discord 管理和 organize 规划。

### `bin/discord-watch.py`
Watcher，扫描 cc-connect session store，并为新的 Discord thread 自动命名。

### `bin/discord-migrate.py`
Continuation migration 编排器，用于把一个活跃的 Claude/cc-connect 会话迁移到新的 Discord thread。

## 依赖

- Python 3.11+
- 具有相应频道 / thread 权限的 Discord bot token
- 如果要使用 watcher / migration 功能，需要兼容的 `cc-connect` session-store 工作流

## Discord bot 权限

在安装或运行前，bot 至少应具备这些服务器权限：

- View Channels
- Manage Channels
- Send Messages
- Read Message History
- Create Public Threads
- Send Messages in Threads
- Manage Threads

推荐 OAuth2 scopes：

- `bot`
- `applications.commands`

推荐权限位（permission bitfield）：

- `395137059856`

授权链接模板示例：

```text
https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&scope=bot%20applications.commands&permissions=395137059856
```

授权方式：

1. 打开 Discord Developer Portal
2. 找到你的 application 和 bot
3. 在 OAuth2 URL 生成器里选择 `bot` 和 `applications.commands`
4. 给目标 server 授予上述权限
5. 完成授权后，再重新执行安装

## 快速开始

### 查看当前上下文

```bash
python3 bin/discordctl.py info --json
```

### 生成 organize 计划

```bash
python3 bin/discordctl.py organize-plan --goal "Organize active Discord threads" --json
```

### 预览 apply

```bash
python3 bin/discordctl.py organize-apply --plan-id <plan_id> --dry-run --json
```

### 执行 organize 计划

```bash
python3 bin/discordctl.py organize-execute --plan-id <plan_id> --json
```

### 忽略 quiet-window blocker 强制执行

```bash
python3 bin/discordctl.py organize-execute --plan-id <plan_id> --force-busy --json
```

## 配置

参见：

- `docs/CONFIGURATION.md`
- `docs/INSTALLATION.md`
- `.env.example`

## Agent 引导安装

如果由 agent 安装本仓库，请使用：

- `AGENTS.md`

该文件规定 agent 应：

- 先判断当前环境是否真的是 Discord + cc-connect + Claude Code
- 自动检查 bot 是否已经具备当前 server 所需权限；如果权限不足，则先指导用户授权再继续
- 不在不匹配环境里安装
- 自动填充所有可探测的本地设置
- 只向用户确认 AI endpoint / key / model
- 在匹配环境中安装成功后自动复用或创建默认结构：已有顶层 `维护`/`入口` channel 就复用，否则创建 `服务器维护专用`；已有 `回收` 类就复用，否则创建 `回收站`
- 将当前 thread continuation-migrate 到 `服务器维护专用`，并改名为 `Discord/cc-connect 控制台`
- 清理保护逻辑同时保护：名称含 `回收` / `维护` / `入口` 的受保护结构；包括 `回收站` category 及其子频道，以及顶层 `服务器维护专用` channel
- 之后自动后台启动 watcher
- 也支持后续通过自然语言再次要求启动 watcher

## 其他文档

- `docs/WATCHER.md`
- `docs/CONTINUATION_MIGRATE.md`

## 当前定位

这个仓库已经可用，但仍然保留了其原始环境的一些特征：

- 假设存在 cc-connect 风格的 session store
- 假设存在 Claude 导向的对话工作流
- 还没有自动化测试
- 部分行为仍偏向个人运维工作流，而不是通用产品

因此，它更适合被理解为一个“已抽取、可运行的工具集”，而不是一个完全打磨好的通用终端产品。

## 许可证

MIT
