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

---

## Install policy

If the environment matches:

- perform installation proactively
- fill in all detectable values automatically
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

1. Ensure the repository directory exists
2. Ensure the `state/` directory exists
3. Ensure `.env` exists, based on `.env.example`
4. Fill in all auto-detectable variables
5. Leave LLM variables blank if not confirmed
6. Tell the user exactly what was auto-filled
7. Tell the user which LLM fields still need confirmation

---

## What NOT to do

- Do not install if the environment is not clearly Discord + cc-connect + Claude Code
- Do not ask unnecessary questions for values that can be detected automatically
- Do not expose bot tokens, API keys, or secret config values in output
- Do not overwrite a user’s existing `.env` blindly; update only known keys
- Do not fabricate paths that do not exist
- Do not assume LLM provider/model values

---

## Agent interaction pattern

### If environment does not match

Reply briefly like this:

> This repository is intended for Discord + cc-connect + Claude Code environments. I did not install it because the current environment does not clearly match that setup.

### If environment matches but LLM values are missing

Auto-fill everything else, then ask:

> I filled the local paths and cc-connect/Claude settings automatically. I still need your confirmation for the AI endpoint, API key, and model before enabling title/summary generation.

### If environment matches and LLM values already exist

Complete installation without asking, then summarize:

- what was detected
- what was written
- where the config lives

---

## Suggested .env keys

```env
DISCORD_BOT_TOKEN=
CC_CONNECT_CONFIG=
CC_CONNECT_SESSIONS_DIR=
CC_CONNECT_DATA_DIR=
CLAUDE_PROJECTS_DIR=
DISCORD_SKILL_ROOT=
DISCORD_SKILL_STATE_DIR=
DISCORD_API_BASE=https://discord.com/api/v10
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
- only AI endpoint/model/key remain pending if not yet confirmed
- the user receives a short summary of what was installed and what still needs confirmation
