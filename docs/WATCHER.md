# Discord Auto-Title Watcher

这个 watcher 不依赖 Claude hooks，而是扫描 `CC_CONNECT_SESSIONS_DIR`（默认 `~/.cc-connect/sessions/*.json`）作为主数据源。每个文件都代表一个 project + work_dir 的会话聚合存储。发现新的 Discord session 后统一调用 `discordctl.py` 完成 AI 命名与 Discord 重命名。

## 入口

```bash
python3 bin/discord-watch.py --daemon
```

如果安装发生在匹配的 Discord + cc-connect + Claude Code 环境中，agent 应在安装成功后先自动确保两套结构存在：用户随手发起对话用的顶层 `通用入口`，以及维护/控制用的顶层 `服务器维护专用`，再确保 `回收站` 存在；随后把当前 thread 迁移为 `Discord/cc-connect 控制台`，在新控制台 thread 回报安装完成，最后再后台启动 watcher。

## 单次扫描调试

```bash
python3 bin/discord-watch.py --dry-run
```

## 工作方式

1. 扫描 `CC_CONNECT_SESSIONS_DIR`
2. 从每个 store 的 `active_session` / `sessions` 中找出新的 `discord:<thread_id>` session_key
3. 读取该 session 的首条 user prompt
4. 调用 `discordctl.suggest_title()` 生成 AI 标题
5. 统一调用 `discordctl.patch_channel(...)` 完成 Discord thread 改名
6. 在 `DISCORD_SKILL_STATE_DIR/auto-title/` 写入状态，避免重复改名
7. 每小时用 Discord API 低频校验这些 thread 是否还真实存在
8. 如果 thread 已消失，则清理对应的 Claude / cc-connect 本地数据。Claude transcript 的定位依赖 `CLAUDE_PROJECTS_DIR` 中的 `agent_session_id` 搜索。

显式为当前 thread 执行 AI 重命名不走 watcher，而是单独使用：

```bash
python3 bin/discordctl.py rename-current-ai --json
```

## 依赖的 AI 配置

可通过环境变量提供：

- `DISCORD_SKILL_LLM_BASE_URL`
- `DISCORD_SKILL_LLM_API_KEY`
- `DISCORD_SKILL_LLM_MODEL`

## 状态文件

- watcher 已发现的 session：`state/watcher/known_sessions.json`
- auto-title 状态：`state/auto-title/*.json`
