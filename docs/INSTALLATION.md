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

## Permission check during agent install

An agent should automatically run:

```bash
python3 bin/discordctl.py permissions-check --json
```

If required permissions are missing, the agent should stop and guide the user to re-authorize the bot before continuing.

## Post-install default structure and watcher startup

If installation is happening in a matching Discord + cc-connect + Claude Code environment, the agent should do this after installation succeeds:

1. finish installation and config writing first
2. reuse an existing top-level text channel if its name contains `维护` or `入口`; otherwise create `服务器维护专用`
3. reuse an existing category if its name contains `回收`; otherwise create `回收站`
4. continuation-migrate the current thread into `服务器维护专用`
5. rename the new continuation thread to `Discord/cc-connect 控制台`
6. restart/report as needed for the migration flow
7. start `python3 bin/discord-watch.py --daemon` in the background
8. optionally store logs/PID information under `state/watcher/`

A later natural-language request such as "启动 watcher" or "后台运行 watcher" should still work the same way: re-check the environment, and if it matches, start the watcher in the background.

## Important

Do not treat this as a generic Discord bot package.
It is an operator toolkit built around an existing local Discord + cc-connect + Claude Code workflow.
