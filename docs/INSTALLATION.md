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
4. Optionally set LLM variables for title/summary generation
5. Run the scripts from the repository root

## Important

Do not treat this as a generic Discord bot package.
It is an operator toolkit built around an existing local Discord + cc-connect + Claude Code workflow.
