#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = REPO_ROOT / ".env"


def load_dotenv_file(path):
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv_file(DOTENV_PATH)

DISCORD_API_BASE = os.environ.get("DISCORD_API_BASE", "https://discord.com/api/v10")
CC_CONNECT_CONFIG = Path(os.environ.get("CC_CONNECT_CONFIG", "~/.cc-connect/config.toml")).expanduser()
CC_CONNECT_SESSIONS_DIR = Path(os.environ.get("CC_CONNECT_SESSIONS_DIR", "~/.cc-connect/sessions")).expanduser()
SKILL_ROOT = Path(os.environ.get("DISCORD_SKILL_ROOT", str(REPO_ROOT))).expanduser()
STATE_ROOT = Path(os.environ.get("DISCORD_SKILL_STATE_DIR", str(SKILL_ROOT / "state"))).expanduser()
AUTO_TITLE_STATE_DIR = STATE_ROOT / "auto-title"
MIGRATION_REGISTRY_PATH = STATE_ROOT / "migration_registry.json"
FRAMEWORK_REGISTRY_PATH = STATE_ROOT / "framework_registry.json"
THREAD_DESCRIPTOR_REGISTRY_PATH = STATE_ROOT / "thread_descriptor_registry.json"
ORGANIZE_PLAN_STATE_PATH = STATE_ROOT / "organize_plan_state.json"

THREAD_TYPES = {10: "announcement_thread", 11: "public_thread", 12: "private_thread"}
CHANNEL_TYPES = {
    0: "text",
    2: "voice",
    4: "category",
    10: "announcement_thread",
    11: "public_thread",
    12: "private_thread",
    15: "forum",
    16: "media",
}
CREATE_TYPES = {"text": 0, "category": 4, "forum": 15}
GENERIC_TITLE = "新会话"
REASONING_CONTENT_RE = re.compile(r'"reasoning_content"\s*:\s*"(?:\\.|[^"\\])*"', re.DOTALL)


class DiscordSkillError(RuntimeError):
    pass


def json_dumps(data):
    return json.dumps(data, ensure_ascii=False, indent=2)


def load_cc_config():
    if not CC_CONNECT_CONFIG.exists():
        raise DiscordSkillError(f"cc-connect config not found: {CC_CONNECT_CONFIG}")
    with CC_CONNECT_CONFIG.open("rb") as f:
        return tomllib.load(f)


def load_cc_token():
    env_token = os.environ.get("DISCORD_BOT_TOKEN")
    if env_token:
        return env_token
    data = load_cc_config()
    for project in data.get("projects", []):
        for platform in project.get("platforms", []):
            if platform.get("type") == "discord":
                token = (platform.get("options") or {}).get("token")
                if token:
                    return token
    raise DiscordSkillError("Discord bot token not found in cc-connect config")


def api_request(method, path, token, payload=None):
    url = DISCORD_API_BASE.rstrip("/") + path
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "discord-skill/0.1",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"message": body}
        raise DiscordSkillError(f"Discord API {method} {path} failed: HTTP {e.code}: {parsed}") from e
    except urllib.error.URLError as e:
        raise DiscordSkillError(f"Discord API request failed: {e}") from e


def get_channel(channel_id, token):
    return api_request("GET", f"/channels/{channel_id}", token)


def send_message(channel_id, token, content):
    return api_request("POST", f"/channels/{channel_id}/messages", token, {"content": content})


def latest_channel_message_meta(channel_id, token):
    msgs = api_request("GET", f"/channels/{channel_id}/messages?limit=1", token)
    if not msgs:
        return {}
    msg = msgs[0]
    return {
        'id': msg.get('id'),
        'timestamp': msg.get('timestamp'),
        'author_id': ((msg.get('author') or {}).get('id')),
    }


def start_message_thread(channel_id, message_id, token, name, archive_duration=1440):
    payload = {
        "name": name,
        "auto_archive_duration": archive_duration,
    }
    return api_request("POST", f"/channels/{channel_id}/messages/{message_id}/threads", token, payload)


def start_forum_thread(channel_id, token, name, content):
    payload = {
        "name": name,
        "message": {"content": content},
    }
    return api_request("POST", f"/channels/{channel_id}/threads", token, payload)


def patch_channel(channel_id, token, payload):
    return api_request("PATCH", f"/channels/{channel_id}", token, payload)


def create_channel(guild_id, token, payload):
    return api_request("POST", f"/guilds/{guild_id}/channels", token, payload)


def delete_channel(channel_id, token):
    return api_request("DELETE", f"/channels/{channel_id}", token)


def list_archived_threads(channel_id, token, private=False):
    kind = "private" if private else "public"
    data = api_request("GET", f"/channels/{channel_id}/threads/archived/{kind}", token)
    if isinstance(data, dict):
        return data.get("threads") or []
    return []


def list_guild_channels(guild_id, token):
    return api_request("GET", f"/guilds/{guild_id}/channels", token)


def get_current_user(token):
    return api_request("GET", "/users/@me", token)


def get_guild_member(guild_id, user_id, token):
    return api_request("GET", f"/guilds/{guild_id}/members/{user_id}", token)


def env_bool(name):
    return (os.environ.get(name) or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def detect_install_environment():
    session_key = current_session_key()
    cc_connect_config_exists = CC_CONNECT_CONFIG.exists()
    cc_connect_sessions_exists = CC_CONNECT_SESSIONS_DIR.exists()
    claude_root_exists = (Path.home() / '.claude').exists()
    cc_project_exists = bool(os.environ.get('CC_PROJECT'))
    discord_session = session_key.startswith('discord:')
    return {
        'claude_code': bool(session_key or cc_project_exists or claude_root_exists),
        'cc_connect': bool(cc_connect_config_exists or cc_connect_sessions_exists),
        'discord': bool(discord_session),
        'session_key': session_key or None,
        'cc_connect_config_exists': cc_connect_config_exists,
        'cc_connect_sessions_exists': cc_connect_sessions_exists,
        'claude_root_exists': claude_root_exists,
    }


def ensure_env_file(dry_run=False):
    env_path = REPO_ROOT / '.env'
    example_path = REPO_ROOT / '.env.example'
    if env_path.exists():
        return env_path
    if dry_run:
        return env_path
    if not example_path.exists():
        raise DiscordSkillError(f'Missing .env.example at {example_path}')
    env_path.write_text(example_path.read_text(encoding='utf-8'), encoding='utf-8')
    return env_path


def parse_env_file(path):
    data = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        data[key.strip()] = value.strip()
    return data


def write_env_file(path, updates, dry_run=False):
    existing = parse_env_file(path)
    merged = {**existing, **updates}
    lines = [f'{k}={v}' for k, v in merged.items()]
    if not dry_run:
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return merged


def list_active_guild_threads(guild_id, token):
    data = api_request("GET", f"/guilds/{guild_id}/threads/active", token)
    if isinstance(data, dict):
        return data.get("threads") or []
    return []


def channel_type_name(type_id):
    return CHANNEL_TYPES.get(type_id, f"type_{type_id}")


def is_thread(channel):
    return int(channel.get("type", -1)) in THREAD_TYPES


def current_session_key():
    return os.environ.get("CC_SESSION_KEY", "")


def thread_id_from_session_key(session_key):
    if not session_key.startswith("discord:"):
        raise DiscordSkillError("Current session is not a Discord cc-connect session")
    rest = session_key.split(":", 1)[1]
    if not rest:
        raise DiscordSkillError("Malformed CC_SESSION_KEY")
    return rest.split(":", 1)[0]


def current_target_id():
    return thread_id_from_session_key(current_session_key())


def context_for_target(channel_id=None, token=None):
    token = token or load_cc_token()
    channel_id = channel_id or current_target_id()
    channel = get_channel(channel_id, token)
    parent = None
    parent_id = channel.get("parent_id")
    if parent_id:
        try:
            parent = get_channel(parent_id, token)
        except DiscordSkillError:
            parent = None
    return {
        "platform": "discord",
        "project": os.environ.get("CC_PROJECT"),
        "session_key": current_session_key() or None,
        "target_id": channel_id,
        "channel": {
            "id": channel.get("id"),
            "name": channel.get("name"),
            "type": int(channel.get("type", -1)),
            "type_name": channel_type_name(int(channel.get("type", -1))),
            "guild_id": channel.get("guild_id"),
            "parent_id": channel.get("parent_id"),
            "archived": (channel.get("thread_metadata") or {}).get("archived"),
            "locked": (channel.get("thread_metadata") or {}).get("locked"),
            "auto_archive_duration": (channel.get("thread_metadata") or {}).get("auto_archive_duration"),
        },
        "parent": None if not parent else {
            "id": parent.get("id"),
            "name": parent.get("name"),
            "type": int(parent.get("type", -1)),
            "type_name": channel_type_name(int(parent.get("type", -1))),
        },
    }


def sanitize_existing_thread_name(prompt):
    text = re.sub(r"<@!?\d+>", "", prompt or "")
    text = " ".join(text.replace("\n", " ").split())
    return text[:90].strip()


def clean_title(title):
    title = (title or "").strip()
    title = re.sub(r"[`*_~#>\[\]\(\)]", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" \t\r\n-—:：;；,.，。!！?？\"'")
    if len(title) > 70:
        title = title[:70].rstrip(" -—:：;；,.，。!！?？\"'")
    return title or GENERIC_TITLE


def strip_prompt_noise(text):
    text = re.sub(r"```[\s\S]*?```", " ", text or "")
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"<@!?\d+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def openai_config():
    base_url = os.environ.get("DISCORD_SKILL_LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("DISCORD_SKILL_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("DISCORD_SKILL_LLM_MODEL") or os.environ.get("OPENAI_MODEL")
    if base_url and api_key and model:
        return {"base_url": base_url.rstrip("/"), "api_key": api_key, "model": model}
    return None


def llm_title(prompt):
    config = openai_config()
    if not config:
        raise DiscordSkillError(
            "AI title generation is not configured. Set DISCORD_SKILL_LLM_BASE_URL, DISCORD_SKILL_LLM_API_KEY, and DISCORD_SKILL_LLM_MODEL."
        )
    system_prompt = (
        "You generate short Discord thread titles. "
        "Return only the title text, no quotes, no markdown, no explanation. "
        "Prefer concise Chinese titles; if the source is English, still keep it short. "
        "Ignore greetings, pasted logs, code fences, stack traces, filler, and obvious politeness phrases. "
        "Summarize the actual task/topic into a compact title suitable for a Discord thread."
    )
    payload = {
        "model": config["model"],
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt[:6000]},
        ],
    }
    url = config["base_url"] + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": "discord-skill/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            cleaned = REASONING_CONTENT_RE.sub('"reasoning_content":""', raw)
            data = json.loads(cleaned)
    except Exception as e:
        raise DiscordSkillError(f"AI title generation request failed: {e}") from e
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        raise DiscordSkillError(f"AI title generation response missing content: {e}") from e
    title = clean_title(content)
    if not title:
        raise DiscordSkillError("AI title generation returned an empty title")
    return title


def suggest_title(prompt):
    return llm_title(prompt), "llm"


def suggest_summary(prompt):
    config = openai_config()
    if not config:
        raise DiscordSkillError(
            "AI summary generation is not configured. Set DISCORD_SKILL_LLM_BASE_URL, DISCORD_SKILL_LLM_API_KEY, and DISCORD_SKILL_LLM_MODEL."
        )
    system_prompt = (
        "You summarize a Discord thread topic into a concise Chinese summary. "
        "Return only one short summary sentence, ideally 10-50 Chinese characters, no markdown, no explanation."
    )
    payload = {
        "model": config["model"],
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt[:6000]},
        ],
    }
    url = config["base_url"] + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": "discord-skill/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            cleaned = REASONING_CONTENT_RE.sub('"reasoning_content":""', raw)
            data = json.loads(cleaned)
    except Exception as e:
        raise DiscordSkillError(f"AI summary generation request failed: {e}") from e
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        raise DiscordSkillError(f"AI summary generation response missing content: {e}") from e
    content = re.sub(r"\s+", " ", (content or "").strip())
    return content[:80].strip()


def ensure_state_dir():
    AUTO_TITLE_STATE_DIR.mkdir(parents=True, exist_ok=True)


def state_path_for_session(session_key):
    digest = hashlib.sha1(session_key.encode("utf-8")).hexdigest()
    return AUTO_TITLE_STATE_DIR / f"{digest}.json"


def load_state(session_key):
    ensure_state_dir()
    path = state_path_for_session(session_key)
    if not path.exists():
        return {}, path
    try:
        return json.loads(path.read_text(encoding="utf-8")), path
    except Exception:
        return {}, path


def save_state(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_state(session_key):
    ensure_state_dir()
    path = state_path_for_session(session_key)
    if path.exists():
        path.unlink()


def acquire_lock(session_key):
    ensure_state_dir()
    digest = hashlib.sha1(session_key.encode("utf-8")).hexdigest()
    lock_path = AUTO_TITLE_STATE_DIR / f"{digest}.lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        return lock_path
    except FileExistsError:
        return None


def session_store_files():
    if not CC_CONNECT_SESSIONS_DIR.exists():
        return []
    return sorted(CC_CONNECT_SESSIONS_DIR.glob('*.json'))


def find_cc_session_record(session_key):
    for path in session_store_files():
        try:
            with path.open('r', encoding='utf-8') as f:
                store = json.load(f)
        except Exception:
            continue
        active = store.get('active_session') or {}
        if session_key not in active:
            continue
        cc_session_id = active[session_key]
        session = (store.get('sessions') or {}).get(cc_session_id)
        project_name = path.stem.rsplit('_', 1)[0]
        return {
            'store_path': str(path),
            'project_name': project_name,
            'cc_session_id': cc_session_id,
            'session': session if isinstance(session, dict) else {},
        }
    return None


def release_lock(lock_path):
    if lock_path and Path(lock_path).exists():
        try:
            Path(lock_path).unlink()
        except FileNotFoundError:
            pass


def load_migration_registry():
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    if not MIGRATION_REGISTRY_PATH.exists():
        return {"migrations": []}
    try:
        return json.loads(MIGRATION_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"migrations": []}


def save_migration_registry(data):
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    MIGRATION_REGISTRY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_framework_registry():
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    if not FRAMEWORK_REGISTRY_PATH.exists():
        return {"frameworks": []}
    try:
        return json.loads(FRAMEWORK_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"frameworks": []}


def save_framework_registry(data):
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    FRAMEWORK_REGISTRY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_organize_plan_state():
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    if not ORGANIZE_PLAN_STATE_PATH.exists():
        return {"plans": []}
    try:
        return json.loads(ORGANIZE_PLAN_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"plans": []}


def save_organize_plan_state(data):
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    ORGANIZE_PLAN_STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_organize_plan(entry):
    data = load_organize_plan_state()
    plans = data.setdefault("plans", [])
    plan_id = entry.get("plan_id") or hashlib.sha1(json.dumps(entry, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    entry = {**entry, "plan_id": plan_id}
    for i, item in enumerate(plans):
        if item.get("plan_id") == plan_id:
            plans[i] = {**item, **entry}
            save_organize_plan_state(data)
            return plans[i]
    plans.append(entry)
    save_organize_plan_state(data)
    return entry


def get_organize_plan(plan_id=None):
    data = load_organize_plan_state()
    plans = data.get("plans") or []
    if not plans:
        return None
    if not plan_id:
        return plans[-1]
    for item in plans:
        if item.get("plan_id") == plan_id:
            return item
    return None


def load_thread_descriptor_registry():
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    if not THREAD_DESCRIPTOR_REGISTRY_PATH.exists():
        return {"threads": {}}
    try:
        return json.loads(THREAD_DESCRIPTOR_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"threads": {}}


def save_thread_descriptor_registry(data):
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    THREAD_DESCRIPTOR_REGISTRY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_thread_descriptor(thread_id, entry):
    data = load_thread_descriptor_registry()
    threads = data.setdefault("threads", {})
    old = threads.get(thread_id, {})
    threads[thread_id] = {**old, **entry}
    save_thread_descriptor_registry(data)
    return threads[thread_id]


def get_thread_descriptor(thread_id):
    data = load_thread_descriptor_registry()
    return (data.get("threads") or {}).get(thread_id)


def delete_thread_descriptor(thread_id):
    data = load_thread_descriptor_registry()
    threads = data.setdefault("threads", {})
    removed = threads.pop(thread_id, None)
    save_thread_descriptor_registry(data)
    return removed


def migrate_thread_descriptor(
    old_thread_id,
    new_thread_id,
    new_last_message_ts=None,
    new_current_title=None,
    fallback_summary=None,
):
    data = load_thread_descriptor_registry()
    threads = data.setdefault("threads", {})
    old = threads.pop(old_thread_id, None) or {}
    current_title = new_current_title if new_current_title is not None else old.get('current_title') or GENERIC_TITLE
    old['thread_id'] = new_thread_id
    old['updated_at'] = int(time.time())
    old['current_title'] = current_title
    if new_last_message_ts is not None:
        old['last_message_ts'] = new_last_message_ts
    old.setdefault('normalized_title', clean_title(current_title))
    old.setdefault('micro_summary', fallback_summary or '')
    threads[new_thread_id] = old
    save_thread_descriptor_registry(data)
    return old


def upsert_framework(entry):
    data = load_framework_registry()
    frameworks = data.setdefault("frameworks", [])
    key = entry.get("name") or entry.get("goal") or "default"
    for i, item in enumerate(frameworks):
        item_key = item.get("name") or item.get("goal") or "default"
        if item_key == key:
            frameworks[i] = {**item, **entry}
            save_framework_registry(data)
            return frameworks[i]
    frameworks.append(entry)
    save_framework_registry(data)
    return entry


def upsert_migration(entry):
    data = load_migration_registry()
    migrations = data.setdefault("migrations", [])
    key = (entry.get("old_session_key"), entry.get("new_session_key"))
    for i, item in enumerate(migrations):
        if (item.get("old_session_key"), item.get("new_session_key")) == key:
            migrations[i] = {**item, **entry}
            save_migration_registry(data)
            return migrations[i]
    migrations.append(entry)
    save_migration_registry(data)
    return entry


def print_result(result, json_mode=False):
    if json_mode:
        print(json_dumps(result))
        return
    if result.get("action") == "info":
        channel = result.get("channel") or {}
        parent = result.get("parent") or {}
        print(f"Current Discord target: {channel.get('name')} ({channel.get('type_name')})")
        print(f"Channel ID: {channel.get('id')}")
        if parent:
            print(f"Parent: {parent.get('name')} ({parent.get('type_name')})")
        print(f"Session key: {result.get('session_key')}")
        return
    if result.get("action") == "suggest-title":
        print(result.get("title"))
        return
    if result.get("action") == "list":
        items = result.get("items") or []
        print(f"Listed {len(items)} channels")
        for item in items:
            print(f"- {item.get('name')} ({item.get('type_name')}) [{item.get('id')}]")
        return
    if result.get("action") == "snapshot":
        ctx = result.get("context") or {}
        channel = (ctx.get("channel") or {})
        print(f"Current: {channel.get('name')} ({channel.get('type_name')})")
        print(f"Categories: {len(result.get('categories') or [])}")
        print(f"Texts: {len(result.get('texts') or [])}")
        print(f"Forums: {len(result.get('forums') or [])}")
        return
    if result.get("action") == "migration-registry":
        print(json_dumps(result.get('data') or {"migrations": []}))
        return
    if result.get("action") == "organize-plan":
        print(json_dumps(result))
        return
    if result.get("action") == "organize-apply":
        print(json_dumps(result))
        return
    status = "dry-run" if result.get("dry_run") else "ok"
    print(f"[{status}] {result.get('action')}: {result.get('message', '')}".strip())
    if result.get("target_name"):
        print(f"target: {result['target_name']}")
    if result.get("new_name"):
        print(f"new name: {result['new_name']}")


def resolve_category_id(guild_id, token, category_name):
    channels = list_guild_channels(guild_id, token)
    matches = [
        ch for ch in channels
        if int(ch.get("type", -1)) == CREATE_TYPES["category"] and (ch.get("name") or "").lower() == category_name.lower()
    ]
    if not matches:
        raise DiscordSkillError(f"Category not found: {category_name}")
    if len(matches) > 1:
        ids = ", ".join(ch.get("id", "?") for ch in matches)
        raise DiscordSkillError(f"Category name is ambiguous: {category_name} ({ids})")
    return matches[0]["id"]


def cmd_info(args):
    token = load_cc_token()
    ctx = context_for_target(args.channel_id, token)
    result = {
        "action": "info",
        **ctx,
    }
    print_result(result, args.json)


def cmd_suggest_title(args):
    title, source = suggest_title(args.text)
    result = {"action": "suggest-title", "title": title, "source": source}
    print_result(result, args.json)


def cmd_rename(args):
    token = load_cc_token()
    ctx = context_for_target(args.channel_id, token)
    channel = ctx["channel"]
    new_name = clean_title(args.name)
    payload = {"name": new_name}
    result = {
        "action": "rename",
        "dry_run": args.dry_run,
        "target_id": channel["id"],
        "target_name": channel.get("name"),
        "new_name": new_name,
        "message": f"rename {channel.get('name')} -> {new_name}",
    }
    if not args.dry_run:
        patch_channel(channel["id"], token, payload)
    print_result(result, args.json)


def cmd_archive(args):
    token = load_cc_token()
    ctx = context_for_target(args.channel_id, token)
    channel = ctx["channel"]
    if channel["type_name"] not in THREAD_TYPES.values():
        raise DiscordSkillError("Archive is only supported for Discord threads")
    payload = {"archived": True}
    if args.lock:
        payload["locked"] = True
    result = {
        "action": "archive",
        "dry_run": args.dry_run,
        "target_id": channel["id"],
        "target_name": channel.get("name"),
        "message": f"archive {channel.get('name')}" + (" and lock" if args.lock else ""),
    }
    if not args.dry_run:
        patch_channel(channel["id"], token, payload)
    print_result(result, args.json)


def cmd_close(args):
    args.lock = True
    cmd_archive(args)


def summarize_channel(ch):
    return {
        "id": ch.get("id"),
        "name": ch.get("name"),
        "type": int(ch.get("type", -1)),
        "type_name": channel_type_name(int(ch.get("type", -1))),
        "parent_id": ch.get("parent_id"),
        "position": ch.get("position"),
    }


def resolve_channel_by_name(guild_id, token, name, type_filter=None):
    channels = list_guild_channels(guild_id, token)
    matches = []
    for ch in channels:
        if (ch.get("name") or "").lower() != name.lower():
            continue
        if type_filter is not None and int(ch.get("type", -1)) not in type_filter:
            continue
        matches.append(ch)
    if not matches:
        raise DiscordSkillError(f"Channel not found: {name}")
    if len(matches) > 1:
        ids = ", ".join(ch.get("id", "?") for ch in matches)
        raise DiscordSkillError(f"Channel name is ambiguous: {name} ({ids})")
    return matches[0]


def cmd_list(args):
    token = load_cc_token()
    ctx = context_for_target(args.channel_id, token)
    guild_id = ctx["channel"]["guild_id"]
    if not guild_id:
        raise DiscordSkillError("Could not infer guild_id from current Discord context")
    channels = list_guild_channels(guild_id, token)
    if args.kind:
        type_filter = {CREATE_TYPES[args.kind]}
        channels = [ch for ch in channels if int(ch.get("type", -1)) in type_filter]
    result = {
        "action": "list",
        "guild_id": guild_id,
        "kind": args.kind,
        "items": [summarize_channel(ch) for ch in channels],
    }
    print_result(result, args.json)


def cmd_create(args):
    token = load_cc_token()
    ctx = context_for_target(args.channel_id, token)
    guild_id = ctx["channel"]["guild_id"]
    if not guild_id:
        raise DiscordSkillError("Could not infer guild_id from current Discord context")
    payload = {"name": clean_title(args.name), "type": CREATE_TYPES[args.kind]}
    if args.parent_id:
        payload["parent_id"] = args.parent_id
    elif args.parent_name:
        payload["parent_id"] = resolve_category_id(guild_id, token, args.parent_name)
    result = {
        "action": "create",
        "dry_run": args.dry_run,
        "kind": args.kind,
        "guild_id": guild_id,
        "target_name": payload["name"],
        "parent_id": payload.get("parent_id"),
        "message": f"create {args.kind} channel {payload['name']}",
    }
    if not args.dry_run:
        created = create_channel(guild_id, token, payload)
        result["created_id"] = created.get("id")
        result["created_type"] = channel_type_name(int(created.get("type", -1)))
    print_result(result, args.json)


def cmd_move(args):
    token = load_cc_token()
    ctx = context_for_target(args.channel_id, token)
    channel = ctx["channel"]
    if channel["type_name"] in THREAD_TYPES.values():
        raise DiscordSkillError("Moving Discord threads between parent channels is not supported in v2 yet")
    guild_id = channel["guild_id"]
    if not guild_id:
        raise DiscordSkillError("Could not infer guild_id from current Discord context")
    parent_id = args.parent_id or resolve_category_id(guild_id, token, args.parent_name)
    result = {
        "action": "move",
        "dry_run": args.dry_run,
        "target_id": channel["id"],
        "target_name": channel.get("name"),
        "parent_id": parent_id,
        "message": f"move {channel.get('name')} under {args.parent_name or parent_id}",
    }
    if not args.dry_run:
        patch_channel(channel["id"], token, {"parent_id": parent_id})
    print_result(result, args.json)


def cmd_preview(args):
    result = {
        "action": "preview",
        "dry_run": True,
        "message": args.message,
    }
    print_result(result, args.json)


def cmd_snapshot(args):
    token = load_cc_token()
    ctx = context_for_target(args.channel_id, token)
    guild_id = ctx["channel"]["guild_id"]
    if not guild_id:
        raise DiscordSkillError("Could not infer guild_id from current Discord context")
    channels = [summarize_channel(ch) for ch in list_guild_channels(guild_id, token)]
    categories = [c for c in channels if c["type_name"] == "category"]
    texts = [c for c in channels if c["type_name"] == "text"]
    forums = [c for c in channels if c["type_name"] == "forum"]
    result = {
        "action": "snapshot",
        "context": ctx,
        "categories": categories,
        "texts": texts,
        "forums": forums,
    }
    print_result(result, args.json)


REQUIRED_PERMISSION_BITS = {
    'View Channels': 1 << 10,
    'Manage Channels': 1 << 4,
    'Send Messages': 1 << 11,
    'Read Message History': 1 << 16,
    'Create Public Threads': 1 << 35,
    'Send Messages in Threads': 1 << 38,
    'Manage Threads': 1 << 34,
}


def cmd_permissions_check(args):
    token = load_cc_token()
    ctx = context_for_target(args.channel_id, token)
    guild_id = ctx['channel']['guild_id']
    if not guild_id:
        raise DiscordSkillError('Could not infer guild_id from current Discord context')
    me = get_current_user(token)
    member = get_guild_member(guild_id, me.get('id'), token)
    permissions_value = int(member.get('permissions') or 0)
    missing = [name for name, bit in REQUIRED_PERMISSION_BITS.items() if not (permissions_value & bit)]
    oauth_permissions = sum(REQUIRED_PERMISSION_BITS.values())
    result = {
        'action': 'permissions-check',
        'guild_id': guild_id,
        'bot_user_id': me.get('id'),
        'permissions_value': str(permissions_value),
        'required_permissions': list(REQUIRED_PERMISSION_BITS.keys()),
        'missing_permissions': missing,
        'ok': not missing,
        'oauth_scopes': ['bot', 'applications.commands'],
        'oauth_permissions': str(oauth_permissions),
        'message': 'permissions ok' if not missing else f'missing {len(missing)} permission(s)',
    }
    print_result(result, args.json)


def infer_cluster(descriptor):
    text = ((descriptor.get('normalized_title') or '') + ' ' + (descriptor.get('micro_summary') or '')).lower()
    rules = [
        (['数据', '财政', '转移支付', '原油', '价格', '金融'], ('数据', '研究与数据')),
        (['discord', 'cc-connect', '机器人', '配置', '权限', '线程'], ('工具', '配置与管理')),
        (['电影', '真探', '华尔街之狼', '上映'], ('杂谈', '娱乐与问答')),
    ]
    for needles, result in rules:
        if any(n.lower() in text for n in needles):
            return result
    return ('杂项', '待整理')


def infer_parent_channel_kind(category_name, parent_name, descriptor):
    text = ' '.join([
        category_name or '',
        parent_name or '',
        descriptor.get('normalized_title') or '',
        descriptor.get('micro_summary') or '',
    ]).lower()
    text_indicators = ['inbox', '入口', '组织', 'organize', 'admin', '管理', '控制', '常规', 'general', '协调']
    forum_indicators = ['研究', '数据', 'bug', '故障', '排障', '提案', '建议', '案例', '专题', '问答', '任务', '分析', '配置']
    if any(word in text for word in text_indicators):
        return {
            'type': 'text',
            'why': '该层更像统一入口、控制面或线性协调区，适合持续线性对话。',
        }
    if any(word in text for word in forum_indicators):
        return {
            'type': 'forum',
            'why': '该层更像长期主题归宿，会持续积累多个独立话题，适合分帖管理。',
        }
    return {
        'type': 'forum',
        'why': '默认按长期主题归宿处理，优先使用 forum 承接后续独立话题。',
    }


def ensure_category(guild_id, token, name, dry_run=False):
    channels = [summarize_channel(ch) for ch in list_guild_channels(guild_id, token)]
    for ch in channels:
        if ch['type_name'] == 'category' and (ch['name'] or '').lower() == name.lower():
            return ch
    if dry_run:
        return {'id': 'dry-run-category-id', 'name': clean_title(name), 'type_name': 'category'}
    created = create_channel(guild_id, token, {'name': clean_title(name), 'type': CREATE_TYPES['category']})
    return summarize_channel(created)


def ensure_text_channel(guild_id, token, name, parent_id=None, dry_run=False):
    channels = [summarize_channel(ch) for ch in list_guild_channels(guild_id, token)]
    for ch in channels:
        if ch['type_name'] == 'text' and (ch['name'] or '').lower() == name.lower() and ch.get('parent_id') == parent_id:
            return ch
    if dry_run:
        return {'id': 'dry-run-text-id', 'name': clean_title(name), 'type_name': 'text', 'parent_id': parent_id}
    payload = {'name': clean_title(name), 'type': CREATE_TYPES['text']}
    if parent_id:
        payload['parent_id'] = parent_id
    created = create_channel(guild_id, token, payload)
    return summarize_channel(created)


def ensure_default_server_structure(
    guild_id,
    token,
    dry_run=False,
    general_entry_name='通用入口',
    maintenance_channel_name='服务器维护专用',
    recycle_category_name='回收站',
):
    channels = [summarize_channel(ch) for ch in list_guild_channels(guild_id, token)]

    general_entry = next(
        (
            ch for ch in channels
            if ch['type_name'] == 'text'
            and not ch.get('parent_id')
            and '入口' in (ch.get('name') or '')
        ),
        None,
    )
    if general_entry is None:
        general_entry = ensure_text_channel(guild_id, token, general_entry_name, parent_id=None, dry_run=dry_run)

    maintenance = next(
        (
            ch for ch in channels
            if ch['type_name'] == 'text'
            and not ch.get('parent_id')
            and '维护' in (ch.get('name') or '')
        ),
        None,
    )
    if maintenance is None:
        maintenance = ensure_text_channel(guild_id, token, maintenance_channel_name, parent_id=None, dry_run=dry_run)

    recycle = next(
        (
            ch for ch in channels
            if ch['type_name'] == 'category'
            and '回收' in (ch.get('name') or '')
        ),
        None,
    )
    if recycle is None:
        recycle = ensure_category(guild_id, token, recycle_category_name, dry_run=dry_run)

    return {
        'general_entry_channel': general_entry,
        'maintenance_channel': maintenance,
        'recycle_category': recycle,
        'dry_run': dry_run,
    }


def old_parent_cleanup_name(channel_name, batch_label, index):
    base = clean_title(channel_name or '旧频道')
    return clean_title(f"{batch_label}-{index:02d}-{base}")


def inspect_parent_retention(channel_id, token, active_threads=None):
    current = get_channel(channel_id, token)
    type_id = int(current.get('type', -1))
    result = {
        'channel_id': channel_id,
        'channel_name': current.get('name'),
        'channel_type': channel_type_name(type_id),
        'parent_id': current.get('parent_id'),
        'active_thread_count': 0,
        'archived_thread_count': 0,
        'locked_thread_count': 0,
        'thread_count': 0,
        'has_message': False,
        'can_delete_now': False,
        'needs_parking': False,
    }
    if type_id not in {0, 15}:
        return result
    active_threads = active_threads if active_threads is not None else list_active_guild_threads(current.get('guild_id'), token)
    active = [t for t in active_threads if t.get('parent_id') == channel_id]
    archived_public = list_archived_threads(channel_id, token, private=False)
    archived_private = list_archived_threads(channel_id, token, private=True)
    archived = archived_public + archived_private
    has_message = False
    if type_id == 0:
        try:
            has_message = bool(latest_channel_message_meta(channel_id, token))
        except Exception:
            has_message = False
    result['active_thread_count'] = len(active)
    result['archived_thread_count'] = len(archived)
    result['locked_thread_count'] = sum(1 for t in archived if (t.get('thread_metadata') or {}).get('locked'))
    result['thread_count'] = result['active_thread_count'] + result['archived_thread_count']
    result['has_message'] = has_message
    result['can_delete_now'] = result['thread_count'] == 0 and not has_message
    result['needs_parking'] = result['active_thread_count'] == 0 and result['archived_thread_count'] > 0
    return result


def cleanup_global_structure(guild_id, token, dry_run=False, graveyard_category_name='回收站'):
    batch_label = time.strftime('%Y%m%d')
    cleaned = {
        'deleted': [],
        'parked': [],
        'skipped': [],
        'deleted_categories': [],
        'skipped_categories': [],
    }
    channels = [summarize_channel(ch) for ch in list_guild_channels(guild_id, token)]
    active_threads = list_active_guild_threads(guild_id, token)
    categories = [c for c in channels if c['type_name'] == 'category']
    protected_keywords = ('回收', '维护', '入口')
    protected_category_ids = {
        c['id'] for c in categories
        if any(word in (c.get('name') or '') for word in protected_keywords)
    }
    graveyard = next((c for c in categories if (c.get('name') or '').lower() == graveyard_category_name.lower()), None)
    parking_index = 1
    simulated_channels = [dict(ch) for ch in channels]

    for ch in sorted(channels, key=lambda x: (x.get('position') or 0, x.get('id') or '')):
        if ch.get('type_name') not in {'text', 'forum'}:
            continue
        if ch.get('parent_id') in protected_category_ids:
            cleaned['skipped'].append({
                'channel_id': ch.get('id'),
                'channel_name': ch.get('name'),
                'channel_type': ch.get('type_name'),
                'reason': 'protected-category',
            })
            continue
        if not ch.get('parent_id') and any(word in (ch.get('name') or '') for word in protected_keywords):
            cleaned['skipped'].append({
                'channel_id': ch.get('id'),
                'channel_name': ch.get('name'),
                'channel_type': ch.get('type_name'),
                'reason': 'protected-top-level-channel',
            })
            continue
        status = inspect_parent_retention(ch['id'], token, active_threads=active_threads)
        if status['can_delete_now']:
            if not dry_run:
                delete_channel(ch['id'], token)
            cleaned['deleted'].append({**status, 'action': 'delete'})
            simulated_channels = [item for item in simulated_channels if item.get('id') != ch['id']]
            continue
        if status['needs_parking']:
            if graveyard and ch.get('parent_id') == graveyard.get('id'):
                cleaned['skipped'].append({**status, 'reason': 'already-in-graveyard'})
                continue
            if graveyard is None:
                graveyard = ensure_category(guild_id, token, graveyard_category_name, dry_run=dry_run)
                simulated_channels.append({
                    'id': graveyard.get('id'),
                    'name': graveyard.get('name'),
                    'type_name': 'category',
                    'type': CREATE_TYPES['category'],
                    'parent_id': None,
                    'position': 9999,
                })
            new_name = old_parent_cleanup_name(ch.get('name'), batch_label, parking_index)
            parking_index += 1
            if not dry_run:
                patch_channel(ch['id'], token, {'name': new_name, 'parent_id': graveyard.get('id')})
            for item in simulated_channels:
                if item.get('id') == ch['id']:
                    item['name'] = new_name
                    item['parent_id'] = graveyard.get('id')
                    break
            cleaned['parked'].append({**status, 'action': 'park', 'new_name': new_name, 'graveyard_category': graveyard.get('name')})
            continue
        if status['active_thread_count'] > 0:
            reason = 'still-has-active-threads'
        elif status['has_message']:
            reason = 'has-messages-no-threads'
        else:
            reason = 'nothing-to-do'
        cleaned['skipped'].append({**status, 'reason': reason})

    remaining_categories = [c for c in simulated_channels if c.get('type_name') == 'category']
    remaining_children = [c for c in simulated_channels if c.get('parent_id')]
    child_count = {}
    for ch in remaining_children:
        child_count[ch['parent_id']] = child_count.get(ch['parent_id'], 0) + 1

    for cat in sorted(remaining_categories, key=lambda x: (x.get('position') or 0, x.get('id') or '')):
        if cat['id'] in protected_category_ids:
            cleaned['skipped_categories'].append({'category_id': cat['id'], 'category_name': cat.get('name'), 'reason': 'protected-category'})
            continue
        if child_count.get(cat['id'], 0) == 0:
            if not dry_run:
                delete_channel(cat['id'], token)
            cleaned['deleted_categories'].append({'category_id': cat['id'], 'category_name': cat.get('name'), 'action': 'delete'})
        else:
            cleaned['skipped_categories'].append({'category_id': cat['id'], 'category_name': cat.get('name'), 'reason': 'non-empty-category'})

    return cleaned


def cmd_organize_plan(args):
    token = load_cc_token()
    ctx = context_for_target(args.channel_id, token)
    guild_id = ctx["channel"]["guild_id"]
    if not guild_id:
        raise DiscordSkillError("Could not infer guild_id from current Discord context")
    channels = [summarize_channel(ch) for ch in list_guild_channels(guild_id, token)]
    categories = [c for c in channels if c["type_name"] == "category"]
    texts = [c for c in channels if c["type_name"] == "text"]
    forums = [c for c in channels if c["type_name"] == "forum"]
    active_threads = [summarize_channel(ch) for ch in list_active_guild_threads(guild_id, token)]
    control_thread_id = current_target_id()
    active_threads = [
        t for t in active_threads
        if t.get('id') != control_thread_id and not ((t.get('archived') or False) or (t.get('locked') or False))
    ]

    goal = args.goal or '规划当前 Discord 讨论区框架，并把活跃话题安家'
    framework_registry = load_framework_registry()
    existing_frameworks = framework_registry.get('frameworks') or []
    reuse_strength = args.reuse_strength

    thread_plans = []
    clusters = {}
    for t in active_threads:
        thread_id = t.get('id')
        cc_record = find_cc_session_record(f'discord:{thread_id}') or {}
        history = (cc_record.get('session') or {}).get('history') or []
        last_meta = latest_channel_message_meta(thread_id, token)
        last_ts = last_meta.get('timestamp')
        descriptor = get_thread_descriptor(thread_id)
        seed_text = ' '.join(item.get('content','') for item in history if isinstance(item, dict) and item.get('role') == 'user') or (t.get('name') or '')
        if descriptor and descriptor.get('last_message_ts') == last_ts:
            normalized_title = descriptor.get('normalized_title') or t.get('name')
            micro_summary = descriptor.get('micro_summary') or ''
            descriptor_source = 'cache'
        else:
            normalized_title, _ = suggest_title(seed_text)
            micro_summary = suggest_summary(seed_text)
            upsert_thread_descriptor(thread_id, {
                'thread_id': thread_id,
                'current_title': t.get('name'),
                'normalized_title': normalized_title,
                'micro_summary': micro_summary,
                'last_message_ts': last_ts,
                'updated_at': int(time.time()),
            })
            descriptor_source = 'llm'

        cluster_category, cluster_parent = infer_cluster({
            'normalized_title': normalized_title,
            'micro_summary': micro_summary,
        })
        parent_kind = infer_parent_channel_kind(cluster_category, cluster_parent, {
            'normalized_title': normalized_title,
            'micro_summary': micro_summary,
        })
        clusters.setdefault((cluster_category, cluster_parent, parent_kind['type'], parent_kind['why']), []).append(thread_id)

        thread_plans.append({
            'thread_id': thread_id,
            'current_title': t.get('name'),
            'normalized_title': normalized_title,
            'micro_summary': micro_summary,
            'descriptor_source': descriptor_source,
            'suggested_layers': {
                'category': cluster_category,
                'parent_channel': {
                    'name': cluster_parent,
                    'type': parent_kind['type'],
                    'why': parent_kind['why'],
                },
                'thread': {
                    'title': normalized_title,
                }
            },
            'needs_continuation_migrate': True,
            'migrate_command': {
                'command': 'discord-migrate.py',
                'args': {
                    'old_session_key': f"discord:{thread_id}",
                    'target_parent_name': cluster_parent,
                    'title': normalized_title,
                    'summary': micro_summary or f"将话题“{t.get('name')}”整理归位到新的长期结构中。",
                }
            }
        })

    suggested_framework = {
        'goal': goal,
        'reuse_strength': reuse_strength,
        'category_layer': [
            {
                'name': category,
                'needs_new': all(c['name'] != category for c in categories),
            }
            for category in sorted({key[0] for key in clusters.keys()})
        ],
        'parent_layer': [
            {
                'name': parent,
                'type': parent_type,
                'why': why,
                'needs_new': all(ch['name'] != parent for ch in (forums if parent_type == 'forum' else texts)),
                'category': category,
            }
            for category, parent, parent_type, why in clusters.keys()
        ],
        'thread_layer': {
            'notes': '活跃 thread 逐个 continuation migrate 到各自的 parent layer 之下。'
        },
        'notes': '框架严格按 Discord 的 category / parent channel / thread 三层组织。'
    }

    framework = {
        'categories': [c['name'] for c in categories],
        'forums': [f['name'] for f in forums],
        'texts': [t['name'] for t in texts],
        'active_thread_descriptors': [
            {
                'thread_id': p['thread_id'],
                'normalized_title': p['normalized_title'],
                'micro_summary': p['micro_summary'],
            }
            for p in thread_plans
        ],
        'clusters': [
            {
                'category': category,
                'parent_channel': {
                    'name': parent,
                    'type': parent_type,
                    'why': why,
                },
                'thread_ids': ids,
            }
            for (category, parent, parent_type, why), ids in clusters.items()
        ],
    }

    summary_lines = [
        f"目标：{goal}",
        f"活跃 thread 数：{len(thread_plans)}",
        "建议框架：",
    ]
    for item in suggested_framework['parent_layer']:
        summary_lines.append(f"- {item['category']} / {item['name']} ({item['type']}): {item['why']}")
    summary_lines.append("线程安家建议：")
    for item in thread_plans[:12]:
        pc = item['suggested_layers']['parent_channel']
        summary_lines.append(f"- {item['current_title']} -> {item['suggested_layers']['category']} / {pc['name']} ({pc['type']})")
    if len(thread_plans) > 12:
        summary_lines.append(f"- 其余 {len(thread_plans) - 12} 个 thread 见 thread_plans")

    plan_entry = upsert_organize_plan({
        'goal': goal,
        'reuse_strength': reuse_strength,
        'context_session_key': ctx.get('session_key'),
        'suggested_framework': suggested_framework,
        'thread_plans': thread_plans,
        'updated_at': int(time.time()),
    })

    result = {
        'action': 'organize-plan',
        'plan_id': plan_entry['plan_id'],
        'summary_text': '\n'.join(summary_lines),
        'context': ctx,
        'framework_registry': existing_frameworks,
        'reuse_strength': reuse_strength,
        'suggested_framework': suggested_framework,
        'framework': framework,
        'categories': categories,
        'texts': texts,
        'forums': forums,
        'active_threads': active_threads,
        'thread_plans': thread_plans,
    }
    print_result(result, args.json)


def session_key_exists(session_key):
    if not session_key:
        return False
    if not CC_CONNECT_SESSIONS_DIR.exists():
        return False
    for path in sorted(CC_CONNECT_SESSIONS_DIR.glob('*.json')):
        try:
            with path.open('r', encoding='utf-8') as f:
                store = json.load(f)
        except Exception:
            continue
        if session_key in ((store.get('active_session') or {}).keys()):
            return True
    return False


def organize_apply_data(args, plan=None, token=None, ctx=None):
    plan = plan or get_organize_plan(args.plan_id)
    if not plan:
        raise DiscordSkillError('No organize plan available to apply')
    thread_plans = plan.get('thread_plans') or []
    suggested = plan.get('suggested_framework') or {}
    parent_layer = suggested.get('parent_layer') or []
    token = token or load_cc_token()
    ctx = ctx or context_for_target(args.channel_id, token)
    guild_id = ctx['channel']['guild_id']
    if not guild_id:
        raise DiscordSkillError('Could not infer guild_id from current Discord context')

    existing = [summarize_channel(ch) for ch in list_guild_channels(guild_id, token)]
    existing_categories = {c['name']: c for c in existing if c['type_name'] == 'category'}
    existing_texts = {c['name']: c for c in existing if c['type_name'] == 'text'}
    existing_forums = {c['name']: c for c in existing if c['type_name'] == 'forum'}

    created = []
    for item in suggested.get('category_layer') or []:
        if item['name'] in existing_categories:
            continue
        payload = {'name': clean_title(item['name']), 'type': CREATE_TYPES['category']}
        if not args.dry_run:
            ch = create_channel(guild_id, token, payload)
            existing_categories[ch['name']] = summarize_channel(ch)
        created.append({'kind': 'category', 'name': item['name'], 'dry_run': args.dry_run})

    for item in parent_layer:
        target_map = existing_forums if item['type'] == 'forum' else existing_texts
        if item['name'] in target_map:
            continue
        category = existing_categories.get(item['category'])
        payload = {'name': clean_title(item['name']), 'type': CREATE_TYPES[item['type']]}
        if category:
            payload['parent_id'] = category['id']
        if not args.dry_run:
            ch = create_channel(guild_id, token, payload)
            target_map[ch['name']] = summarize_channel(ch)
        created.append({'kind': item['type'], 'name': item['name'], 'category': item['category'], 'dry_run': args.dry_run})

    current_session = current_session_key()
    current_thread_id = current_target_id() if current_session.startswith('discord:') else None

    migrations = []
    skipped_stale = []
    for item in thread_plans:
        old_session_key = f"discord:{item['thread_id']}"
        if old_session_key == current_session or item['thread_id'] == current_thread_id:
            continue
        if not session_key_exists(old_session_key):
            skipped_stale.append({
                'thread_id': item['thread_id'],
                'old_session_key': old_session_key,
                'reason': 'stale-session-key',
            })
            continue
        pc = item['suggested_layers']['parent_channel']
        migrations.append({
            'old_session_key': old_session_key,
            'target_parent_name': pc['name'],
            'target_parent_type': pc['type'],
            'title': item['suggested_layers']['thread']['title'],
            'summary': item['micro_summary'] or f"将话题“{item['current_title']}”整理归位到新的长期结构中。",
        })

    return {
        'action': 'organize-apply',
        'plan_id': plan.get('plan_id'),
        'dry_run': args.dry_run,
        'created': created,
        'migrations': migrations,
        'skipped_stale': skipped_stale,
        'message': f"prepared organize apply for {len(migrations)} thread(s)",
    }


def cmd_organize_apply(args):
    result = organize_apply_data(args)
    print_result(result, args.json)


def cmd_migration_registry(args):
    result = {
        "action": "migration-registry",
        "data": load_migration_registry(),
    }
    print_result(result, args.json)


def load_migrate_module():
    import importlib.util
    migrate_path = SKILL_ROOT / 'bin' / 'discord-migrate.py'
    migrate_spec = importlib.util.spec_from_file_location('discord_migrate_runtime', migrate_path)
    migrate_mod = importlib.util.module_from_spec(migrate_spec)
    migrate_spec.loader.exec_module(migrate_mod)
    return migrate_mod


def cmd_install(args):
    env_info = detect_install_environment()
    if not (env_info['claude_code'] and env_info['cc_connect'] and env_info['discord']):
        raise DiscordSkillError('Current environment does not clearly match Discord + cc-connect + Claude Code')

    env_path = ensure_env_file(dry_run=args.dry_run)
    updates = {
        'CC_CONNECT_CONFIG': str(CC_CONNECT_CONFIG),
        'CC_CONNECT_SESSIONS_DIR': str(CC_CONNECT_SESSIONS_DIR),
        'CC_CONNECT_DATA_DIR': str(Path(os.environ.get('CC_CONNECT_DATA_DIR', '~/.cc-connect')).expanduser()),
        'CLAUDE_PROJECTS_DIR': str(Path(os.environ.get('CLAUDE_PROJECTS_DIR', '~/.claude/projects')).expanduser()),
        'DISCORD_SKILL_ROOT': str(SKILL_ROOT),
        'DISCORD_SKILL_STATE_DIR': str(STATE_ROOT),
        'DISCORD_API_BASE': DISCORD_API_BASE,
        'CC_CONNECT_LOG': os.environ.get('CC_CONNECT_LOG', str(Path('~/.cc-connect/cc-connect.log').expanduser())),
        'CC_CONNECT_BIN': os.environ.get('CC_CONNECT_BIN', 'cc-connect'),
        'CC_CONNECT_MATCH': os.environ.get('CC_CONNECT_MATCH', f'cc-connect --config {CC_CONNECT_CONFIG}'),
        'CC_CONNECT_START_CMD': os.environ.get('CC_CONNECT_START_CMD', ''),
    }
    for key in ('DISCORD_BOT_TOKEN', 'DISCORD_SKILL_LLM_BASE_URL', 'DISCORD_SKILL_LLM_API_KEY', 'DISCORD_SKILL_LLM_MODEL'):
        if os.environ.get(key):
            updates[key] = os.environ.get(key)
    merged_env = write_env_file(env_path, updates, dry_run=args.dry_run)

    token = load_cc_token()
    ctx = context_for_target(args.channel_id, token)
    guild_id = ctx['channel']['guild_id']
    if not guild_id:
        raise DiscordSkillError('Could not infer guild_id from current Discord context')

    permissions_ns = argparse.Namespace(channel_id=args.channel_id, json=True)
    me = get_current_user(token)
    member = get_guild_member(guild_id, me.get('id'), token)
    permissions_value = int(member.get('permissions') or 0)
    missing = [name for name, bit in REQUIRED_PERMISSION_BITS.items() if not (permissions_value & bit)]
    if missing:
        result = {
            'action': 'install',
            'dry_run': args.dry_run,
            'environment': env_info,
            'env_path': str(env_path),
            'env_updates': merged_env,
            'permissions_ok': False,
            'missing_permissions': missing,
            'oauth_scopes': ['bot', 'applications.commands'],
            'oauth_permissions': str(sum(REQUIRED_PERMISSION_BITS.values())),
            'message': 'Bot permissions are insufficient; re-authorize before continuing',
        }
        print_result(result, args.json)
        return

    structure = ensure_default_server_structure(guild_id, token, dry_run=args.dry_run)
    maintenance = structure['maintenance_channel']
    recycle = structure['recycle_category']
    general_entry = structure['general_entry_channel']

    llm_pending = [
        key for key in ('DISCORD_SKILL_LLM_BASE_URL', 'DISCORD_SKILL_LLM_API_KEY', 'DISCORD_SKILL_LLM_MODEL')
        if not (merged_env.get(key) or os.environ.get(key))
    ]

    migration_result = None
    watcher_started = False
    watcher_cmd = ['python3', str(SKILL_ROOT / 'bin' / 'discord-watch.py'), '--daemon']
    if not args.dry_run:
        migrate_mod = load_migrate_module()
        current_session = current_session_key()
        if not current_session.startswith('discord:'):
            raise DiscordSkillError('Current context is not a Discord thread session')
        migrate_args = argparse.Namespace(
            old_session_key=current_session,
            target_parent_id=maintenance['id'],
            target_parent_name=maintenance['name'],
            organize_thread_id=None,
            title='Discord/cc-connect 控制台',
            summary='安装完成后的 Discord / cc-connect 控制面线程。',
            skip_quiet_window_check=True,
            dry_run=False,
            json=True,
        )
        migration_result = migrate_mod.run(migrate_args)
        new_thread_id = migration_result.get('new_thread_id')
        if new_thread_id:
            install_report = (
                f"安装完成。\n\n"
                f"- 维护频道：{maintenance.get('name')}\n"
                f"- 通用入口：{general_entry.get('name')}\n"
                f"- 回收类：{recycle.get('name')}\n"
                f"- watcher：准备后台启动\n"
                f"- LLM 待确认字段：{', '.join(llm_pending) if llm_pending else '无'}"
            )
            send_message(new_thread_id, token, install_report)
        import subprocess
        log_path = STATE_ROOT / 'watcher' / 'watcher-install.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('ab') as out:
            subprocess.Popen(watcher_cmd, stdout=out, stderr=out, stdin=subprocess.DEVNULL, start_new_session=True)
        watcher_started = True
        if new_thread_id:
            send_message(new_thread_id, token, 'watcher 已在后台启动。')

    result = {
        'action': 'install',
        'dry_run': args.dry_run,
        'environment': env_info,
        'env_path': str(env_path),
        'env_updates': merged_env,
        'permissions_ok': True,
        'maintenance_channel': maintenance,
        'general_entry_channel': general_entry,
        'recycle_category': recycle,
        'llm_pending': llm_pending,
        'migration_result': migration_result,
        'watcher_started': watcher_started,
        'message': 'install flow completed' if not llm_pending else 'install flow completed; LLM confirmation still pending',
    }
    print_result(result, args.json)


def cmd_organize_execute(args):
    migrate_mod = load_migrate_module()

    plan = get_organize_plan(args.plan_id)
    if not plan:
        raise DiscordSkillError('No organize plan available to execute')

    preview = {
        'plan_id': plan.get('plan_id'),
        'channel_id': args.channel_id,
        'dry_run': args.dry_run,
    }
    preview_args = argparse.Namespace(**preview)
    token = load_cc_token()
    ctx = context_for_target(args.channel_id, token)
    guild_id = ctx['channel']['guild_id']
    if not guild_id:
        raise DiscordSkillError('Could not infer guild_id from current Discord context')

    apply_result = organize_apply_data(preview_args, plan=plan, token=token, ctx=ctx)
    migrations = apply_result.get('migrations') or []
    control_thread_id = current_target_id()

    blockers = []
    if migrations:
        first_old_session_key = migrations[0]['old_session_key']
        blockers = migrate_mod.quiet_window_ok(token, control_thread_id, first_old_session_key)
        if blockers and not args.force_busy:
            result = {
                'action': 'organize-execute',
                'plan_id': plan.get('plan_id'),
                'dry_run': args.dry_run,
                'force_busy': args.force_busy,
                'created': apply_result.get('created') or [],
                'migrations': migrations,
                'completed_migrations': [],
                'failed_migrations': [],
                'blockers': blockers,
                'message': f'blocked by quiet window: {len(blockers)} active thread(s)',
            }
            print_result(result, args.json)
            return

    completed = []
    failed = []
    prepared = []
    reserved_titles = set()
    for item in migrations:
        migrate_args = argparse.Namespace(
            old_session_key=item['old_session_key'],
            target_parent_id=None,
            target_parent_name=item['target_parent_name'],
            organize_thread_id=control_thread_id,
            title=item['title'],
            summary=item['summary'],
            skip_quiet_window_check=True,
            dry_run=args.dry_run,
            json=True,
        )
        try:
            token2, record, prep = migrate_mod.prepare_migration(migrate_args, extra_taken_titles=reserved_titles)
            reserved_titles.add(prep.get('new_title'))
            prepared.append({'item': item, 'record': record, 'prepared': prep, 'token': token2})
        except Exception as e:
            failed.append({**item, 'phase': 'prepare', 'error': str(e)})

    cc_connect_stop_pids = []
    cc_connect_new_pid = None
    parent_cleanup = {'deleted': [], 'parked': [], 'skipped': [], 'deleted_categories': [], 'skipped_categories': []}
    if prepared and not args.dry_run:
        try:
            cc_connect_stop_pids = migrate_mod.stop_cc_connect()
            for bundle in prepared:
                migrate_mod.discordctl.upsert_migration(bundle['prepared']['migration_entry'])
                out = migrate_mod.finalize_prepared_migration(
                    bundle['prepared'],
                    bundle['record'],
                    bundle['token'],
                    organize_thread_id=control_thread_id,
                    cc_connect_pid=None,
                    report=False,
                    verify=False,
                    mark_completed=False,
                )
                completed.append({**bundle['item'], **out})
            parent_cleanup = cleanup_global_structure(guild_id, token, dry_run=False)
            cc_connect_new_pid = migrate_mod.start_cc_connect()
            time.sleep(2)
            for bundle in prepared:
                migrate_mod.verify_store_mapping(
                    bundle['prepared']['old_session_key'],
                    bundle['prepared']['new_session_key'],
                    bundle['record']['cc_session_id'],
                )
                migrate_mod.discordctl.upsert_migration({
                    **bundle['prepared']['migration_entry'],
                    'status': 'completed',
                    'updated_at': int(time.time()),
                })
            lines = [
                f"organize 执行完成：成功迁移 {len(completed)} 个 thread，失败 {len(failed)} 个。",
            ]
            if parent_cleanup.get('deleted') or parent_cleanup.get('parked') or parent_cleanup.get('deleted_categories'):
                lines.append("全局清理：")
                for idx, item in enumerate(parent_cleanup.get('deleted') or [], start=1):
                    lines.append(f"删频道{idx}. {item.get('channel_name')}")
                for idx, item in enumerate(parent_cleanup.get('parked') or [], start=1):
                    lines.append(f"收频道{idx}. {item.get('channel_name')} -> {item.get('new_name')} / {item.get('graveyard_category')}")
                for idx, item in enumerate(parent_cleanup.get('deleted_categories') or [], start=1):
                    lines.append(f"删分类{idx}. {item.get('category_name')}")
            if cc_connect_new_pid:
                lines.append(f"cc-connect 已统一重启（pid {cc_connect_new_pid}）。")
            if completed:
                lines.append("成功项：")
                for idx, item in enumerate(completed, start=1):
                    lines.append(f"{idx}. {item.get('new_title')} -> {item.get('target_parent_name')}")
            if failed:
                lines.append("失败项：")
                for idx, item in enumerate(failed, start=1):
                    lines.append(f"{idx}. {item.get('title')} ({item.get('phase')}): {item.get('error')}")
            migrate_mod.report_to_organize_thread(token, control_thread_id, '\n'.join(lines))
        except Exception as e:
            failed.append({'phase': 'switch-cleanup-or-restart', 'error': str(e)})
    else:
        for bundle in prepared:
            completed.append({**bundle['item'], **bundle['prepared']})
        parent_cleanup = cleanup_global_structure(guild_id, token, dry_run=True)

    result = {
        'action': 'organize-execute',
        'plan_id': plan.get('plan_id'),
        'dry_run': args.dry_run,
        'force_busy': args.force_busy,
        'created': apply_result.get('created') or [],
        'migrations': migrations,
        'skipped_stale': apply_result.get('skipped_stale') or [],
        'completed_migrations': completed,
        'failed_migrations': failed,
        'blockers': blockers,
        'parent_cleanup': parent_cleanup,
        'cc_connect_stopped_pids': cc_connect_stop_pids,
        'cc_connect_new_pid': cc_connect_new_pid,
        'message': f"executed {len(completed)}/{len(migrations)} migration(s)",
    }
    print_result(result, args.json)


def auto_rename_result(**kwargs):
    base = {
        "action": "auto-rename-hook",
        "continue": True,
        "suppressOutput": True,
    }
    base.update(kwargs)
    return base


def cmd_auto_rename_hook(args):
    hook_input = {}
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            try:
                hook_input = json.loads(raw)
            except json.JSONDecodeError:
                hook_input = {}

    session_key = current_session_key()
    if args.reset:
        reset_state(session_key)

    if not session_key.startswith("discord:"):
        if args.json:
            print(json_dumps(auto_rename_result(message="Not a Discord session")))
        return

    lock_path = acquire_lock(session_key)
    if lock_path is None:
        if args.json:
            print(json_dumps(auto_rename_result(message="Another auto-rename is already running")))
        return

    try:
        token = load_cc_token()
        ctx = context_for_target(None, token)
        channel = ctx["channel"]
        if channel["type_name"] not in THREAD_TYPES.values():
            if args.json:
                print(json_dumps(auto_rename_result(message="Current target is not a thread")))
            return

        state, path = load_state(session_key)
        if state.get("done"):
            if args.json:
                print(json_dumps(auto_rename_result(message="Already auto-renamed")))
            return

        user_prompt = hook_input.get("user_prompt", "")
        if not user_prompt.strip():
            if args.json:
                print(json_dumps(auto_rename_result(message="Missing user prompt")))
            return

        current_name = channel.get("name") or ""
        expected_existing = sanitize_existing_thread_name(user_prompt)
        if expected_existing and current_name != expected_existing:
            if current_name == GENERIC_TITLE:
                expected_existing = current_name
            else:
                save_state(path, {
                    "done": True,
                    "reason": "current-name-changed",
                    "current_name": current_name,
                    "expected_existing": expected_existing,
                    "updated_at": int(time.time()),
                })
                if args.json:
                    print(json_dumps(auto_rename_result(message="Thread name already changed; not auto-renaming")))
                return

        title, source = suggest_title(user_prompt)
        if not title:
            title = GENERIC_TITLE
        if title == current_name:
            save_state(path, {
                "done": True,
                "reason": "generated-same-as-current",
                "current_name": current_name,
                "updated_at": int(time.time()),
            })
            if args.json:
                print(json_dumps(auto_rename_result(message="Generated title matches current name")))
            return

        result = {
            "done": True,
            "source": source,
            "old_name": current_name,
            "new_name": title,
            "expected_existing": expected_existing,
            "updated_at": int(time.time()),
        }
        if not args.dry_run:
            patch_channel(channel["id"], token, {"name": title})
        save_state(path, result)
        if args.json:
            payload = auto_rename_result(message=f"Renamed thread to {title}", new_name=title, source=source, dry_run=args.dry_run)
            print(json_dumps(payload))
    finally:
        release_lock(lock_path)


def build_parser():
    parser = argparse.ArgumentParser(description="Discord skill backend for cc-connect sessions")
    sub = parser.add_subparsers(dest="command", required=True)

    info = sub.add_parser("info")
    info.add_argument("--channel-id")
    info.add_argument("--json", action="store_true")
    info.set_defaults(func=cmd_info)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--kind", choices=sorted(CREATE_TYPES.keys()))
    list_cmd.add_argument("--channel-id")
    list_cmd.add_argument("--json", action="store_true")
    list_cmd.set_defaults(func=cmd_list)

    suggest = sub.add_parser("suggest-title")
    suggest.add_argument("--text", required=True)
    suggest.add_argument("--json", action="store_true")
    suggest.set_defaults(func=cmd_suggest_title)

    rename = sub.add_parser("rename")
    rename.add_argument("--name", required=True)
    rename.add_argument("--channel-id")
    rename.add_argument("--dry-run", action="store_true")
    rename.add_argument("--json", action="store_true")
    rename.set_defaults(func=cmd_rename)

    archive = sub.add_parser("archive")
    archive.add_argument("--channel-id")
    archive.add_argument("--lock", action="store_true")
    archive.add_argument("--dry-run", action="store_true")
    archive.add_argument("--json", action="store_true")
    archive.set_defaults(func=cmd_archive)

    close = sub.add_parser("close")
    close.add_argument("--channel-id")
    close.add_argument("--dry-run", action="store_true")
    close.add_argument("--json", action="store_true")
    close.set_defaults(func=cmd_close)

    create = sub.add_parser("create")
    create.add_argument("kind", choices=sorted(CREATE_TYPES.keys()))
    create.add_argument("--name", required=True)
    create.add_argument("--parent-id")
    create.add_argument("--parent-name")
    create.add_argument("--channel-id")
    create.add_argument("--dry-run", action="store_true")
    create.add_argument("--json", action="store_true")
    create.set_defaults(func=cmd_create)

    move = sub.add_parser("move")
    move.add_argument("--parent-id")
    move.add_argument("--parent-name")
    move.add_argument("--channel-id")
    move.add_argument("--dry-run", action="store_true")
    move.add_argument("--json", action="store_true")
    move.set_defaults(func=cmd_move)

    preview = sub.add_parser("preview")
    preview.add_argument("--message", required=True)
    preview.add_argument("--json", action="store_true")
    preview.set_defaults(func=cmd_preview)

    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--channel-id")
    snapshot.add_argument("--json", action="store_true")
    snapshot.set_defaults(func=cmd_snapshot)

    permissions_check = sub.add_parser("permissions-check")
    permissions_check.add_argument("--channel-id")
    permissions_check.add_argument("--json", action="store_true")
    permissions_check.set_defaults(func=cmd_permissions_check)

    install = sub.add_parser("install")
    install.add_argument("--channel-id")
    install.add_argument("--dry-run", action="store_true")
    install.add_argument("--json", action="store_true")
    install.set_defaults(func=cmd_install)

    structure = sub.add_parser("structure")
    structure.add_argument("--channel-id")
    structure.add_argument("--json", action="store_true")
    structure.set_defaults(func=cmd_snapshot)

    registry = sub.add_parser("migration-registry")
    registry.add_argument("--json", action="store_true")
    registry.set_defaults(func=cmd_migration_registry)

    organize = sub.add_parser("organize-plan")
    organize.add_argument("--channel-id")
    organize.add_argument("--goal")
    organize.add_argument("--reuse-strength", choices=['conservative', 'neutral', 'aggressive'], default='neutral')
    organize.add_argument("--json", action="store_true")
    organize.set_defaults(func=cmd_organize_plan)

    organize_apply = sub.add_parser("organize-apply")
    organize_apply.add_argument("--channel-id")
    organize_apply.add_argument("--plan-id")
    organize_apply.add_argument("--dry-run", action="store_true")
    organize_apply.add_argument("--json", action="store_true")
    organize_apply.set_defaults(func=cmd_organize_apply)

    organize_execute = sub.add_parser("organize-execute")
    organize_execute.add_argument("--channel-id")
    organize_execute.add_argument("--plan-id")
    organize_execute.add_argument("--force-busy", action="store_true")
    organize_execute.add_argument("--dry-run", action="store_true")
    organize_execute.add_argument("--json", action="store_true")
    organize_execute.set_defaults(func=cmd_organize_execute)

    auto = sub.add_parser("auto-rename-hook")
    auto.add_argument("--dry-run", action="store_true")
    auto.add_argument("--reset", action="store_true")
    auto.add_argument("--json", action="store_true")
    auto.set_defaults(func=cmd_auto_rename_hook)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except DiscordSkillError as e:
        if getattr(args, "command", None) == "auto-rename-hook":
            if getattr(args, "json", False):
                print(json_dumps(auto_rename_result(message=str(e))))
            return 0
        print(str(e), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
