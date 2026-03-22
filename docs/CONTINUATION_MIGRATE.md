# Continuation Migrate (cold migration)

这是 `/discord organize` 的主执行方向设计：

- 创建一个新的 continuation thread
- 旧 thread 与新 thread 互相附链接与整理摘要
- 旧 thread 关闭
- 停止 cc-connect
- 修改 `CC_CONNECT_SESSIONS_DIR` 中的 session 映射
- 让新 thread 接管旧 `agent_session_id`
- 重启 cc-connect
- 通过 Discord API 向 organize thread 报告完成

## 当前实现状态

已完成：
- `migration_registry.json` 支持
- watcher 识别 migration registry，避免误清理
- `discord-migrate.py` 冷迁移 orchestrator 骨架
- dry-run 无副作用
- 默认 continuation 标题自动加编号（如 `②`）
- 迁移完成后通过 Discord API 直接向 organize thread 报告结果
- quiet-window 规则：
  - 只检查已绑定到 cc-connect 的 Discord thread
  - 排除 organize thread
  - 最近 5 分钟无消息则允许迁移

未完成/待谨慎验证：
- 真实迁移演练
- 失败回滚
- 管理 thread 自动调用迁移 orchestrator
- organize 方案与执行串联

## 关键文件

- `bin/discordctl.py`
- `bin/discord-watch.py`
- `bin/discord-migrate.py`
- `state/migration_registry.json`

## 风险提示

真实迁移会：
- 关闭旧 thread
- 冷重启 cc-connect
- 改写 session store

因此必须只在确认的 quiet window 中运行。
