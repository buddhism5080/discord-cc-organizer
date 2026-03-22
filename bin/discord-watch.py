#!/usr/bin/env python3
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import discordctl

WATCH_STATE_DIR = discordctl.STATE_ROOT / "watcher"
MIGRATION_REGISTRY_PATH = discordctl.MIGRATION_REGISTRY_PATH
CC_CONNECT_DATA_DIR = Path(discordctl.configured_env_get("CC_CONNECT_DATA_DIR", "~/.cc-connect")).expanduser()
CC_CONNECT_SESSIONS_DIR = Path(discordctl.configured_env_get("CC_CONNECT_SESSIONS_DIR", str(CC_CONNECT_DATA_DIR / "sessions"))).expanduser()
CLAUDE_PROJECTS_DIR = Path(discordctl.configured_env_get("CLAUDE_PROJECTS_DIR", "~/.claude/projects")).expanduser()
CONTENT_RE = re.compile(r'"content"\s*:\s*"((?:\\.|[^"\\])*)"')


class WatcherError(RuntimeError):
    pass


def ensure_watch_dir():
    WATCH_STATE_DIR.mkdir(parents=True, exist_ok=True)


def watcher_state_path(name):
    ensure_watch_dir()
    return WATCH_STATE_DIR / f"{name}.json"


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def project_store_files():
    if not CC_CONNECT_SESSIONS_DIR.exists():
        return []
    return sorted(CC_CONNECT_SESSIONS_DIR.glob('*.json'))


def load_cc_connect_sessions(path):
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def all_claude_session_files():
    if not CLAUDE_PROJECTS_DIR.exists():
        return []
    files = []
    for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        files.extend(project_dir.glob('*.jsonl'))
    return files


def delete_claude_session_file(agent_session_id):
    if not agent_session_id:
        return None
    target_name = f"{agent_session_id}.jsonl"
    for path in all_claude_session_files():
        if path.name == target_name:
            path.unlink()
            return str(path)
    return None


def discover_new_discord_sessions(store, seen):
    active = store.get("active_session", {})
    discovered = []
    for session_key in active.keys():
        if not session_key.startswith("discord:"):
            continue
        if session_key in seen:
            continue
        discovered.append(session_key)
    return discovered


def discover_deleted_discord_sessions(store, seen):
    active = set((store.get("active_session") or {}).keys())
    migrated = migration_lookup()
    deleted = []
    for session_key in sorted(seen):
        if not session_key.startswith("discord:"):
            continue
        if session_key in migrated:
            continue
        if session_key not in active:
            deleted.append(session_key)
    return deleted


def cleanup_state_path():
    return watcher_state_path("cleanup_state")


def load_migration_registry():
    if not MIGRATION_REGISTRY_PATH.exists():
        return {"migrations": []}
    try:
        return json.loads(MIGRATION_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"migrations": []}


def migration_lookup():
    data = load_migration_registry()
    lookup = {}
    for item in data.get("migrations", []):
        old_key = item.get("old_session_key")
        if old_key:
            lookup[old_key] = item
    return lookup


def discover_api_deleted_sessions(store, token, now_ts, interval_seconds):
    state_path = cleanup_state_path()
    state = load_json(state_path, {"last_run": 0})
    last_run = int(state.get("last_run") or 0)
    if now_ts - last_run < interval_seconds:
        return []

    active = store.get("active_session") or {}
    deleted = []
    for session_key in sorted(active.keys()):
        if not session_key.startswith("discord:"):
            continue
        channel_id = session_key.split(":", 1)[1].split(":", 1)[0]
        try:
            discordctl.get_channel(channel_id, token)
        except Exception:
            deleted.append(session_key)

    state["last_run"] = now_ts
    save_json(state_path, state)
    return deleted


def latest_prompt_for_session(session_key, store):
    session_id = (store.get("active_session") or {}).get(session_key)
    if not session_id:
        return None
    session = (store.get("sessions") or {}).get(session_id)
    if not isinstance(session, dict):
        return None
    history = session.get("history") or []
    if not isinstance(history, list):
        return None
    for item in history:
        if not isinstance(item, dict):
            continue
        if item.get("role") == "user":
            content = (item.get("content") or "").strip()
            if content:
                return content
    return None


def cc_session_record(session_key, store):
    session_id = (store.get("active_session") or {}).get(session_key)
    if not session_id:
        return None, None
    session = (store.get("sessions") or {}).get(session_id)
    if not isinstance(session, dict):
        return session_id, None
    return session_id, session


def delete_cc_connect_session(store_path, project_name, session_key, store, dry_run=False):
    session_id, session = cc_session_record(session_key, store)
    if not session_id:
        return {"status": "skip", "reason": "session-missing", "session_key": session_key}

    agent_session_id = session.get("agent_session_id") if isinstance(session, dict) else None
    if not dry_run:
        sessions = store.get("sessions") or {}
        sessions.pop(session_id, None)
        active = store.get("active_session") or {}
        active.pop(session_key, None)
        user_sessions = store.get("user_sessions") or {}
        arr = user_sessions.get(session_key) or []
        user_sessions[session_key] = [sid for sid in arr if sid != session_id]
        if not user_sessions[session_key]:
            user_sessions.pop(session_key, None)
        user_meta = store.get("user_meta") or {}
        user_meta.pop(session_key, None)
        with store_path.open("w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)

        deleted_claude_path = None
        if agent_session_id:
            deleted_claude_path = delete_claude_session_file(agent_session_id)
        state_path = discordctl.state_path_for_session(session_key)
        if state_path.exists():
            state_path.unlink()
        thread_id = session_key.split(':', 1)[1].split(':', 1)[0]
        discordctl.delete_thread_descriptor(thread_id)

    return {
        "status": "deleted",
        "project": project_name,
        "session_key": session_key,
        "cc_session_id": session_id,
        "agent_session_id": agent_session_id,
        "deleted_claude_path": None if dry_run else deleted_claude_path,
        "dry_run": dry_run,
    }


def maybe_rename_session(session_key, prompt, dry_run=False):
    token = discordctl.load_cc_token()
    channel_id = session_key.split(":", 1)[1].split(":", 1)[0]
    ctx = discordctl.context_for_target(channel_id, token)
    channel = ctx["channel"]
    if channel["type_name"] not in discordctl.THREAD_TYPES.values():
        return {"status": "skip", "reason": "not-thread", "session_key": session_key}

    state, path = discordctl.load_state(session_key)
    if state.get("done"):
        return {"status": "skip", "reason": "already-done", "session_key": session_key}

    current_name = channel.get("name") or ""
    expected_existing = discordctl.sanitize_existing_thread_name(prompt)
    if expected_existing and current_name != expected_existing:
        if current_name != discordctl.GENERIC_TITLE:
            discordctl.save_state(path, {
                "done": True,
                "reason": "current-name-changed",
                "current_name": current_name,
                "expected_existing": expected_existing,
                "updated_at": int(time.time()),
            })
            return {"status": "skip", "reason": "current-name-changed", "session_key": session_key, "current_name": current_name}

    title, source = discordctl.suggest_title(prompt)
    if not title:
        raise WatcherError("AI title generator returned empty title")

    result = {
        "done": True,
        "source": source,
        "old_name": current_name,
        "new_name": title,
        "expected_existing": expected_existing,
        "updated_at": int(time.time()),
    }
    if not dry_run:
        discordctl.patch_channel(channel_id, token, {"name": title})
    discordctl.save_state(path, result)
    return {
        "status": "renamed",
        "session_key": session_key,
        "old_name": current_name,
        "new_name": title,
        "source": source,
        "dry_run": dry_run,
    }


def scan_once(args):
    token = discordctl.load_cc_token()
    known_path = watcher_state_path("known_sessions")
    known = load_json(known_path, {"seen": []})
    seen = set(known.get("seen", []))
    discovered = []
    renamed = []
    deleted_results = []

    for store_path in project_store_files():
        project_name = store_path.stem.rsplit('_', 1)[0]
        store = load_cc_connect_sessions(store_path)
        project_discovered = discover_new_discord_sessions(store, seen)
        deleted = discover_deleted_discord_sessions(store, seen)
        api_deleted = discover_api_deleted_sessions(store, token, int(time.time()), args.cleanup_interval)
        deleted = sorted(set(deleted + api_deleted))

        discovered.extend(project_discovered)

        for session_key in project_discovered:
            prompt = latest_prompt_for_session(session_key, store)
            if not prompt:
                renamed.append({"status": "skip", "reason": "missing-prompt", "project": project_name, "session_key": session_key})
                continue
            try:
                result = maybe_rename_session(session_key, prompt, dry_run=args.dry_run)
                result["project"] = project_name
                renamed.append(result)
                if result.get("status") in {"renamed", "skip"}:
                    seen.add(session_key)
            except Exception as e:
                renamed.append({"status": "error", "project": project_name, "session_key": session_key, "error": str(e)})

        for session_key in deleted:
            try:
                result = delete_cc_connect_session(store_path, project_name, session_key, store, dry_run=args.dry_run)
                deleted_results.append(result)
                seen.discard(session_key)
            except Exception as e:
                deleted_results.append({"status": "error", "project": project_name, "session_key": session_key, "error": str(e)})

    save_json(known_path, {"seen": sorted(seen)})

    payload = {
        "discovered": discovered,
        "renamed": renamed,
        "deleted": deleted_results,
        "dry_run": args.dry_run,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def daemon_loop(args):
    while True:
        try:
            scan_once(args)
        except Exception as e:
            print(json.dumps({"daemon_error": str(e)}, ensure_ascii=False), flush=True)
        time.sleep(args.interval)


def build_parser():
    parser = argparse.ArgumentParser(description="Watch cc-connect session store and auto-rename/cleanup Discord threads")
    parser.add_argument("--interval", type=int, default=8)
    parser.add_argument("--cleanup-interval", type=int, default=3600)
    parser.add_argument("--file-limit", type=int, default=40)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    if args.daemon:
        daemon_loop(args)
    else:
        scan_once(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
