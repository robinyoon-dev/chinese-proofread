"""Files shared by the proofreading hooks.

detect_chinese.py leaves <job>.running in the session's folder and starts
proofread_worker.py, which replaces it with <job>.json when there is something
to show. show_result.py claims the .json files and prints them. Job names
start with the time, so sorting them gives the order of the prompts.

Corrections also go to a file per month in HISTORY_DIR, which stays after the
jobs are swept.
"""

import datetime
import json
import os
import shutil
import time
import uuid

# Keep the parent folder in sync with STATE_PATH in scripts/toggle.py.
JOBS_DIR = os.path.expanduser("~/.claude/chinese-proofread/jobs")
HISTORY_DIR = os.path.expanduser("~/.claude/chinese-proofread/history")
HISTORY_VERSION = 1
BLOCK = "📝 中文校对"
NOTHING_TO_FIX = BLOCK + ": ✅"
# In the session's folder: the language the current turn must reply in.
REPLY_FILE = "reply-language"
# Set for the claude -p of the worker, so it never starts another job.
INTERNAL_ENV = "CHINESE_PROOFREAD_INTERNAL"
WORKER_TIMEOUT = 60
# How long a job may stay .running before its worker counts as dead.
STALE_SECONDS = WORKER_TIMEOUT + 30
KEEP_SECONDS = 24 * 60 * 60
LEVELS = ("beginner", "intermediate", "advanced")
DEFAULT_LEVEL = "intermediate"
REGIONS = ("mainland", "taiwan")
DEFAULT_REGION = "mainland"
PHONETICS = ("pinyin", "zhuyin")
DEFAULT_PHONETIC = "pinyin"


def session_dir(session_id):
    # Session ids are UUIDs; anything else could point outside JOBS_DIR.
    if not isinstance(session_id, str) or not session_id.replace("-", "").isalnum():
        return None
    return os.path.join(JOBS_DIR, session_id)


def new_job(session_dir_path):
    name = f"{time.time_ns():020d}-{uuid.uuid4().hex}"
    return os.path.join(session_dir_path, name)


def jobs(path, suffix):
    try:
        names = sorted(os.listdir(path))
    except OSError:
        return []
    return [os.path.join(path, n) for n in names if n.endswith(suffix)]


def setting(name, values, default):
    # An unknown value proofreads as before instead of failing the hook.
    value = os.environ.get(name, "").strip().lower()
    return value if value in values else default


def level():
    return setting("CHINESE_PROOFREAD_LEVEL", LEVELS, DEFAULT_LEVEL)


def region():
    return setting("CHINESE_PROOFREAD_REGION", REGIONS, DEFAULT_REGION)


def phonetic():
    return setting("CHINESE_PROOFREAD_PHONETIC", PHONETICS, DEFAULT_PHONETIC)


def write_json(path, value):
    # A reader must never see half a file.
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False)
    os.replace(tmp, path)


def append_history(block, lang):
    """Keeps a correction. The prompt stays out: it may hold pasted code or
    secrets, and these files are never swept."""
    if (os.environ.get("CHINESE_PROOFREAD_HISTORY") == "0"
            or block.startswith(NOTHING_TO_FIX)):
        return
    now = datetime.datetime.now().astimezone()
    line = json.dumps({
        "v": HISTORY_VERSION,
        "time": now.isoformat(timespec="seconds"),
        "lang": lang,
        "block": block,
    }, ensure_ascii=False) + "\n"
    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = os.path.join(HISTORY_DIR, now.strftime("%Y-%m") + ".jsonl")
    # Workers run in parallel: one appending write keeps each line whole.
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def sweep():
    # Results of sessions that ended before showing them.
    try:
        names = os.listdir(JOBS_DIR)
    except OSError:
        return
    for name in names:
        path = os.path.join(JOBS_DIR, name)
        try:
            if time.time() - os.path.getmtime(path) > KEEP_SECONDS:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
