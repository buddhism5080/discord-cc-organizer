English | [简体中文](./README.zh-CN.md)

# discord-cc-organizer

`discord-cc-organizer` is a Python-based Discord management toolkit for thread-heavy workflows.

It was originally built around a Claude Code + cc-connect setup, then extracted into a standalone repository.

## Features

- Inspect the current Discord thread / channel context
- Rename, archive, and close threads
- Create categories, text channels, and forum channels
- Generate organize plans for active Discord threads
- Apply organize plans by creating structure and migrating threads
- Continue a live conversation into a new Discord thread while preserving session mapping
- Watch cc-connect session stores and auto-title new Discord sessions
- When a Discord thread is deleted, automatically clean related local cc-connect / Claude session garbage
- Clean up stale/old channels and empty categories after organize runs

## Repository layout

```text
bin/
  discordctl.py
  discord-watch.py
  discord-migrate.py
docs/
  CONFIGURATION.md
  CONTINUATION_MIGRATE.md
  WATCHER.md
state/
.env.example
LICENSE
README.md
SKILL.md
```

## Scripts

### `bin/discordctl.py`
Main CLI for Discord management and organize planning.

### `bin/discord-watch.py`
Watcher that scans cc-connect session stores and auto-renames new Discord threads.

### `bin/discord-migrate.py`
Continuation migration orchestrator that moves an active Claude/cc-connect session into a new Discord thread.

## Requirements

- Python 3.11+
- A Discord bot token with the required channel/thread permissions
- A compatible `cc-connect` session-store workflow if you want watcher/migration features

## Discord bot permissions

Before installation or runtime setup, the bot should have at least these server permissions:

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

Recommended permission bitfield for invite/authorization:

- `395137059856`

Example authorization URL template:

```text
https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&scope=bot%20applications.commands&permissions=395137059856
```

How to authorize:

1. Open the Discord Developer Portal
2. Find your application and bot
3. Use OAuth2 URL generation with scopes `bot` and `applications.commands`
4. Grant the permissions above to the target server
5. Re-run installation after the bot has joined with the required permissions

## Quick start

### Inspect current context

```bash
python3 bin/discordctl.py info --json
```

### Create an organize plan

```bash
python3 bin/discordctl.py organize-plan --goal "Organize active Discord threads" --json
```

### Preview an apply step

```bash
python3 bin/discordctl.py organize-apply --plan-id <plan_id> --dry-run --json
```

### Execute an organize plan

```bash
python3 bin/discordctl.py organize-execute --plan-id <plan_id> --json
```

### Force execution despite quiet-window blockers

```bash
python3 bin/discordctl.py organize-execute --plan-id <plan_id> --force-busy --json
```

## Configuration

See:

- `docs/CONFIGURATION.md`
- `docs/INSTALLATION.md`
- `.env.example`

## Agent-guided setup

If an agent is installing this repository, use:

- `AGENTS.md`

That file tells an agent to:

- verify that the current environment is really Discord + cc-connect + Claude Code
- automatically check whether the bot already has the required Discord server permissions
- if permissions are missing, stop and tell the user how to authorize the bot before continuing
- refuse installation outside that workflow
- auto-fill all detectable local settings
- ask the user only for AI endpoint / key / model confirmation
- install now has a real command entry: `python3 bin/discordctl.py install --json`
- during install, automatically ensure both structures exist: a general-purpose top-level entry channel (`通用入口`, reused if a top-level `入口` channel already exists) and a maintenance/control top-level channel (`服务器维护专用`, reused if a top-level `维护` channel already exists), plus a recycle category (`回收站`, reused if a `回收` category already exists)
- continuation-migrate the current thread into `服务器维护专用` and rename it to `Discord/cc-connect 控制台`
- align cleanup protection with that default structure: protect names containing `回收`, `维护`, or `入口`, including the `回收站` category and its children plus top-level maintenance/entry channels
- auto-start the watcher after that
- also allow the watcher to be started later from a natural-language user request

## Additional docs

- `docs/WATCHER.md`
- `docs/CONTINUATION_MIGRATE.md`

## Current scope

This repository is already useful, but it still reflects its original environment:

- it assumes a cc-connect-style session store
- it assumes a Claude-oriented conversation workflow
- it does not yet include automated tests
- some behavior is still tuned for a personal operations workflow rather than a general product

So this is best described as an extracted, working toolkit rather than a polished end-user package.

## License

MIT
