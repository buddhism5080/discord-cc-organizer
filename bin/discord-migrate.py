#!/usr/bin/env python3
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import importlib.util

import discordctl

_watch_path = Path(__file__).resolve().parent / 'discord-watch.py'
_watch_spec = importlib.util.spec_from_file_location('discord_watch', _watch_path)
discord_watch = importlib.util.module_from_spec(_watch_spec)
_watch_spec.loader.exec_module(discord_watch)

CC_CONNECT_CONFIG = Path(discordctl.configured_env_get('CC_CONNECT_CONFIG', '~/.cc-connect/config.toml')).expanduser()
CC_CONNECT_LOG = Path(discordctl.configured_env_get('CC_CONNECT_LOG', '~/.cc-connect/cc-connect.log')).expanduser()
CC_CONNECT_BIN = discordctl.configured_env_get('CC_CONNECT_BIN', 'cc-connect')
CC_CONNECT_MATCH = discordctl.configured_env_get('CC_CONNECT_MATCH', 'cc-connect')
CC_CONNECT_START_CMD = discordctl.configured_env_get('CC_CONNECT_START_CMD', '')
QUIET_WINDOW_SECS = 300


class MigrationError(RuntimeError):
    pass


def parse_args():
    parser = argparse.ArgumentParser(description='Cold migrate a Discord thread to a new thread while preserving Claude session binding')
    parser.add_argument('--old-session-key', required=True)
    parser.add_argument('--target-parent-id')
    parser.add_argument('--target-parent-name')
    parser.add_argument('--organize-thread-id')
    parser.add_argument('--title')
    parser.add_argument('--summary', default='')
    parser.add_argument('--skip-quiet-window-check', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--json', action='store_true')
    return parser.parse_args()


def load_all_stores():
    stores = []
    for path in discord_watch.project_store_files():
        stores.append((path, discord_watch.load_cc_connect_sessions(path)))
    return stores


def find_session_record(old_session_key):
    for store_path, store in load_all_stores():
        active = store.get('active_session') or {}
        if old_session_key in active:
            session_id = active.get(old_session_key)
            session = (store.get('sessions') or {}).get(session_id)
            project_name = store_path.stem.rsplit('_', 1)[0]
            return {
                'store_path': store_path,
                'store': store,
                'project_name': project_name,
                'cc_session_id': session_id,
                'session': session,
            }
    raise MigrationError(f'Old session key not found: {old_session_key}')


def resolve_target_parent(token, guild_id, parent_id=None, parent_name=None):
    if parent_id:
        parent = discordctl.get_channel(parent_id, token)
        return parent
    if parent_name:
        return discordctl.resolve_channel_by_name(guild_id, token, parent_name, type_filter={0, 15})
    raise MigrationError('Either --target-parent-id or --target-parent-name is required')


def circled_number(n):
    if 1 <= n <= 20:
        return chr(0x2460 + n - 1)
    return f'({n})'


CIRCLED_TO_INT = {chr(0x2460 + i): i + 1 for i in range(20)}
SUFFIX_RE = re.compile(r'^(?P<base>.*?)(?:\s+(?P<circled>[①-⑳])|\s+\((?P<paren>\d+)\))?$')


def split_title_suffix(title):
    cleaned = discordctl.clean_title(title)
    if not cleaned:
        return discordctl.GENERIC_TITLE, None
    match = SUFFIX_RE.match(cleaned)
    if not match:
        return cleaned, None
    base = (match.group('base') or '').strip() or discordctl.GENERIC_TITLE
    if match.group('circled'):
        return base, CIRCLED_TO_INT[match.group('circled')]
    if match.group('paren'):
        return base, int(match.group('paren'))
    return base, None


def title_with_suffix(base_title, extra_taken_titles=None):
    title, current_index = split_title_suffix(base_title)
    if not title:
        title = discordctl.GENERIC_TITLE
    registry = discordctl.load_migration_registry().get('migrations', [])
    taken = {item.get('new_title') for item in registry if item.get('new_title')}
    taken.update({t for t in (extra_taken_titles or set()) if t})

    base_taken = False
    max_taken_index = 0
    for existing in taken:
        existing_base, existing_index = split_title_suffix(existing)
        if existing_base != title:
            continue
        if existing_index is None:
            base_taken = True
            max_taken_index = max(max_taken_index, 1)
        else:
            max_taken_index = max(max_taken_index, existing_index)

    if current_index is None and not base_taken and max_taken_index == 0:
        return title

    next_index = max(
        2,
        max_taken_index + 1 if max_taken_index else 2,
        current_index + 1 if current_index else 2,
    )
    while True:
        candidate = f'{title} {circled_number(next_index)}'
        if candidate not in taken:
            return candidate
        next_index += 1


def active_discord_work_threads(token, organize_thread_id, bound_session_keys):
    active = []
    for session_key in sorted(bound_session_keys):
        if not session_key.startswith('discord:'):
            continue
        thread_id = discordctl.thread_id_from_session_key(session_key)
        if organize_thread_id and thread_id == organize_thread_id:
            continue
        try:
            ch = discordctl.get_channel(thread_id, token)
        except Exception:
            continue
        if ch.get('id') == organize_thread_id:
            continue
        if (ch.get('thread_metadata') or {}).get('archived'):
            continue
        active.append(ch)
    return active


def latest_message_epoch(channel_id, token):
    msgs = discordctl.api_request('GET', f'/channels/{channel_id}/messages?limit=1', token)
    if not msgs:
        return 0
    msg = msgs[0]
    ts = msg.get('timestamp')
    if not ts:
        return 0
    from datetime import datetime
    return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()


def quiet_window_ok(token, organize_thread_id, old_session_key):
    bound = set()
    for _, store in load_all_stores():
        bound.update((store.get('active_session') or {}).keys())
    exempt_thread = discordctl.thread_id_from_session_key(old_session_key)
    now = time.time()
    blockers = []
    for ch in active_discord_work_threads(token, organize_thread_id, bound):
        thread_id = ch.get('id')
        if thread_id == exempt_thread:
            continue
        last_ts = latest_message_epoch(thread_id, token)
        if last_ts and now - last_ts < QUIET_WINDOW_SECS:
            blockers.append({
                'thread_id': thread_id,
                'thread_name': ch.get('name'),
                'seconds_since_last_message': int(now - last_ts),
            })
    return blockers


def post_link_messages(token, old_thread_id, new_thread_id, summary):
    discordctl.send_message(old_thread_id, token, f'后续讨论已迁移到新话题：<#${new_thread_id}>'.replace('$', ''))
    content = f'此话题承接自旧讨论：<#${old_thread_id}>'.replace('$', '')
    if summary:
        content += f'\n\n整理摘要：{summary}'
    discordctl.send_message(new_thread_id, token, content)


def create_new_thread(token, parent_id, new_title, summary):
    parent = discordctl.get_channel(parent_id, token)
    ptype = int(parent.get('type', -1))
    if ptype == 15:
        created = discordctl.start_forum_thread(parent_id, token, new_title, summary or f'承接整理后的讨论：{new_title}')
        return created
    if ptype == 0:
        message = discordctl.send_message(parent_id, token, summary or f'承接整理后的讨论：{new_title}')
        message_id = (message or {}).get('id')
        if not message_id:
            raise MigrationError('Failed to create starter message in target text channel')
        created = discordctl.start_message_thread(parent_id, message_id, token, new_title)
        return created
    raise MigrationError('Target parent must be a forum or text channel')


def list_cc_connect_pids():
    out = subprocess.check_output(['ps', '-eo', 'pid=,comm=,args='], text=True)
    pids = []
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        pid_text, comm, args = parts
        if comm == 'claude':
            continue
        if CC_CONNECT_MATCH in args:
            pids.append(int(pid_text))
    return pids


def stop_cc_connect():
    pids = list_cc_connect_pids()
    for pid in pids:
        os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 10
    while time.time() < deadline:
        time.sleep(0.5)
        live = list_cc_connect_pids()
        if not live:
            return pids
    raise MigrationError(f'cc-connect did not stop within timeout; still running: {live}')


def start_cc_connect():
    CC_CONNECT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CC_CONNECT_LOG.open('ab') as out:
        if CC_CONNECT_START_CMD:
            p = subprocess.Popen(
                CC_CONNECT_START_CMD,
                stdout=out,
                stderr=out,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                shell=True,
            )
        else:
            p = subprocess.Popen([
                CC_CONNECT_BIN
            ], stdout=out, stderr=out, stdin=subprocess.DEVNULL, start_new_session=True)
    return p.pid


def migrate_store(record, old_session_key, new_session_key):
    store = record['store']
    store_path = record['store_path']
    cc_session_id = record['cc_session_id']
    sessions = store.get('sessions') or {}
    if cc_session_id not in sessions:
        raise MigrationError('cc session missing during migration')
    active = store.get('active_session') or {}
    active.pop(old_session_key, None)
    active[new_session_key] = cc_session_id
    user_sessions = store.get('user_sessions') or {}
    arr = user_sessions.get(old_session_key) or []
    user_sessions[new_session_key] = [cc_session_id]
    user_sessions.pop(old_session_key, None)
    user_meta = store.get('user_meta') or {}
    old_meta = user_meta.get(old_session_key) or {}
    user_meta[new_session_key] = dict(old_meta)
    user_meta.pop(old_session_key, None)
    with store_path.open('w', encoding='utf-8') as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def sync_watcher_state(old_session_key, new_session_key, token, new_title='', summary=''):
    known_path = discord_watch.watcher_state_path('known_sessions')
    known = discord_watch.load_json(known_path, {'seen': []})
    seen = set(known.get('seen', []))
    new_seen = sorted((seen - {old_session_key}) | {new_session_key})
    if new_seen != known.get('seen', []):
        discord_watch.save_json(known_path, {'seen': new_seen})

    state_path = discordctl.state_path_for_session(new_session_key)
    discordctl.save_state(state_path, {
        'done': True,
        'reason': 'continuation-migrate',
        'updated_at': int(time.time()),
    })

    old_thread_id = discordctl.thread_id_from_session_key(old_session_key)
    new_thread_id = discordctl.thread_id_from_session_key(new_session_key)
    last_meta = discordctl.latest_channel_message_meta(new_thread_id, token)
    discordctl.migrate_thread_descriptor(
        old_thread_id,
        new_thread_id,
        last_meta.get('timestamp'),
        new_current_title=new_title,
        fallback_summary=summary,
    )


def report_to_organize_thread(token, organize_thread_id, message):
    if not organize_thread_id:
        return
    discordctl.send_message(organize_thread_id, token, message)


def prepare_migration(args, extra_taken_titles=None):
    token = discordctl.load_cc_token()
    record = find_session_record(args.old_session_key)
    session = record['session'] or {}
    agent_session_id = session.get('agent_session_id')
    old_thread_id = discordctl.thread_id_from_session_key(args.old_session_key)
    old_channel = discordctl.get_channel(old_thread_id, token)
    guild_id = old_channel.get('guild_id')
    old_title = old_channel.get('name') or discordctl.GENERIC_TITLE
    target_parent = resolve_target_parent(token, guild_id, args.target_parent_id, args.target_parent_name)
    new_title = title_with_suffix(args.title or old_title, extra_taken_titles=extra_taken_titles)
    blockers = []
    if not args.skip_quiet_window_check:
        blockers = quiet_window_ok(token, args.organize_thread_id, args.old_session_key)
        if blockers:
            raise MigrationError(f'Not in migration-safe quiet window: {blockers}')

    if args.dry_run:
        new_thread_id = 'dry-run-thread-id'
        new_session_key = f'discord:{new_thread_id}'
    else:
        created = create_new_thread(token, target_parent['id'], new_title, args.summary)
        new_thread_id = created.get('id')
        if not new_thread_id:
            raise MigrationError('Failed to create continuation thread')
        new_session_key = f'discord:{new_thread_id}'

    migration_entry = {
        'old_session_key': args.old_session_key,
        'new_session_key': new_session_key,
        'cc_session_id': record['cc_session_id'],
        'agent_session_id': agent_session_id,
        'old_thread_id': old_thread_id,
        'new_thread_id': new_thread_id,
        'new_title': new_title,
        'status': 'prepared',
        'created_at': int(time.time()),
        'updated_at': int(time.time()),
        'summary': args.summary,
        'target_parent_id': target_parent.get('id'),
        'target_parent_name': target_parent.get('name'),
    }

    result = {
        'status': 'prepared',
        'old_session_key': args.old_session_key,
        'new_session_key': new_session_key,
        'new_title': new_title,
        'target_parent_id': target_parent.get('id'),
        'target_parent_name': target_parent.get('name'),
        'new_thread_id': new_thread_id,
        'old_thread_id': old_thread_id,
        'agent_session_id': agent_session_id,
        'blockers': blockers,
        'dry_run': args.dry_run,
        'migration_entry': migration_entry,
    }

    return token, record, result


def finalize_prepared_migration(prepared, record, token, organize_thread_id=None, cc_connect_pid=None, report=False, verify=True, mark_completed=True):
    migration_entry = prepared['migration_entry']
    old_thread_id = prepared['old_thread_id']
    new_thread_id = prepared['new_thread_id']
    new_session_key = prepared['new_session_key']
    old_session_key = prepared['old_session_key']
    new_title = prepared['new_title']
    summary = migration_entry.get('summary') or ''

    post_link_messages(token, old_thread_id, new_thread_id, summary)
    discordctl.patch_channel(old_thread_id, token, {'archived': True, 'locked': True})
    migrate_store(record, old_session_key, new_session_key)
    sync_watcher_state(old_session_key, new_session_key, token, new_title=new_title, summary=summary)
    discordctl.upsert_migration({**migration_entry, 'status': 'switched', 'updated_at': int(time.time())})
    if verify:
        verify_store_mapping(old_session_key, new_session_key, record['cc_session_id'])
    if report:
        pid_text = f'\ncc-connect 已重启（pid {cc_connect_pid}）。' if cc_connect_pid else ''
        report_to_organize_thread(token, organize_thread_id, f'迁移完成：旧话题已关闭，新话题已接管原会话。\n新话题：{new_thread_id}\n原 Claude 会话：{prepared.get("agent_session_id")}{pid_text}')
    if mark_completed:
        discordctl.upsert_migration({**migration_entry, 'status': 'completed', 'updated_at': int(time.time())})
        status = 'completed'
    else:
        status = 'switched'
    return {
        'status': status,
        'old_session_key': old_session_key,
        'new_session_key': new_session_key,
        'new_title': new_title,
        'old_thread_id': old_thread_id,
        'new_thread_id': new_thread_id,
        'agent_session_id': prepared.get('agent_session_id'),
        'cc_connect_pid': cc_connect_pid,
    }


def verify_store_mapping(old_session_key, new_session_key, expected_cc_session_id):
    record = find_session_record(new_session_key)
    if record['cc_session_id'] != expected_cc_session_id:
        raise MigrationError('New thread did not bind to expected cc session id after restart')
    # old key should be gone everywhere
    for _, store in load_all_stores():
        if old_session_key in (store.get('active_session') or {}):
            raise MigrationError('Old session key still exists after migration')


def run(args):
    token, record, prepared = prepare_migration(args)
    if args.dry_run:
        return prepared

    discordctl.upsert_migration(prepared['migration_entry'])
    stop_cc_connect()
    finalize_prepared_migration(prepared, record, token, verify=False, mark_completed=False)
    new_pid = start_cc_connect()
    time.sleep(2)
    verify_store_mapping(prepared['old_session_key'], prepared['new_session_key'], record['cc_session_id'])
    discordctl.upsert_migration({**prepared['migration_entry'], 'status': 'completed', 'updated_at': int(time.time())})
    report_to_organize_thread(token, args.organize_thread_id, f'迁移完成：旧话题已关闭，新话题已接管原会话。\n新话题：{prepared["new_thread_id"]}\n原 Claude 会话：{prepared.get("agent_session_id")}\ncc-connect 已重启（pid {new_pid}）。')
    return {
        'status': 'completed',
        'old_session_key': prepared['old_session_key'],
        'new_session_key': prepared['new_session_key'],
        'new_title': prepared['new_title'],
        'old_thread_id': prepared['old_thread_id'],
        'new_thread_id': prepared['new_thread_id'],
        'agent_session_id': prepared.get('agent_session_id'),
        'cc_connect_pid': new_pid,
    }


def main():
    args = parse_args()
    result = run(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
