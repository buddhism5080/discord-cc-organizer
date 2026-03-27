---
name: discord
description: Use when working with the standalone discord-cc-organizer repository in a Discord plus cc-connect plus Claude Code workflow, especially for explicit current-thread AI renaming, watcher setup, or continuation migration.
---

# discord-cc-organizer

## Quick commands

### Explicitly AI-rename the current Discord thread

When the user asks to rename the current Discord thread based on its content, run:

```bash
python3 bin/discordctl.py rename-current-ai --json
```

This command is explicit/manual. It is separate from watcher-based auto-titling for newly discovered threads.

### Inspect current Discord context

```bash
python3 bin/discordctl.py info --json
```

### Start the watcher manually

```bash
python3 bin/discord-watch.py --daemon
```

### Continue using repo docs

See:

- `README.md`
- `docs/WATCHER.md`
- `docs/CONTINUATION_MIGRATE.md`
