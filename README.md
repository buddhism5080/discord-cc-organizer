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
- refuse installation outside that workflow
- auto-fill all detectable local settings
- ask the user only for AI endpoint / key / model confirmation

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
