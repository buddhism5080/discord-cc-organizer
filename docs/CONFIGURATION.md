# Configuration

This project is configured primarily through environment variables.

For agent-guided installs, the preferred source is:

1. current process environment
2. Claude settings env (`~/.claude/settings.local.json`, then `~/.claude/settings.json`)
3. cc-connect config for Discord token fallback

Agent installs should not rely on a repository-local `.env` file.

## Required

### `DISCORD_BOT_TOKEN`
Discord bot token used for API calls.

If omitted, `bin/discordctl.py` will try to load a token from `CC_CONNECT_CONFIG`.

## Session store paths

### `CC_CONNECT_CONFIG`
Path to the cc-connect TOML config.

Default:

```text
~/.cc-connect/config.toml
```

### `CC_CONNECT_SESSIONS_DIR`
Directory containing cc-connect session store JSON files.

Default:

```text
~/.cc-connect/sessions
```

### `CC_CONNECT_DATA_DIR`
Base cc-connect data directory.

Default:

```text
~/.cc-connect
```

### `CLAUDE_PROJECTS_DIR`
Claude transcript/project storage used by the watcher cleanup flow.

Default:

```text
~/.claude/projects
```

## Repository-local paths

### `DISCORD_SKILL_ROOT`
Override repository root.

Default: inferred from the script location.

### `DISCORD_SKILL_STATE_DIR`
State directory for organize plans, migration registry, watcher state, and auto-title state.

Default:

```text
<repo>/state
```

### `DISCORD_SKILL_INSTALL_REPO_ZIP_URL`
Optional GitHub/source archive URL used by `install`.

Default:

```text
https://github.com/buddhism5080/discord-cc-organizer/archive/refs/heads/main.zip
```

## LLM title/summary generation

### `DISCORD_SKILL_LLM_BASE_URL`
### `DISCORD_SKILL_LLM_API_KEY`
### `DISCORD_SKILL_LLM_MODEL`

If all three are present, `discordctl.py` can generate thread titles and summaries.

## cc-connect restart integration

Used by `bin/discord-migrate.py`.

### `CC_CONNECT_LOG`
Path to the cc-connect log file.

Default:

```text
~/.cc-connect/cc-connect.log
```

### `CC_CONNECT_BIN`
Executable used to start cc-connect.

Default:

```text
cc-connect
```

### `CC_CONNECT_MATCH`
Substring used to detect running cc-connect processes in `ps` output.

Default:

```text
cc-connect --config <CC_CONNECT_CONFIG>
```

### `CC_CONNECT_START_CMD`
Optional full shell command used instead of `CC_CONNECT_BIN`.

Use this if your install path or startup method is unusual.

## Discord API

### `DISCORD_API_BASE`
Discord API base URL.

Default:

```text
https://discord.com/api/v10
```
