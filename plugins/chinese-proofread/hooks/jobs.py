"""Files shared by the proofreading hooks.

detect_chinese.py leaves <job>.running in the session's folder and starts
proofread_worker.py, which replaces it with <job>.json when there is something
to show. show_result.py claims the .json files and prints them. Job names
start with the time, so sorting them gives the order of the prompts.
"""

import json
import os
import shutil
import time
import uuid

# Keep the parent folder in sync with STATE_PATH in scripts/toggle.py.
JOBS_DIR = os.path.expanduser("~/.claude/chinese-proofread/jobs")
BLOCK = "📝 中文校对"
# In the session's folder: the language the current turn must reply in.
REPLY_FILE = "reply-language"
# Set for the claude -p of the worker, so it never starts another job.
INTERNAL_ENV = "CHINESE_PROOFREAD_INTERNAL"
WORKER_TIMEOUT = 60
# How long a job may stay .running before its worker counts as dead.
STALE_SECONDS = WORKER_TIMEOUT + 30
KEEP_SECONDS = 24 * 60 * 60


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


def write_json(path, value):
    # A reader must never see half a file.
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False)
    os.replace(tmp, path)


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
