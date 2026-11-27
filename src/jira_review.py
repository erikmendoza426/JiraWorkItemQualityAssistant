"""Review one Jira issue with the assistant.
  python src/jira_review.py PROJ-1            # dry run: prints draft, posts nothing
  python src/jira_review.py PROJ-1 --post     # posts the draft as a comment
  python src/jira_review.py PROJ-1 --no-kb
"""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from assess import assess, load_config, audit
from jira_client import JiraClient, issue_to_work_item, result_to_adf

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("key")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--no-kb", action="store_true")
    args = ap.parse_args()

    jc, cfg = JiraClient(), load_config()
    item = issue_to_work_item(jc.get_issue(args.key))
    print("Work item sent to model:\n", json.dumps(item, indent=2), "\n")
    result, usage, raw = assess(item, cfg, use_kb=not args.no_kb)
    print(json.dumps(result, indent=2))
    audit({"ts": time.time(), "jira_key": args.key, "work_item_id": item["id"], "kb": not args.no_kb,
           "model": cfg["model"], "rubric_version": cfg["rubric_version"], "usage": usage,
           "category": result["category"], "llm_category": raw, "posted": args.post})
    if args.post:
        jc.add_comment(args.key, result_to_adf(result))
        print(f"\nPosted draft comment to {args.key}")
    else:
        print("\n(dry run: nothing posted; add --post to comment)")

if __name__ == "__main__":
    main()
