# AGENTS.md

This file tells an agent how to decide whether this repository should be installed in the current environment, and how to perform the installation safely.

## Goal

Install and wire up `discord-cc-organizer` **only** when the current environment is clearly a:

- Discord workflow
- cc-connect workflow
- Claude Code workflow

If the environment does **not** match, do **not** install anything.

---

## Install gate: when to proceed

Before installing, check all of the following.

### Required signals

Proceed only if the environment appears to satisfy **all** of these:

1. **Claude Code environment is present**
   - Strong signals include any of:
     - `CC_SESSION_KEY` exists
     - `CC_PROJECT` exists
     - `~/.claude/` exists
     - the user explicitly says they are using Claude Code

2. **cc-connect is present**
   - Strong signals include any of:
     - `~/.cc-connect/config.toml` exists
     - `~/.cc-connect/sessions/` exists
     - `cc-connect` executable is available in `PATH`
     - the user explicitly says they are using cc-connect

3. **Discord usage is present**
   - Strong signals include any of:
     - current `CC_SESSION_KEY` starts with `discord:`
     - the user says they want Discord thread/channel management
     - existing config/session store clearly contains Discord platform data

If any of the three areas above are missing or unclear, **stop** and tell the user that the repository is intended only for Discord + cc-connect + Claude Code environments.

Do not install in generic Python environments.
Do not install in non-Discord chat environments.
Do not install just because the repository is present.

After the environment gate passes, the agent should also run a bot permission check against the current Discord server before continuing.

---

## Install policy

If the environment matches:

- perform installation proactively
- download the repository from GitHub instead of installing from unrelated local files
- install it into the Claude Code skill area (for example under `~/.claude/skills/discord-cc-organizer/`)
- fill in all detectable values automatically from the current runtime environment, cc-connect, and Claude settings
- do not require `.env` for agent installation
- if a required value is not available from the current environment, ask the user for it or write it into Claude local settings so it becomes available as an environment variable
- ask the user only for:
  - `DISCORD_SKILL_LLM_BASE_URL`
  - `DISCORD_SKILL_LLM_API_KEY`
  - `DISCORD_SKILL_LLM_MODEL`

Everything else should be auto-detected or defaulted if possible.

---

## Auto-detectable values

The agent should try to fill these automatically.

### Repository-local

- `DISCORD_SKILL_ROOT` = repository root
- `DISCORD_SKILL_STATE_DIR` = `<repo>/state`

### cc-connect

- `CC_CONNECT_CONFIG` = first existing match, usually `~/.cc-connect/config.toml`
- `CC_CONNECT_DATA_DIR` = `~/.cc-connect`
- `CC_CONNECT_SESSIONS_DIR` = `~/.cc-connect/sessions`
- `CC_CONNECT_LOG` = `~/.cc-connect/cc-connect.log`

### Claude

- `CLAUDE_PROJECTS_DIR` = `~/.claude/projects`

### Runtime defaults

- `DISCORD_API_BASE` = `https://discord.com/api/v10`
- `CC_CONNECT_BIN` = `cc-connect`
- `CC_CONNECT_MATCH` = `cc-connect --config <CC_CONNECT_CONFIG>`

### Required Discord bot permissions

The agent should verify that the bot has at least:

- View Channels
- Manage Channels
- Send Messages
- Read Message History
- Create Public Threads
- Send Messages in Threads
- Manage Threads

Recommended OAuth2 scopes:

- `bot`
- `applications.commands`

Recommended permissions bitfield:

- `326417583120`

### Discord token source

Prefer this order:

1. existing `DISCORD_BOT_TOKEN` env var
2. token discovered from `CC_CONNECT_CONFIG`

Do not ask the user for the bot token if it is already discoverable.
Do not echo secrets back to the user.

---

## What to install

The agent should set up the repository for local use, not publish it.

Recommended install actions:

1. Download the repository from GitHub into the Claude Code skill area (for example `~/.claude/skills/discord-cc-organizer/`)
2. Ensure the `state/` directory exists inside that installed skill directory
3. Detect all auto-detectable variables from the current runtime environment
4. If install-local non-secret `DISCORD_*` values need to survive outside the current process, prefer writing them to Claude local settings so they become runtime environment variables
5. Run `python3 bin/discordctl.py permissions-check --json`
6. If permissions are insufficient, stop and guide the user to re-authorize the bot, then wait
7. Leave LLM variables pending until confirmed
8. Fetch the canonical GitHub repository into the Claude skill area
9. Persist the detected non-secret install/runtime `DISCORD_*` values into Claude local settings env
10. Tell the user exactly what was auto-detected
11. Tell the user which LLM fields still need confirmation
12. After installation is fully confirmed, automatically ensure default Discord server structure:
   - ensure a general-purpose top-level entry channel exists: reuse a top-level channel containing `入口`, or create `通用入口`
   - ensure a maintenance/control top-level channel exists: reuse a top-level channel containing `维护`, or create `服务器维护专用`
   - ensure a recycle category exists: reuse a category containing `回收`, or create `回收站`
13. Continuation-migrate the current thread into the maintenance/control top-level channel
14. Rename the new continuation thread to `Discord/cc-connect 控制台`
15. Restart the relevant local runtime if needed and report completion in the new control thread

Important:

- If the environment matches and installation succeeds, the agent should automatically create the default Discord server structure first
- The default structure should distinguish:
  - general-purpose entry channel: `通用入口`
  - maintenance/control channel: `服务器维护专用`
  - recycle category: `回收站`
- After that, the agent should continuation-migrate the current thread into `服务器维护专用`
- The new thread title should be `Discord/cc-connect 控制台`
- After migration/restart succeeds, report completion in the new control thread, then ensure the watcher is running

---

## What NOT to do

- Do not install if the environment is not clearly Discord + cc-connect + Claude Code
- Do not continue installation if the bot is missing required Discord permissions
- Do not ask unnecessary questions for values that can be detected automatically
- Do not expose bot tokens, API keys, or secret config values in output
- Do not depend on `.env` for agent installation
- Do not install from unrelated local copies when the canonical GitHub repository should be fetched
- Do not fabricate paths that do not exist
- Do not assume LLM provider/model values
- Do not start the watcher before installation/config writing has completed successfully

---

## Agent interaction pattern

### If environment does not match

Reply briefly like this:

> This repository is intended for Discord + cc-connect + Claude Code environments. I did not install it because the current environment does not clearly match that setup.

### If the bot is missing required Discord permissions

Stop before installation and reply briefly like this:

> The bot does not yet have the required Discord server permissions. Please re-authorize it with `bot` + `applications.commands` scopes and the required channel/thread permissions, then I can continue installation.

### If environment matches but LLM values are missing

Auto-fill everything else, ask for the missing LLM values, and then complete installation. After installation succeeds, automatically create the default Discord server structure, continuation-migrate the current thread into the maintenance channel as `Discord/cc-connect 控制台`, then start the watcher in the background.

A short summary should include:

- what was detected
- what was written
- where the config lives
- that `服务器维护专用` and `回收站` were created or already existed
- that the current thread was migrated to `Discord/cc-connect 控制台`
- that the watcher has been started in the background

### If environment matches and LLM values already exist

Complete installation without asking, automatically create the default Discord server structure, continuation-migrate the current thread into the maintenance channel as `Discord/cc-connect 控制台`, automatically start the watcher in the background, then summarize:

- what was detected
- what was written
- where the config lives
- that `服务器维护专用` and `回收站` were created or already existed
- that the current thread was migrated to `Discord/cc-connect 控制台`
- that the watcher has been started in the background

### If the user later asks to run the watcher again

Natural-language requests like these should be treated as valid watcher-start requests:

- "启动 watcher"
- "后台运行 watcher"
- "把 watcher 挂起来"
- "如果当前环境合适就启动 watcher"

In that case, the agent should:

1. re-check that the environment is still Discord + cc-connect + Claude Code
2. refuse to start if the environment does not match
3. start the watcher in the background if it does match
4. record a PID file under `state/watcher/` if practical
5. tell the user the watcher is now running in the background

The agent should prefer a background command equivalent to:

```bash
python3 bin/discord-watch.py --daemon
```

and may redirect logs to a file under `state/watcher/`.

---

## Suggested runtime/local-settings keys

These values should come from the current runtime environment when possible. In the current install flow, only non-secret `DISCORD_*` install/runtime values are persisted automatically; if the agent must persist any relevant values, prefer Claude local settings so they are exposed back as environment variables:

```env
DISCORD_BOT_TOKEN=
CC_CONNECT_CONFIG=
CC_CONNECT_SESSIONS_DIR=
CC_CONNECT_DATA_DIR=
CLAUDE_PROJECTS_DIR=
DISCORD_SKILL_ROOT=
DISCORD_SKILL_STATE_DIR=
DISCORD_API_BASE=https://discord.com/api/v10
DISCORD_SKILL_INSTALL_REPO_ZIP_URL=
DISCORD_SKILL_LLM_BASE_URL=
DISCORD_SKILL_LLM_API_KEY=
DISCORD_SKILL_LLM_MODEL=
CC_CONNECT_LOG=
CC_CONNECT_BIN=cc-connect
CC_CONNECT_MATCH=
CC_CONNECT_START_CMD=
```

---

## Success criteria

An installation is considered successful when:

- the environment is confirmed to be Discord + cc-connect + Claude Code
- repository-local config exists
- all detectable values are filled in
- only AI endpoint/model/key remain pending before confirmation if not yet confirmed
- after confirmation, the default Discord server structure is present (`服务器维护专用` + `回收站`)
- the current thread has been migrated into `服务器维护专用` as `Discord/cc-connect 控制台`
- after that, the watcher is started in the background
- the user receives a short summary of what was installed and whether the watcher is running
