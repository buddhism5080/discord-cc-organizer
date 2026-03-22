---
name: discord
description: Claude Code skill reference for the standalone discord-cc-organizer repository.
---

# Claude Code skill note

This repository started as a Claude Code skill.

The original in-product `SKILL.md` was highly tied to a private local environment and absolute file paths, so the public repository keeps only this short note.

For actual usage and setup, see:

- `README.md`
- `docs/WATCHER.md`
- `docs/CONTINUATION_MIGRATE.md`

If you want to rebuild a Claude Code skill on top of this repository, point your skill implementation to:

- `bin/discordctl.py`
- `bin/discord-watch.py`
- `bin/discord-migrate.py`

and adapt the prompts/commands to your own environment.
