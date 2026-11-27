"""In-process queue with retry + dead-letter file. Swap for Pub/Sub / Cloud Tasks on GCP."""
import json, queue, sqlite3, threading, time
from pathlib import Path
from worker import process_issue
from assess import ROOT

MAX_TRIES, BACKOFF = 3, 5
Q: "queue.Queue[dict]" = queue.Queue()
_inflight, _lock = set(), threading.Lock()
DB = ROOT / "logs" / "store.db"

def db():
    (ROOT / "logs").mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS reviews(ts REAL, key TEXT, mode TEXT, summary TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS decisions(ts REAL, key TEXT, decision TEXT)")
    return c

def enqueue(key: str, mode: str) -> bool:
    with _lock:
        if (key, mode) in _inflight:
            return False          # already queued or running
        _inflight.add((key, mode))
    Q.put({"key": key, "mode": mode, "tries": 0})
    return True

def _dead_letter(job, err):
    with open(ROOT / "logs" / "dlq.jsonl", "a") as f:
        f.write(json.dumps({**job, "error": str(err)[:500], "ts": time.time()}) + "\n")

def _loop():
    while True:
        job = Q.get()
        key, mode = job["key"], job["mode"]
        try:
            res = process_issue(key, mode, post=True)
            print(f"[worker] {key} {mode} -> {res}", flush=True)
            if res.get("status") == "posted":
                with db() as c:
                    c.execute("INSERT INTO reviews VALUES(?,?,?,?)", (time.time(), key, mode, res["summary"]))
            with _lock: _inflight.discard((key, mode))
        except Exception as e:
            job["tries"] += 1
            if job["tries"] >= MAX_TRIES:
                print(f"[worker] {key} {mode} DEAD-LETTERED: {e}", flush=True)
                _dead_letter(job, e)
                with _lock: _inflight.discard((key, mode))
            else:
                time.sleep(BACKOFF * job["tries"])
                Q.put(job)
        finally:
            Q.task_done()

def start():
    threading.Thread(target=_loop, daemon=True).start()