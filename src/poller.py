"""Automation loop: polls Jira and comments. Comment-only: it never edits labels or fields.

  Human adds label  needs-refinement  -> AI posts a review comment   (stage 1)
  Human adds label  ac-approved       -> AI posts draft test cases   (stage 2)

Duplicates are avoided by looking for the markers [wiqa:review] / [wiqa:tests] in existing comments.

  python src/poller.py            # run forever (Ctrl+C to stop)
  python src/poller.py --once     # one cycle
  python src/poller.py --dry      # show what it would do, post nothing
"""
import argparse, sys, time
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from assess import load_config
from jira_client import JiraClient
from worker import process_issue

def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)

def run_cycle(jc, cfg: dict, dry: bool, failures: dict) -> None:
    proj = cfg["jira_project"]
    stages = [("review", cfg["review_label"]), ("tests", cfg["tests_label"])]
    for stage, label in stages:
        for issue in jc.search(f'project = {proj} AND labels = "{label}" ORDER BY created ASC'):
            key = issue["key"]
            if failures[(key, stage)] >= cfg["max_failures_per_issue"]:
                continue
            try:
                res = process_issue(key, stage, post=not dry, jc=jc, cfg=cfg)
                if res["status"] == "refused":  # e.g. no acceptance criteria: don't retry every poll
                    failures[(key, stage)] = cfg["max_failures_per_issue"]
                if res["status"] != "skipped_duplicate":
                    log(f"{key} [{stage}] {res}")
            except Exception as e:
                failures[(key, stage)] += 1
                log(f"{key} [{stage}] FAILED ({failures[(key, stage)]}/{cfg['max_failures_per_issue']}): {e}")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    cfg, jc, failures = load_config(), JiraClient(), defaultdict(int)
    log(f"Watching project {cfg['jira_project']} for labels "
        f"'{cfg['review_label']}' and '{cfg['tests_label']}'{' (DRY RUN)' if args.dry else ''}")
    while True:
        try:
            run_cycle(jc, cfg, args.dry, failures)
        except Exception as e:
            log(f"cycle error: {e}")
        if args.once:
            break
        time.sleep(cfg["poll_seconds"])

if __name__ == "__main__":
    main()
