# Installation

This repository is meant for a specific workflow:

- Discord
- cc-connect
- Claude Code

If your environment does not match that stack, do not install it.

## Recommended approach

Use `AGENTS.md` as the agent-facing installation contract.

It tells an agent to:

- detect whether the current environment is the right one
- refuse installation outside the intended workflow
- auto-fill local paths and detectable config values
- ask the user only for AI endpoint / API key / model confirmation

## Manual install outline

1. Copy `.env.example` to `.env`
2. Fill auto-detectable local paths
3. Set `DISCORD_BOT_TOKEN` or ensure `CC_CONNECT_CONFIG` can provide one
4. Verify that the bot has the required Discord server permissions
5. Optionally set LLM variables for title/summary generation
6. Run the scripts from the repository root

## Real install command

A real install orchestration entry now exists:

```bash
python3 bin/discordctl.py install --json
```

## Permission check during agent install

An agent should automatically run:

```bash
python3 bin/discordctl.py permissions-check --json
```

If required permissions are missing, the agent should stop and guide the user to re-authorize the bot before continuing.

## Post-install default structure and watcher startup

If installation is happening in a matching Discord + cc-connect + Claude Code environment, the agent should do this after installation succeeds:

1. finish installation and config writing first
2. ensure a general-purpose top-level entry channel exists: reuse a top-level channel containing `入口`, or create `通用入口`
3. ensure a maintenance/control top-level channel exists: reuse a top-level channel containing `维护`, or create `服务器维护专用`
4. ensure a recycle category exists: reuse a category containing `回收`, or create `回收站`
5. continuation-migrate the current thread into `服务器维护专用`
6. rename the new continuation thread to `Discord/cc-connect 控制台`
7. restart/report as needed for the migration flow, and send an install-complete report in the new control thread
8. start `python3 bin/discord-watch.py --daemon` in the background
9. optionally store logs/PID information under `state/watcher/`

A later natural-language request such as "启动 watcher" or "后台运行 watcher" should still work the same way: re-check the environment, and if it matches, start the watcher in the background.

## Important

Do not treat this as a generic Discord bot package.
It is an operator toolkit built around an existing local Discord + cc-connect + Claude Code workflow.
